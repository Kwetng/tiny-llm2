# Fraud case — transaction 11053

**Action:** BLOCK  
**Truth (synthetic label, unknown to the system):** account_takeover

## Scores

| Signal | Value |
|---|---|
| Jev P(fraud) | 87.7% |
| Jev fraud type | account takeover |
| Challenger P(fraud) (trees + mini LLM) | 99.3% |
| Combined risk | 93.5% (STEP-UP ≥ 8.1%, HOLD ≥ 32.5%, BLOCK ≥ 73.5%) |
| Mini LLM surprise | 1.65 bits/char (rarer than 88.2% of normal descriptions) |

## Transaction

| Field | Value |
|---|---|
| Amount | £750.28 |
| Channel | faster_payment |
| Description | DRINKS LATE |
| Local time | 22:30 |

## Reason codes (deterministic)

- New device for this customer
- Password reset in the last 24 hours
- Payment 5 minutes after login
- Amount is 20x the customer's median (£37)
- First payment to this payee or merchant
- Payee account opened 32 days ago
- Merchant or payee abroad

## Overrides applied

- None

**Analyst decision:** _pending_
