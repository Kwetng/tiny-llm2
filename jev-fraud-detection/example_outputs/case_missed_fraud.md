# Fraud case — transaction 6040

**Action:** ALLOW  
**Truth (synthetic label, unknown to the system):** app_scam

## Scores

| Signal | Value |
|---|---|
| Jev P(fraud) | 12.2% |
| Jev fraud type | genuine |
| Challenger P(fraud) (trees + mini LLM) | 2.6% |
| Combined risk | 7.4% (STEP-UP ≥ 8.1%, HOLD ≥ 32.5%, BLOCK ≥ 73.5%) |
| Mini LLM surprise | 0.48 bits/char (rarer than 8.4% of normal descriptions) |

## Transaction

| Field | Value |
|---|---|
| Amount | £1,359.03 |
| Channel | faster_payment |
| Description | CAR PURCHASE DEALER |
| Local time | 12:53 |

## Reason codes (deterministic)

- Amount is 30x the customer's median (£46)
- First payment to this payee or merchant

## Overrides applied

- None

**Analyst decision:** _pending_
