# Mini GPT

A complete GPT-style language model built from scratch in about 170 lines of PyTorch. Every stage is labelled in the code, from data and tokeniser to attention, training loop, evaluation and text generation.

It is the "mini LLM" used by the other projects in this repository:
- **Jev fraud detection:** trained on normal payment descriptions, it flags unusual wording such as "SAFE ACCOUNT TRANSFER".
- **BTC expert panel:** reads Bitcoin's daily moves written as letters and imagines possible next weeks.
- **Jev credit decisions:** drafts the narrative of a credit memo.

## Run it

```bash
pip install torch
python mini_gpt.py                   # built-in finance text
python mini_gpt.py my_text.txt       # your own corpus
python mini_gpt.py my_text.txt 5000  # train for 5,000 steps
```

On a laptop CPU the model has 0.81M parameters and trains 1,500 steps in about 2.5 minutes. Loss falls from 3.75 to 0.08, and output goes from random characters to sentences such as "The bank manages credit risk by…".

**Data leakage:** the sample corpus repeats, so validation loss tracks training loss closely. That is memorisation, not generalisation, and a small example of why real pipelines de-duplicate data before splitting it.

## What each part does

1. **Data:** text in, cleaned.
2. **Tokeniser:** one token per character; production models use sub-word tokenisers such as BPE.
3. **Objective:** predict the next token; the targets are the inputs shifted by one.
4. **Architecture:** token and position embeddings, causal multi-head self-attention, feed-forward layers, residual connections and LayerNorm.
5. **Training:** forward pass, cross-entropy loss, backpropagation, AdamW update.
6. **Evaluation:** training loss compared with held-out validation loss.
7. **Generation:** one token at a time, with temperature and top-k sampling.
