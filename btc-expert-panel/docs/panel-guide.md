\title BTC Expert Panel
\subtitle A plain-English guide to five AI experts calling Bitcoin's next week
\subtitle Walk-forward results on real data, January 2020 – May 2026

\pagebreak

\toc

\pagebreak

# 1. The idea in one minute

Investment banks rarely trust a single opinion. They use committees: several experts look at the same market from different angles, and the committee acts only when enough of them agree.

This project builds that committee for **Bitcoin**, using AI models from three of Kwet's own projects plus Jev:

- **Two quant research models** from the IPO prediction project (`projectskf`): a random forest and a tabular transformer.
- **The neuroplastic world model (V5):** six small networks that learn how the Bitcoin "world" evolves.
- **Jev:** a decision model that returns a calibrated probability. This run uses an offline stand-in (see section 7).
- **The mini LLM**, built from scratch, reading the market's daily moves as if they were text.

Every Sunday, each expert says whether Bitcoin will be **higher in 7 days**. A **panel chair** then acts only if at least 3 of the 5 agree.

Everything is tested **walk-forward**. Each January the models are retrained using only data from before that year, then used unchanged for the whole year, so no model ever sees the future. The test runs from January 2020 to May 2026: 332 weeks.

> **In one sentence:** five different AI experts vote on Bitcoin each week; on its own none beats simply holding Bitcoin by much, but the committee matched buy-and-hold's risk-adjusted return with roughly half the worst loss.

![Figure 1 — The dashboard: latest verdict and each expert's call](img/docs_img_top.png)

# 2. The data every expert sees

All data is real. Prices and on-chain activity come from Coin Metrics' public data (CC BY-NC 4.0), and the VIX (the US stock market's "fear index") from a public dataset. Both were downloaded from GitHub.

Each week the market is summarised in **12 numbers**:

| Input | Plain meaning | Why it might matter |
|---|---|---|
| 1-, 4-, 12-, 26-week returns | How much the price moved over each period | Trends tend to persist, until they don't |
| 4-week volatility | How wild daily moves have been | Calm and panic behave differently |
| MVRV | Market value divided by the average price holders paid | Very high means holders sit on big profits and may sell; below 1 means most are at a loss |
| Drawdown from 52-week high | How far below its one-year peak the price is | Deep drawdowns mark crashes and bottoms |
| Active addresses, 4-week change | Is network use growing or shrinking? | More users can mean more demand |
| Hash rate, 4-week change | Is mining power growing? | A sign of miners' confidence |
| Net exchange inflows | Coins moving onto exchanges (often to sell) | Large inflows can precede selling |
| VIX level and 4-week change | Fear in stock markets | Risk-off moods hit Bitcoin too |

**Calls:** each expert gives a probability that Bitcoin is higher next week. At 55% or more it goes **LONG** (buys), at 45% or less it goes **SHORT** (bets on a fall), and anything in between is **FLAT** (stays out). Every change of position costs 0.10% in trading costs.

# 3. The experts

## 3.1 Random Forest (quant research project)

**What it is:** hundreds of decision trees, each asking yes/no questions such as *"Is 4-week momentum above 5%?"* and *"Is MVRV above 2.5?"*. Their votes are averaged into a probability. It was the best model in the original IPO project.

**Changes for Bitcoin:** 300 trees, and each final branch must contain at least 10 weeks of history, so the trees can't memorise individual weeks.

**Latest call:** FLAT, 49%. Its most important inputs were the 4-week return, the change in active addresses and the 1-week return.

## 3.2 Tabular Transformer (quant research project)

**What it is:** the same attention mechanism that powers large language models, applied to a table. Each of the 12 inputs becomes a "token", and the model learns which inputs to pay attention to together. Three copies with different random starting points are averaged.

**One fix to the original method:** the IPO project picked the best training round by looking at the test data, which quietly leaks test information into the result. Here the transformer trains for a fixed 60 rounds and never sees the test period.

**Latest call:** FLAT, 51%.

## 3.3 Neuroplastic World Model (V5)

**What it is:** six small networks. Each learns a compressed "state of the world" and is trained to predict two things: the next week's full set of 12 inputs, and next week's return. This is the world-model idea: understand how the world moves, not just the price.

**How it decides:** each of the six networks simulates 300 possible outcomes, and votes BUY, SELL or HOLD after subtracting trading costs and a penalty for uncertainty. The model trades only if **4 of the 6 agree**; otherwise it holds.

**Latest call:** FLAT. The vote was 2 BUY, 0 SELL, 4 HOLD, with a predicted return of +1.1% for the week. The "67%" on the dashboard is a vote share, not a probability.

## 3.4 Jev (System One)

**What it is:** a decision model from TypeSafe AI. It reads the 12 inputs as structured data and answers two questions in one call:
- **"Will Bitcoin be higher in 7 days?"**, as a probability
- **"Which market regime is this?"**: bull trend, bear trend, range-bound, capitulation or euphoria

**Important:** Jev's online service could not be reached from the build environment. In this run a **hand-written stand-in** answers instead. It follows the 12-week and 4-week trend, leans against extreme valuation (MVRV above 3.2 or below 1.0) and is cautious when the VIX is above 30. **It is not Jev.** With an API key, the same code calls the real model.

**Latest call:** LONG, 62%, with the regime labelled *range-bound*.

## 3.5 Mini LLM tape reader

**What it is:** the small GPT built from scratch in this repository. Traders call the stream of price moves "the tape", so the mini LLM reads it as text:

| Letter | Daily move |
|---|---|
| a | Biggest falls (bottom seventh of days) |
| b, c | Smaller falls |
| d | Roughly flat |
| e, f | Smaller rises |
| g | Biggest rises (top seventh of days) |

So the last 14 days before the latest call read **"ffebdefcbbfabc"**. The model learns which letters tend to follow which. To make a call, it **writes 256 possible next weeks** (7 letters each), converts them back to returns, and counts how many end higher.

**Latest call:** LONG, 79%. The average of its 256 imagined weeks was +4.7%.

**A warning sign the numbers revealed:** the model's "surprise" on new data averaged 4.9 bits per day. Blind guessing among 7 letters scores 2.8 bits. It had **memorised the past** rather than learned something general, and its results show it (section 5).

## 3.6 The panel chair

**What it is:** a simple rule. LONG if at least 3 of the 5 experts say LONG; SHORT if at least 3 say SHORT; otherwise FLAT.

**Latest call:** FLAT. Two experts said LONG (Jev and the mini LLM), three said FLAT, none said SHORT.

# 4. A worked example: one week

The latest call was for the week after **17 May 2026**, with Bitcoin at **$77,498**. The public data ends on 23 May 2026, so this is the most recent week the system can call.

| Expert | P(price higher) | Call | Reason |
|---|---|---|---|
| Random Forest | 49% | FLAT | Between 45% and 55% |
| Tabular Transformer | 51% | FLAT | Between 45% and 55% |
| Neuroplastic World Model | vote 2 BUY / 4 HOLD | FLAT | Needs 4 of 6 to agree |
| Jev (stand-in) | 62% | LONG | Above 55%; regime range-bound |
| Mini LLM | 79% | LONG | 203 of 256 imagined weeks ended higher |
| **Panel chair** | — | **FLAT** | Only 2 of 5 LONG; needs 3 |

The committee stays out of the market. The two confident experts are the stand-in rule and the model that memorised the past, which is exactly the kind of situation where waiting for broader agreement protects you.

\pagebreak

# 5. How did they do?

![Figure 2 — Growth of $1 following each expert, after trading costs (log scale)](img/docs_img_equity.png)

## Five ways to measure

- **Total return:** what $1 became.
- **CAGR:** the average yearly growth rate.
- **Sharpe ratio:** return per unit of risk (weekly volatility). Higher is better; buy-and-hold Bitcoin scored 0.93 over this period.
- **Maximum drawdown:** the worst fall from a peak, which is what hurts investors most.
- **Hit rate:** how often a call was right, counting only weeks with a position.

## Results, 332 weeks out of sample

| Expert | Total return | CAGR | Sharpe | Max drawdown | Hit rate | Time long / short |
|---|---|---|---|---|---|---|
| Neuroplastic World Model | +1,161% | 48.7% | **1.13** | −50% | 53.6% | 45% / 8% |
| Jev (stand-in) | +863% | 42.6% | 0.94 | −45% | 52.5% | 53% / 26% |
| **Panel chair** | +671% | 37.7% | 0.93 | **−41%** | **57.6%** | 45% / 14% |
| Buy & hold | +954% | 44.6% | 0.93 | −75% | 52.1% | 100% / 0% |
| Mini LLM | +171% | 16.9% | 0.56 | −77% | 54.8% | 46% / 39% |
| Random Forest | +122% | 13.3% | 0.50 | −51% | 53.7% | 47% / 14% |
| Tabular Transformer | +103% | 11.8% | 0.48 | −75% | 56.0% | 49% / 39% |

## What the results mean

1. **The committee's value is protection, not extra return.** The panel chair earned less than buy-and-hold, but with the same Sharpe ratio (0.93) and a worst loss of 41% instead of 75%. It also had the best hit rate.
2. **The neuroplastic world model was the strongest single expert,** with a Sharpe of 1.13 against 0.93 for buy-and-hold.
3. **The quant classifiers struggled.** Models that worked on IPO data did not carry over to weekly Bitcoin moves, which are much noisier.
4. **The mini LLM shows what overfitting looks like.** It had a spectacular 2020–2021 (+300% and +191%) and then lost money every year after.

## Calendar years

| Expert | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|---|
| Random Forest | +99% | +6% | −26% | +83% | +9% | −5% | −25% |
| Tabular Transformer | +211% | −24% | −33% | +22% | +28% | −4% | −16% |
| Neuroplastic World Model | +284% | +1% | −6% | +35% | +104% | +4% | +20% |
| Jev (stand-in) | +118% | +84% | −10% | +71% | +40% | +12% | 0% |
| Mini LLM | +300% | +191% | −21% | −27% | −41% | −5% | −28% |
| **Panel chair** | +265% | +14% | −9% | +57% | 0% | +30% | +1% |
| Buy & hold | +353% | +42% | −65% | +164% | +124% | −7% | −15% |

\* 2026 to 10 May.

**The 2022 crash is the clearest example.** Bitcoin fell 65%; the panel chair lost 9%. In 2025, when Bitcoin fell 7%, the chair gained 30%.

## The signal board

![Figure 3 — Each expert's weekly call (blue long, red short, grey flat) above what the market actually did](img/docs_img_board.png)

Reading the board: a call is right when its colour matches the market row underneath.

The experts often disagree. For example, the world model and the transformer made the same call in only 34% of weeks. This is what makes a committee useful: **independent opinions whose mistakes don't all happen at once.**

# 6. How the test was kept honest

- **Walk-forward retraining:** models are retrained every January on data before that year only.
- **No peeking:** the transformer no longer selects its best training round using test data.
- **Trading costs:** 0.10% per position change.
- **No leverage:** positions are fully in, fully out, or fully short.
- **Reproducible:** all random seeds are fixed. A second full run gave identical results, apart from rounding at the 16th decimal place.
- **Latest week excluded from scoring:** its outcome is not in the data yet.

# 7. Read this before trusting the numbers

- **One historical path.** 332 weeks is one run of history. A different period could rank the experts differently.
- **A friendly period for holding Bitcoin.** 2020–2021 was a strong bull market, so buy-and-hold is hard to beat on raw return.
- **The Jev results are not Jev.** They come from a hand-written trend-and-valuation rule. Re-run with an API key to test the real model.
- **Weekly shorting assumes it is possible and cheap.** Real short positions cost funding and borrowing fees that are not included.
- **The data ends in May 2026**, because Coin Metrics' public GitHub files stop there. The "latest call" is therefore four months old.
- **Research, not advice.** Nothing here is investment advice.

# 8. How to run it

```
cd btc-expert-panel/code
pip install torch scikit-learn pandas numpy
python panel_backtest.py      # downloads data, trains, tests (about 10 minutes)
python make_dashboard.py      # rebuilds ../dashboard/index.html
export TYPESAFE_API_KEY=...   # optional: use the real Jev
```

# 9. How to use it in an interview

> "I put models from three of my projects on one committee for Bitcoin and tested them honestly: annual walk-forward retraining, costs included, no look-ahead. I even fixed a test-set leak in my own earlier code. The finding I'd highlight isn't the best single model; it's that a simple 3-of-5 vote kept buy-and-hold's risk-adjusted return while cutting the worst loss from 75% to 41%. I'd also point out the mini LLM's failure: it memorised the past, and its surprise score on new data was a warning sign I could have used to switch it off."

# 10. Glossary

| Term | Plain meaning |
|---|---|
| Walk-forward test | Retraining on the past and testing on the next period, repeatedly, so the model never sees the future |
| Out of sample | Data the model was not trained on |
| LONG / SHORT / FLAT | Own Bitcoin / bet on a fall / stay out |
| Sharpe ratio | Return divided by volatility; a measure of reward per unit of risk |
| Drawdown | Fall from a previous peak |
| Hit rate | Share of calls that were right |
| MVRV | Market value divided by the average price holders paid (realised value) |
| Hash rate | Total computing power securing the Bitcoin network |
| VIX | A measure of expected volatility in US stocks, often called the fear index |
| Overfitting | Learning the noise of the past so well that the model fails on new data |
| Bits of surprise | How hard a language model finds new data to predict; above blind guessing means it is confused |
| World model | A model that learns how the whole environment changes, not just one target |
