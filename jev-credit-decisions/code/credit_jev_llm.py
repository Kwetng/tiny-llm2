"""
credit_jev_llm.py - credit decision support with Jev (System One) + a tiny LLM (System Two).

  Jev  (System One) : fast, calibrated judgement. Given a borrower's data as JSON,
                      it answers typed questions in one call:
                        can_repay  (noul)   -> probability the borrower meets all payments
                        main_risk  (choice) -> the dominant risk driver
                        risk_grade (score)  -> 1 (strong) .. 5 (weak)
  Tiny LLM (System Two) : the character-level GPT from mini_gpt.py, pre-trained on
                      analyst notes, drafts the narrative for the credit memo.
  Decision engine   : deterministic policy rules + PD bands + challenger check
                      -> a RECOMMENDATION; the credit committee decides.

Principles:
  - Numbers come from source data and the decision model, never from LLM text.
  - The LLM only drafts narrative; a human owns the decision.
  - Jev's calibration claim is VALIDATED on our own data, not taken on trust.
  - Every recommendation is logged with model versions (SS1/23 evidence).

Usage:
    pip install torch scikit-learn numpy
    export TYPESAFE_API_KEY=...          # to call the real Jev API
    python credit_jev_llm.py             # uses Jev if the key is set, else the local stand-in
    python credit_jev_llm.py --offline   # force the local stand-in
    python credit_jev_llm.py --quick     # smaller run

DISCLAIMER: synthetic borrowers; educational code, not a production credit model.
Sending real client data to any third-party API needs vendor due diligence,
data-protection review and model-risk approval first.
"""
import hashlib, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from jev_client import get_jev

QUICK, OFFLINE = "--quick" in sys.argv, "--offline" in sys.argv
SEED = 11
torch.manual_seed(SEED); np.random.seed(SEED)
OUT = "credit_outputs"
os.makedirs(OUT, exist_ok=True)

FEATURES = ["leverage_x", "interest_cover_x", "current_ratio", "ebitda_margin", "revenue_growth", "cash_to_assets"]
SECTORS = ["industrials", "retail", "technology", "energy"]
T_OBS, T_FUT = 8, 4
N_NOTES, N_TRAIN, N_TEST = (800, 400, 150) if QUICK else (2000, 600, 400)
N = N_NOTES + N_TRAIN + N_TEST

# =============================================================================
# 1. SYNTHETIC BORROWERS: hidden health drifts; ratios are noisy views of it;
#    default risk depends on health over the NEXT 4 quarters.
# =============================================================================
def make_borrowers(n, rng):
    sector = rng.integers(0, len(SECTORS), n)
    sector_lev = np.array([0.4, 0.8, -0.3, 0.6])[sector]
    T = T_OBS + T_FUT
    h = np.zeros((n, T))
    h0, drift = rng.normal(0, 1, n), rng.normal(0, 0.22, n)
    shock_q = rng.integers(4, T, n)
    shock = np.where(rng.random(n) < 0.15, rng.normal(-0.8, 0.3, n), 0.0)
    for t in range(T):
        prev = h0 if t == 0 else h[:, t - 1]
        h[:, t] = prev + drift + rng.normal(0, 0.12, n) + np.where(shock_q == t, shock, 0)
    X = np.zeros((n, T, len(FEATURES)))
    noise = lambda s: rng.normal(0, s, (n, T))
    X[..., 0] = np.clip(3.0 - 0.9 * h + sector_lev[:, None] + noise(0.55), 0.2, 12)
    X[..., 1] = np.clip(4.5 + 1.8 * h + noise(0.9), 0.1, 25)
    X[..., 2] = np.clip(1.4 + 0.25 * h + noise(0.15), 0.3, 4)
    X[..., 3] = 0.14 + 0.04 * h + noise(0.02)
    X[..., 4] = 0.01 + 0.10 * drift[:, None] + 0.02 * h + noise(0.03)
    X[..., 5] = np.clip(0.08 + 0.02 * h + noise(0.02), 0, 1)
    stress = np.minimum(h[:, T_OBS:], 0).sum(1)
    pd_true = 1 / (1 + np.exp(-(-2.9 - 1.35 * h[:, -1] + 0.35 * stress)))
    y = (rng.random(n) < pd_true).astype(int)                      # 1 = defaulted (did NOT repay)
    view = drift + rng.normal(0, 0.12, n) + 0.3 * np.where(shock_q < T_OBS, shock, 0)
    outlook = np.where(view < -0.12, "negative", np.where(view > 0.12, "positive", "stable"))
    phrases = {
        "negative": ["Management reports softer orders and rising input costs.", "Covenant headroom is narrowing on the leverage test.",
                     "Customer concentration is a concern after a key contract loss.", "Working capital has absorbed cash for two quarters.",
                     "Refinancing of the term loan is not yet agreed."],
        "stable": ["Trading is in line with budget and guidance is unchanged.", "Leverage is steady with comfortable covenant headroom.",
                   "Order book is flat and margins are holding.", "No change to the funding structure is expected."],
        "positive": ["Order book is strengthening and pricing is firm.", "Deleveraging is ahead of plan after asset disposals.",
                     "New contracts extend revenue visibility.", "Free cash flow is supporting early debt repayment."],
    }
    notes = []
    for i in range(n):
        p = rng.choice(phrases[outlook[i]], 2, replace=False)
        notes.append(f"Outlook {outlook[i]}. {p[0]} {p[1]} Sector: {SECTORS[sector[i]]}.")
    return X[:, :T_OBS], y, notes, sector, pd_true, outlook

rng = np.random.default_rng(SEED)
X, y, notes, sector, pd_true, outlook = make_borrowers(N, rng)
idx_notes = np.arange(0, N_NOTES)                                  # unlabelled notes for LLM pre-training
idx_train = np.arange(N_NOTES, N_NOTES + N_TRAIN)                  # labelled (for the challenger scorecard)
idx_test = np.arange(N_NOTES + N_TRAIN, N)                          # hold-out
print(f"Borrowers: {N} | test set {N_TEST} | default rate {y.mean():.1%}")

def borrower_state(i):
    """The JSON 'state' Jev reads: exactly what a credit analyst would see today."""
    latest, prior = X[i, -1], X[i, -5]
    r2 = lambda v: round(float(v), 3)
    return {
        "borrower_id": int(i), "sector": SECTORS[sector[i]],
        "facility": {"type": "senior secured term loan", "tenor_years": 5, "amortising": True},
        "latest_quarter": dict(zip(FEATURES, map(r2, latest))),
        "change_over_4_quarters": dict(zip(FEATURES, map(r2, latest - prior))),
        "last_8_quarters_leverage_x": [r2(v) for v in X[i, :, 0]],
        "analyst_note": notes[i],
    }

# =============================================================================
# 2. JEV (SYSTEM ONE): three typed questions, answered in one call per borrower
# =============================================================================
QUESTIONS = {
    "can_repay": {"type": "noul",
        "instructions": ("Will this corporate borrower be able to meet every scheduled interest and principal "
                         "payment on the facility over the next 12 months, without restructuring or default?"),
        "criteria": {"true": "Debt service is covered by earnings and liquidity, and the trend and outlook do not "
                             "point to a payment shortfall within 12 months.",
                     "false": "Leverage, weak interest cover, thin liquidity, a deteriorating trend or a negative "
                              "outlook make a missed payment, restructuring or default within 12 months likely."}},
    "main_risk": {"type": "choice",
        "instructions": "Which factor is the main risk to repayment?",
        "criteria": {"leverage": "Debt is high relative to earnings or rising.",
                     "liquidity": "Short-term liquidity or working capital is tight.",
                     "profitability": "Margins or interest cover are weak.",
                     "business outlook": "The qualitative outlook is deteriorating.",
                     "none material": "No material risk to repayment."}},
    "risk_grade": {"type": "score",
        "instructions": "Grade the borrower's overall credit quality.",
        "criteria": ["Strong: very low risk", "Good: low risk", "Satisfactory: moderate risk",
                     "Weak: high risk", "Very weak: default likely"]},
}

jev = get_jev(offline=OFFLINE)
print(f"\n[JEV] decision model: {jev.name}")
t0 = time.time()
def ask(i):
    return i, jev.ask(borrower_state(i), QUESTIONS)
with ThreadPoolExecutor(max_workers=8) as ex:
    jev_out = dict(ex.map(ask, idx_test))
print(f"  scored {len(jev_out)} borrowers in {time.time() - t0:.1f}s, {jev.input_tokens} input tokens")

pd_jev = np.array([1 - jev_out[i]["answers"]["can_repay"]["noul"] for i in idx_test])   # PD = 1 - P(repay)

# =============================================================================
# 3. VALIDATE JEV ON OUR OWN DATA (do not rely on vendor calibration claims)
#    Challenger: a conventional scorecard trained on 600 labelled borrowers.
# =============================================================================
def scorecard_features(idx):
    return np.concatenate([X[idx, -1], X[idx, -1] - X[idx, -5]], 1)
sc = StandardScaler().fit(scorecard_features(idx_train))
challenger = LogisticRegression(C=0.5, max_iter=2000).fit(sc.transform(scorecard_features(idx_train)), y[idx_train])
pd_chal = challenger.predict_proba(sc.transform(scorecard_features(idx_test)))[:, 1]
y_test = y[idx_test]

def calib_table(p, yy, bins=(0, .02, .05, .10, .20, 1.01)):
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum():
            rows.append((f"{lo:.0%}-{min(hi,1):.0%}", int(m.sum()), float(p[m].mean()), float(yy[m].mean())))
    return rows

results = {
    "Jev (zero labels)" if "live" in jev.name else "Local stand-in (zero labels)":
        {"auc": roc_auc_score(y_test, pd_jev), "brier": brier_score_loss(y_test, pd_jev), "labels_used": 0},
    f"Challenger scorecard ({N_TRAIN} labels)":
        {"auc": roc_auc_score(y_test, pd_chal), "brier": brier_score_loss(y_test, pd_chal), "labels_used": N_TRAIN},
    "Oracle (true synthetic PD)":
        {"auc": roc_auc_score(y_test, pd_true[idx_test]), "brier": brier_score_loss(y_test, pd_true[idx_test]), "labels_used": None},
}
print(f"\n  {'Model':38s} {'AUC':>6s} {'Brier':>8s}")
for k, v in results.items():
    print(f"  {k:38s} {v['auc']:6.3f} {v['brier']:8.4f}")
print("\n  Calibration of the decision model (predicted PD vs realised default rate):")
print(f"  {'PD bucket':10s} {'n':>5s} {'mean PD':>9s} {'realised':>9s}")
calib = calib_table(pd_jev, y_test)
for b, n_, mp, rr in calib:
    print(f"  {b:10s} {n_:5d} {mp:9.1%} {rr:9.1%}")

# =============================================================================
# 4. TINY LLM (SYSTEM TWO): pre-trained on analyst notes, drafts memo narrative
# =============================================================================
corpus = "\n".join(notes[i] for i in idx_notes) + "\n"
chars = sorted(set("".join(notes)) | {"\n"})
stoi = {c: i for i, c in enumerate(chars)}; itos = {i: c for c, i in stoi.items()}
enc = lambda s: [stoi[c] for c in s]; dec = lambda ids: "".join(itos[i] for i in ids)
data = torch.tensor(enc(corpus), dtype=torch.long)
BLOCK, NE, NH, NL = 128, 96, 4, 3

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

class TinyGPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.tok, self.pos = nn.Embedding(len(chars), NE), nn.Embedding(BLOCK, NE)
        self.blocks = nn.Sequential(*[Block() for _ in range(NL)])
        self.ln_f, self.head = nn.LayerNorm(NE), nn.Linear(NE, len(chars))
    def forward(self, idx, tgt=None):
        logits = self.head(self.ln_f(self.blocks(self.tok(idx) + self.pos(torch.arange(idx.size(1))))))
        return logits, None if tgt is None else F.cross_entropy(logits.view(-1, logits.size(-1)), tgt.view(-1))
    @torch.no_grad()
    def generate(self, prompt, n=140, temperature=0.6):
        self.eval()
        idx = torch.tensor([enc(prompt)])
        for _ in range(n):
            logits, _ = self(idx[:, -BLOCK:])
            nxt = torch.multinomial(F.softmax(logits[:, -1] / temperature, -1), 1)
            if itos[nxt.item()] == "\n":
                break
            idx = torch.cat([idx, nxt], 1)
        text = dec(idx[0].tolist())
        return text.split(" Sector:")[0].strip()          # keep the narrative, drop any generated sector tag

gpt = TinyGPT()
gopt = torch.optim.AdamW(gpt.parameters(), lr=2e-3, weight_decay=0.1)
steps = 300 if QUICK else 900
print(f"\n[LLM] pre-training tiny GPT ({sum(p.numel() for p in gpt.parameters())/1e6:.2f}M params) on analyst notes ({steps} steps)")
t0 = time.time()
for step in range(steps + 1):
    ix = torch.randint(len(data) - BLOCK - 1, (32,))
    xb = torch.stack([data[i:i + BLOCK] for i in ix]); yb = torch.stack([data[i + 1:i + BLOCK + 1] for i in ix])
    _, loss = gpt(xb, yb)
    gopt.zero_grad(); loss.backward(); gopt.step()
    if step % (steps // 3) == 0:
        print(f"  step {step:5d} | loss {loss.item():.3f}")
print(f"  done in {time.time() - t0:.0f}s")

# =============================================================================
# 5. DECISION ENGINE: policy rules + PD bands + challenger check -> RECOMMENDATION
# =============================================================================
POLICY = {"max_leverage_x": 6.0, "min_interest_cover_x": 1.5, "max_model_disagreement": 0.10}
BANDS = [(0.03, "APPROVE (recommend)"), (0.10, "REFER to credit committee"), (1.01, "DECLINE (recommend)")]

def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]
VERSIONS = {"decision_model": jev_out[idx_test[0]]["model"], "questions": sha(QUESTIONS), "policy": sha(POLICY),
            "tiny_gpt": hashlib.sha256(b"".join(t.numpy().tobytes() for t in gpt.state_dict().values())).hexdigest()[:12],
            "challenger": hashlib.sha256(challenger.coef_.tobytes()).hexdigest()[:12]}

def assess(i, k):
    s = borrower_state(i)
    ans = jev_out[i]["answers"]
    p_repay = ans["can_repay"]["noul"]
    pd_ = 1 - p_repay
    lq = s["latest_quarter"]
    rules = []
    if lq["leverage_x"] > POLICY["max_leverage_x"]:
        rules.append(f"Leverage {lq['leverage_x']:.1f}x exceeds policy limit {POLICY['max_leverage_x']:.1f}x")
    if lq["interest_cover_x"] < POLICY["min_interest_cover_x"]:
        rules.append(f"Interest cover {lq['interest_cover_x']:.1f}x below policy floor {POLICY['min_interest_cover_x']:.1f}x")
    band = next(label for cut, label in BANDS if pd_ < cut)
    reasons = []
    if rules and band.startswith("APPROVE"):
        band, _ = "REFER to credit committee", reasons.append("policy breach overrides an approve recommendation")
    if abs(pd_ - pd_chal[k]) > POLICY["max_model_disagreement"] and band.startswith(("APPROVE", "DECLINE")):
        band, _ = "REFER to credit committee", reasons.append(
            f"decision model ({pd_:.1%}) and challenger ({pd_chal[k]:.1%}) disagree by more than "
            f"{POLICY['max_model_disagreement']:.0%} points")
    tone = "negative" if pd_ >= 0.10 else ("positive" if pd_ < 0.03 else "stable")
    return {"borrower_id": int(i), "sector": s["sector"], "p_repay": p_repay, "pd": pd_, "challenger_pd": float(pd_chal[k]),
            "main_risk": ans["main_risk"], "risk_grade": ans["risk_grade"], "recommendation": band,
            "policy_rules_triggered": rules, "override_reasons": reasons, "state": s,
            "llm_draft_narrative": gpt.generate(f"Outlook {tone}.")}

GRADES = QUESTIONS["risk_grade"]["criteria"]
def memo(a):
    lq, ch = a["state"]["latest_quarter"], a["state"]["change_over_4_quarters"]
    g = a["risk_grade"].get("score")
    grade = f"{g} — {GRADES[int(g) - 1]}" if isinstance(g, (int, float)) and 1 <= g <= len(GRADES) else json.dumps(a["risk_grade"])
    mr = a["main_risk"]
    L = [f"# Credit recommendation — Borrower {a['borrower_id']} ({a['sector']})", "",
         f"**Recommendation:** {a['recommendation']}  ",
         f"**Probability of repaying (decision model):** {a['p_repay']:.1%}  → PD {a['pd']:.1%}  ",
         f"**Challenger scorecard PD:** {a['challenger_pd']:.1%}  ",
         f"**Risk grade:** {grade}  ",
         f"**Main risk:** {mr.get('choice', mr)}" + (f" (p = {mr['probability']:.2f})" if "probability" in mr else ""), "",
         "**Status:** DRAFT — the credit committee makes the decision.", "",
         "## Key figures (source data — not generated by the LLM)", "",
         "| Ratio | Latest quarter | Change over 4 quarters |", "|---|---|---|",
         f"| Leverage (Debt/EBITDA) | {lq['leverage_x']:.1f}x | {ch['leverage_x']:+.1f}x |",
         f"| Interest cover | {lq['interest_cover_x']:.1f}x | {ch['interest_cover_x']:+.1f}x |",
         f"| Current ratio | {lq['current_ratio']:.2f} | {ch['current_ratio']:+.2f} |",
         f"| EBITDA margin | {lq['ebitda_margin']:.1%} | {ch['ebitda_margin']:+.1%} |", "",
         "## Policy checks", ""]
    L += [f"- BREACH: {r}" for r in a["policy_rules_triggered"]] or ["- No policy limits breached"]
    L += [f"- OVERRIDE: {r}" for r in a["override_reasons"]]
    L += ["", "## Analyst note (source)", "", f"> {a['state']['analyst_note']}", "",
          "## Draft narrative (tiny LLM — for RM review, contains no figures)", "", f"> {a['llm_draft_narrative']}", ""]
    return "\n".join(L)

order = np.argsort(pd_jev)
picks = [order[len(order) // 10], order[int(len(order) * 0.8)], order[-2]]
with open(os.path.join(OUT, "audit_log.jsonl"), "w") as log:
    for k in picks:
        i = idx_test[k]
        a = assess(i, k)
        md = memo(a)
        with open(os.path.join(OUT, f"memo_borrower_{i}.md"), "w") as fh:
            fh.write(md)
        log.write(json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "model_versions": VERSIONS,
                              "input_hash": sha(a["state"]), "jev_answers": jev_out[i]["answers"],
                              **{f: a[f] for f in ("borrower_id", "pd", "challenger_pd", "recommendation",
                                                   "policy_rules_triggered", "override_reasons")},
                              "human_decision": None, "decided_by": None}) + "\n")
        print("\n" + "=" * 78 + "\n" + md)

bands = np.array([next(l for c, l in BANDS if p < c) for p in pd_jev])
print("\n[PORTFOLIO VIEW] recommendation bands on the test set (before overrides):")
dist = {}
for _, b in BANDS:
    m = bands == b
    dist[b] = {"n": int(m.sum()), "realised_default_rate": float(y_test[m].mean()) if m.sum() else None}
    print(f"  {b:28s} {m.sum():5d} borrowers | realised default rate {y_test[m].mean() if m.sum() else float('nan'):.1%}")

json.dump({"decision_model": jev.name, "results": results, "calibration": calib, "bands": dist, "versions": VERSIONS},
          open(os.path.join(OUT, "metrics.json"), "w"), indent=2)
with open(os.path.join(OUT, "model_card.md"), "w") as fh:
    fh.write(f"# Model card — Jev + tiny LLM credit decision support (synthetic demo)\n\n"
             f"**Decision model used in this run:** {jev.name}\n\n"
             "**Purpose:** decision SUPPORT for corporate lending. The credit committee decides.\n\n"
             "## Components\n\n- Jev (System One): calibrated P(repay), main risk, risk grade — zero labels.\n"
             "- Challenger: logistic scorecard on ratios and 4-quarter changes, trained on labelled history.\n"
             "- Tiny GPT (System Two): drafts narrative only; no figures.\n- Deterministic policy rules and PD bands.\n\n"
             "## Hold-out validation\n\n| Model | AUC | Brier | Labels |\n|---|---|---|---|\n" +
             "".join(f"| {k} | {v['auc']:.3f} | {v['brier']:.4f} | {v['labels_used']} |\n" for k, v in results.items()) +
             "\n## Calibration (decision model)\n\n| PD bucket | n | Mean PD | Realised |\n|---|---|---|---|\n" +
             "".join(f"| {b} | {n_} | {mp:.1%} | {rr:.1%} |\n" for b, n_, mp, rr in calib) +
             "\n## Governance notes\n\n- Third-party model: vendor due diligence, version pinning, change notification (SS1/23 principle 4).\n"
             "- Client data leaves the bank when calling an external API: DPIA, data residency and contract terms first.\n"
             "- Calibration must be re-validated on the bank's own portfolio and monitored monthly.\n"
             "- EU AI Act: corporate borrowers are outside Annex III; creditworthiness of natural persons would be high-risk.\n"
             f"\n## Versions\n\n```\n{json.dumps(VERSIONS, indent=2)}\n```\n")
print(f"\nSaved memos, audit_log.jsonl, metrics.json and model_card.md to ./{OUT}/")
