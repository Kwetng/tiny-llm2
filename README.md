# tiny-llm2

Small language models built from scratch, and how to combine them with Jev (TypeSafe AI's "System One" decision model) and governed AI engineering in banking.

| Folder | What it is |
|---|---|
| [`sentinel-ai-platform/`](sentinel-ai-platform/) | **A governed GenAI platform for a bank**: AI gateway, entitlement-aware RAG with information barriers, CSA extraction, controlled agent, a release gate with 12 thresholds, drift monitoring, Azure and GCP Terraform, and an automatic model-risk evidence pack |
| [`jev-fraud-detection/`](jev-fraud-detection/) | **Jev + mini LLM for real-time fraud detection** on card payments and bank transfers |
| [`jev-credit-decisions/`](jev-credit-decisions/) | **Jev + mini LLM for credit decision support**: probability of repayment, policy rules, challenger model and audit log |
| [`btc-expert-panel/`](btc-expert-panel/) | **A panel of AI experts on Bitcoin**: quant research models, the neuroplastic world model, Jev and the mini LLM, backtested walk-forward on real data, with a dashboard |
| [`mini-gpt/`](mini-gpt/) | **A GPT built from scratch** in about 170 lines of PyTorch, used by the projects above |
| `tiny_llm.py` | The first TinyLLM: a word-level next-word predictor |
| `tools/` | Builds the Word guides from Markdown |

Each project has a README and a plain-English guide (Markdown and Word).

All data is synthetic except the Bitcoin panel, which uses Coin Metrics community data (CC BY-NC 4.0). Where the Jev API was not reachable, the pipelines use a clearly labelled offline stand-in that is **not Jev**. Set `TYPESAFE_API_KEY` to run them against the real model. The code is for learning and demonstration, not production use.
