# Model card — Jev + mini LLM transaction fraud detection (synthetic demo)

**Decision model in this run:** LOCAL STAND-IN (not Jev) - set TYPESAFE_API_KEY to use the real model

**Purpose:** real-time screening of card and Faster Payments transactions; analysts review HOLDs and customers confirm STEP-UPs.

## Ranking power (test set)

| Score | PR-AUC | ROC-AUC | Recall at 2% alerts |
|---|---|---|---|
| Local stand-in (zero labels) | 0.611 | 0.965 | 62.5% |
| Challenger, no LLM | 0.839 | 0.996 | 84.0% |
| Challenger + mini LLM surprise | 0.960 | 0.999 | 94.4% |
| Ensemble (Jev + challenger) | 0.952 | 0.998 | 93.8% |
| Mini LLM surprise on its own | 0.363 | 0.779 | 36.8% |

## Business outcome (test set)

| Design | Fraud lost | Friction | Total | Genuine interrupted |
|---|---|---|---|---|
| No controls | £92,391 | £0 | £92,391 | 0 |
| Rules only | £29,232 | £1,100 | £30,332 | 181 |
| Jev only | £13,836 | £474 | £14,311 | 287 |
| Challenger only (no LLM) | £15,872 | £302 | £16,174 | 284 |
| Challenger + mini LLM | £10,078 | £190 | £10,269 | 298 |
| Full design: Jev + challenger + mini LLM + rules | £7,884 | £177 | £8,061 | 260 |

## Limitations

- Synthetic data; stop rates and friction costs are assumptions.
- The offline stand-in is not Jev; run with an API key to validate the real model.
- Fraud patterns shift: retrain the mini LLM and challenger regularly and monitor alert precision weekly.

## Versions

```
{
  "decision_model": "local-stand-in",
  "questions": "eb2fba19fcf6",
  "thresholds": "edd2f10cb404",
  "mini_llm": "bd4be8e4d883",
  "challenger": "0f1ecab8f5dd"
}
```
