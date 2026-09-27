"""
fraud_jev_llm.py - real-time fraud detection for banking transactions with Jev + the mini LLM.

  Jev (System One)     : reads each transaction as JSON and answers, in one call,
                           is_fraud   (noul)   -> probability the transaction is fraud or a scam
                           fraud_type (choice) -> card fraud / account takeover / APP scam / genuine
  Mini LLM             : the character-level GPT from mini_gpt.py, trained ONLY on the bank's
                         normal payment descriptions. It is not asked to write anything. It
                         measures how SURPRISING a new description is (bits per character):
                         "TESCO STORES 2291 LONDON" is familiar; "SAFE ACCOUNT TRANSFER" is not.
  Challenger           : gradient-boosted trees trained on labelled past cases, with and
                         without the LLM surprise feature (to measure what the LLM adds).
  Decision engine      : hard rules + risk bands sized to team capacity + overrides
                         -> ALLOW / STEP-UP (confirm with customer) / HOLD (analyst) / BLOCK.

Principles:
  - Jev's zero-label calibration is validated on our own labelled data, not assumed.
  - The LLM is used as a detector, not a writer: no generated text reaches customers or
    case files (the credit demo showed a tiny LLM will invent facts).
  - Customer messages and reason codes are deterministic templates.
  - Every decision is logged with model versions and an empty field for the analyst.

Usage:
    pip install torch scikit-learn numpy
    export TYPESAFE_API_KEY=...     # use the real Jev API
    python fraud_jev_llm.py         # Jev if the key is set, else the local stand-in
    python fraud_jev_llm.py --offline
    python fraud_jev_llm.py --quick # smaller, faster run

DISCLAIMER: synthetic data; educational code, not a production fraud system.
"""
import hashlib, json, math, os, string, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import cross_val_predict

from jev_client import get_jev

QUICK, OFFLINE = "--quick" in sys.argv, "--offline" in sys.argv
SEED = 21
rng = np.random.default_rng(SEED)
torch.manual_seed(SEED)
OUT = "fraud_outputs"
os.makedirs(OUT, exist_ok=True)

N_CUST = 800 if QUICK else 1500
N_EVAL = 8000 if QUICK else 24000
N_HIST_REFS = 12000 if QUICK else 40000
FRAUD_RATE = 0.015
TYPES = ["genuine", "card_fraud", "account_takeover", "app_scam"]

# =============================================================================
# 1. SYNTHETIC CUSTOMERS AND TRANSACTIONS
# =============================================================================
TOWNS = ["LONDON", "LEEDS", "BRISTOL", "MILTON KEYNES", "MANCHESTER", "LEICESTER", "BRIGHTON", "YORK"]
POS = ["TESCO STORES", "SAINSBURYS", "PRET A MANGER", "BOOTS", "COSTA COFFEE", "SHELL", "WAITROSE", "CO-OP FOOD",
       "LIDL GB", "ALDI", "GREGGS", "TFL TRAVEL", "WHSMITH", "PETS AT HOME", "SQ *COFFEE CORNER", "SUMUP *MARKET STALL",
       "IZ *FOOD VAN", "B&Q", "SCREWFIX", "PRIMARK", "NANDOS", "WETHERSPOON"]
ONLINE = ["AMAZON.CO.UK", "AMZN MKTP UK*{c}", "NETFLIX.COM", "SPOTIFY", "APPLE.COM/BILL", "DELIVEROO", "UBER TRIP",
          "ASOS.COM", "PAYPAL *EBAY {c}", "PAYPAL *{c}", "TRAINLINE", "OCADO", "JUST EAT", "GOOGLE *YOUTUBE",
          "STEAMGAMES.COM {n}", "PLAYSTATION NETWORK", "VODAFONE TOPUP", "ARGOS", "CURRYS", "ONE4ALL GIFT CARD",
          "COINBASE UK", "SHEIN.COM", "TEMU.COM {c}"]
ABROAD = ["BOOKING.COM", "AIRBNB", "RYANAIR", "HOTEL BARCELONA", "EASYJET", "CARREFOUR PARIS"]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
USUAL_PAY = ["RENT {m}", "COUNCIL TAX", "BRITISH GAS", "THAMES WATER", "SAVINGS", "MUM BIRTHDAY", "SPLIT DINNER",
             "GYM MEMBERSHIP", "NURSERY FEES {m}", "CAR INSURANCE", "OCTOPUS ENERGY", "POCKET MONEY", "TICKETS {m}",
             "J SMITH", "A PATEL", "M AHMED", "S JONES", "DAD", "CLEANER", "WINDOW CLEANER", "LOAN REPAYMENT", "TRANSFER",
             "PAYMENT", "INVOICE {n}", "HMRC SELF ASSESSMENT", "VANGUARD INVESTMENT", "INVESTMENT ISA", "SAVINGS 2"]
BIG_NEW_PAY = ["SOLICITOR COMPLETION FUNDS", "HOUSE DEPOSIT", "BUILDER INVOICE KITCHEN", "CAR PURCHASE DEALER",
               "WEDDING VENUE DEPOSIT", "UNIVERSITY FEES", "HOLIDAY VILLA BOOKING", "NEW LANDLORD DEPOSIT"]
CARD_FRAUD = ["PAYPAL *{c}", "AMZN MKTP UK*{c}", "STEAMGAMES.COM {n}", "ONE4ALL GIFT CARD", "APPLE.COM/BILL",
              "DIGITALGOODS*{c}", "ELECTRONICS HK {c}", "TOPUP MOBILE INTL", "LUXURY WATCHES {c}"]
ATO_REFS = ["TRANSFER", "PAYMENT", "LOAN REPAYMENT", "J SMITH", "A KOWALSKI", "INVOICE {n}", "SAVINGS 2", "M AHMED",
            "D NOWAK", "BILLS"]
APP_SCAM = ["SAFE ACCOUNT TRANSFER", "HMRC TAX SETTLEMENT", "CRYPTO INVESTMENT DEPOSIT", "INVOICE {n} UPDATED BANK DETAILS",
            "RELEASE PARCEL CUSTOMS FEE", "BANK SECURITY TEAM MOVE FUNDS", "PROTECT SAVINGS NEW ACCOUNT",
            "TRADING PLATFORM TOP UP"]
ALPHABET = string.ascii_uppercase + string.digits + " .*/-&'\n"
SURNAMES = ["SMITH", "JONES", "PATEL", "AHMED", "OKAFOR", "WILLIAMS", "KHAN", "BROWN", "TAYLOR", "NOWAK", "KOWALSKI",
            "MURPHY", "SINGH", "EVANS", "WALKER", "HUGHES", "ALI", "GREEN", "LEWIS", "ROBINSON", "WOOD", "HALL", "CLARKE",
            "MENSAH", "OSEI", "GARCIA", "ROSSI", "NGUYEN", "CHEN", "WRIGHT", "THOMPSON", "WHITE", "HARRIS", "MARTIN",
            "JACKSON", "BAKER", "KING", "SCOTT", "MORRIS", "COOPER", "WARD", "PRICE", "BELL", "HUSSAIN", "BEGUM"]
WORDS = ["FOR", "THE", "BIKE", "THANKS", "PIZZA", "LAST", "NIGHT", "CONCERT", "FLOWERS", "TAXI", "SHARE", "HOLS", "BDAY",
         "PRESENT", "SORRY", "LATE", "FUEL", "BOOKS", "KIDS", "CLUB", "FEES", "FOOTBALL", "DANCE", "LESSONS", "GARDEN",
         "WORK", "LUNCH", "TRIP", "DRINKS", "WEDDING", "GIFT", "PARKING", "TUTOR", "PIANO", "VET", "SOFA", "TABLE"]
SYL = ["BRAM", "KOR", "VEL", "LA", "WICK", "TON", "MER", "SHA", "DEN", "ROS", "FIN", "GAL", "HOLT", "PER", "RY", "ASH"]
KINDS = ["DELI", "HARDWARE", "BAKERY", "CAFE", "BARBERS", "NAILS", "FLORIST", "TAKEAWAY", "GARAGE", "BOUTIQUE", "PHARMACY"]

def code():
    return "".join(rng.choice(list(string.ascii_uppercase + string.digits), 5))

def fill(t):
    return t.format(m=rng.choice(MONTHS), c=code(), n=int(rng.integers(1000, 9999)))

cust_median = np.exp(rng.normal(np.log(35), 0.5, N_CUST))
cust_hour = rng.normal(14, 2.5, N_CUST).clip(9, 19)
cust_abroad = rng.choice([0.0, 0.03, 0.10], N_CUST, p=[0.6, 0.3, 0.1])

def legit_kind():
    return rng.choice(["pos", "online", "usual_pay", "big_new_pay"], p=[0.55, 0.25, 0.17, 0.03])

def person():
    return f"{rng.choice(list(string.ascii_uppercase))} {rng.choice(SURNAMES)}"

def free_text():
    return " ".join(rng.choice(WORDS, int(rng.integers(1, 4)), replace=False))

def small_merchant():
    return "".join(rng.choice(SYL, int(rng.integers(2, 4)))) + " " + rng.choice(KINDS)

def legit_description(kind, abroad=False):
    """Genuine descriptions have a long tail: small merchants, names and customers' own free text."""
    if kind == "pos":
        if rng.random() < 0.3:
            return f"{small_merchant()} {rng.choice(TOWNS)}"
        return f"{rng.choice(POS)} {rng.integers(100, 9999)} {rng.choice(TOWNS)}"
    if kind == "online":
        return rng.choice(ABROAD) if abroad else fill(rng.choice(ONLINE))
    if kind == "usual_pay":
        u = rng.random()
        return person() if u < 0.35 else free_text() if u < 0.6 else fill(rng.choice(USUAL_PAY))
    return rng.choice(BIG_NEW_PAY)

def make_transaction(cid, kind):
    """Return one transaction record. kind: a legit kind or a fraud type."""
    med, h0 = cust_median[cid], cust_hour[cid]
    r = dict(customer_id=int(cid), median=float(med), label=0, fraud_type="genuine", on_mule_list=False)
    hour = float(np.clip(rng.normal(h0, 3.5), 0, 23.9)) if rng.random() > 0.05 else float(rng.uniform(0, 6))
    if kind in ("pos", "online", "usual_pay", "big_new_pay"):
        abroad = kind == "online" and rng.random() < cust_abroad[cid] * 3
        r.update(channel={"pos": "card_present", "online": "card_online"}.get(kind, "faster_payment"),
                 description=legit_description(kind, abroad), abroad=bool(abroad or (kind == "pos" and rng.random() < cust_abroad[cid])),
                 amount=med * float(np.exp(rng.normal({"pos": 0, "online": 0.2, "usual_pay": 1.2, "big_new_pay": 3.2}[kind],
                                                        {"pos": 0.6, "online": 0.7, "usual_pay": 0.8, "big_new_pay": 0.7}[kind]))),
                 new_payee=bool(kind == "big_new_pay" or (kind in ("pos", "online") and rng.random() < 0.12)),
                 new_device=bool(kind != "pos" and rng.random() < 0.05),
                 password_reset=bool(rng.random() < 0.01),
                 mins_since_login=float(rng.exponential(8) + 1) if kind in ("usual_pay", "big_new_pay") else None,
                 txns_last_hour=int(rng.poisson(4) if rng.random() < 0.03 else rng.poisson(0.8)))
        r["payee_age"] = (None if r["channel"] != "faster_payment" else
                          float(rng.integers(5, 300)) if (kind == "big_new_pay" and rng.random() < 0.25) else float(rng.integers(400, 5000)))
    elif kind == "card_fraud":
        small = rng.random() < 0.55
        r.update(channel="card_online", description=(fill(rng.choice(ONLINE)) if rng.random() < 0.4 else small_merchant() if rng.random() < 0.3
                             else fill(rng.choice(CARD_FRAUD))), abroad=bool(rng.random() < 0.45),
                 amount=float(rng.uniform(1, 5)) if small else med * float(np.exp(rng.normal(1.3, 0.6))),
                 new_payee=bool(rng.random() < 0.9), new_device=bool(rng.random() < 0.65), password_reset=False, mins_since_login=None,
                 txns_last_hour=int(rng.poisson(4) + 1) if rng.random() < 0.5 else int(rng.poisson(1)), payee_age=None)
        hour = float(rng.uniform(0, 23.9))
    elif kind == "account_takeover":
        r.update(channel="faster_payment", description=(person() if rng.random() < 0.5 else free_text() if rng.random() < 0.4 else fill(rng.choice(ATO_REFS))), abroad=bool(rng.random() < 0.1),
                 amount=med * float(np.exp(rng.normal(3.0, 0.8))), new_payee=True, new_device=bool(rng.random() < 0.7),
                 password_reset=bool(rng.random() < 0.45), mins_since_login=float(rng.uniform(0.5, 10)),
                 txns_last_hour=int(rng.poisson(1.5)),
                 payee_age=float(rng.integers(1, 90)) if rng.random() < 0.6 else float(rng.integers(90, 3000)))
        if rng.random() < 0.3:
            hour = float(rng.uniform(0, 5))
    elif kind == "app_scam":
        scammy = rng.random() < 0.6
        r.update(channel="faster_payment", description=fill(rng.choice(APP_SCAM)) if scammy else fill(rng.choice(["INVOICE {n}", "CAR PURCHASE DEALER", "HOLIDAY VILLA BOOKING", "J SMITH", "DEPOSIT"])),
                 abroad=bool(rng.random() < 0.15), amount=med * float(np.exp(rng.normal(2.8, 0.9))), new_payee=True,
                 new_device=bool(rng.random() < 0.03), password_reset=bool(rng.random() < 0.01),
                 mins_since_login=float(rng.exponential(15) + 2), txns_last_hour=int(rng.poisson(0.7)),
                 payee_age=float(rng.integers(1, 60)) if rng.random() < 0.55 else float(rng.integers(60, 2000)))
    if kind in TYPES[1:]:
        r.update(label=1, fraud_type=kind, on_mule_list=bool(kind != "card_fraud" and rng.random() < 0.3))
    r["hour"] = hour
    r["unusual_hour"] = bool(abs(hour - h0) > 7 or hour < 6)
    r["amount"] = round(max(r["amount"], 0.5), 2)
    r["amount_ratio"] = r["amount"] / med
    return r

# history of NORMAL descriptions (for the LLM) - unlabelled, mostly genuine
hist_refs = []
for _ in range(N_HIST_REFS):
    cid = int(rng.integers(N_CUST))
    k = legit_kind()
    hist_refs.append(legit_description(k, k == "online" and rng.random() < cust_abroad[cid] * 3))

# evaluation stream with ~1.5% fraud
txns = []
for _ in range(N_EVAL):
    cid = int(rng.integers(N_CUST))
    if rng.random() < FRAUD_RATE:
        txns.append(make_transaction(cid, rng.choice(TYPES[1:], p=[0.35, 0.30, 0.35])))
    else:
        txns.append(make_transaction(cid, legit_kind()))
y = np.array([t["label"] for t in txns])
ftype = np.array([t["fraud_type"] for t in txns])
perm = rng.permutation(N_EVAL)
idx_train, idx_test = perm[: int(0.6 * N_EVAL)], perm[int(0.6 * N_EVAL):]
print(f"Transactions: {N_EVAL} ({y.sum()} fraud, {y.mean():.2%}) | train {len(idx_train)} | test {len(idx_test)}")
print("  fraud by type:", {k: int((ftype == k).sum()) for k in TYPES[1:]})

# =============================================================================
# 2. MINI LLM: learn what NORMAL payment descriptions look like
# =============================================================================
stoi = {c: i for i, c in enumerate(ALPHABET)}; V = len(ALPHABET)
enc = lambda s: [stoi[c] for c in s if c in stoi]
corpus = torch.tensor(enc("\n".join(hist_refs) + "\n"), dtype=torch.long)
BLOCK, NE, NH, NL = 64, 96, 4, 3

class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.ln1, self.ln2 = nn.LayerNorm(NE), nn.LayerNorm(NE)
        self.qkv, self.proj = nn.Linear(NE, 3 * NE), nn.Linear(NE, NE)
        self.ff = nn.Sequential(nn.Linear(NE, 4 * NE), nn.GELU(), nn.Linear(4 * NE, NE))
        self.register_buffer("mask", torch.tril(torch.ones(BLOCK, BLOCK)))
    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(self.ln1(x)).split(NE, 2)
        q, k, v = (t.view(B, T, NH, C // NH).transpose(1, 2) for t in (q, k, v))
        a = F.softmax(((q @ k.transpose(-2, -1)) / math.sqrt(C // NH)).masked_fill(self.mask[:T, :T] == 0, float("-inf")), -1)
        x = x + self.proj((a @ v).transpose(1, 2).reshape(B, T, C))
        return x + self.ff(self.ln2(x))

class MiniGPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.tok, self.pos = nn.Embedding(V, NE), nn.Embedding(BLOCK, NE)
        self.blocks = nn.Sequential(*[Block() for _ in range(NL)])
        self.ln_f, self.head = nn.LayerNorm(NE), nn.Linear(NE, V)
    def forward(self, idx):
        return self.head(self.ln_f(self.blocks(self.tok(idx) + self.pos(torch.arange(idx.size(1))))))

gpt = MiniGPT()
opt = torch.optim.AdamW(gpt.parameters(), lr=2e-3, weight_decay=0.1)
steps = 400 if QUICK else 1200
print(f"\n[MINI LLM] learning normal payment descriptions ({sum(p.numel() for p in gpt.parameters())/1e6:.2f}M params, "
      f"{len(hist_refs)} descriptions, {steps} steps)")
t0 = time.time()
for step in range(steps + 1):
    ix = torch.randint(len(corpus) - BLOCK - 1, (48,))
    xb = torch.stack([corpus[i:i + BLOCK] for i in ix]); yb = torch.stack([corpus[i + 1:i + BLOCK + 1] for i in ix])
    loss = F.cross_entropy(gpt(xb).view(-1, V), yb.view(-1))
    opt.zero_grad(); loss.backward(); opt.step()
    if step % (steps // 3) == 0:
        print(f"  step {step:5d} | loss {loss.item():.3f} ({loss.item() / math.log(2):.2f} bits/char)")
print(f"  done in {time.time() - t0:.0f}s")

@torch.no_grad()
def surprise(descs, bs=512):
    """Average bits per character the mini LLM needs to 'explain' each description.
    Low = looks like normal banking text. High = unlike anything it has seen."""
    gpt.eval(); out = []
    for i in range(0, len(descs), bs):
        seqs = [enc("\n" + d[:60] + "\n") for d in descs[i:i + bs]]
        L = max(map(len, seqs))
        idx = torch.full((len(seqs), L), stoi["\n"], dtype=torch.long)
        m = torch.zeros(len(seqs), L - 1)
        for j, s in enumerate(seqs):
            idx[j, :len(s)] = torch.tensor(s); m[j, :len(s) - 1] = 1
        nll = F.cross_entropy(gpt(idx[:, :-1]).reshape(-1, V), idx[:, 1:].reshape(-1), reduction="none").view(len(seqs), -1)
        out.append(((nll * m).sum(1) / m.sum(1) / math.log(2)).numpy())
    return np.concatenate(out)

baseline_surprise = np.sort(surprise(hist_refs[:5000]))           # what 'normal' looks like
s_all = surprise([t["description"] for t in txns])
s_pct = np.searchsorted(baseline_surprise, s_all) / len(baseline_surprise) * 100
t0 = time.time()
for t in txns[:100]:
    surprise([t["description"]])
llm_ms = (time.time() - t0) * 10
print(f"  mean surprise (bits/char): genuine {s_all[y == 0].mean():.2f} | "
      + " | ".join(f"{k} {s_all[ftype == k].mean():.2f}" for k in TYPES[1:]))
print(f"  latency: {llm_ms:.1f} ms per single transaction on CPU")

# =============================================================================
# 3. JEV: one call per transaction, two typed questions
# =============================================================================
QUESTIONS = {
    "is_fraud": {"type": "noul",
        "instructions": ("Is this transaction fraudulent or the result of a scam - that is, NOT a genuine payment that the "
                         "account holder knowingly intends for its real, legitimate recipient?"),
        "criteria": {"true": "Signs of stolen card use, account takeover by a third party, or a customer being manipulated "
                             "into paying a fraudster (for example 'safe account', fake HMRC, fake investment, changed bank details).",
                     "false": "Consistent with the customer's normal behaviour, or an unusual but plausible genuine payment."}},
    "fraud_type": {"type": "choice",
        "instructions": "Which pattern best describes this transaction?",
        "criteria": {"card fraud (card not present)": "Stolen card details used online, often small test payments first.",
                     "account takeover": "Someone other than the customer has taken control of the account or device.",
                     "authorised push payment scam": "The real customer is being tricked into sending money to a fraudster.",
                     "genuine": "A genuine transaction by the customer."}},
}

def jev_state(t):
    """What Jev reads: the transaction plus the customer's behavioural context."""
    return {"transaction": {"amount_gbp": t["amount"], "channel": t["channel"], "description": t["description"],
                            "abroad": t["abroad"], "local_hour": round(t["hour"], 1)},
            "customer_context": {"median_amount_gbp": round(t["median"], 2), "amount_vs_customer_median": round(t["amount_ratio"], 2),
                                 "new_payee_or_merchant": t["new_payee"], "payee_account_age_days": t["payee_age"],
                                 "new_device": t["new_device"], "password_reset_last_24h": t["password_reset"],
                                 "minutes_since_login": None if t["mins_since_login"] is None else round(t["mins_since_login"], 1),
                                 "transactions_last_hour": t["txns_last_hour"], "unusual_hour_for_customer": t["unusual_hour"]}}

jev = get_jev(offline=OFFLINE)
print(f"\n[JEV] decision model: {jev.name}")
t0 = time.time()
with ThreadPoolExecutor(max_workers=12) as ex:
    jev_out = list(ex.map(lambda t: jev.ask(jev_state(t), QUESTIONS), txns))
print(f"  scored {len(txns)} transactions in {time.time() - t0:.1f}s, {jev.input_tokens} input tokens")
p_jev = np.array([o["answers"]["is_fraud"]["noul"] for o in jev_out])
jev_type = np.array([o["answers"]["fraud_type"]["choice"] for o in jev_out])

# =============================================================================
# 4. CHALLENGER: trees trained on labelled past cases, with and without the LLM signal
# =============================================================================
CH = ["card_present", "card_online", "faster_payment"]
def features(with_llm):
    rows = []
    for k, t in enumerate(txns):
        row = [math.log1p(t["amount"]), math.log1p(t["amount_ratio"]), *[t["channel"] == c for c in CH], t["new_payee"],
               -1 if t["payee_age"] is None else t["payee_age"], t["new_device"], t["password_reset"],
               -1 if t["mins_since_login"] is None else t["mins_since_login"], t["txns_last_hour"], t["abroad"],
               t["hour"], t["unusual_hour"]]
        rows.append(row + ([s_all[k]] if with_llm else []))
    return np.array(rows, dtype=float)

X_no, X_llm = features(False), features(True)
def challenger(X):
    m = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=15, l2_regularization=1.0, random_state=SEED)
    oof = cross_val_predict(m, X[idx_train], y[idx_train], cv=5, method="predict_proba")[:, 1]
    m.fit(X[idx_train], y[idx_train])
    p = np.zeros(N_EVAL); p[idx_train] = oof; p[idx_test] = m.predict_proba(X[idx_test])[:, 1]
    return m, p
chal_no, p_chal_no = challenger(X_no)
chal_llm, p_chal = challenger(X_llm)
p_ens = 0.5 * p_jev + 0.5 * p_chal

# =============================================================================
# 5. DECISION ENGINE
# =============================================================================
CAPACITY = {"BLOCK": 0.004, "HOLD": 0.012, "STEP-UP": 0.04}   # share of traffic each action may take
RANK = {"ALLOW": 0, "STEP-UP": 1, "HOLD": 2, "BLOCK": 3}

def thresholds(p):
    """Set cut-offs on TRAINING scores so each action fits the team's capacity."""
    q = lambda share: float(np.quantile(p[idx_train], 1 - share))
    return {"BLOCK": q(CAPACITY["BLOCK"]), "HOLD": q(CAPACITY["HOLD"]), "STEP-UP": q(CAPACITY["STEP-UP"])}

def decide(k, risk, cut, use_overrides=True, use_llm_rule=True, pj=None, pc=None):
    t = txns[k]
    action = next((a for a in ("BLOCK", "HOLD", "STEP-UP") if risk >= cut[a]), "ALLOW")
    why = []
    if not use_overrides:
        return action, why
    def lift(to, reason):
        nonlocal action
        if RANK[to] > RANK[action]:
            action = to; why.append(reason)
    if t["on_mule_list"]:
        lift("BLOCK", "payee account is on the shared mule-account list")
    if t["channel"] != "faster_payment" and t["txns_last_hour"] >= 10:
        lift("BLOCK", f"{t['txns_last_hour']} card transactions in the last hour (card-testing rule)")
    if use_llm_rule and t["channel"] == "faster_payment" and t["new_payee"] and t["amount_ratio"] >= 5 and s_pct[k] >= 99.5:
        lift("STEP-UP", f"payment description is unlike normal payments (mini LLM surprise in the top 0.5%)")
    if pj is not None and max(pj[k], pc[k]) >= 0.9:
        lift("HOLD", "one model is very confident this is fraud")
    return action, why

# what each action achieves (assumptions - tune to your own operations data)
STOP = {"STEP-UP": {"card_fraud": 0.85, "account_takeover": 0.80, "app_scam": 0.35},
        "HOLD": {"card_fraud": 0.95, "account_takeover": 0.95, "app_scam": 0.75},
        "BLOCK": {"card_fraud": 1.0, "account_takeover": 1.0, "app_scam": 1.0}}
FRICTION = {"ALLOW": 0.0, "STEP-UP": 0.5, "HOLD": 6.0, "BLOCK": 20.0}   # £ cost of inconveniencing a genuine customer

def evaluate(actions, idx):
    loss = prevented = friction = 0.0
    caught = {k: [0.0, 0] for k in TYPES[1:]}
    for k, a in zip(idx, actions):
        t = txns[k]
        if t["label"]:
            s = STOP.get(a, {}).get(t["fraud_type"], 0.0)
            prevented += s * t["amount"]; loss += (1 - s) * t["amount"]
            caught[t["fraud_type"]][0] += s; caught[t["fraud_type"]][1] += 1
        else:
            friction += FRICTION[a]
    genuine = [a for k, a in zip(idx, actions) if not txns[k]["label"]]
    return {"fraud_loss_gbp": loss, "fraud_prevented_gbp": prevented, "friction_cost_gbp": friction,
            "total_cost_gbp": loss + friction,
            "genuine_interrupted": sum(a != "ALLOW" for a in genuine), "genuine_blocked": sum(a == "BLOCK" for a in genuine),
            "genuine_by_action": {x: sum(a == x for a in genuine) for x in RANK},
            "fraud_by_action": {x: sum(a == x for k, a in zip(idx, actions) if txns[k]["label"]) for x in RANK},
            "fraud_stopped_share": {k: v[0] / max(v[1], 1) for k, v in caught.items()}}

def run_design(name, risk, **kw):
    cut = thresholds(risk) if risk is not None else None
    acts = []
    for k in idx_test:
        if risk is None:                                   # rules only
            t = txns[k]
            a = "HOLD" if (t["new_payee"] and t["amount_ratio"] >= 20 and t["channel"] == "faster_payment") else "ALLOW"
            a2, _ = decide(k, 0.0, {"BLOCK": 9, "HOLD": 9, "STEP-UP": 9}, use_llm_rule=False)
            acts.append(max(a, a2, key=RANK.get))
        else:
            acts.append(decide(k, risk[k], cut, **kw)[0])
    return name, acts, cut

designs = [
    ("No controls", ["ALLOW"] * len(idx_test), None),
    run_design("Rules only", None),
    run_design("Jev only", p_jev, use_llm_rule=False),
    run_design("Challenger only (no LLM)", p_chal_no, use_llm_rule=False),
    run_design("Challenger + mini LLM", p_chal),
    run_design("Full design: Jev + challenger + mini LLM + rules", p_ens, pj=p_jev, pc=p_chal),
]
results = {name: evaluate(acts, idx_test) for name, acts, _ in designs}
_, final_actions, CUT = designs[-1]

# =============================================================================
# 6. REPORT
# =============================================================================
yt = y[idx_test]
scores = {"Jev (zero labels)" if "live" in jev.name else "Local stand-in (zero labels)": p_jev,
          "Challenger, no LLM": p_chal_no, "Challenger + mini LLM surprise": p_chal, "Ensemble (Jev + challenger)": p_ens,
          "Mini LLM surprise on its own": s_all}
ranking = {}
print(f"\n[RANKING POWER on {len(idx_test)} test transactions, {yt.sum()} fraud]")
print(f"  {'Score':34s} {'PR-AUC':>7s} {'ROC-AUC':>8s} {'Recall @2% alerts':>18s}")
for name, s in scores.items():
    st = s[idx_test]; top = st >= np.quantile(st, 0.98)
    ranking[name] = {"pr_auc": average_precision_score(yt, st), "roc_auc": roc_auc_score(yt, st),
                     "recall_at_2pct": float(yt[top].sum() / yt.sum())}
    r = ranking[name]
    print(f"  {name:34s} {r['pr_auc']:7.3f} {r['roc_auc']:8.3f} {r['recall_at_2pct']:18.1%}")
print(f"  (fraud base rate {yt.mean():.2%} - a random score has PR-AUC ~{yt.mean():.3f})")

calib = []
for lo, hi in [(0, .05), (.05, .2), (.2, .5), (.5, .8), (.8, 1.01)]:
    m = (p_jev[idx_test] >= lo) & (p_jev[idx_test] < hi)
    if m.sum():
        calib.append([f"{lo:.0%}-{min(hi, 1):.0%}", int(m.sum()), float(p_jev[idx_test][m].mean()), float(yt[m].mean())])
print("\n  Calibration of the decision model:  bucket | n | mean predicted | actual fraud rate")
for b in calib:
    print(f"    {b[0]:9s} {b[1]:6d} {b[2]:8.1%} {b[3]:8.1%}")

print(f"\n[BUSINESS OUTCOME on the test set - fraud value £{sum(txns[k]['amount'] for k in idx_test if txns[k]['label']):,.0f}]")
print(f"  {'Design':50s} {'Fraud lost':>11s} {'Friction':>9s} {'Total':>9s} {'Genuine interrupted':>20s}")
for name, r in results.items():
    print(f"  {name:50s} £{r['fraud_loss_gbp']:>9,.0f} £{r['friction_cost_gbp']:>7,.0f} £{r['total_cost_gbp']:>7,.0f} "
          f"{r['genuine_interrupted']:>10d} ({r['genuine_blocked']} blocked)")
fs = results[designs[-1][0]]["fraud_stopped_share"]
print("  Full design - share of fraud stopped by type: " + ", ".join(f"{k} {v:.0%}" for k, v in fs.items()))
dist = {a: int(sum(x == a for x in final_actions)) for a in RANK}
print("  Full design - actions: " + ", ".join(f"{a} {n}" for a, n in dist.items()))
fr = results[designs[-1][0]]
print("  Full design - genuine by action: " + ", ".join(f"{a} {n}" for a, n in fr["genuine_by_action"].items())
      + " | fraud by action: " + ", ".join(f"{a} {n}" for a, n in fr["fraud_by_action"].items()))

# =============================================================================
# 7. CASE FILES + AUDIT LOG (deterministic text only - no generated prose)
# =============================================================================
WARN = {"authorised push payment scam": ("Stop - this could be a scam. Your bank, HMRC and the police will never ask you to "
                                         "move money to a 'safe account' or pay a fee to release funds. If someone is telling "
                                         "you what to do, hang up and call us on the number on your card."),
        "account takeover": "We have noticed a new device and unusual activity. Please confirm this payment in your app.",
        "card fraud (card not present)": "Please confirm this card payment in your app.",
        "genuine": "Please confirm this payment in your app."}

def rarity(k):
    return "rarer than every normal description sampled" if s_pct[k] >= 99.95 else f"rarer than {s_pct[k]:.1f}% of normal descriptions"

def reason_codes(k):
    t = txns[k]; r = []
    if t["new_device"]: r.append("New device for this customer")
    if t["password_reset"]: r.append("Password reset in the last 24 hours")
    if t["mins_since_login"] is not None and t["mins_since_login"] < 5: r.append(f"Payment {t['mins_since_login']:.0f} minutes after login")
    if t["amount_ratio"] >= 5: r.append(f"Amount is {t['amount_ratio']:.0f}x the customer's median (£{t['median']:.0f})")
    if t["new_payee"]: r.append("First payment to this payee or merchant")
    if t["payee_age"] is not None and t["payee_age"] < 90: r.append(f"Payee account opened {t['payee_age']:.0f} days ago")
    if t["txns_last_hour"] >= 4: r.append(f"{t['txns_last_hour']} transactions in the last hour")
    if t["abroad"]: r.append("Merchant or payee abroad")
    if t["unusual_hour"]: r.append(f"Unusual time for this customer ({int(t['hour']):02d}:{int(t['hour'] % 1 * 60):02d})")
    if s_pct[k] >= 99: r.append(f"Description unlike normal payments (mini LLM surprise {s_all[k]:.1f} bits/char, {rarity(k)})")
    if t["on_mule_list"]: r.append("Payee on shared mule-account list")
    return r or ["No unusual signals"]

def sha(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()[:12]
VERSIONS = {"decision_model": jev_out[0]["model"], "questions": sha(QUESTIONS), "thresholds": sha(CUT),
            "mini_llm": hashlib.sha256(b"".join(v.numpy().tobytes() for v in gpt.state_dict().values())).hexdigest()[:12],
            "challenger": sha(chal_llm.get_params())}

def case_file(pos):
    k = idx_test[pos]; t = txns[k]
    action, why = decide(k, p_ens[k], CUT, pj=p_jev, pc=p_chal)
    jt = jev_type[k]
    lines = [f"# Fraud case — transaction {k}", "",
             f"**Action:** {action}  ", f"**Truth (synthetic label, unknown to the system):** {t['fraud_type']}", "",
             "## Scores", "", "| Signal | Value |", "|---|---|",
             f"| Jev P(fraud) | {p_jev[k]:.1%} |", f"| Jev fraud type | {jt} |",
             f"| Challenger P(fraud) (trees + mini LLM) | {p_chal[k]:.1%} |",
             f"| Combined risk | {p_ens[k]:.1%} (STEP-UP ≥ {CUT['STEP-UP']:.1%}, HOLD ≥ {CUT['HOLD']:.1%}, BLOCK ≥ {CUT['BLOCK']:.1%}) |",
             f"| Mini LLM surprise | {s_all[k]:.2f} bits/char ({rarity(k)}) |", "",
             "## Transaction", "", "| Field | Value |", "|---|---|",
             f"| Amount | £{t['amount']:,.2f} |", f"| Channel | {t['channel']} |", f"| Description | {t['description']} |",
             f"| Local time | {int(t['hour']):02d}:{int(t['hour'] % 1 * 60):02d} |", "",
             "## Reason codes (deterministic)", ""] + [f"- {r}" for r in reason_codes(k)]
    lines += ["", "## Overrides applied", ""] + ([f"- {w}" for w in why] or ["- None"])
    if action == "STEP-UP":
        # push payments to a new payee get the scam warning unless Jev points to a different pattern
        w = jt if jt != "genuine" else ("authorised push payment scam" if t["channel"] == "faster_payment" and t["new_payee"] else "genuine")
        lines += ["", "## Message shown to the customer (fixed template)", "", f"> {WARN[w]}"]
    lines += ["", "**Analyst decision:** _pending_", ""]
    return "\n".join(lines), {"transaction_id": int(k), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "model_versions": VERSIONS,
                              "input_hash": sha(jev_state(t)), "jev_answers": jev_out[k]["answers"], "p_challenger": float(p_chal[k]),
                              "risk": float(p_ens[k]), "llm_surprise_bits": float(s_all[k]), "action": action, "overrides": why,
                              "reason_codes": reason_codes(k), "analyst_decision": None, "analyst": None}

def action_of(k):
    return decide(k, p_ens[k], CUT, pj=p_jev, pc=p_chal)[0]

def pick(cond, prefer=None, key=None):
    c = [p for p, k in enumerate(idx_test) if cond(k)]
    if prefer:
        c = [p for p in c if action_of(idx_test[p]) == prefer] or c
    return max(c, key=key or (lambda p: p_ens[idx_test[p]])) if c else None

picks = [
    ("genuine_large_new_payee", pick(lambda k: txns[k]["fraud_type"] == "genuine" and txns[k]["description"] in BIG_NEW_PAY)),
    ("app_scam", pick(lambda k: txns[k]["fraud_type"] == "app_scam" and not txns[k]["on_mule_list"], prefer="STEP-UP")),
    ("app_scam_scam_wording", pick(lambda k: txns[k]["fraud_type"] == "app_scam" and not txns[k]["on_mule_list"]
                                   and any(w in txns[k]["description"] for w in ("SAFE", "HMRC", "CRYPTO")))),
    ("account_takeover", pick(lambda k: txns[k]["fraud_type"] == "account_takeover" and not txns[k]["on_mule_list"])),
    ("card_fraud", pick(lambda k: txns[k]["fraud_type"] == "card_fraud")),
    ("missed_fraud", pick(lambda k: txns[k]["label"] == 1 and action_of(k) == "ALLOW", key=lambda p: txns[idx_test[p]]["amount"])),
]
with open(os.path.join(OUT, "audit_log.jsonl"), "w") as log:
    for label, p in picks:
        if p is None:
            continue
        md, rec = case_file(p)
        open(os.path.join(OUT, f"case_{label}.md"), "w").write(md)
        log.write(json.dumps(rec, default=str) + "\n")
        print("\n" + "=" * 78 + "\n" + md)

metrics = {"decision_model": jev.name, "ranking": ranking, "calibration": calib, "business": results,
           "actions_full_design": dist, "thresholds": CUT, "capacity": CAPACITY, "stop_rates": STOP, "friction_costs": FRICTION,
           "mini_llm_latency_ms": llm_ms, "versions": VERSIONS,
           "data": {"transactions": N_EVAL, "fraud": int(y.sum()), "test": len(idx_test), "test_fraud": int(yt.sum())}}
json.dump(metrics, open(os.path.join(OUT, "metrics.json"), "w"), indent=2, default=float)
# curves for the documentation
curves = {}
for name in ["Ensemble (Jev + challenger)", "Challenger + mini LLM surprise", "Challenger, no LLM",
             list(scores)[0], "Mini LLM surprise on its own"]:
    st = scores[name][idx_test]; order = np.argsort(-st); tp = np.cumsum(yt[order])
    pts = [(float(tp[i] / yt.sum()), float(tp[i] / (i + 1))) for i in np.unique(np.linspace(5, len(st) - 1, 200).astype(int))]
    curves[name] = pts
json.dump(curves, open(os.path.join(OUT, "pr_curves.json"), "w"))
with open(os.path.join(OUT, "model_card.md"), "w") as fh:
    fh.write(f"# Model card — Jev + mini LLM transaction fraud detection (synthetic demo)\n\n"
             f"**Decision model in this run:** {jev.name}\n\n"
             "**Purpose:** real-time screening of card and Faster Payments transactions; analysts review HOLDs and customers confirm STEP-UPs.\n\n"
             "## Ranking power (test set)\n\n| Score | PR-AUC | ROC-AUC | Recall at 2% alerts |\n|---|---|---|---|\n" +
             "".join(f"| {k} | {v['pr_auc']:.3f} | {v['roc_auc']:.3f} | {v['recall_at_2pct']:.1%} |\n" for k, v in ranking.items()) +
             "\n## Business outcome (test set)\n\n| Design | Fraud lost | Friction | Total | Genuine interrupted |\n|---|---|---|---|---|\n" +
             "".join(f"| {k} | £{v['fraud_loss_gbp']:,.0f} | £{v['friction_cost_gbp']:,.0f} | £{v['total_cost_gbp']:,.0f} | {v['genuine_interrupted']} |\n"
                     for k, v in results.items()) +
             "\n## Limitations\n\n- Synthetic data; stop rates and friction costs are assumptions.\n"
             "- The offline stand-in is not Jev; run with an API key to validate the real model.\n"
             "- Fraud patterns shift: retrain the mini LLM and challenger regularly and monitor alert precision weekly.\n"
             f"\n## Versions\n\n```\n{json.dumps(VERSIONS, indent=2)}\n```\n")
print(f"\nSaved case files, audit_log.jsonl, metrics.json, pr_curves.json and model_card.md to ./{OUT}/")

# =============================================================================
# 8. OPTIONAL: EXPORT A MODEL BUNDLE for the scoring service in ../gcp/
#    python fraud_jev_llm.py --offline --export-bundle ../gcp/model_bundle
# =============================================================================
if "--export-bundle" in sys.argv:
    import joblib
    bdir = sys.argv[sys.argv.index("--export-bundle") + 1]
    os.makedirs(bdir, exist_ok=True)
    torch.save(gpt.state_dict(), os.path.join(bdir, "mini_llm.pt"))
    np.save(os.path.join(bdir, "baseline_surprise.npy"), baseline_surprise)
    joblib.dump(chal_llm, os.path.join(bdir, "challenger.joblib"))
    engine = {"mini_llm": {"alphabet": ALPHABET, "block": BLOCK, "n_embd": NE, "n_head": NH, "n_layer": NL},
              "channels": CH, "thresholds": CUT, "capacity": CAPACITY, "questions": QUESTIONS, "warnings": WARN,
              "overrides": {"card_testing_txns_last_hour": 10, "llm_rule_amount_ratio": 5, "llm_rule_surprise_percentile": 99.5,
                            "confident_model": 0.9},
              "versions": VERSIONS, "trained_on": f"{N_EVAL} synthetic transactions (seed {SEED})"}
    json.dump(engine, open(os.path.join(bdir, "engine.json"), "w"), indent=1)
    samples = []
    for label, p in picks:
        if p is None:
            continue
        k = idx_test[p]; t = txns[k]
        a, why = decide(k, p_ens[k], CUT, pj=p_jev, pc=p_chal)
        samples.append({"name": label,
                        "transaction": {f: t[f] for f in ("customer_id", "amount", "channel", "description", "hour", "abroad",
                                                          "median", "new_payee", "payee_age", "new_device", "password_reset",
                                                          "mins_since_login", "txns_last_hour", "unusual_hour", "on_mule_list")},
                        "expected": {"action": a, "risk": float(p_ens[k]), "p_jev": float(p_jev[k]), "p_challenger": float(p_chal[k]),
                                     "surprise_bits": float(s_all[k]), "overrides": why}})
    json.dump(samples, open(os.path.join(bdir, "samples.json"), "w"), indent=1)
    print(f"Exported model bundle ({len(samples)} sample transactions) to {bdir}")
