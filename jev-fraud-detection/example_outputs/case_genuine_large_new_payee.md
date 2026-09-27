# Fraud case — transaction 12033

**Action:** HOLD  
**Truth (synthetic label, unknown to the system):** genuine

## Scores

| Signal | Value |
|---|---|
| Jev P(fraud) | 64.7% |
| Jev fraud type | account takeover |
| Challenger P(fraud) (trees + mini LLM) | 31.5% |
| Combined risk | 48.1% (STEP-UP ≥ 8.1%, HOLD ≥ 32.5%, BLOCK ≥ 73.5%) |
| Mini LLM surprise | 0.65 bits/char (rarer than 14.4% of normal descriptions) |

## Transaction

| Field | Value |
|---|---|
| Amount | £846.55 |
| Channel | faster_payment |
| Description | HOUSE DEPOSIT |
| Local time | 00:56 |

## Reason codes (deterministic)

- New device for this customer
- Payment 2 minutes after login
- Amount is 33x the customer's median (£26)
- First payment to this payee or merchant
- Unusual time for this customer (00:56)

## Overrides applied

- None

**Analyst decision:** _pending_
