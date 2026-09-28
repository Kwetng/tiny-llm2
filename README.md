# tiny-llm2

Small language models built from scratch, and how to combine them with decision models such as Jev (TypeSafe AI) and its open-source alternative Laya, and governed AI engineering in banking.

| Folder | What it is |
|---|---|
| [`sentinel-ai-platform/`](sentinel-ai-platform/) | **A governed GenAI platform for a bank**: AI gateway, entitlement-aware RAG with information barriers, CSA extraction, controlled agent, a release gate with 12 thresholds, drift monitoring, Azure and GCP Terraform, and an automatic model-risk evidence pack |
| [`jev-fraud-detection/`](jev-fraud-detection/) | **Jev + mini LLM for real-time fraud detection** on card payments and bank transfers |
| [`jev-credit-decisions/`](jev-credit-decisions/) | **Jev + mini LLM for credit decision support**: probability of repayment, policy rules, challenger model and audit log |
| [`laya-vs-jev-credit/`](laya-vs-jev-credit/) | **Laya vs Jev on credit decisions**: an open-source, in-house decision model against a closed cloud one, on identical borrowers, with recalibration, bootstrap intervals and pre-set decision rules |
| [`btc-expert-panel/`](btc-expert-panel/) | **A panel of experts on Bitcoin**: quant research models, the neuroplastic world model, Jev, the mini LLM, the Phantom Flow indicator and the prediction market's own price, backtested walk-forward on real data, with a dashboard |
| [`mini-gpt/`](mini-gpt/) | **A GPT built from scratch** in about 170 lines of PyTorch, used by the projects above |
| `tiny_llm.py` | The first TinyLLM: a word-level next-word predictor |
| `tools/` | Builds the Word guides from Markdown |

Each project has a README and a plain-English guide (Markdown and Word).

All data is synthetic except the Bitcoin panel, which uses Coin Metrics community data (CC BY-NC 4.0). Where the Jev API was not reachable, the pipelines use a clearly labelled offline stand-in that is **not Jev**. Set `TYPESAFE_API_KEY` to run them against the real model. The Laya comparison runs locally once Laya's weights are downloaded. The code is for learning and demonstration, not production use.
