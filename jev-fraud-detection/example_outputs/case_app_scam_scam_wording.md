# Fraud case — transaction 23370

**Action:** BLOCK  
**Truth (synthetic label, unknown to the system):** app_scam

## Scores

| Signal | Value |
|---|---|
| Jev P(fraud) | 63.9% |
| Jev fraud type | authorised push payment scam |
| Challenger P(fraud) (trees + mini LLM) | 99.0% |
| Combined risk | 81.5% (STEP-UP ≥ 8.1%, HOLD ≥ 32.5%, BLOCK ≥ 73.5%) |
| Mini LLM surprise | 6.18 bits/char (rarer than every normal description sampled) |

## Transaction

| Field | Value |
|---|---|
| Amount | £842.28 |
| Channel | faster_payment |
| Description | SAFE ACCOUNT TRANSFER |
| Local time | 11:55 |

## Reason codes (deterministic)

- Payment 5 minutes after login
- Amount is 49x the customer's median (£17)
- First payment to this payee or merchant
- Payee account opened 46 days ago
- Description unlike normal payments (mini LLM surprise 6.2 bits/char, rarer than every normal description sampled)

## Overrides applied

- None

**Analyst decision:** _pending_
