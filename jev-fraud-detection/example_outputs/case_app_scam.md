# Fraud case — transaction 11935

**Action:** STEP-UP  
**Truth (synthetic label, unknown to the system):** app_scam

## Scores

| Signal | Value |
|---|---|
| Jev P(fraud) | 15.8% |
| Jev fraud type | genuine |
| Challenger P(fraud) (trees + mini LLM) | 32.8% |
| Combined risk | 24.3% (STEP-UP ≥ 8.1%, HOLD ≥ 32.5%, BLOCK ≥ 73.5%) |
| Mini LLM surprise | 0.44 bits/char (rarer than 4.4% of normal descriptions) |

## Transaction

| Field | Value |
|---|---|
| Amount | £248.87 |
| Channel | faster_payment |
| Description | HOLIDAY VILLA BOOKING |
| Local time | 14:44 |

## Reason codes (deterministic)

- Amount is 17x the customer's median (£14)
- First payment to this payee or merchant
- Payee account opened 17 days ago

## Overrides applied

- None

## Message shown to the customer (fixed template)

> Stop - this could be a scam. Your bank, HMRC and the police will never ask you to move money to a 'safe account' or pay a fee to release funds. If someone is telling you what to do, hang up and call us on the number on your card.

**Analyst decision:** _pending_
