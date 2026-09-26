# SMBC Head of AI Engineering — Interview Preparation

Preparation pack and supporting code for the Head of AI Engineering role (ITSD, SMBC Group EMEA).

## Contents

| Path | What it is |
|---|---|
| `docs/interview-prep.md` | The full six-level prep programme in Markdown (Foundations → Expert), including the LLM history and the build-an-LLM guide |
| `docs/SMBC_AI_Engineering_Interview_Prep.docx` | The same content as a formatted Word document with diagrams |
| `diagrams/` | LLM evolution flowchart, bank AI platform architecture, credit memo copilot architecture |
| `code/mini_gpt.py` | A complete GPT-style language model built from scratch in PyTorch (~170 lines) |
| `code/credit_jev_llm.py` | Credit decision support: Jev (calibrated ability-to-repay probability) + the tiny LLM (memo narrative) + policy rules, validation and audit log |
| `code/jev_client.py` | Minimal client for the Jev API, plus a clearly labelled offline stand-in |
| `code/diagrams.py` | Regenerates the three diagrams as PNGs |
| `code/build_docx.js` | Converts the Markdown pack into the Word document |

## mini_gpt.py — a GPT from scratch

A decoder-only Transformer with every stage labelled in the code:

1. **Data** — built-in finance corpus, or any text file you pass in
2. **Tokeniser** — character-level (production models use BPE)
3. **Training objective** — next-token prediction (targets are inputs shifted by one)
4. **Architecture** — token and positional embeddings, causal multi-head self-attention, feed-forward layers, residual connections and LayerNorm
5. **Training loop** — forward → cross-entropy loss → backprop → AdamW update
6. **Evaluation** — train vs held-out validation loss
7. **Inference** — autoregressive generation with temperature and top-k sampling

```bash
pip install torch
python code/mini_gpt.py                   # built-in finance text
python code/mini_gpt.py my_text.txt       # your own corpus
python code/mini_gpt.py my_text.txt 5000  # train for 5,000 steps
```

Tested on CPU: 0.81M parameters, about 2.5 minutes for 1,500 steps. Loss falls from 3.75 to 0.08, and output goes from random characters to sentences such as "The bank manages credit risk by…".

Note: the sample corpus repeats, so validation loss tracks training loss closely. That is memorisation, not generalisation — a small illustration of why real pipelines de-duplicate data before splitting.

## credit_jev_llm.py — Jev + tiny LLM for credit decisions

Jev is TypeSafe AI's "System One" decision model: it reads a text or JSON state and returns calibrated numbers rather than text. The same kind of question that scores a message as spam or not can score a borrower's ability to repay.

```
borrower JSON ──► Jev (System One) ──► P(repay), main risk, risk grade
                                          │
          challenger scorecard ──────────►├──► policy rules + PD bands ──► RECOMMENDATION
                                          │                                 (committee decides)
          tiny GPT (System Two) ─────────►└──► memo narrative (no figures)  + audit log
```

1. **Borrower state (JSON):** latest ratios, 4-quarter changes, 8-quarter leverage history, facility terms and the analyst note.
2. **Jev, one call per borrower, three typed questions:**
   - `can_repay` (noul): probability the borrower meets every payment over 12 months, so PD = 1 − P(repay)
   - `main_risk` (choice): leverage, liquidity, profitability, business outlook, or none material
   - `risk_grade` (score): 1 (strong) to 5 (very weak)
3. **Validation on our own data:** AUC, Brier score and a calibration table against realised defaults, compared with a conventional challenger scorecard trained on 600 labelled borrowers. Vendor calibration claims are tested, not assumed.
4. **Decision engine:** deterministic policy limits (leverage above 6.0x, interest cover below 1.5x), PD bands (below 3% approve, 3–10% refer, above 10% decline), and a challenger check. A breach, or a disagreement of more than 10 points with the challenger, forces REFER.
5. **Tiny LLM:** the GPT from `mini_gpt.py`, pre-trained on analyst notes, drafts the memo narrative. All figures come from source data, never from the LLM.
6. **Outputs in `credit_outputs/`:** example credit memos, `audit_log.jsonl` (inputs hash, model versions, Jev answers, recommendation, and an empty human-decision field), `metrics.json` and `model_card.md`.

```bash
pip install torch scikit-learn numpy
export TYPESAFE_API_KEY=...        # calls the real Jev API (https://api.typesafe.ai/v1/systemone)
cd code && python credit_jev_llm.py
python credit_jev_llm.py --offline # local stand-in, no API key needed
```

**About the offline stand-in:** without an API key, `jev_client.py` falls back to `LocalJevStandIn`. It is **not Jev**: it's a hand-written rule with the same response format, so the pipeline runs anywhere. In the test run it ranked borrowers about as well as the trained challenger (AUC 0.665 vs 0.673) but over-predicted PD at the high end (mean PD 39% where 6.7% actually defaulted). That's exactly what the validation step is there to catch, and why any model — Jev included — must be calibration-tested on the bank's own portfolio before use.

**Governance notes:** Jev is a third-party API, so sending client data to it needs vendor due diligence, a DPIA, data-residency checks and model-risk approval (PRA SS1/23). Corporate lending is outside EU AI Act Annex III, but a version scoring individuals would be high-risk. Synthetic data only: this is not a production credit model.

## Rebuilding the diagrams and the Word document

```bash
pip install cairosvg
python code/diagrams.py                   # writes diagram_*.png
npm install docx
node code/build_docx.js docs/interview-prep.md out.docx
```

Run the builder from a folder where the diagram PNGs referenced in the Markdown can be found.
