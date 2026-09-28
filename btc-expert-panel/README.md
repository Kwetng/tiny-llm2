# BTC Expert Panel

A weekly "investment committee" for Bitcoin, backtested on real data. **Eleven experts in six families** — machine learning, latent state models, decision and language models, a technical indicator, and two outside views — each call Bitcoin's next week LONG, FLAT or SHORT. A panel chair acts only when at least 3 agree and they outnumber the other side. Everything is tested walk-forward, out of sample, from January 2020 to May 2026.

The newest pair — a simulated 6-qubit quantum circuit and a hidden Markov regime model — is reported the same way as every earlier addition, including when the finding is unflattering: see "Results" below.

**[Open the dashboard](dashboard/index.html)** (download and open in a browser) · **[Plain-English guide](docs/panel-guide.md)** ([Word version](docs/BTC_Expert_Panel_Guide.docx))

![Dashboard](docs/img/docs_img_top.png)

## The panel

| Seat | Where it comes from | How it makes its call |
|---|---|---|
| **Random Forest** | Quant research project `projectskf` (`ml exercise.py`) | 300 trees classify next-week direction from 12 inputs |
| **Tabular Transformer** | Quant research project `projectskf` (`ml nn transformer python file.py`) | Each input is a token; attention across inputs; average of 3 seeds |
| **Neuroplastic World Model** | `neuroplastic-financial-world-model` V5 | Six networks learn to predict the next "world state" and next week's return; trades only when 4 of 6 agree |
| **Jev (System One)** | TypeSafe AI decision model | Answers "Will Bitcoin be higher in 7 days?" (probability) and names the regime. **Offline stand-in in this run, not Jev** |
| **Mini LLM tape reader** | `tiny-llm2` mini GPT | Reads the last 64 days of returns written as letters (a = big fall … g = big rise), writes 256 possible next weeks, and counts how many end higher |
| **Phantom Flow** | Open re-implementation of the paid TradingView indicator's three published modules | Trend shift (trailing stop at 3 × ATR), swing structure (break of structure / change of character on 5-day pivots) and oscillator (distance from the 21-day average in ATRs), all on daily closes. LONG or SHORT only when trend and oscillator agree and structure does not contradict. No training; settings fixed in advance; no repainting |
| **Market consensus** | Polymarket / Kalshi BTC contracts — **not a model** | Reads the ladder of "will Bitcoin reach $X" contracts and compares what the crowd pays for a +10% move against an equidistant −10% move. Corrects for the three traps: touch ≠ close, a monthly clock against a weekly question, and the risk premium in any price. **Abstains** on every week with no liquid market |
| **Chart JEPA** | Technical analysis, built here | Draws the last 52 weeks as a 24×52 picture scaled to its own high and low, so only the **shape** survives. A joint embedding predictive architecture predicts the *embedding* of the next piece of chart rather than its pixels; a logistic probe turns that into a probability. Embedding spread is reported every run, because collapse is this model's failure mode |
| **Fundamentals** | On-chain valuation | The only seat that never looks at price action: MVRV, Puell multiple, hash ribbon and a Metcalfe residual, each scored against its own previous four years. Votes only when the average passes ±0.5 |
| **Quantum NN** | Built here | A real (simulated) 6-qubit circuit — RY rotations and CNOT gates only, so every amplitude stays real — reads momentum, valuation, volatility and VIX as rotation angles, re-uploaded before each of 3 layers. 25 trained parameters; a classical linear layer turns 6 qubit measurements into P(up). **No quantum advantage is claimed** |
| **HMM Regime** | Built here | A 3-state Gaussian hidden Markov model over weekly return and volatility. Fitted with Baum-Welch, but voted on using only the **forward-filtered** state probability (never the smoothed one, which would leak the future) — turned into an exact mixture probability that next week is positive |
| **Panel chair** | Panel rule | LONG or SHORT if at least 3 agree and outnumber the other side, otherwise FLAT. The 5-, 6-, 7- and 9-expert chairs are kept as benchmarks |

**Calls:** P(up) of 55% or more is LONG, 45% or less is SHORT, anything in between is FLAT.

**The 12 inputs**, all from [Coin Metrics community data](https://github.com/coinmetrics/data) (CC BY-NC 4.0) plus the CBOE VIX:
- 1-, 4-, 12- and 26-week returns
- 4-week volatility
- MVRV (market value over the average cost basis of coins)
- drawdown from the 52-week high
- 4-week change in active addresses and in hash rate
- net exchange inflows
- the VIX level and its 4-week change

## Results: 332 weeks out of sample (5 Jan 2020 – 10 May 2026)

These are after 10 bp trading costs, with no leverage.

| Seat | Total return | CAGR | Sharpe | Max drawdown | Hit rate |
|---|---|---|---|---|---|
| Chair without quantum + regime (9 experts) | +2,103% | 62.3% | **1.21** | −45% | 57.5% |
| Neuroplastic World Model | +1,161% | 48.7% | 1.13 | −50% | 53.6% |
| **Panel chair (11 experts)** | **+1,579%** | 55.6% | 1.07 | −47% | 55.3% |
| Chair with 7 experts | +1,111% | 47.8% | 1.05 | −43% | 56.9% |
| Buy & hold | +954% | 44.6% | 0.93 | −75% | 52.1% |
| Jev (offline stand-in) | +863% | 42.6% | 0.94 | −45% | 52.5% |
| Chair with 5 experts | +671% | 37.7% | 0.93 | **−41%** | **57.6%** |
| HMM Regime | +264% | 22.4% | 0.69 | −72% | 50.9% |
| Phantom Flow | +191% | 18.2% | 0.58 | −58% | 49.4% |
| Mini LLM tape reader | +171% | 16.9% | 0.56 | −77% | 54.8% |
| Random Forest | +122% | 13.3% | 0.50 | −51% | 53.7% |
| Tabular Transformer | +103% | 11.8% | 0.48 | −75% | 56.0% |
| Chart JEPA | +4% | 0.6% | 0.16 | −51% | 48.3% |
| Fundamentals | −88% | −28.3% | −0.54 | −94% | 52.3% |
| Quantum NN | **−91%** | −31.0% | **−0.48** | −94% | 46.0% |

**What this shows:**
- **The five-expert chair matched buy-and-hold's Sharpe ratio (0.93) with roughly half the worst loss** (−41% against −75%). It also had the best hit rate. In 2022, when Bitcoin fell 65%, the chair lost 9%.
- **The newest pair, quantum NN and regime HMM, made the committee worse — and that is reported exactly as plainly as every improvement was.** The quantum NN lost 91% on its own, the worst of any seat, and the regime HMM made a respectable 264% alone (Sharpe 0.69) but the two together pulled the 9-expert chair's Sharpe down from 1.21 to 1.07. The 95% interval is **[−0.48, +0.17]** — mostly negative, and the committee did no better in 81% of resampled histories — and unlike the JEPA+fundamentals step, it does **not** survive dropping 2020 (0.72 → 0.52). The honest verdict is "not proven, and the evidence leans toward worse rather than better." Run `python code/chair_effect.py` to reproduce the whole ladder.
- **The chart JEPA and fundamentals pair lost money alone, and the committee still improved when they joined.** The chart JEPA made 4% with a 48.3% hit rate — the shape of the chart carries very little week-ahead information. The fundamentals seat lost 88%, because it was bearish through most of a bull market. Yet the 7→9 expert chair's Sharpe rose from 1.05 to 1.21, because the fundamentals seat was wrong at different times from the momentum models. **The 95% interval for that gain is [−0.11, +0.44], so it is reported as not proven**, though unlike Phantom Flow it survives dropping 2020 (0.55 → 0.72).
- **The market expert abstained on every week of this run**, because the Polymarket and Kalshi APIs were unreachable from the build machine. An abstaining expert changes neither the LONG nor the SHORT count, so the panel's figures above are unchanged by it. Run `python code/fetch_markets.py` to fill it in.
- **Phantom Flow was weak alone but independent, and adding it lifted the chair to a Sharpe of 1.05.** That gain may be luck: its 95% bootstrap range is −0.22 to +0.50, and excluding 2020 the two chairs score 0.55 and 0.53. Across all 9 indicator settings tried as a check (ATR × 2–4, pivots of 3–10 days), the chair stays between 0.99 and 1.14. The honest reading is "didn't hurt, may help".
- **The neuroplastic world model was the strongest single expert**, with a Sharpe of 1.13 against 0.93 for buy and hold. The Jev stand-in only just beat buy and hold (0.94).
- **The two quant-project classifiers and the mini LLM underperformed buy and hold.** The mini LLM overfitted: on new data its average surprise was worse than blind guessing among 7 letters. Its gains came in 2020–2021, and it lost money in every year from 2022 on.
- **The quantum NN's own parameter budget (25 parameters) is not the explanation for its loss.** It is a small, high-bias model that should underfit rather than overfit, so its poor result says its six rank-encoded features carried little week-ahead signal through this particular circuit and readout — a real, disclosed limitation, not evidence against the simulator or the parameter-shift gradient, both of which check out exactly in tests.
- **The experts disagree a lot**, which is what makes a panel useful.

**Caveats:**
- This is one historical path of about 330 weeks.
- 2020–2021 was a strong bull market.
- The Jev figures come from a hand-written stand-in.
- This is research on historical data, not investment advice.

## Latest calls (week after 17 May 2026, BTC $77,498)

The public Coin Metrics files currently end on 23 May 2026, so this is the most recent week that can be scored. Re-run with newer data to update it.

| Seat | Call | P(up) | Why |
|---|---|---|---|
| Random Forest | FLAT | 49% | Most important inputs: 4-week return, active addresses, 1-week return |
| Tabular Transformer | FLAT | 51% | |
| Neuroplastic World Model | FLAT | 67%* | 2 BUY / 0 SELL / 4 HOLD; needs 4 of 6 |
| Jev (stand-in) | LONG | 62% | Regime: range-bound |
| Mini LLM | LONG | 79% | 256 simulated weeks, average +4.7% |
| Phantom Flow | FLAT | score −1 | Trend just flipped down (stop $80,716), oscillator −0.66 ATR, structure still bullish. By 23 May structure had also turned: daily SHORT |
| Market consensus | FLAT | — | Abstained: no prediction-market data fetched in this run |
| Chart JEPA | FLAT | 51% | Embedding spread 1.06 (no collapse) |
| Fundamentals | FLAT | 49% | Valuation score −0.32 against its own four-year norm |
| Quantum NN | FLAT | 52% | Six qubit measurements: [−0.17, −0.08, −0.10, +0.13, −0.06, +0.08] |
| HMM Regime | LONG | 60% | Filtered state: "calm and rising", 100% confident |
| **Panel chair** | **LONG** | 56% avg | 3 long, 8 flat, 0 short |

\* For the world model this is a vote share, (BUY + ½ HOLD) ÷ 6, not a probability.

## Run it

```bash
pip install torch scikit-learn pandas numpy scipy
cd code
python panel_backtest.py        # downloads the data to ../data/, about 13-15 minutes on a laptop CPU
python fetch_markets.py         # optional: prediction-market data (needs internet)
python pf_effect.py             # did Phantom Flow really help? (bootstrap, ex-2020)
python chair_effect.py          # did every added seat help? (the full ladder, 5 -> 6 -> 7 -> 9 -> 11)
node export_dashboard_pdf.js    # optional: the dashboard as a printable A4 PDF (needs playwright + chart.js)
python make_dashboard.py        # rebuilds ../dashboard/index.html
pytest -q ../tests              # all seats' tests, including the no-hindsight and no-look-ahead checks
export TYPESAFE_API_KEY=...     # optional: use the real Jev instead of the stand-in
```

All seeds are fixed, so re-running should reproduce these numbers.

| Path | Contents |
|---|---|
| `code/panel_backtest.py` | Data, features, all eleven experts, walk-forward loop, metrics, Phantom Flow sensitivity |
| `code/phantom_flow.py` | The Phantom Flow re-implementation: trend shift, structure, oscillator, combined call |
| `code/chart_jepa.py` | The technical seat: chart rendering, patching, the JEPA encoder/predictor with an EMA target, the anti-collapse term and the probe |
| `code/fundamentals.py` | The fundamental seat: MVRV, Puell, hash ribbon, Metcalfe residual, causal trailing z-scores and the vote rule |
| `code/prediction_market.py` | The market expert: question parsing, the touch ladder, the symmetric lean, the touch→close correction, abstention rules |
| `code/quantum_nn.py` | The quantum seat: a real-amplitude (RY + CNOT only) state-vector simulator, data re-uploading, classical readout, and the parameter-shift gradient rule |
| `code/hmm_regime.py` | The regime seat: a Gaussian hidden Markov model fitted with Baum-Welch, voted on using forward-filtered (never smoothed) state probabilities |
| `code/fetch_markets.py` | Builds the weekly market cache from Polymarket or Kalshi (run where there is internet) |
| `code/pf_effect.py` | Bootstrap and ex-2020 check of what Phantom Flow adds to the chair |
| `code/chair_effect.py` | The full ladder: did each later addition (Phantom Flow, the market, JEPA+fundamentals, quantum+regime) actually help, with a block-bootstrap verdict for each |
| `tests/test_phantom_flow.py` | 6 tests: no look-ahead, trend flips, stop ratchet, BOS/CHoCH, combo rule |
| `tests/test_new_experts.py` | 14 tests: the chart picture is scale-free, charts never use future prices, embeddings do not collapse, trailing z-scores are causal, metrics are scale-free, and the seat votes only at extremes |
| `tests/test_prediction_market.py` | 22 tests: question parsing, a symmetric ladder giving zero lean, a common premium cancelling, abstention instead of extrapolation, the touch→close halving, and the documented API response shapes |
| `tests/test_quantum_hmm.py` | 16 tests: the simulator reproduces a textbook Bell state, the parameter-shift rule agrees with autograd, and — the one this file exists for — filtering a truncated series gives the identical answer for its last week as filtering the whole series |
| `code/jev_market.py` | Jev API client and the offline stand-in |
| `code/dashboard_template.html`, `code/make_dashboard.py` | The dashboard |
| `code/export_dashboard_pdf.js` | The dashboard as a printable A4 landscape PDF: pins the light theme, opens the scrolling boxes so no table is cut off, and keeps cards and tables off page breaks |
| `outputs/` | `panel_results.json`, `weekly_signals.csv`, `performance_summary.csv`, `yearly_returns.csv`, `weekly_features.csv`, `phantom_flow_daily.csv`, `phantom_flow_sensitivity.csv`, `phantom_flow_effect.json`, `chair_effect.json` |
| `dashboard/index.html` | Self-contained dashboard; needs internet for the chart library and fonts |
| `docs/` | Plain-English guide (Markdown and Word) and dashboard screenshots |

## How the source projects were adapted

- **projectskf:**
  - The IPO dataset was replaced by weekly Bitcoin data.
  - The random forest keeps 300 trees but adds `min_samples_leaf=10` to limit overfitting on about 400–680 weekly rows.
  - The transformer keeps the original architecture, with `d_model` 32 instead of 64.
  - The transformer trains for a **fixed 60 epochs**. The original picked the best epoch on the test set, which leaks test information into the result.
- **neuroplastic-financial-world-model V5:**
  - The architecture, loss (0.3 × next state + 1.0 × next return), 180 epochs, six seeds, 4-of-6 vote and uncertainty penalty are all kept.
  - The monthly EUR/USD macro world is replaced by the weekly Bitcoin world, and the cost is 10 bp instead of 1 bp.
- **Chart JEPA:** the window is normalised to itself so the model sees shape rather than price level; the loss is measured between embeddings, never pixels; and the collapse score is published on every run rather than checked privately.
- **Fundamentals:** an early version standardised against the training window, which produced readings like "13 standard deviations cheap" because Bitcoin's market cap grew a thousandfold. Replaced with causal trailing z-scores against each measure's own previous four years.
- **Prediction markets:** the signal is a *difference* between two symmetric contracts rather than a raw probability, which cancels the risk premium common to both legs. Touch contracts are never read as closing-price forecasts. Where the ladder does not bracket a ±10% move, the expert abstains rather than extrapolating.
- **Phantom Flow:** the proprietary Pine Script is closed, so each published module is rebuilt with the standard method. Order blocks and fair value gaps are omitted because they need intraday highs and lows. **It is not the paid indicator.**
- **tiny-llm2 mini GPT:** the same architecture, with 7 "letters" for daily-return buckets instead of text characters. It is retrained each January.
- **Quantum NN:** built for this project. Restricted to RY and CNOT gates so every amplitude stays real, which makes a state-vector simulator on 6 qubits trivial and lets its output be checked against a textbook Bell state. Features are encoded by rank against the training distribution rather than a z-score, because an angle is periodic and an outlier past π would silently wrap around and invert.
- **HMM Regime:** built for this project. The one design decision that mattered was keeping the forward-backward algorithm (used only for fitting) strictly separate from the forward-only filter (used for every vote), because the smoothed probabilities the former also produces would leak future returns into a live decision — the single most common way a hidden Markov trading strategy fools its author.

Data: Coin Metrics community data, CC BY-NC 4.0, attribution required and non-commercial use only. VIX data comes from [datasets/finance-vix](https://github.com/datasets/finance-vix). Raw data is downloaded at run time and not stored in this repository.
