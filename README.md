# tiny-llm2

Small language models built from scratch, and how to use them alongside Jev (TypeSafe AI's "System One" decision model) in banking.

| Folder / file | What it is |
|---|---|
| `tiny_llm.py` | The first TinyLLM: a word-level next-word predictor in a few lines of PyTorch |
| [`smbc-interview-prep/`](smbc-interview-prep/) | Interview preparation pack for Head of AI Engineering (SMBC EMEA), `mini_gpt.py` (a GPT from scratch), and **Jev + tiny LLM for credit decisions** |
| [`jev-fraud-detection/`](jev-fraud-detection/) | **Jev + mini LLM for real-time fraud detection** on card payments and bank transfers, with a plain-English guide |

All data in this repository is synthetic, and the code is for learning, not production use. Where the Jev API was not reachable, the pipelines use a clearly labelled offline stand-in that is **not Jev**. Set `TYPESAFE_API_KEY` to run them against the real model.
