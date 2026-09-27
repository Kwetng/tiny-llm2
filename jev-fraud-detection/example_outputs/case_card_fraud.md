# Fraud case — transaction 16918

**Action:** BLOCK  
**Truth (synthetic label, unknown to the system):** card_fraud

## Scores

| Signal | Value |
|---|---|
| Jev P(fraud) | 69.2% |
| Jev fraud type | card fraud (card not present) |
| Challenger P(fraud) (trees + mini LLM) | 89.4% |
| Combined risk | 79.3% (STEP-UP ≥ 8.1%, HOLD ≥ 32.5%, BLOCK ≥ 73.5%) |
| Mini LLM surprise | 0.34 bits/char (rarer than 1.7% of normal descriptions) |

## Transaction

| Field | Value |
|---|---|
| Amount | £64.40 |
| Channel | card_online |
| Description | ONE4ALL GIFT CARD |
| Local time | 21:24 |

## Reason codes (deterministic)

- New device for this customer
- First payment to this payee or merchant
- 7 transactions in the last hour
- Unusual time for this customer (21:24)

## Overrides applied

- None

**Analyst decision:** _pending_
