# Jev + mini LLM: real-time fraud detection for banking transactions

This folder shows how to use **Jev**, TypeSafe AI's "System One" decision model, together with the **mini LLM** (the character-level GPT from `smbc-interview-prep/code/mini_gpt.py`) to catch fraudulent card payments and bank transfers. Each transaction ends in one of four actions: **ALLOW, STEP-UP, HOLD or BLOCK**.

A spam filter answers *"is this email spam?"* with a probability. Here, Jev answers *"is this transaction fraud or a scam?"* in the same way. The mini LLM adds something Jev's behavioural signals miss: it has read thousands of normal payment descriptions, so it notices when one looks nothing like normal banking text, such as *SAFE ACCOUNT TRANSFER*.

> **Synthetic data, educational code.** Not a production fraud system. Read [the plain-English guide](docs/fraud-guide.md) ([Word version](docs/Jev_Fraud_Detection_Guide.docx)) first.

![System flow](diagrams/fraud_flow.png)

## What is in this folder

| Path | What it is |
|---|---|
| `code/fraud_jev_llm.py` | The full pipeline: synthetic data → mini LLM → Jev → challenger → decision engine → case files and audit log |
| `code/jev_client.py` | Jev API client, plus a clearly labelled offline stand-in (**not Jev**) with the same response format |
| `code/make_figures.py` | Rebuilds the diagrams and charts in `diagrams/` from `example_outputs/` |
| `example_outputs/` | Results of the full run: six case files, `audit_log.jsonl`, `metrics.json`, `model_card.md`, `run_log.txt` |
| `docs/fraud-guide.md` | Plain-English guide with worked examples (also as a Word document) |
| `diagrams/` | Flow diagram, action ladder and result charts |

## How it works

1. **Transaction arrives** with its amount, channel (card present, card online, Faster Payment), description, device, login and payee details, compared with the customer's own normal behaviour.
2. **Jev (System One)** gets the transaction as JSON and answers two questions in one call:
   - `is_fraud` (noul): probability that the transaction is fraud or a scam
   - `fraud_type` (choice): card fraud, account takeover, authorised push payment (APP) scam, or genuine
3. **Mini LLM** is trained only on normal payment descriptions. It never writes anything. It scores how **surprising** each new description is, in bits per character.
4. **Challenger model:** gradient-boosted trees trained on labelled past cases, using behaviour plus the mini LLM surprise score.
5. **Decision engine:**
   - Combined risk is the average of Jev and the challenger.
   - Cut-offs are set so each action fits the team's capacity: STEP-UP 4% of traffic, HOLD 1.2%, BLOCK 0.4%.
   - **Overrides can only raise an action:** a payee on the mule-account list, the card-testing velocity rule, a very surprising description on a large payment to a new payee, or one model being very sure.
6. **Output:** the action, deterministic reason codes, a fixed customer message for STEP-UP (a scam warning for push payments), a case file for analysts, and an audit-log line with model versions and an empty field for the analyst's decision.

![Action ladder](diagrams/fraud_actions.png)

## Results of the full run

The run used 24,000 synthetic transactions with 1.4% fraud: card fraud, account takeover and APP scams. It was tested on 9,600 held-out transactions (144 frauds worth £92,391).

| Score | PR-AUC | Recall at 2% alerts |
|---|---|---|
| Offline stand-in for Jev (zero labels) | 0.61 | 62.5% |
| Challenger, behaviour only | 0.84 | 84.0% |
| **Challenger + mini LLM surprise** | **0.96** | **94.4%** |
| Ensemble (Jev stand-in + challenger) | 0.95 | 93.8% |
| Mini LLM surprise on its own | 0.36 | 36.8% |

A random score would have a PR-AUC of about 0.015 (the fraud rate).

| Design | Fraud lost | Customer friction | **Total cost** | Genuine customers interrupted |
|---|---|---|---|---|
| No controls | £92,391 | £0 | £92,391 | 0 |
| Rules only | £29,232 | £1,100 | £30,332 | 181 |
| Jev only | £13,836 | £474 | £14,311 | 287 |
| Challenger only (no LLM) | £15,872 | £302 | £16,174 | 284 |
| Challenger + mini LLM | £10,078 | £190 | £10,269 | 298 |
| **Full design** | **£7,884** | **£177** | **£8,061** | **260 (1 blocked)** |

**What this shows:**
- **On its own the mini LLM is a weak detector** (PR-AUC 0.36): most fraud uses ordinary-looking descriptions.
- **As one extra signal it's the biggest single improvement**, lifting the challenger's PR-AUC from 0.84 to 0.96. It is strongest on APP scams, whose descriptions average 4.1 bits/char against 1.0 for genuine payments.
- **The full design had the lowest total cost** and stopped 88% of card fraud, 99% of account takeovers and 82% of APP scams. It interrupted 260 genuine transactions (2.7%): 254 were simply asked to confirm in the app, 5 were held for an analyst and 1 was blocked. Of the 75 HOLDs, 70 were real fraud.
- **Some fraud still gets through.** `example_outputs/case_missed_fraud.md` is a fake-car-dealer purchase scam that looked exactly like a genuine purchase.

Stop rates and friction costs are assumptions, listed in `metrics.json`. Replace them with your own operations data.

## Run it

```bash
pip install torch scikit-learn numpy
cd code
export TYPESAFE_API_KEY=...          # calls the real Jev API (https://api.typesafe.ai/v1/systemone)
python fraud_jev_llm.py              # full run, about 1.5 minutes on a laptop CPU
python fraud_jev_llm.py --offline    # offline stand-in, no API key needed
python fraud_jev_llm.py --quick      # smaller run
```

Outputs go to `code/fraud_outputs/`. To rebuild the figures, copy that folder to `example_outputs/` and run `python code/make_figures.py` from this folder (it needs `cairosvg` and `matplotlib`).

## Important: the numbers above come from the offline stand-in, not Jev

The environment that built this could not reach `api.typesafe.ai`. Every "Jev" result above comes from `LocalFraudStandIn`, a hand-written rule model with Jev's response format. It is **not Jev**, and its results say nothing about Jev's real accuracy. Set `TYPESAFE_API_KEY` and re-run: the same validation, cost analysis and case files will then reflect the real model. Jev's public benchmark is spam detection, so its performance on fraud has to be proven on the bank's own data.

## Design choices worth defending in an interview

- **The LLM is a detector, not a writer.** The credit demo in `smbc-interview-prep` showed a tiny LLM inventing facts. Here, every customer message and reason code is a fixed template, and the LLM only produces a number.
- **Zero-label model, validated with labels.** Jev needs no training data, which helps with brand-new fraud patterns. Its probabilities are still checked against confirmed outcomes. The stand-in over-predicted fraud at the low end: 3.1% predicted against 0.1% actual.
- **Cut-offs sized to capacity.** Thresholds are set by how many STEP-UPs, HOLDs and BLOCKs the customers and analysts can absorb, not by an arbitrary 50% line.
- **Overrides only raise an action.** A model can never release a payment that the mule list or card-testing rule would stop.
- **Everything is auditable.** Each decision logs the input hash, model versions, Jev's answers, the challenger's score, the LLM surprise, overrides, reason codes and the analyst's final decision.

**Regulatory context:**
- **UK APP scams:** since 7 October 2024 UK payment firms must reimburse APP scam victims up to £85,000 per claim, with the cost shared between the sending and receiving firms. Stopping APP scams is therefore a direct cost saving as well as customer protection.
- **EU AI Act:** Annex III excludes AI systems used to detect financial fraud from the high-risk creditworthiness category. PRA SS1/23 model risk management and GDPR still apply.

## Sources

- [Jev introduces a new shape of LLM, Simon Willison](https://simonwillison.net/2026/Sep/21/jev/)
- [Jev: the System One model for fast, calibrated AI decisions](https://jevai.net/articles/what-is-system-one-jev/)
- [jev-test benchmark and API request format](https://github.com/pniessen/jev-test)
- [APP scams reimbursement dashboard, Payment Systems Regulator](https://www.psr.org.uk/information-for-consumers/app-scams-reimbursement-dashboard/)
- [PS25/5 APP scams reimbursement policy statement, PSR](https://www.psr.org.uk/media/rhelv4op/ps25-5-app-scams-reimbursement-consolidated-policy-statement-may-2025.pdf)
