# Model card — Jev + tiny LLM credit decision support (synthetic demo)

**Decision model used in this run:** LOCAL STAND-IN (not Jev) - set TYPESAFE_API_KEY to use the real model

**Purpose:** decision SUPPORT for corporate lending. The credit committee decides.

## Components

- Jev (System One): calibrated P(repay), main risk, risk grade — zero labels.
- Challenger: logistic scorecard on ratios and 4-quarter changes, trained on labelled history.
- Tiny GPT (System Two): drafts narrative only; no figures.
- Deterministic policy rules and PD bands.

## Hold-out validation

| Model | AUC | Brier | Labels |
|---|---|---|---|
| Local stand-in (zero labels) | 0.665 | 0.0751 | 0 |
| Challenger scorecard (600 labels) | 0.673 | 0.0428 | 600 |
| Oracle (true synthetic PD) | 0.731 | 0.0399 | None |

## Calibration (decision model)

| PD bucket | n | Mean PD | Realised |
|---|---|---|---|
| 0%-2% | 111 | 0.9% | 0.9% |
| 2%-5% | 67 | 3.4% | 1.5% |
| 5%-10% | 56 | 7.4% | 7.1% |
| 10%-20% | 61 | 14.3% | 6.6% |
| 20%-100% | 105 | 39.2% | 6.7% |

## Governance notes

- Third-party model: vendor due diligence, version pinning, change notification (SS1/23 principle 4).
- Client data leaves the bank when calling an external API: DPIA, data residency and contract terms first.
- Calibration must be re-validated on the bank's own portfolio and monitored monthly.
- EU AI Act: corporate borrowers are outside Annex III; creditworthiness of natural persons would be high-risk.

## Versions

```
{
  "decision_model": "local-stand-in",
  "questions": "edf1045b597f",
  "policy": "543979278b96",
  "tiny_gpt": "31fa26fa55ec",
  "challenger": "64a7b30d9102"
}
```
