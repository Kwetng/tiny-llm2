"""
compare_credit.py - head-to-head: Jev vs Laya on the same credit decisions.

Both models get byte-identical states (borrower JSON) and byte-identical questions, on the
same 400 hold-out borrowers used in the Jev credit project. Only the model changes.

    pip install -r ../requirements.txt
    export TYPESAFE_API_KEY=...                    # for Jev
    python compare_credit.py --a jev --b laya      # the real comparison, on the 400 borrowers of the Jev project
    python compare_credit.py --a jev --b laya --extra-test 3600   # 4,000 test borrowers: needed to separate close models
    python compare_credit.py --a jev --b laya:typed-decisions
    python compare_credit.py --dry-run --quick     # plumbing test with two stand-ins (NOT a comparison)

What it measures, for each model:
  1. Ranking     AUC: does it put the borrowers who later default at the top?
  2. Calibration Brier score, expected calibration error (ECE), mean PD vs realised default rate.
                 Raw (as the vendor ships it) AND after a one-parameter recalibration fitted on the
                 600 labelled training borrowers (Platt scaling) - what a bank would actually deploy.
  3. Decisions   approve / refer / decline under the same policy engine; realised default rate per band;
                 how often each model is overruled by policy rules or by the challenger scorecard.
  4. Agreement   between the two models: PD rank correlation, same band, same main risk.
  5. Operations  latency p50 / p95 per borrower, tokens sent, where the data went.

Answers are cached in outputs/cache_<model>.jsonl, so a re-run does not call the API again.
DISCLAIMER: synthetic borrowers; educational code, not a production credit model.
"""
import argparse, hashlib, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score, roc_curve
from sklearn.preprocessing import StandardScaler
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from borrowers import Portfolio, QUESTIONS           # noqa: E402
import decision_models                               # noqa: E402

POLICY = {"max_leverage_x": 6.0, "min_interest_cover_x": 1.5, "max_model_disagreement": 0.10}
BANDS = [(0.03, "APPROVE"), (0.10, "REFER"), (1.01, "DECLINE")]
CAL_BINS = (0, .02, .05, .10, .20, 1.01)


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]


# ----------------------------------------------------------------------------- scoring
def score_all(model, pf, idx, cache_path, workers):
    cache = {}
    if os.path.exists(cache_path):
        for line in open(cache_path):
            rec = json.loads(line)
            if rec.get("questions") == sha(QUESTIONS):
                cache[rec["i"]] = rec["out"]
    todo = [int(i) for i in idx if int(i) not in cache]
    if todo:
        print(f"  {model.label}: scoring {len(todo)} borrowers ({len(idx) - len(todo)} cached)")
        t0 = time.time()
        with open(cache_path, "a") as fh:
            def one(i):
                return i, model.ask(pf.state(i), QUESTIONS)
            n_workers = workers if model.kind == "jev" else 1        # local model: one call at a time
            with ThreadPoolExecutor(max_workers=n_workers) as ex:
                for k, (i, out) in enumerate(ex.map(one, todo)):
                    cache[i] = out
                    fh.write(json.dumps({"i": i, "questions": sha(QUESTIONS), "out": out}) + "\n")
                    if (k + 1) % 100 == 0:
                        print(f"    {k + 1}/{len(todo)}  ({time.time() - t0:.0f}s)")
    return [cache[int(i)] for i in idx]


# ----------------------------------------------------------------------------- metrics
def ece(p, y, bins=10):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1)); edges[-1] += 1e-9
    tot = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi)
        if m.any():
            tot += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(tot)


def calib_table(p, y):
    rows = []
    for lo, hi in zip(CAL_BINS[:-1], CAL_BINS[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum():
            rows.append({"bucket": f"{lo:.0%}-{min(hi, 1):.0%}", "n": int(m.sum()),
                         "mean_pd": float(p[m].mean()), "realised": float(y[m].mean())})
    return rows


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


class Recalibrator:
    """Platt scaling on the model's own PD: PD' = sigmoid(a * logit(PD) + b), fitted on labelled history.
    Two numbers, so it cannot change the ranking (AUC) - only how the probabilities are scaled."""
    def fit(self, pd, y):
        self.lr = LogisticRegression(C=1e6, max_iter=1000).fit(logit(pd)[:, None], y)
        self.a, self.b = float(self.lr.coef_[0, 0]), float(self.lr.intercept_[0])
        return self

    def __call__(self, pd):
        return self.lr.predict_proba(logit(pd)[:, None])[:, 1]


def auc_diff_ci(y, pa, pb, n_boot=2000, seed=7):
    """Paired bootstrap: resample borrowers, recompute AUC(A) - AUC(B). Returns (diff, lo95, hi95)."""
    rng = np.random.default_rng(seed)
    diffs, n = [], len(y)
    for _ in range(n_boot):
        k = rng.integers(0, n, n)
        if y[k].min() == y[k].max():
            continue
        diffs.append(roc_auc_score(y[k], pa[k]) - roc_auc_score(y[k], pb[k]))
    return float(roc_auc_score(y, pa) - roc_auc_score(y, pb)), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def band(pd):
    return next(lbl for cut, lbl in BANDS if pd < cut)


def decide(state, pd, pd_chal):
    lq = state["latest_quarter"]
    rules, why = [], []
    if lq["leverage_x"] > POLICY["max_leverage_x"]:
        rules.append(f"leverage {lq['leverage_x']:.1f}x > {POLICY['max_leverage_x']:.1f}x")
    if lq["interest_cover_x"] < POLICY["min_interest_cover_x"]:
        rules.append(f"interest cover {lq['interest_cover_x']:.1f}x < {POLICY['min_interest_cover_x']:.1f}x")
    b = band(pd)
    if rules and b == "APPROVE":
        b = "REFER"; why.append("policy")
    if abs(pd - pd_chal) > POLICY["max_model_disagreement"] and b in ("APPROVE", "DECLINE"):
        b = "REFER"; why.append("challenger")
    return b, rules, why


def evaluate(name, outs, y, pd_train=None, y_train=None):
    pd = np.array([1 - o["p_repay"] for o in outs])
    lat = np.array([o["latency_ms"] for o in outs])
    r = {"model": name, "model_id": outs[0]["model_id"],
         "auc": float(roc_auc_score(y, pd)), "brier": float(brier_score_loss(y, pd)), "ece": ece(pd, y),
         "mean_pd": float(pd.mean()), "realised": float(y.mean()), "calibration": calib_table(pd, y),
         "latency_ms_p50": float(np.percentile(lat, 50)), "latency_ms_p95": float(np.percentile(lat, 95)),
         "grade_vs_pd_spearman": float(spearmanr([o["grade"] for o in outs], pd)[0]),
         "main_risk_counts": {k: int(v) for k, v in zip(*np.unique([str(o["main_risk"]) for o in outs], return_counts=True))}}
    pd_cal = None
    if pd_train is not None:
        rc = Recalibrator().fit(pd_train, y_train)
        pd_cal = rc(pd)
        r["recalibrated"] = {"a": rc.a, "b": rc.b, "brier": float(brier_score_loss(y, pd_cal)), "ece": ece(pd_cal, y),
                             "mean_pd": float(pd_cal.mean()), "calibration": calib_table(pd_cal, y)}
    return r, pd, pd_cal


# ----------------------------------------------------------------------------- figures
BLUE, ORANGE, GREY, INK, MUTED = "#2a78d6", "#eb6834", "#8a8984", "#0b0b0b", "#52514e"


def figures(out_dir, y, series, pd_chal, pd_true, lat):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#c9c8c3", "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb"})
    cols = [BLUE, ORANGE]
    names = list(series)

    # 1. reliability: raw and recalibrated side by side
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2), sharey=True)
    for ax, key, title in zip(axes, ("raw", "cal"), ("As shipped (raw)", "After recalibration on 600 labels")):
        ax.plot([0, .5], [0, .5], color="#c9c8c3", lw=1, ls="--")
        ax.text(.36, .40, "perfect", color=MUTED, fontsize=8, rotation=38)
        for c, n in zip(cols, names):
            p = series[n][key]
            if p is None:
                continue
            edges = np.quantile(p, np.linspace(0, 1, 9)); edges[-1] += 1e-9
            xs, ys = [], []
            for lo, hi in zip(edges[:-1], edges[1:]):
                m = (p >= lo) & (p < hi)
                if m.any():
                    xs.append(p[m].mean()); ys.append(y[m].mean())
            ax.plot(xs, ys, color=c, lw=2, marker="o", ms=5, label=n)
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_xlabel("predicted PD (octiles)"); ax.set_xlim(0, max(.5, ax.get_xlim()[1]))
        ax.grid(alpha=.25)
    axes[0].set_ylabel("realised default rate")
    axes[0].legend(frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, "calibration.png"), dpi=160); plt.close(fig)

    # 2. ROC
    fig, ax = plt.subplots(figsize=(5, 4.4))
    for c, n in zip(cols, names):
        f, t, _ = roc_curve(y, series[n]["raw"])
        ax.plot(f, t, color=c, lw=2, label=f"{n}  AUC {roc_auc_score(y, series[n]['raw']):.3f}")
    f, t, _ = roc_curve(y, pd_chal)
    ax.plot(f, t, color=GREY, lw=1.5, ls="--", label=f"Challenger scorecard  AUC {roc_auc_score(y, pd_chal):.3f}")
    f, t, _ = roc_curve(y, pd_true)
    ax.plot(f, t, color="#c9c8c3", lw=1.2, ls=":", label=f"Best possible  AUC {roc_auc_score(y, pd_true):.3f}")
    ax.plot([0, 1], [0, 1], color="#e4e3df", lw=1)
    ax.set_xlabel("false alarm rate (good borrowers flagged)"); ax.set_ylabel("defaulters caught")
    ax.legend(frameon=False, fontsize=8, loc="lower right"); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, "roc.png"), dpi=160); plt.close(fig)

    # 3. PD of A vs PD of B
    fig, ax = plt.subplots(figsize=(5, 4.6))
    a, b = series[names[0]]["raw"], series[names[1]]["raw"]
    ax.scatter(a[y == 0], b[y == 0], s=14, color=GREY, alpha=.45, label="repaid", edgecolors="none")
    ax.scatter(a[y == 1], b[y == 1], s=26, color=INK, marker="x", label="defaulted")
    hi = max(a.max(), b.max()) * 1.05
    ax.plot([0, hi], [0, hi], color="#c9c8c3", lw=1, ls="--")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel(f"PD from {names[0]}"); ax.set_ylabel(f"PD from {names[1]}")
    ax.legend(frameon=False, fontsize=8, loc="upper left"); ax.grid(alpha=.25, which="both")
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, "pd_agreement.png"), dpi=160); plt.close(fig)

    # 4. latency
    fig, ax = plt.subplots(figsize=(6, 2.6))
    for k, (c, n) in enumerate(zip(cols, names)):
        p50, p95 = np.percentile(lat[n], 50), np.percentile(lat[n], 95)
        ax.barh(k, p50, color=c, height=.5)
        ax.plot([p50, p95], [k, k], color=INK, lw=1.2); ax.plot([p95], [k], "|", color=INK, ms=10)
        ax.text(p95 * 1.04 + 1e-3, k, f"p50 {ms(p50)} · p95 {ms(p95)}", va="center", color=INK, fontsize=9)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names)
    ax.set_xlabel("time per borrower (3 questions, one call)"); ax.set_xlim(0, max(np.percentile(lat[n], 95) for n in names) * 1.9 + 1e-3)
    ax.grid(axis="x", alpha=.25)
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, "latency.png"), dpi=160); plt.close(fig)


# ----------------------------------------------------------------------------- report
def ms(v):
    return f"{v:,.0f} ms" if v >= 10 else f"{v:.2f} ms"


def report(M, names, agree, decisions_summary, meta):
    pct = lambda v: f"{v:.1%}"
    L = [f"# Jev vs Laya on credit decisions: results", ""]
    if meta["plumbing_test"]:
        L += ["> **PLUMBING TEST, NOT A MODEL COMPARISON.** At least one slot is the hand-written stand-in. "
              "These numbers only prove the harness runs end to end. Run with `--a jev --b laya` for the real comparison.", ""]
    L += [f"Run {meta['generated']} · {meta['n_test']} hold-out borrowers · {meta['n_train']} labelled borrowers used "
          f"for recalibration and the challenger · realised default rate {pct(meta['default_rate'])}", "",
          "## Headline", "", "| | " + " | ".join(names) + " | Challenger scorecard |", "|---|" + "---|" * (len(names) + 1)]
    ch = meta["challenger"]
    rows = [("Model version", [M[n]["model_id"] for n in names], "logistic, 12 features"),
            ("Labels used", ["0 (zero-shot)"] * len(names), str(meta["n_train"])),
            ("AUC (ranking; higher is better)", [f"{M[n]['auc']:.3f}" for n in names], f"{ch['auc']:.3f}"),
            ("Brier, raw (lower is better)", [f"{M[n]['brier']:.4f}" for n in names], f"{ch['brier']:.4f}"),
            ("Brier, recalibrated", [f"{M[n]['recalibrated']['brier']:.4f}" if 'recalibrated' in M[n] else "-" for n in names], "-"),
            ("ECE, raw (lower is better)", [f"{M[n]['ece']:.3f}" for n in names], f"{ch['ece']:.3f}"),
            ("ECE, recalibrated", [f"{M[n]['recalibrated']['ece']:.3f}" if 'recalibrated' in M[n] else "-" for n in names], "-"),
            ("Mean PD vs realised " + pct(meta['default_rate']), [pct(M[n]['mean_pd']) for n in names], pct(ch['mean_pd'])),
            ("Risk grade agrees with PD (Spearman)", [f"{M[n]['grade_vs_pd_spearman']:.2f}" for n in names], "-"),
            ("Latency per borrower, p50 / p95", [f"{ms(M[n]['latency_ms_p50'])} / {ms(M[n]['latency_ms_p95'])}" for n in names], "<1 ms"),
            ("Where the borrower data went", [meta["data_location"][n] for n in names], "in-house")]
    for lbl, vals, c in rows:
        L.append(f"| {lbl} | " + " | ".join(vals) + f" | {c} |")
    L += ["", f"Best possible AUC on this data (true synthetic PD): {meta['oracle_auc']:.3f}.", "",
          "## Is the ranking difference real?", "",
          f"AUC({names[0]}) - AUC({names[1]}) = **{agree['auc_diff'][0]:+.3f}**, 95% paired-bootstrap interval "
          f"**[{agree['auc_diff'][1]:+.3f}, {agree['auc_diff'][2]:+.3f}]** "
          f"({meta['n_defaults']} defaults in the test set). "
          + ("The interval includes zero, so on this data the two models **rank borrowers equally well**; "
             "the choice rests on calibration after recalibration, operations and governance."
             if agree['auc_diff'][1] <= 0 <= agree['auc_diff'][2] else
             f"The interval excludes zero, so **{names[0] if agree['auc_diff'][0] > 0 else names[1]} ranks borrowers better** on this data."), "",
          "## Agreement between the two models", "",
          f"- PD rank correlation (Spearman): **{agree['pd_spearman']:.2f}**",
          f"- Same approve / refer / decline band (before overrides): **{pct(agree['same_band'])}**",
          f"- Same main risk: **{pct(agree['same_main_risk'])}**",
          f"- Borrowers where the two PDs differ by more than 10 points: **{agree['big_disagreements']}**", "",
          "## Decisions under the same policy engine (recalibrated PD, after policy and challenger overrides)", "",
          "| Model | Approve | Refer | Decline | Default rate in Approve | Default rate in Decline | Overruled by challenger |",
          "|---|---|---|---|---|---|---|"]
    for n in names:
        d = decisions_summary[n]
        L.append(f"| {n} | {d['APPROVE']['n']} | {d['REFER']['n']} | {d['DECLINE']['n']} | "
                 f"{pct(d['APPROVE']['dr']) if d['APPROVE']['n'] else '-'} | {pct(d['DECLINE']['dr']) if d['DECLINE']['n'] else '-'} | "
                 f"{d['challenger_overrides']} |")
    L += ["", "## Calibration by PD bucket (raw)", ""]
    for n in names:
        L += [f"**{n}**", "", "| PD bucket | n | Mean PD | Realised |", "|---|---|---|---|"]
        L += [f"| {r['bucket']} | {r['n']} | {pct(r['mean_pd'])} | {pct(r['realised'])} |" for r in M[n]["calibration"]]
        if "recalibrated" in M[n]:
            rc = M[n]["recalibrated"]
            L += ["", f"Recalibration fitted on the {meta['n_train']} labelled borrowers: PD' = sigmoid({rc['a']:.2f} × logit(PD) {rc['b']:+.2f})."]
        L.append("")
    L += ["## Figures", "", "![Calibration](calibration.png)", "", "![ROC](roc.png)", "",
          "![PD agreement](pd_agreement.png)", "", "![Latency](latency.png)", ""]
    return "\n".join(L)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", default="jev"); ap.add_argument("--b", default="laya")
    ap.add_argument("--dry-run", action="store_true", help="two stand-ins; tests the harness only")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--extra-test", type=int, default=0, help="extra hold-out borrowers (3600 recommended)"); ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outputs"))
    args = ap.parse_args()
    if args.dry_run:
        args.a, args.b = "standin", "standin:0.8"
    out = os.path.abspath(args.out + ("/plumbing_test" if args.dry_run else "")); os.makedirs(out, exist_ok=True)

    pf = Portfolio(quick=args.quick, extra_test=args.extra_test)
    y_tr, y_te = pf.y[pf.idx_train], pf.y[pf.idx_test]
    print(f"Borrowers: {len(pf.idx_test)} test, {len(pf.idx_train)} labelled | test default rate {y_te.mean():.1%}")

    sc = StandardScaler().fit(pf.scorecard_features(pf.idx_train))
    chal = LogisticRegression(C=0.5, max_iter=2000).fit(sc.transform(pf.scorecard_features(pf.idx_train)), y_tr)
    pd_chal = chal.predict_proba(sc.transform(pf.scorecard_features(pf.idx_test)))[:, 1]

    models = [decision_models.build(args.a), decision_models.build(args.b)]
    names = [m.label.split(" (")[0] for m in models]
    M, series, lat, outs_test, data_loc = {}, {}, {}, {}, {}
    for m, n in zip(models, names):
        tag = m.kind + ("-" + m.checkpoint if m.kind == "laya" else "") + ("-" + n[-1] if m.kind == "stand-in" else "")
        o_tr = score_all(m, pf, pf.idx_train, os.path.join(out, f"cache_{tag}_train.jsonl"), args.workers)
        o_te = score_all(m, pf, pf.idx_test, os.path.join(out, f"cache_{tag}_test.jsonl"), args.workers)
        pd_tr = np.array([1 - o["p_repay"] for o in o_tr])
        M[n], pd_raw, pd_cal = evaluate(n, o_te, y_te, pd_tr, y_tr)
        M[n]["label"], M[n]["tokens_sent"] = m.label, m.input_tokens
        series[n] = {"raw": pd_raw, "cal": pd_cal}
        lat[n] = np.array([o["latency_ms"] for o in o_te]); outs_test[n] = o_te
        data_loc[n] = {"jev": "TypeSafe cloud API", "laya": "stays on this machine", "stand-in": "stays on this machine"}[m.kind]

    a, b = names
    ba = np.array([band(p) for p in series[a]["cal"]]); bb = np.array([band(p) for p in series[b]["cal"]])
    agree = {"pd_spearman": float(spearmanr(series[a]["raw"], series[b]["raw"])[0]),
             "same_band": float((ba == bb).mean()),
             "same_main_risk": float(np.mean([x["main_risk"] == z["main_risk"] for x, z in zip(outs_test[a], outs_test[b])])),
             "big_disagreements": int((np.abs(series[a]["cal"] - series[b]["cal"]) > 0.10).sum()),
             "auc_diff": auc_diff_ci(y_te, series[a]["raw"], series[b]["raw"])}

    dec_summary, rows = {}, []
    for n in names:
        d = {k: {"n": 0, "defaults": 0} for _, k in BANDS}; d["challenger_overrides"] = 0; d["policy_overrides"] = 0
        for k, i in enumerate(pf.idx_test):
            st = pf.state(int(i))
            bnd, rules, why = decide(st, series[n]["cal"][k], pd_chal[k])
            d[bnd]["n"] += 1; d[bnd]["defaults"] += int(y_te[k])
            d["challenger_overrides"] += "challenger" in why; d["policy_overrides"] += "policy" in why
            rows.append({"model": n, "borrower_id": int(i), "pd_raw": round(float(series[n]["raw"][k]), 4),
                         "pd_recalibrated": round(float(series[n]["cal"][k]), 4), "challenger_pd": round(float(pd_chal[k]), 4),
                         "main_risk": outs_test[n][k]["main_risk"], "grade": outs_test[n][k]["grade"],
                         "recommendation": bnd, "policy_rules": rules, "overrides": why, "defaulted": int(y_te[k])})
        for _, k in BANDS:
            d[k]["dr"] = d[k]["defaults"] / d[k]["n"] if d[k]["n"] else None
        dec_summary[n] = d

    meta = {"generated": time.strftime("%Y-%m-%d %H:%M"), "n_test": len(pf.idx_test), "n_train": len(pf.idx_train),
            "default_rate": float(y_te.mean()), "n_defaults": int(y_te.sum()), "oracle_auc": float(roc_auc_score(y_te, pf.pd_true[pf.idx_test])),
            "plumbing_test": any(m.kind == "stand-in" for m in models), "data_location": data_loc,
            "challenger": {"auc": float(roc_auc_score(y_te, pd_chal)), "brier": float(brier_score_loss(y_te, pd_chal)),
                           "ece": ece(pd_chal, y_te), "mean_pd": float(pd_chal.mean())},
            "versions": {"questions": sha(QUESTIONS), "policy": sha(POLICY), "models": {n: M[n]["model_id"] for n in names}}}

    figures(out, y_te, series, pd_chal, pf.pd_true[pf.idx_test], lat)
    with open(os.path.join(out, "decisions.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps({**r, "human_decision": None}) + "\n")
    json.dump({"meta": meta, "models": M, "agreement": agree, "decisions": dec_summary},
              open(os.path.join(out, "metrics.json"), "w"), indent=2, default=float)
    md = report(M, names, agree, dec_summary, meta)
    open(os.path.join(out, "comparison_report.md"), "w").write(md)
    print("\n" + md.split("## Calibration by PD bucket")[0])
    print(f"Saved report, metrics, decisions and figures to {out}")


if __name__ == "__main__":
    main()
