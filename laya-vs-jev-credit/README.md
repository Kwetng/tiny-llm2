# Laya vs Jev: credit decisions, head to head

**Jev** (TypeSafe AI) and **Laya** (Convai Innovations) are both "System One" decision models. They read a state and return calibrated probabilities for typed questions, without generating text.

| | Jev | Laya |
|---|---|---|
| Model | Closed | Open source, Apache 2.0 |
| Where it runs | Cloud API | On your own machine |
| Borrower data | Leaves the bank | Stays in-house |

This project runs both on **the same credit decisions**. It uses the same synthetic borrowers as [`jev-credit-decisions`](../jev-credit-decisions/), byte-identical questions, and the same policy engine and challenger scorecard. It then compares them on:

- ranking
- calibration (raw and after recalibration on 600 labelled borrowers)
- approve / refer / decline outcomes
- agreement
- speed
- where the data goes

> Read the **[plain-English guide](docs/laya-vs-jev-guide.md)** ([Word version](docs/Laya_vs_Jev_Credit_Guide.docx)) first.

![The harness](docs/img/harness.png)

## Status

The harness is built and tested. **The head-to-head numbers are not in the repository yet.** The Jev API needs a paid key, and Laya's weights come from Hugging Face; neither was reachable from the build environment, and no results have been invented. Run the commands below on any machine with internet access. `build_guide.py` then writes the real results into the guide.

## Run it

```bash
pip install -r requirements.txt
export TYPESAFE_API_KEY=...                                        # Jev
python code/compare_credit.py --a jev --b laya --extra-test 3600   # 4,000 test borrowers
python code/build_guide.py                                          # results into the guide + Word
```

| Option | What it does |
|---|---|
| `--b laya:typed-decisions` | Laya's checkpoint fine-tuned for business decisions |
| `--a laya --b laya:typed-decisions` | Two Laya checkpoints, no API key needed |
| `--dry-run --quick` | Plumbing test with two labelled stand-ins; not a comparison |
| `LAYA_THREADS=8` | On CPU, set to your physical core count (much faster) |

Answers are cached in `outputs/`, so a re-run never pays for the same API call twice.

## What it reports (`outputs/comparison_report.md`)

- **AUC with a paired-bootstrap 95% interval for the Jev − Laya gap.** The original 400 test borrowers contain only 17 defaults, too few to separate two good models; `--extra-test 3600` gives 176.
- **Brier score and ECE**, raw and after Platt recalibration, plus a calibration table by PD bucket.
- **Decision outcomes:** approve / refer / decline counts, the default rate in each band, and how often the challenger overrules each model.
- **Agreement:** PD rank correlation, same band, same main risk.
- **Operations:** latency p50 / p95, and where the data went.
- **`decisions.jsonl`:** one auditable record per borrower per model, with an empty `human_decision` field.

The guide sets the **decision rules in advance** (section 7): which model becomes champion depending on what the results show.

## Files

| File | Purpose |
|---|---|
| `code/borrowers.py` | Borrower generator and questions (identical to the Jev project) |
| `code/decision_models.py` | Adapters for Jev (HTTPS API), Laya (`laya.Router`, local) and the stand-in, all normalised to one answer format. Laya's score answers are 0-based and are converted |
| `code/compare_credit.py` | The comparison: scoring, recalibration, policy engine, metrics, bootstrap, figures, report |
| `code/build_guide.py` | Puts the results into the guide and rebuilds the Word file |
| `tests/test_harness.py` | 5 tests; one runs a borrower through the real Laya router with only the weights faked |

Synthetic data; educational code, not a production credit model.
