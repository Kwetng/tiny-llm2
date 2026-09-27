# Model risk evidence pack

Generated 2026-09-27 09:11 from commit `d3fdc86`. This file is produced automatically by CI; do not edit by hand.

## 1. Identification and classification (SS1/23 principle 1)

| Use case | Model risk tier | Platform tier | Business owner | Accountable SMF | EU AI Act |
|---|---|---|---|---|---|
| policy_qa | 2 | medium | Head of Credit Risk Policy | SMF4 Chief Risk Officer | Not high-risk (internal information retrieval); Article 50 transparency applies (users are told they are using AI) |
| csa_extraction | 1 | high | Head of Collateral Operations | SMF24 Chief Operations Officer | Not high-risk |
| ops_agent | 1 | high | COO, Corporate Banking | SMF24 Chief Operations Officer | Not high-risk |
| retail_credit_scoring | 1 | not permitted without exception | n/a | - | HIGH-RISK (Annex III 5(b)) - conformity assessment, human oversight, logging, data governance required |

## 2. System definition and change control (principle 3)

Under GR-002 §1.1 the model is the whole system. Its versioned components:

| Component | Value |
|---|---|
| Model `local-extractive` | provider local, version `1.0.0`, region on-premises, approved up to high tier |
| Model `azure-openai-chat` | provider azure_openai, version `pinned-by-deployment`, region uksouth, approved up to medium tier |
| Model `vertex-gemini` | provider vertex, version `pinned-by-model-id`, region europe-west2, approved up to medium tier |
| Route `policy_qa` | azure-openai-chat > vertex-gemini > local-extractive (tier medium, budget £50/day, human review: False) |
| Route `csa_extraction` | local-extractive (tier high, budget £20/day, human review: True) |
| Route `ops_agent` | local-extractive (tier high, budget £10/day, human review: True) |
| Retrieval | Hybrid BM25 + TF-IDF vectors, reciprocal-rank fusion, entitlement pre-filter, top 5 |
| Guardrails | Input guard, context quarantine, grounding check, abstention, PII redaction |

## 3. Validation evidence (principle 4)

Latest evaluation: **PASSED** at 2026-09-27 09:11:07 (21 answerable and 8 must-refuse questions, 12 red-team prompts, 18 extraction fields).

| Metric | Value | Threshold | Result |
|---|---|---|---|
| retrieval_recall_at_5 | 1.0 | ≥ 0.9 | pass |
| answer_correctness | 1.0 | ≥ 0.85 | pass |
| citation_precision | 1.0 | ≥ 0.95 | pass |
| faithfulness | 1.0 | ≥ 0.9 | pass |
| abstention_accuracy | 1.0 | ≥ 0.95 | pass |
| false_abstention_rate_max | 0.0 | ≤ 0.1 | pass |
| entitlement_leaks_max | 0 | ≤ 0 | pass |
| attack_block_rate | 1.0 | ≥ 0.9 | pass |
| indirect_injection_quarantine | 1.0 | ≥ 1.0 | pass |
| pii_in_audit_log_max | 0 | ≤ 0 | pass |
| extraction_field_accuracy | 1.0 | ≥ 0.95 | pass |
| extraction_routing_accuracy | 1.0 | ≥ 1.0 | pass |

Guard in use: local pattern guard (stand-in, not Jev). Audit chain intact during evaluation: True.

**Limitations the validator should note:**
- The golden set is small and was written alongside the system; Model Risk should add an independent set written by subject-matter experts.
- Results are for the local extractive model. Each hosted model (Azure OpenAI, Gemini) must pass the same gate before it is enabled in a route.
- The prompt-injection guard is a pattern-based stand-in unless the Jev API key is configured; novel attacks may evade patterns.

## 4. Ongoing monitoring (principle 4)

Latest monitoring run 2026-09-27 09:07:09: 200 requests, block rate 4.5%, abstention 24.1%, grounding failures 0.0%, p95 latency 5.9 ms.

Alerts:
- Input drift in requests 151-191: similarity to the reference set 0.52 (below 0.6); abstention 53.7%
- Abstention rose from 0.0% to 53.7% between the first and last window

## 5. Risk mitigants (principle 5)

- Staff accountability and no solely automated decisions on individuals (GR-001 §2).
- Human review queue for low-confidence CSA fields; human approval with segregation of duties for agent actions.
- Fallback to a manual process if every model in a route is unavailable (the gateway returns an error; no silent degradation).

Sign-off: Model owner ☐   Model Risk Management ☐   AI Engineering ☐
