"""Builds the model risk evidence pack (SS1/23) from what the platform actually produced:
the use-case register, pinned model configuration, latest evaluation report, monitoring report
and audit-chain status. Run in CI after the evaluation gate; attach to the validation file.

    python governance/build_evidence_pack.py   -> governance/evidence_pack.md
"""
import json, subprocess, sys, time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sentinel.config import MODELS, USE_CASES          # noqa: E402

register = yaml.safe_load((ROOT / "governance" / "use_case_register.yaml").read_text())["use_cases"]
ev_path = ROOT / "evals" / "reports" / "latest.json"
ev = json.loads(ev_path.read_text()) if ev_path.exists() else None
mon_path = ROOT / "monitoring" / "latest.json"
mon = json.loads(mon_path.read_text()) if mon_path.exists() else None
try:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "uncommitted"
except Exception:
    commit = "unknown"

L = ["# Model risk evidence pack", "",
     f"Generated {time.strftime('%Y-%m-%d %H:%M')} from commit `{commit}`. This file is produced automatically by CI; do not edit by hand.", "",
     "## 1. Identification and classification (SS1/23 principle 1)", "",
     "| Use case | Model risk tier | Platform tier | Business owner | Accountable SMF | EU AI Act |", "|---|---|---|---|---|---|"]
for u in register:
    L.append(f"| {u['id']} | {u.get('model_risk_tier', '-')} | {u.get('platform_risk_tier', '-')} | {u.get('business_owner', '-')} | "
             f"{u.get('smf_accountable', '-')} | {u.get('eu_ai_act', '-')} |")
L += ["", "## 2. System definition and change control (principle 3)", "",
      "Under GR-002 §1.1 the model is the whole system. Its versioned components:", "",
      "| Component | Value |", "|---|---|"]
for mid, m in MODELS.items():
    L.append(f"| Model `{mid}` | provider {m.provider}, version `{m.version}`, region {m.region}, approved up to {m.max_risk_tier} tier |")
for uid, u in USE_CASES.items():
    L.append(f"| Route `{uid}` | {' > '.join(u.route)} (tier {u.risk_tier}, budget £{u.daily_budget_gbp:.0f}/day, human review: {u.human_review}) |")
L += ["| Retrieval | Hybrid BM25 + TF-IDF vectors, reciprocal-rank fusion, entitlement pre-filter, top 5 |",
      "| Guardrails | Input guard, context quarantine, grounding check, abstention, PII redaction |", ""]
L += ["## 3. Validation evidence (principle 4)", ""]
if ev:
    L += [f"Latest evaluation: **{'PASSED' if ev['passed'] else 'FAILED'}** at {ev['generated']} "
          f"({ev['counts']['should_answer']} answerable and {ev['counts']['should_abstain']} must-refuse questions, "
          f"{ev['counts']['redteam']} red-team prompts, {ev['counts']['extraction_fields']} extraction fields).", "",
          "| Metric | Value | Threshold | Result |", "|---|---|---|---|"]
    L += [f"| {k} | {r['value']} | {'≤' if k.endswith('_max') else '≥'} {r['threshold']} | {'pass' if r['passed'] else 'FAIL'} |" for k, r in ev["metrics"].items()]
    L += ["", f"Guard in use: {ev['guard']}. Audit chain intact during evaluation: {ev['audit_chain_intact']}."]
else:
    L += ["No evaluation report found - run `python -m evals.run_evals`."]
L += ["", "**Limitations the validator should note:**",
      "- The golden set is small and was written alongside the system; Model Risk should add an independent set written by subject-matter experts.",
      "- Results are for the local extractive model. Each hosted model (Azure OpenAI, Gemini) must pass the same gate before it is enabled in a route.",
      "- The prompt-injection guard is a pattern-based stand-in unless the Jev API key is configured; novel attacks may evade patterns.", ""]
L += ["## 4. Ongoing monitoring (principle 4)", ""]
if mon:
    m = mon["metrics"]
    L += [f"Latest monitoring run {mon['generated']}: {m['requests']} requests, block rate {m['block_rate']:.1%}, "
          f"abstention {m['abstention_rate']:.1%}, grounding failures {m['grounding_failure_rate']:.1%}, p95 latency {m['latency_p95_ms']} ms.", "",
          "Alerts:"] + ([f"- {a}" for a in mon["alerts"]] or ["- None"])
else:
    L += ["No monitoring report found - run `python -m sentinel.monitoring`."]
L += ["", "## 5. Risk mitigants (principle 5)", "",
      "- Staff accountability and no solely automated decisions on individuals (GR-001 §2).",
      "- Human review queue for low-confidence CSA fields; human approval with segregation of duties for agent actions.",
      "- Fallback to a manual process if every model in a route is unavailable (the gateway returns an error; no silent degradation).",
      "", "Sign-off: Model owner ☐   Model Risk Management ☐   AI Engineering ☐"]
(ROOT / "governance" / "evidence_pack.md").write_text("\n".join(L) + "\n")
print("wrote governance/evidence_pack.md")
