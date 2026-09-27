"""Monitoring and drift detection, computed from the audit log.

Four panels (quality, safety, operations, cost) plus input drift: are users now asking about
things the reference question set - and possibly the policy library - does not cover?

    python -m sentinel.monitoring [path/to/audit.jsonl]   -> monitoring/latest.md and latest.json
"""
import json, sys, time
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .audit import AuditLog
from .config import ROOT, STATE

ALERTS = {"abstention_rate": 0.35, "block_rate": 0.10, "grounding_failure_rate": 0.02, "drift_similarity_min": 0.60,
          "latency_p95_ms": 2000, "window_share_abstained_jump": 0.15}


def _pct(v):
    return f"{v:.1%}"


def analyse(records, reference_questions, window=50):
    req = [r for r in records if r["type"] in ("llm_request", "request_blocked")]
    llm = [r for r in req if r["type"] == "llm_request"]
    n = max(len(req), 1)
    lat = sorted(r["latency_ms"] for r in llm) or [0]
    cost = Counter()
    for r in llm:
        cost[r["business_line"]] += r.get("cost_gbp", 0)
    m = {"requests": len(req), "blocked": sum(r["type"] == "request_blocked" for r in req),
         "abstention_rate": sum(r["abstained"] for r in llm) / max(len(llm), 1),
         "block_rate": sum(r["type"] == "request_blocked" for r in req) / n,
         "grounding_failure_rate": sum(bool(r.get("invalid_citations")) for r in llm) / max(len(llm), 1),
         "quarantine_events": sum(bool(r.get("quarantined")) for r in llm),
         "pii_redactions": sum(bool(r.get("pii_redacted")) for r in req),
         "latency_p50_ms": lat[len(lat) // 2], "latency_p95_ms": lat[max(int(len(lat) * 0.95) - 1, 0)],
         "model_mix": dict(Counter(r["model"] for r in llm)), "cost_gbp_by_business_line": {k: round(v, 4) for k, v in cost.items()}}

    # input drift: similarity of recent questions to the reference set, per window
    qs = [r.get("question") or "" for r in llm]
    vec = TfidfVectorizer(stop_words="english").fit(reference_questions + qs)
    windows = []
    for i in range(0, len(llm), window):
        w = llm[i:i + window]
        X = vec.transform([r.get("question") or "" for r in w]).toarray()      # TF-IDF rows are L2-normalised
        R = vec.transform(reference_questions).toarray()
        best = [float((R @ x).max()) if x.any() else 0.0 for x in X]            # cosine to the closest reference question
        windows.append({"from": i + 1, "to": i + len(w), "mean_similarity_to_reference": round(float(np.mean(best)), 3),
                        "abstention_rate": round(sum(r["abstained"] for r in w) / len(w), 3)})
    gaps = Counter(r.get("question") for r in llm if r["abstained"] and r.get("question")).most_common(8)

    alerts = []
    if m["abstention_rate"] > ALERTS["abstention_rate"]:
        alerts.append(f"Abstention rate {_pct(m['abstention_rate'])} above {_pct(ALERTS['abstention_rate'])}: users ask about topics the policy library does not cover")
    if m["block_rate"] > ALERTS["block_rate"]:
        alerts.append(f"Block rate {_pct(m['block_rate'])} above {_pct(ALERTS['block_rate'])}: possible attack campaign or over-blocking")
    if m["grounding_failure_rate"] > ALERTS["grounding_failure_rate"]:
        alerts.append(f"Grounding failures {_pct(m['grounding_failure_rate'])}: model is citing clauses it was not given")
    if m["latency_p95_ms"] > ALERTS["latency_p95_ms"]:
        alerts.append(f"p95 latency {m['latency_p95_ms']} ms above {ALERTS['latency_p95_ms']} ms")
    for w in windows:
        if w["mean_similarity_to_reference"] < ALERTS["drift_similarity_min"]:
            alerts.append(f"Input drift in requests {w['from']}-{w['to']}: similarity to the reference set {w['mean_similarity_to_reference']} "
                          f"(below {ALERTS['drift_similarity_min']}); abstention {_pct(w['abstention_rate'])}")
    if len(windows) >= 2 and windows[-1]["abstention_rate"] - windows[0]["abstention_rate"] > ALERTS["window_share_abstained_jump"]:
        alerts.append(f"Abstention rose from {_pct(windows[0]['abstention_rate'])} to {_pct(windows[-1]['abstention_rate'])} between the first and last window")
    return {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "metrics": m, "windows": windows, "top_unanswered": gaps, "alerts": alerts}


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else STATE / "audit.jsonl"
    log = AuditLog(path)
    ok, n, broken = log.verify()
    refs = [json.loads(l)["question"] for l in (ROOT / "evals" / "golden_rag.jsonl").read_text().splitlines() if l.strip()]
    rep = analyse(log.records(), refs)
    rep["audit_chain"] = {"intact": ok, "records": n, "first_broken": broken}
    out = ROOT / "monitoring"; out.mkdir(exist_ok=True)
    (out / "latest.json").write_text(json.dumps(rep, indent=2))
    m = rep["metrics"]
    md = [f"# Monitoring report - {rep['generated']}", "", f"Audit chain intact: **{ok}** ({n} records)", "",
          "## Alerts", ""] + ([f"- {a}" for a in rep["alerts"]] or ["- None"]) + [
          "", "## Quality and safety", "", "| Measure | Value |", "|---|---|",
          f"| Requests | {m['requests']} |", f"| Blocked | {m['blocked']} ({_pct(m['block_rate'])}) |",
          f"| Abstention rate | {_pct(m['abstention_rate'])} |", f"| Grounding failures | {_pct(m['grounding_failure_rate'])} |",
          f"| Requests with quarantined sources | {m['quarantine_events']} |", f"| Requests with PII redacted | {m['pii_redactions']} |",
          "", "## Operations and cost", "", "| Measure | Value |", "|---|---|",
          f"| Latency p50 / p95 | {m['latency_p50_ms']} / {m['latency_p95_ms']} ms |", f"| Model mix | {m['model_mix']} |",
          f"| Cost by business line (GBP) | {m['cost_gbp_by_business_line']} |",
          "", "## Input drift by window", "", "| Requests | Similarity to reference | Abstention |", "|---|---|---|"] + [
          f"| {w['from']}-{w['to']} | {w['mean_similarity_to_reference']} | {_pct(w['abstention_rate'])} |" for w in rep["windows"]] + [
          "", "## Most frequent unanswered questions (candidates for new policy content)", ""] + [
          f"- ({c}x) {q}" for q, c in rep["top_unanswered"]]
    (out / "latest.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
