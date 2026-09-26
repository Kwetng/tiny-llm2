"""
mini_gpt.py - a complete GPT-style language model built from scratch.

Runs on a laptop CPU in a few minutes. Each numbered STEP matches the
step-by-step explanation. Only dependency: PyTorch (pip install torch).

Usage:
    python mini_gpt.py                  # uses the built-in sample text
    python mini_gpt.py my_corpus.txt    # train on your own text file
"""
import sys, math, torch
import torch.nn as nn
import torch.nn.functional as F

torch.manual_seed(42)

# ---------------------------------------------------------------------------
# STEP 1 - DATA: collect and clean text
# Real LLMs use trillions of tokens (web, books, code), heavily filtered
# and de-duplicated. Here we use a small finance-flavoured corpus.
# ---------------------------------------------------------------------------
SAMPLE = """
The bank manages credit risk by assessing the probability of default of each counterparty.
Market risk arises from movements in interest rates, exchange rates and equity prices.
A derivative is a contract whose value depends on an underlying asset such as a bond or a stock.
The trader hedges the option position by buying or selling the underlying asset.
Counterparty credit risk is the risk that the other side of a trade defaults before settlement.
Model risk is the risk of loss caused by decisions based on incorrect or misused models.
The validation team challenges the assumptions, data and performance of every model.
Liquidity risk is the risk that the bank cannot meet its obligations when they fall due.
Operational risk comes from failed processes, people, systems or external events.
The regulator expects the bank to hold enough capital to absorb unexpected losses.
Interest rate swaps exchange fixed payments for floating payments over an agreed period.
The collateral agreement defines thresholds, minimum transfer amounts and eligible assets.
""" * 40

text = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else SAMPLE

# ---------------------------------------------------------------------------
# STEP 2 - TOKENISER: turn text into integers
# Production models use sub-word tokenisers (BPE / SentencePiece, ~100k
# tokens). A character-level tokeniser keeps the idea transparent.
# ---------------------------------------------------------------------------
chars = sorted(set(text))
vocab_size = len(chars)
stoi = {c: i for i, c in enumerate(chars)}
itos = {i: c for c, i in stoi.items()}
encode = lambda s: [stoi[c] for c in s]
decode = lambda ids: "".join(itos[i] for i in ids)

data = torch.tensor(encode(text), dtype=torch.long)
split = int(0.9 * len(data))
train_data, val_data = data[:split], data[split:]   # hold-out set = validation

# ---------------------------------------------------------------------------
# Hyper-parameters (GPT-3 scale for comparison in brackets)
# ---------------------------------------------------------------------------
block_size = 64      # context window in tokens          [2,048+]
batch_size = 32      # sequences per training step
n_embd     = 128     # size of each token vector          [12,288]
n_head     = 4       # attention heads per layer          [96]
n_layer    = 4       # transformer blocks stacked         [96]
dropout    = 0.1
lr         = 3e-4
max_iters  = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
eval_every = 250

def get_batch(split):
    """STEP 3 - TRAINING OBJECTIVE: inputs x, targets y = x shifted by one.
    The model learns to predict the next token at every position."""
    d = train_data if split == "train" else val_data
    ix = torch.randint(len(d) - block_size - 1, (batch_size,))
    x = torch.stack([d[i:i + block_size] for i in ix])
    y = torch.stack([d[i + 1:i + block_size + 1] for i in ix])
    return x, y

# ---------------------------------------------------------------------------
# STEP 4 - ARCHITECTURE: the Transformer (decoder-only, like GPT)
# ---------------------------------------------------------------------------
class CausalSelfAttention(nn.Module):
    """Each token asks 'which earlier tokens matter to me?' (query vs key),
    then blends their information (values). The causal mask stops it
    peeking at future tokens."""
    def __init__(self):
        super().__init__()
        self.qkv = nn.Linear(n_embd, 3 * n_embd)
        self.proj = nn.Linear(n_embd, n_embd)
        self.drop = nn.Dropout(dropout)
        self.register_buffer("mask", torch.tril(torch.ones(block_size, block_size)))

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(n_embd, dim=2)
        # split into heads: (B, heads, T, head_dim)
        q, k, v = (t.view(B, T, n_head, C // n_head).transpose(1, 2) for t in (q, k, v))
        att = (q @ k.transpose(-2, -1)) / math.sqrt(k.size(-1))     # relevance scores
        att = att.masked_fill(self.mask[:T, :T] == 0, float("-inf"))  # no looking ahead
        att = self.drop(F.softmax(att, dim=-1))                      # scores -> weights
        out = (att @ v).transpose(1, 2).contiguous().view(B, T, C)   # weighted blend
        return self.proj(out)

class FeedForward(nn.Module):
    """Per-token 'thinking' layer; stores much of the model's knowledge."""
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(n_embd, 4 * n_embd), nn.GELU(),
                                 nn.Linear(4 * n_embd, n_embd), nn.Dropout(dropout))
    def forward(self, x):
        return self.net(x)

class Block(nn.Module):
    """One transformer layer: attention (communicate) + MLP (compute),
    each with layer-norm and a residual connection for stable training."""
    def __init__(self):
        super().__init__()
        self.ln1, self.ln2 = nn.LayerNorm(n_embd), nn.LayerNorm(n_embd)
        self.attn, self.ff = CausalSelfAttention(), FeedForward()
    def forward(self, x):
        x = x + self.attn(self.ln1(x))
        x = x + self.ff(self.ln2(x))
        return x

class MiniGPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.tok_emb = nn.Embedding(vocab_size, n_embd)   # token id -> vector (meaning)
        self.pos_emb = nn.Embedding(block_size, n_embd)   # position -> vector (order)
        self.blocks = nn.Sequential(*[Block() for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(n_embd)
        self.head = nn.Linear(n_embd, vocab_size)         # vector -> score per token

    def forward(self, idx, targets=None):
        B, T = idx.shape
        x = self.tok_emb(idx) + self.pos_emb(torch.arange(T))
        logits = self.head(self.ln_f(self.blocks(x)))
        loss = None
        if targets is not None:   # cross-entropy = how surprised the model is
            loss = F.cross_entropy(logits.view(-1, vocab_size), targets.view(-1))
        return logits, loss

    @torch.no_grad()
    def generate(self, idx, max_new_tokens, temperature=0.8, top_k=20):
        """STEP 7 - INFERENCE: predict one token, append it, repeat."""
        for _ in range(max_new_tokens):
            logits, _ = self(idx[:, -block_size:])
            logits = logits[:, -1, :] / temperature           # low temp = safer choices
            v, _ = torch.topk(logits, top_k)
            logits[logits < v[:, [-1]]] = -float("inf")       # keep top-k candidates
            nxt = torch.multinomial(F.softmax(logits, dim=-1), 1)
            idx = torch.cat([idx, nxt], dim=1)
        return idx

model = MiniGPT()
print(f"Vocabulary: {vocab_size} tokens | Parameters: {sum(p.numel() for p in model.parameters())/1e6:.2f}M")

# ---------------------------------------------------------------------------
# STEP 5 - PRE-TRAINING LOOP: forward -> loss -> backward -> update
# ---------------------------------------------------------------------------
optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.1)

@torch.no_grad()
def estimate_loss():
    """STEP 6 - EVALUATION: compare train vs held-out loss (over-fitting check)."""
    model.eval()
    out = {}
    for s in ("train", "val"):
        out[s] = torch.stack([model(*get_batch(s))[1] for _ in range(20)]).mean().item()
    model.train()
    return out

prompt = torch.tensor([encode("The bank ")], dtype=torch.long)
print("\nBefore training:", decode(model.generate(prompt, 60)[0].tolist()))

for it in range(max_iters + 1):
    if it % eval_every == 0:
        l = estimate_loss()
        print(f"step {it:5d} | train loss {l['train']:.3f} | val loss {l['val']:.3f}")
    xb, yb = get_batch("train")
    _, loss = model(xb, yb)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()                                          # compute gradients
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)  # stability
    optimizer.step()                                         # nudge the weights

print("\nAfter training: ", decode(model.generate(prompt, 200)[0].tolist()))
torch.save(model.state_dict(), "mini_gpt.pt")
print("\nSaved weights to mini_gpt.pt")
