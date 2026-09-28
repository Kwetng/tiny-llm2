"""
chart_jepa.py - the technical-analysis seat: a JEPA that predicts the next piece of the chart.

WHAT A JEPA IS, IN ONE PARAGRAPH
A Joint Embedding Predictive Architecture (Yann LeCun's proposal, and the I-JEPA family)
learns by predicting the *embedding* of a hidden part of its input from the parts it can see.
The crucial difference from an autoencoder or a generative model is that it never reconstructs
the raw input. Pixels contain a great deal that is unpredictable noise, and forcing a model to
reproduce them wastes its capacity on detail nobody needs. Predicting in embedding space lets
the model keep only what is actually predictable.

That is a good match for a price chart, where most of the pixel-level detail is noise and a
technical analyst claims to read the *shape*.

WHAT THIS ONE ACTUALLY DOES
  1. Draws the last 52 weeks as a real picture: a 24 x 52 grid, price normalised to the window,
     with the line drawn between consecutive closes. Normalising inside the window means the
     model sees the SHAPE of the chart and never the price level, which is the point of
     technical analysis and also stops it memorising "2021 was expensive".
  2. Cuts the picture into 13 vertical strips of 4 weeks.
  3. Context = the first 10 strips. Target = the last 3. An encoder embeds both, a predictor
     tries to guess the target embeddings from the context ones, and the loss is measured
     between embeddings - never between pixels.
  4. The target encoder is an exponential moving average of the online encoder, with no
     gradient, which is the standard way to stop a JEPA collapsing to a constant.
  5. For the trading signal it runs the predictor one strip PAST the end of the chart, giving a
     predicted embedding of the four weeks that have not happened yet, and a small logistic
     probe turns that into P(up next week).

COLLAPSE IS THE FAILURE MODE, SO IT IS MEASURED
A JEPA can cheat by mapping everything to the same point: the prediction is then perfect and
the embedding useless. `collapse_score()` reports the average standard deviation of the
embedding dimensions across the training set. Near zero means collapsed and the seat should be
ignored. It is recorded on every run and printed in the results, not quietly dropped.

HONEST LIMITS
  - About 680 weekly charts is a tiny dataset for this architecture. It is kept deliberately
    small (a few thousand parameters) and is still the most overfit-prone seat on the panel.
  - The panel already has a latent-dynamics model (the neuroplastic world model), so the two
    could agree for the wrong reasons. The agreement matrix on the dashboard is the check.
  - Rendering a series as a picture cannot add information that was not in the series. The
    claim is only that the grid emphasises shape over level.
"""
import math

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

WINDOW = 52          # weeks of chart the model looks at
ROWS = 24            # vertical resolution of the picture
PATCH = 4            # weeks per vertical strip
N_CONTEXT = 10       # strips the model may see
EMB = 32             # embedding width
EMA = 0.996          # how slowly the target encoder follows the online one
VAR_WEIGHT = 1.0     # strength of the anti-collapse term
VAR_FLOOR = 1.0      # each embedding dimension should keep at least this much spread
N_PATCH = WINDOW // PATCH


def render_chart(prices):
    """Draw a price window as a real picture: ROWS x WINDOW, values in [0, 1].

    The window is scaled to its own high and low, so only the shape survives: the same pattern
    at $300 and at $60,000 renders identically.
    """
    p = np.asarray(prices, dtype=float)
    lo, hi = p.min(), p.max()
    y = np.zeros_like(p) if hi - lo < 1e-12 else (p - lo) / (hi - lo)
    rowf = np.clip(y * (ROWS - 1), 0, ROWS - 1)
    img = np.zeros((ROWS, len(p)), dtype=np.float32)
    for c in range(len(p)):
        img[int(round(rowf[c])), c] = 1.0
        if c:                                            # join the dots, so it is a line not dots
            a, b = sorted((int(round(rowf[c - 1])), int(round(rowf[c]))))
            img[a:b + 1, c] = np.maximum(img[a:b + 1, c], 0.6)
    return img


def to_patches(img):
    """Cut the picture into vertical strips: (N_PATCH, ROWS * PATCH)."""
    return np.stack([img[:, i * PATCH:(i + 1) * PATCH].reshape(-1) for i in range(N_PATCH)])


class Encoder(nn.Module):
    """One strip of chart -> one embedding. Deliberately small: the dataset is ~680 charts."""

    def __init__(self, dim_in):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(dim_in, 64), nn.GELU(), nn.Linear(64, EMB), nn.LayerNorm(EMB))

    def forward(self, x):
        return self.net(x)


class Predictor(nn.Module):
    """Context embeddings + 'which strip am I predicting' -> that strip's embedding."""

    def __init__(self):
        super().__init__()
        self.pos = nn.Embedding(N_PATCH + 1, EMB)        # +1: one strip past the end of the chart
        self.net = nn.Sequential(nn.Linear(EMB * 2, 64), nn.GELU(), nn.Linear(64, EMB))

    def forward(self, ctx, positions):
        ctx = ctx.unsqueeze(1).expand(-1, positions.size(1), -1)
        return self.net(torch.cat([ctx, self.pos(positions)], dim=-1))


class ChartJEPA:
    """Trains on one expanding window of history, then scores weeks out of sample."""

    def __init__(self, seed=0, steps=600, lr=2e-3):
        self.seed, self.steps, self.lr = seed, steps, lr
        self.enc = self.tgt = self.pred = None
        self.probe = None
        self.stats = {}

    # ---- training -------------------------------------------------------------------------
    def fit(self, charts, y_next):
        """charts: (N, N_PATCH, dim) strips per week. y_next: 1 if the next week rose."""
        torch.manual_seed(self.seed)
        np.random.seed(self.seed)
        X = torch.tensor(charts, dtype=torch.float32)
        dim = X.shape[-1]
        self.enc, self.pred = Encoder(dim), Predictor()
        self.tgt = Encoder(dim)
        self.tgt.load_state_dict(self.enc.state_dict())
        for p in self.tgt.parameters():
            p.requires_grad_(False)

        opt = torch.optim.AdamW(list(self.enc.parameters()) + list(self.pred.parameters()),
                                lr=self.lr, weight_decay=1e-4)
        tgt_pos = torch.arange(N_CONTEXT, N_PATCH)
        n = len(X)
        for _ in range(self.steps):
            idx = torch.randint(0, n, (min(64, n),))
            batch = X[idx]
            ctx = self.enc(batch[:, :N_CONTEXT]).mean(1)                 # what the model may see
            with torch.no_grad():
                want = self.tgt(batch[:, N_CONTEXT:])                    # what it must predict
            got = self.pred(ctx, tgt_pos.expand(len(batch), -1))
            loss = F.mse_loss(got, want)
            # anti-collapse: every embedding dimension must keep some spread across the batch
            std = torch.sqrt(ctx.var(dim=0) + 1e-6)
            loss = loss + VAR_WEIGHT * torch.relu(VAR_FLOOR - std).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            with torch.no_grad():                                        # EMA target encoder
                for a, b in zip(self.tgt.parameters(), self.enc.parameters()):
                    a.mul_(EMA).add_(b, alpha=1 - EMA)

        # a logistic probe on the PREDICTED next-strip embedding, fitted on training weeks only
        from sklearn.linear_model import LogisticRegression
        feats = self.future_embedding(charts)
        self.probe = LogisticRegression(C=0.3, max_iter=2000, class_weight="balanced").fit(feats, y_next)
        with torch.no_grad():
            emb = self.enc(X[:, :N_CONTEXT]).mean(1)
        self.stats = {"collapse_score": float(emb.std(dim=0).mean()), "loss": float(loss.detach()),
                      "n_charts": int(n), "params": sum(p.numel() for p in self.enc.parameters())
                                                  + sum(p.numel() for p in self.pred.parameters())}
        return self

    # ---- scoring --------------------------------------------------------------------------
    @torch.no_grad()
    def future_embedding(self, charts):
        """Run the predictor one strip PAST the chart: the four weeks that have not happened."""
        X = torch.tensor(np.atleast_3d(charts), dtype=torch.float32)
        ctx = self.enc(X[:, :N_CONTEXT]).mean(1)
        nxt = torch.full((len(X), 1), N_PATCH, dtype=torch.long)
        return self.pred(ctx, nxt).squeeze(1).numpy()

    def p_up(self, chart):
        """P(Bitcoin is higher in 7 days) implied by the predicted next piece of the chart."""
        return float(self.probe.predict_proba(self.future_embedding(chart[None]))[0, 1])

    def collapse_score(self):
        """Average spread of the embedding dimensions. Near zero means the JEPA collapsed."""
        return self.stats.get("collapse_score", float("nan"))


def build_charts(weekly_price, dates):
    """One rendered chart per date, using only the WINDOW weeks up to and including it."""
    p = weekly_price
    out, keep = [], []
    for d in dates:
        hist = p.loc[:d]
        if len(hist) < WINDOW:
            continue
        out.append(to_patches(render_chart(hist.iloc[-WINDOW:].values)))
        keep.append(d)
    return np.asarray(out, dtype=np.float32), keep
