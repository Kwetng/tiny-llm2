"""
panel_backtest.py - a panel of AI experts on Bitcoin, backtested walk-forward on real data.

Experts (each gives a weekly LONG / FLAT / SHORT call for the next 7 days):
  1. Random Forest            - from the quant research project (projectskf, "ml exercise.py")
  2. Tabular Transformer      - from the quant research project (projectskf, "ml nn transformer python file.py")
  3. Neuroplastic World Model - V5 predictive-latent ensemble (neuroplastic-financial-world-model), 6 seeds, 4-of-6 vote
  4. Jev (System One)         - TypeSafe AI decision model: P(price higher in 7 days) + market regime
                                (offline stand-in unless TYPESAFE_API_KEY is set)
  5. Mini LLM tape reader     - the character-level GPT from mini_gpt.py, trained on daily returns written as
                                letters; it "writes" 256 possible next weeks and counts how many end higher
  6. Panel chair (consensus)  - LONG or SHORT only if at least 3 of the 5 experts agree, otherwise FLAT

Data: Coin Metrics community data (CC BY-NC 4.0) - price, MVRV, active addresses, hash rate,
exchange flows - plus the CBOE VIX (datasets/finance-vix). Both are fetched from GitHub.

Method: weekly decisions (Sunday close to Sunday close). Every model is retrained each January on
all data before that year (expanding window) and used out of sample for that year, 2020 onwards.
Costs: 10 bp per unit of position change. No leverage.

Usage:
    pip install torch scikit-learn pandas numpy
    python panel_backtest.py            # writes ../outputs/panel_results.json and CSVs
    python panel_backtest.py --offline  # force the Jev stand-in

Research code on historical data - not investment advice.
"""
import json, math, os, random, sys, time, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from jev_market import get_jev

OFFLINE = "--offline" in sys.argv
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"; DATA.mkdir(exist_ok=True)
OUT = HERE.parent / "outputs"; OUT.mkdir(exist_ok=True)
SOURCES = {"btc.csv": "https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv",
           "vix.csv": "https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv"}
TEST_START = 2020
COST = 0.001            # 10 bp per unit of turnover
LONG_T, SHORT_T = 0.55, 0.45

def seedall(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)

# =============================================================================
# 1. DATA -> weekly "world state"
# =============================================================================
for f, url in SOURCES.items():
    if not (DATA / f).exists():
        print(f"downloading {f} ...")
        urllib.request.urlretrieve(url, DATA / f)

cm = pd.read_csv(DATA / "btc.csv", parse_dates=["time"], low_memory=False).set_index("time").sort_index()
cm = cm[["PriceUSD", "CapMVRVCur", "AdrActCnt", "HashRate", "FlowInExNtv", "FlowOutExNtv", "SplyCur"]].loc["2012-01-01":]
cm = cm.dropna(subset=["PriceUSD"])
vix = pd.read_csv(DATA / "vix.csv", parse_dates=["DATE"]).set_index("DATE")["CLOSE"]
day = cm.copy()
day["vix"] = vix.reindex(day.index).ffill()
day["r"] = np.log(day.PriceUSD).diff()
last_day = day.index.max()

wk = pd.DataFrame(index=pd.date_range(day.index.min() + pd.Timedelta(days=7), last_day, freq="W-SUN"))
P = day.PriceUSD
wk["price"] = P.reindex(wk.index)
lp = np.log(wk.price)
wk["ret_1w"] = lp.diff(1)
wk["mom_4w"] = lp.diff(4)
wk["mom_12w"] = lp.diff(12)
wk["mom_26w"] = lp.diff(26)
wk["vol_4w"] = day.r.rolling(28).std().reindex(wk.index) * math.sqrt(365)
wk["mvrv"] = day.CapMVRVCur.reindex(wk.index)
wk["dd_52w"] = wk.price / P.rolling(364).max().reindex(wk.index) - 1
a7 = day.AdrActCnt.rolling(7).mean(); h7 = day.HashRate.rolling(7).mean()
wk["addr_g"] = np.log(a7 / a7.shift(28)).reindex(wk.index)
wk["hash_g"] = np.log(h7 / h7.shift(28)).reindex(wk.index)
wk["netflow"] = ((day.FlowInExNtv - day.FlowOutExNtv) / day.SplyCur).rolling(28).sum().reindex(wk.index) * 1e4
wk["vix"] = day.vix.reindex(wk.index)
wk["vix_chg"] = wk.vix - day.vix.shift(28).reindex(wk.index)
wk["next_ret"] = lp.shift(-1) - lp                     # the thing every expert tries to call
FEATURES = ["ret_1w", "mom_4w", "mom_12w", "mom_26w", "vol_4w", "mvrv", "dd_52w", "addr_g", "hash_g", "netflow", "vix", "vix_chg"]
wk = wk.loc["2013-01-01":].dropna(subset=FEATURES)
live_date = wk.index.max()                              # last complete week: its outcome is not known yet
print(f"Weekly world: {len(wk)} weeks, {wk.index.min().date()} to {live_date.date()} (daily data to {last_day.date()})")

# =============================================================================
# 2. EXPERTS
# =============================================================================
class PositionalEncoding(nn.Module):              # as in projectskf
    def __init__(self, d_model, max_len=100):
        super().__init__()
        pe = torch.zeros(max_len, d_model); pos = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div); pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))
    def forward(self, x):
        return x + self.pe[:, :x.size(1), :]

class TabularTransformer(nn.Module):              # as in projectskf (each feature is a token)
    def __init__(self, input_dim, d_model=64, nhead=4, num_layers=2, num_classes=2):
        super().__init__()
        self.feature_embedding = nn.Linear(1, d_model)
        self.pos_encoder = PositionalEncoding(d_model, max_len=input_dim)
        layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, dim_feedforward=256, dropout=0.1,
                                           activation="gelu", batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
        self.classifier = nn.Sequential(nn.Linear(d_model * input_dim, 128), nn.ReLU(), nn.Dropout(0.3),
                                        nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, num_classes))
    def forward(self, x):
        b = x.size(0)
        x = self.transformer_encoder(self.pos_encoder(self.feature_embedding(x.unsqueeze(-1))))
        return self.classifier(x.reshape(b, -1))

def fit_transformer(Xtr, ytr, seed, epochs=60):
    seedall(seed)
    m = TabularTransformer(Xtr.shape[1], 32, 4, 2, 2)
    opt = torch.optim.AdamW(m.parameters(), lr=0.0005, weight_decay=1e-4)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    X, Y = torch.tensor(Xtr, dtype=torch.float32), torch.tensor(ytr, dtype=torch.long)
    for _ in range(epochs):                        # fixed epochs: no peeking at test data to pick the best epoch
        m.train()
        for idx in torch.randperm(len(X)).split(32):
            loss = F.cross_entropy(m(X[idx]), Y[idx])
            opt.zero_grad(); loss.backward(); opt.step()
        sch.step()
    m.eval()
    return m

class PredictiveWorldModel(nn.Module):            # as in neuroplastic_world_model_v5.py
    def __init__(self, input_dim, latent_dim=4):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(input_dim, 10), nn.Tanh(), nn.Linear(10, latent_dim))
        self.next_state = nn.Sequential(nn.Linear(latent_dim, 10), nn.Tanh(), nn.Linear(10, input_dim))
        self.next_ret = nn.Sequential(nn.Linear(latent_dim, 6), nn.Tanh(), nn.Linear(6, 1))
    def forward(self, x):
        z = self.encoder(x)
        return z, self.next_state(z), self.next_ret(z).squeeze(-1)

V5_SEEDS = [0, 1, 2, 3, 4, 42]
def v5_member(train, seed):
    seedall(seed)
    sc = StandardScaler().fit(train[FEATURES]); X = sc.transform(train[FEATURES])
    xt, xn = torch.tensor(X[:-1], dtype=torch.float32), torch.tensor(X[1:], dtype=torch.float32)
    yr = torch.tensor(train["ret_1w"].values[1:], dtype=torch.float32)
    m = PredictiveWorldModel(len(FEATURES), 4); opt = torch.optim.Adam(m.parameters(), lr=0.007)
    for _ in range(180):
        _, xh, rh = m(xt)
        loss = 0.30 * ((xh - xn) ** 2).mean() + 1.00 * ((rh - yr) ** 2).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    m.eval()
    with torch.no_grad():
        sigma = float(np.std((yr - m(xt)[2]).numpy()) + 1e-6)
    return sc, m, sigma

def v5_vote(members, row, date_seed):
    votes, preds = [], []
    for s in V5_SEEDS:
        sc, m, sigma = members[s]
        with torch.no_grad():
            mu = float(m(torch.tensor(sc.transform(pd.DataFrame([row[FEATURES].values], columns=FEATURES)), dtype=torch.float32))[2])
        sims = mu + np.random.default_rng(s + date_seed).normal(0, sigma, 300)
        mm, ss = sims.mean(), sims.std()
        u = {"BUY": mm - COST - 0.10 * ss, "SELL": -mm - COST - 0.10 * ss, "HOLD": 0.0}
        votes.append(max(u, key=u.get)); preds.append(mm)
    vc = {k: votes.count(k) for k in ("BUY", "SELL", "HOLD")}
    top = max(vc, key=vc.get)
    return (top if vc[top] >= 4 else "HOLD"), vc, float(np.mean(preds))

# ---- Mini LLM: the market's daily tape as text --------------------------------
LETTERS = "abcdefg"                               # a = big down day ... g = big up day
BLOCK, NE, NH, NL = 64, 64, 4, 3
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
        self.tok, self.pos = nn.Embedding(len(LETTERS), NE), nn.Embedding(BLOCK, NE)
        self.blocks = nn.Sequential(*[Block() for _ in range(NL)])
        self.ln_f, self.head = nn.LayerNorm(NE), nn.Linear(NE, len(LETTERS))
    def forward(self, idx):
        return self.head(self.ln_f(self.blocks(self.tok(idx) + self.pos(torch.arange(idx.size(1))))))

def fit_tape_llm(daily_r, seed=7, steps=700):
    seedall(seed)
    edges = np.quantile(daily_r, np.linspace(0, 1, len(LETTERS) + 1)[1:-1])
    sym = np.digitize(daily_r, edges)
    centre = np.array([daily_r[sym == k].mean() for k in range(len(LETTERS))])
    data = torch.tensor(sym, dtype=torch.long)
    g = MiniGPT(); opt = torch.optim.AdamW(g.parameters(), lr=2e-3, weight_decay=0.1)
    for _ in range(steps):
        ix = torch.randint(len(data) - BLOCK - 1, (32,))
        xb = torch.stack([data[i:i + BLOCK] for i in ix]); yb = torch.stack([data[i + 1:i + BLOCK + 1] for i in ix])
        loss = F.cross_entropy(g(xb).view(-1, len(LETTERS)), yb.view(-1))
        opt.zero_grad(); loss.backward(); opt.step()
    g.eval()
    return g, edges, centre

@torch.no_grad()
def tape_forecast(llm, recent_r, date_seed, n=256):
    g, edges, centre = llm
    ctx = torch.tensor(np.digitize(recent_r[-BLOCK:], edges), dtype=torch.long)
    torch.manual_seed(date_seed)
    idx = ctx.unsqueeze(0).repeat(n, 1)
    total = torch.zeros(n)
    for _ in range(7):                             # write 7 more days, 256 times
        nxt = torch.multinomial(F.softmax(g(idx[:, -BLOCK:])[:, -1], -1), 1)
        total += torch.tensor(centre, dtype=torch.float32)[nxt.squeeze(1)]
        idx = torch.cat([idx, nxt], 1)
    # surprise: how unusual the last 28 days were for the model (bits per day)
    seq = ctx.unsqueeze(0)
    nll = F.cross_entropy(g(seq[:, :-1])[0, -28:], seq[0, 1:][-28:])
    return float((total > 0).float().mean()), float(total.mean()), float(nll / math.log(2)), "".join(LETTERS[i] for i in ctx[-14:])

def jev_state(row):
    return {"asset": "Bitcoin (BTC/USD)", "as_of": str(row.name.date()),
            "snapshot": {"price_usd": round(float(row.price), 2), "return_1w": round(float(row.ret_1w), 4),
                         "return_4w": round(float(row.mom_4w), 4), "return_12w": round(float(row.mom_12w), 4),
                         "return_26w": round(float(row.mom_26w), 4), "volatility_4w": round(float(row.vol_4w), 3),
                         "mvrv": round(float(row.mvrv), 3), "drawdown_from_52w_high": round(float(row.dd_52w), 3),
                         "active_addresses_change_4w": round(float(row.addr_g), 4), "hash_rate_change_4w": round(float(row.hash_g), 4),
                         "exchange_net_inflow_bp_of_supply_4w": round(float(row.netflow), 2),
                         "vix": round(float(row.vix), 2), "vix_change_4w": round(float(row.vix_chg), 2)}}

def to_action(p):
    return 1 if p >= LONG_T else -1 if p <= SHORT_T else 0

# =============================================================================
# 3. WALK-FORWARD: retrain every January, predict that year's weeks
# =============================================================================
jev = get_jev(offline=OFFLINE)
print(f"Jev: {jev.name}")
EXPERTS = ["Random Forest", "Tabular Transformer", "Neuroplastic World Model", "Jev (System One)", "Mini LLM tape reader"]
rows = []
test = wk.loc[f"{TEST_START}-01-01":]
t_all = time.time()
for year in sorted(set(test.index.year)):
    t0 = time.time()
    train = wk[(wk.index < f"{year}-01-01") & wk.next_ret.notna()]
    tr = train.iloc[:-1]                              # drop the last week: its outcome falls in the new year
    sc = StandardScaler().fit(tr[FEATURES].values); Xtr = sc.transform(tr[FEATURES].values); ytr = (tr.next_ret > 0).astype(int).values
    rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=10, random_state=42, n_jobs=-1).fit(Xtr, ytr)
    tfs = [fit_transformer(Xtr, ytr, s) for s in (0, 1, 2)]
    v5 = {s: v5_member(train, s) for s in V5_SEEDS}
    llm = fit_tape_llm(day.r.loc["2013-01-01":f"{year - 1}-12-31"].dropna().values)
    imp = sorted(zip(FEATURES, rf.feature_importances_), key=lambda t: -t[1])[:3]
    for date, row in test[test.index.year == year].iterrows():
        x = sc.transform(row[FEATURES].values.reshape(1, -1).astype(float))
        p_rf = float(rf.predict_proba(x)[0, 1])
        with torch.no_grad():
            p_tf = float(np.mean([F.softmax(m(torch.tensor(x, dtype=torch.float32)), -1)[0, 1].item() for m in tfs]))
        v5_sig, vc, v5_mu = v5_vote(v5, row, int(date.strftime("%Y%m%d")))
        p_v5 = (vc["BUY"] + 0.5 * vc["HOLD"]) / 6
        ja = jev.ask(jev_state(row))["answers"]
        p_jev, regime = ja["up_next_week"]["noul"], ja["regime"]["choice"]
        recent = day.r.loc[:date].dropna().values
        p_llm, mu_llm, surprise, tape = tape_forecast(llm, recent, int(date.strftime("%Y%m%d")))
        acts = {"Random Forest": to_action(p_rf), "Tabular Transformer": to_action(p_tf),
                "Neuroplastic World Model": {"BUY": 1, "SELL": -1, "HOLD": 0}[v5_sig],
                "Jev (System One)": to_action(p_jev), "Mini LLM tape reader": to_action(p_llm)}
        n_long, n_short = sum(a == 1 for a in acts.values()), sum(a == -1 for a in acts.values())
        acts["Panel chair (consensus)"] = 1 if n_long >= 3 else -1 if n_short >= 3 else 0
        rows.append({"date": date, "price": row.price, "next_ret": row.next_ret,
                     "p": {"Random Forest": p_rf, "Tabular Transformer": p_tf, "Neuroplastic World Model": p_v5,
                           "Jev (System One)": p_jev, "Mini LLM tape reader": p_llm,
                           "Panel chair (consensus)": float(np.mean([p_rf, p_tf, p_v5, p_jev, p_llm]))},
                     "action": acts,
                     "detail": {"rf_top_features": [(f, round(float(v), 3)) for f, v in imp], "v5_votes": vc, "v5_pred": v5_mu,
                                "regime": regime, "llm_mean": mu_llm, "llm_surprise": surprise, "tape": tape,
                                "n_long": n_long, "n_short": n_short}})
    print(f"  {year}: trained on {len(tr)} weeks, predicted {sum(test.index.year == year)} weeks ({time.time() - t0:.0f}s)")
print(f"walk-forward done in {time.time() - t_all:.0f}s")

# =============================================================================
# 4. PERFORMANCE
# =============================================================================
NAMES = EXPERTS + ["Panel chair (consensus)"]
dates = [r["date"] for r in rows]
done = [r for r in rows if not pd.isna(r["next_ret"])]          # weeks whose outcome is known
simple = np.array([math.expm1(r["next_ret"]) for r in done])
series = {}
for n in NAMES + ["Buy & hold"]:
    a = np.array([1 if n == "Buy & hold" else r["action"][n] for r in done])
    turn = np.abs(np.diff(np.concatenate([[0], a])))
    series[n] = {"action": a, "ret": a * simple - COST * turn, "turn": turn}

def metrics(n):
    s = series[n]; r = s["ret"]; a = s["action"]
    eq = np.cumprod(1 + r)
    active = a != 0
    dir_ok = (np.sign(a) == np.sign(simple))[active]
    p = np.array([rr["p"][n] for rr in done]) if n != "Buy & hold" else None
    yrs = {}
    for y in sorted(set(d.year for d in dates[:len(done)])):
        m = np.array([d.year == y for d in dates[:len(done)]])
        yrs[str(y)] = float(np.prod(1 + r[m]) - 1)
    return {"total_return": float(eq[-1] - 1), "cagr": float(eq[-1] ** (52 / len(r)) - 1),
            "volatility": float(r.std(ddof=1) * math.sqrt(52)),
            "sharpe": float(r.mean() / r.std(ddof=1) * math.sqrt(52)) if r.std() > 0 else 0.0,
            "max_drawdown": float((eq / np.maximum.accumulate(eq) - 1).min()),
            "hit_rate": float(dir_ok.mean()) if active.any() else None,
            "time_long": float((a == 1).mean()), "time_short": float((a == -1).mean()), "time_flat": float((a == 0).mean()),
            "trades": int((s["turn"] > 0).sum()),
            "direction_accuracy": float(((p > 0.5) == (simple > 0)).mean()) if p is not None else float((simple > 0).mean()),
            "yearly": yrs, "equity": [float(v) for v in eq]}

perf = {n: metrics(n) for n in NAMES + ["Buy & hold"]}
agree = {a: {b: float(np.mean(series[a]["action"] == series[b]["action"])) for b in NAMES} for a in NAMES}

print(f"\nOut-of-sample {dates[0].date()} to {done[-1]['date'].date()} ({len(done)} weeks)")
print(f"  {'Expert':28s} {'Total':>9s} {'CAGR':>7s} {'Sharpe':>7s} {'MaxDD':>7s} {'Hit':>6s} {'Long':>5s} {'Short':>6s}")
for n, m in perf.items():
    print(f"  {n:28s} {m['total_return']:9.1%} {m['cagr']:7.1%} {m['sharpe']:7.2f} {m['max_drawdown']:7.1%} "
          f"{(m['hit_rate'] or 0):6.1%} {m['time_long']:5.0%} {m['time_short']:6.0%}")

# =============================================================================
# 5. LATEST CALL + RATIONALES (deterministic text)
# =============================================================================
last = rows[-1]; d = last["detail"]; LBL = {1: "LONG", 0: "FLAT", -1: "SHORT"}
why = {
    "Random Forest": f"Most important inputs: {', '.join(f for f, _ in d['rf_top_features'])}.",
    "Tabular Transformer": "Treats each of the 12 inputs as a token and attends across them; average of 3 seeds.",
    "Neuroplastic World Model": f"Votes {d['v5_votes']['BUY']} BUY / {d['v5_votes']['SELL']} SELL / {d['v5_votes']['HOLD']} HOLD "
                                f"(needs 4 of 6); predicted next-week return {d['v5_pred']:+.2%}.",
    "Jev (System One)": f"Regime: {d['regime']}.",
    "Mini LLM tape reader": f"Wrote 256 possible next weeks from the last 64 days; average {d['llm_mean']:+.2%}. "
                            f"Last 14 days as text: '{d['tape']}' (a = big down day, g = big up day); surprise {d['llm_surprise']:.2f} bits/day.",
    "Panel chair (consensus)": f"{d['n_long']} of 5 experts LONG, {d['n_short']} SHORT; needs 3 to act.",
}
latest = {n: {"action": LBL[last["action"][n]], "p_up": last["p"][n], "why": why[n]} for n in NAMES}
print(f"\nCall for the week after {last['date'].date()} (BTC ${last['price']:,.0f}):")
for n, v in latest.items():
    print(f"  {n:28s} {v['action']:5s} P(up) {v['p_up']:.0%}  {v['why']}")

result = {"generated": time.strftime("%Y-%m-%d"), "decision_model": jev.name, "asset": "Bitcoin (BTC/USD)",
          "data_to": str(last_day.date()), "live_week": str(last["date"].date()), "live_price": float(last["price"]),
          "test_start": str(dates[0].date()), "test_end": str(done[-1]["date"].date()), "weeks": len(done),
          "cost_bp": COST * 1e4, "thresholds": [SHORT_T, LONG_T], "experts": NAMES, "features": FEATURES,
          "dates": [str(r["date"].date()) for r in rows], "price": [float(r["price"]) for r in rows],
          "p": {n: [float(r["p"][n]) for r in rows] for n in NAMES},
          "action": {n: [int(r["action"][n]) for r in rows] for n in NAMES},
          "regime": [r["detail"]["regime"] for r in rows],
          "llm_surprise": [float(r["detail"]["llm_surprise"]) for r in rows],
          "perf": perf, "agreement": agree, "latest": latest,
          "sources": {"Coin Metrics community data (CC BY-NC 4.0)": SOURCES["btc.csv"],
                      "CBOE VIX via datasets/finance-vix": SOURCES["vix.csv"]}}
json.dump(result, open(OUT / "panel_results.json", "w"), indent=1, default=float)
pd.DataFrame({"date": result["dates"], "price": result["price"],
              **{f"{n} action": result["action"][n] for n in NAMES}, **{f"{n} P(up)": result["p"][n] for n in NAMES},
              "Jev regime": result["regime"]}).to_csv(OUT / "weekly_signals.csv", index=False)
pd.DataFrame({n: {k: v for k, v in m.items() if k not in ("equity", "yearly")} for n, m in perf.items()}).T.to_csv(OUT / "performance_summary.csv")
pd.DataFrame({n: m["yearly"] for n, m in perf.items()}).T.to_csv(OUT / "yearly_returns.csv")
wk[FEATURES + ["price", "next_ret"]].to_csv(OUT / "weekly_features.csv")
print(f"\nSaved panel_results.json, weekly_signals.csv, performance_summary.csv, yearly_returns.csv, weekly_features.csv to {OUT}")
