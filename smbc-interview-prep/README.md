# SMBC Head of AI Engineering — Interview Preparation

Preparation pack and supporting code for the Head of AI Engineering role (ITSD, SMBC Group EMEA).

## Contents

| Path | What it is |
|---|---|
| `docs/interview-prep.md` | The full six-level prep programme in Markdown (Foundations → Expert), including the LLM history and the build-an-LLM guide |
| `docs/SMBC_AI_Engineering_Interview_Prep.docx` | The same content as a formatted Word document with diagrams |
| `diagrams/` | LLM evolution flowchart, bank AI platform architecture, credit memo copilot architecture |
| `code/mini_gpt.py` | A complete GPT-style language model built from scratch in PyTorch (~170 lines) |
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

## Rebuilding the diagrams and the Word document

```bash
pip install cairosvg
python code/diagrams.py                   # writes diagram_*.png
npm install docx
node code/build_docx.js docs/interview-prep.md out.docx
```

Run the builder from a folder where the diagram PNGs referenced in the Markdown can be found.
