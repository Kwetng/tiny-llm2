"""
hmm_regime.py - the regime seat: a hidden Markov model that works out which market we are in.

THE IDEA
Markets do not behave the same way all the time. There are quiet drifting stretches, violent
falls, and sharp recoveries, and the same signal means different things in each. A hidden Markov
model formalises that: it assumes the market is always in one of K hidden states, that each state
produces returns with its own average and its own volatility, and that it switches between states
with fixed probabilities. Nobody labels the states - the model discovers them from the data.

WHAT IT OBSERVES
Two numbers a week: the log return, and four-week volatility. Returns alone would separate up
from down; adding volatility separates a calm 2% rise from a panicky one, which is the
distinction that matters when deciding whether to hold a position.

HOW IT LEARNS
Baum-Welch, the expectation-maximisation algorithm for HMMs, implemented here rather than
imported so the filtering is under our control. It alternates between working out which state
each past week was probably in, and re-estimating each state's average, volatility and switching
probabilities from that.

THE BUG THIS FILE EXISTS TO AVOID
Baum-Welch uses the FORWARD-BACKWARD algorithm, whose output - the smoothed probability - answers
"knowing everything that happened, which state was week t in?" That is the right question when
fitting, and completely the wrong one when trading, because the backward pass walks through the
future. A backtest built on smoothed probabilities looks superb and cannot be repeated live. It
is the single most common way an HMM strategy fools its author.

So this file keeps them apart:
  fit()        uses forward-backward, on training data only, because it is estimating parameters
  filter()     uses the FORWARD PASS ONLY, and answers "given everything up to today, and nothing
               after it, which state are we in?" That is what the panel votes on.
A test fixes this by construction: filtering a truncated series must give the same answer for the
last week as filtering the whole series.

HOW IT VOTES
Given today's state probabilities, the model knows where it is likely to switch next, and each
state's return distribution is a Gaussian it has already estimated. So the probability that next
week is positive can be written down exactly, as a mixture:

    P(next return > 0) = sum over states k of  P(in state k now) x
                         sum over states j of  P(k -> j) x  Phi( mu_j / sigma_j )

No extra model is fitted on top and no threshold is tuned: the probability falls out of the HMM.

WHAT IT CANNOT DO
It detects that a regime HAS changed, not that one is ABOUT to. Filtering needs evidence, and
evidence arrives as returns, so the seat turns bearish after a fall has started rather than
before. That is a real limitation of the method and not a tuning problem.
"""
import numpy as np
from scipy.stats import norm

N_STATES = 3
EPS = 1e-300


def _gaussian_logpdf(X, mu, var):
    """log N(x | mu, diag(var)) for every observation against every state: (T, K)."""
    X = np.atleast_2d(X)
    d = X[:, None, :] - mu[None, :, :]
    return -0.5 * (np.log(2 * np.pi * var)[None, :, :] + d ** 2 / var[None, :, :]).sum(axis=2)


class RegimeHMM:
    """Gaussian HMM with diagonal covariance, fitted by Baum-Welch."""

    def __init__(self, n_states=N_STATES, n_iter=60, seed=0, tol=1e-4):
        self.K, self.n_iter, self.seed, self.tol = n_states, n_iter, seed, tol
        self.pi = self.A = self.mu = self.var = None
        self.stats = {}

    # ---- forward pass: uses the past only. This is what the panel is allowed to see. ----
    def _forward(self, logB):
        T, K = logB.shape
        alpha = np.zeros((T, K))
        scale = np.zeros(T)
        B = np.exp(logB - logB.max(axis=1, keepdims=True))     # rescaled, so nothing underflows
        a = self.pi * B[0]
        scale[0] = a.sum() + EPS
        alpha[0] = a / scale[0]
        for t in range(1, T):
            a = (alpha[t - 1] @ self.A) * B[t]
            scale[t] = a.sum() + EPS
            alpha[t] = a / scale[t]
        return alpha, np.log(scale) + logB.max(axis=1)

    # ---- backward pass: uses the future. Fitting only, NEVER inference. ----
    def _backward(self, logB, alpha):
        T, K = logB.shape
        B = np.exp(logB - logB.max(axis=1, keepdims=True))
        beta = np.zeros((T, K))
        beta[-1] = 1.0
        for t in range(T - 2, -1, -1):
            b = self.A @ (B[t + 1] * beta[t + 1])
            beta[t] = b / (b.sum() + EPS)
        return beta

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        T, D = X.shape
        order = np.argsort(X[:, 0])                            # seed the states by return, low to high
        chunks = np.array_split(order, self.K)
        self.mu = np.stack([X[c].mean(axis=0) for c in chunks])
        self.var = np.stack([X[c].var(axis=0) + 1e-6 for c in chunks])
        self.pi = np.full(self.K, 1 / self.K)
        self.A = np.full((self.K, self.K), 0.1 / (self.K - 1))
        np.fill_diagonal(self.A, 0.9)                          # regimes persist; start there

        prev = -np.inf
        for it in range(self.n_iter):
            logB = _gaussian_logpdf(X, self.mu, self.var)
            alpha, logscale = self._forward(logB)
            beta = self._backward(logB, alpha)
            loglik = float(logscale.sum())

            gamma = alpha * beta
            gamma /= gamma.sum(axis=1, keepdims=True) + EPS
            Bn = np.exp(logB - logB.max(axis=1, keepdims=True))
            xi = np.zeros((self.K, self.K))
            for t in range(T - 1):
                m = np.outer(alpha[t], Bn[t + 1] * beta[t + 1]) * self.A
                xi += m / (m.sum() + EPS)

            self.pi = gamma[0] / (gamma[0].sum() + EPS)
            self.A = xi / (xi.sum(axis=1, keepdims=True) + EPS)
            w = gamma.sum(axis=0) + EPS
            self.mu = (gamma.T @ X) / w[:, None]
            self.var = np.maximum((gamma.T @ (X ** 2)) / w[:, None] - self.mu ** 2, 1e-8)

            if abs(loglik - prev) < self.tol * abs(prev if prev else 1.0):
                break
            prev = loglik

        self._sort_states()
        self.stats = {"loglik": float(prev), "iters": it + 1, "states": self.K,
                      "mean_weekly_return": [float(m) for m in self.mu[:, 0]],
                      "weekly_vol": [float(np.sqrt(v)) for v in self.var[:, 0]],
                      "persistence": [float(self.A[k, k]) for k in range(self.K)],
                      "labels": self.labels()}
        return self

    def _sort_states(self):
        """Order states from worst average return to best, so state 0 is always the bad one."""
        order = np.argsort(self.mu[:, 0])
        self.mu, self.var, self.pi = self.mu[order], self.var[order], self.pi[order]
        self.A = self.A[np.ix_(order, order)]

    def labels(self):
        """A plain-English name for each state, from what it actually looks like.

        Ranked rather than split at the median: with 3+ states a median split can leave two
        states on the same side and therefore the same word, which reads as a bug to anyone
        looking at the dashboard even though the underlying states are perfectly distinct.
        Ranking guarantees the lowest-volatility state is always "calm" and the highest always
        "volatile", with anything in between called "choppy".
        """
        vols = np.sqrt(self.var[:, 0])
        order = np.argsort(vols)                                       # low to high volatility
        word = {}
        for rank, k in enumerate(order):
            if self.K <= 2:
                word[k] = "calm" if rank == 0 else "volatile"
            else:
                word[k] = "calm" if rank == 0 else "volatile" if rank == len(order) - 1 else "choppy"
        out = []
        for k in range(self.K):
            move = "falling" if self.mu[k, 0] < -0.002 else "rising" if self.mu[k, 0] > 0.002 else "flat"
            out.append(f"{word[k]} and {move}")
        return out

    # ---- inference: forward only, so it never sees the future ----
    def filter(self, X):
        """State probabilities for every week, using only that week and the ones before it."""
        alpha, _ = self._forward(_gaussian_logpdf(np.asarray(X, dtype=float), self.mu, self.var))
        return alpha

    def p_up_next(self, filtered_row):
        """P(next week's return > 0), exactly, as a mixture over where we might switch to."""
        nxt = np.asarray(filtered_row) @ self.A
        per_state = norm.cdf(self.mu[:, 0] / np.sqrt(self.var[:, 0]))
        return float(nxt @ per_state)

    def describe(self, filtered_row):
        k = int(np.argmax(filtered_row))
        return {"state": k, "label": self.labels()[k], "confidence": float(filtered_row[k]),
                "mean_weekly_return": float(self.mu[k, 0]), "weekly_vol": float(np.sqrt(self.var[k, 0])),
                "stay_probability": float(self.A[k, k])}


def observations(weekly):
    """What the model watches: the weekly log return and four-week volatility."""
    return np.column_stack([weekly["ret_1w"].values, weekly["vol_4w"].values])
