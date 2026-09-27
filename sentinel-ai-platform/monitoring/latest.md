# Monitoring report - 2026-09-27 09:25:00

Audit chain intact: **True** (200 records)

## Alerts

- Input drift in requests 151-191: similarity to the reference set 0.52 (below 0.6); abstention 53.7%
- Abstention rose from 0.0% to 53.7% between the first and last window

## Quality and safety

| Measure | Value |
|---|---|
| Requests | 200 |
| Blocked | 9 (4.5%) |
| Abstention rate | 24.1% |
| Grounding failures | 0.0% |
| Requests with quarantined sources | 22 |
| Requests with PII redacted | 0 |

## Operations and cost

| Measure | Value |
|---|---|
| Latency p50 / p95 | 4.7 / 5.8 ms |
| Model mix | {'local-extractive': 191} |
| Cost by business line (GBP) | {'group': 0.0, 'corporate_banking': 0.0, 'capital_markets': 0.0} |

## Input drift by window

| Requests | Similarity to reference | Abstention |
|---|---|---|
| 1-50 | 1.0 | 0.0% |
| 51-100 | 0.947 | 6.0% |
| 101-150 | 0.615 | 42.0% |
| 151-191 | 0.52 | 53.7% |

## Most frequent unanswered questions (candidates for new policy content)

- (15x) Who approves a potential sanctions match before a payment is released?
- (11x) What sanctions screening is required before onboarding a shipping client?
- (11x) Which sanctions lists must be screened for a new counterparty?
- (9x) How often must existing clients be re-screened against sanctions lists?
