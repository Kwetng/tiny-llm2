"""
borrowers.py - the synthetic corporate borrowers and the credit questions.

Identical generator, seed and split to ../../jev-credit-decisions/code/credit_jev_llm.py,
so the 400 test borrowers here are exactly the ones used in the Jev credit project.

  3,000 borrowers = 2,000 notes-only (not used here) + 600 labelled (train) + 400 hold-out (test)
  y = 1 means the borrower DEFAULTED within 12 months (did not repay).
"""
import numpy as np

FEATURES = ["leverage_x", "interest_cover_x", "current_ratio", "ebitda_margin", "revenue_growth", "cash_to_assets"]
SECTORS = ["industrials", "retail", "technology", "energy"]
T_OBS, T_FUT = 8, 4
SEED = 11


def make_borrowers(n, rng):
    sector = rng.integers(0, len(SECTORS), n)
    sector_lev = np.array([0.4, 0.8, -0.3, 0.6])[sector]
    T = T_OBS + T_FUT
    h = np.zeros((n, T))
    h0, drift = rng.normal(0, 1, n), rng.normal(0, 0.22, n)
    shock_q = rng.integers(4, T, n)
    shock = np.where(rng.random(n) < 0.15, rng.normal(-0.8, 0.3, n), 0.0)
    for t in range(T):
        prev = h0 if t == 0 else h[:, t - 1]
        h[:, t] = prev + drift + rng.normal(0, 0.12, n) + np.where(shock_q == t, shock, 0)
    X = np.zeros((n, T, len(FEATURES)))
    noise = lambda s: rng.normal(0, s, (n, T))
    X[..., 0] = np.clip(3.0 - 0.9 * h + sector_lev[:, None] + noise(0.55), 0.2, 12)
    X[..., 1] = np.clip(4.5 + 1.8 * h + noise(0.9), 0.1, 25)
    X[..., 2] = np.clip(1.4 + 0.25 * h + noise(0.15), 0.3, 4)
    X[..., 3] = 0.14 + 0.04 * h + noise(0.02)
    X[..., 4] = 0.01 + 0.10 * drift[:, None] + 0.02 * h + noise(0.03)
    X[..., 5] = np.clip(0.08 + 0.02 * h + noise(0.02), 0, 1)
    stress = np.minimum(h[:, T_OBS:], 0).sum(1)
    pd_true = 1 / (1 + np.exp(-(-2.9 - 1.35 * h[:, -1] + 0.35 * stress)))
    y = (rng.random(n) < pd_true).astype(int)
    view = drift + rng.normal(0, 0.12, n) + 0.3 * np.where(shock_q < T_OBS, shock, 0)
    outlook = np.where(view < -0.12, "negative", np.where(view > 0.12, "positive", "stable"))
    phrases = {
        "negative": ["Management reports softer orders and rising input costs.", "Covenant headroom is narrowing on the leverage test.",
                     "Customer concentration is a concern after a key contract loss.", "Working capital has absorbed cash for two quarters.",
                     "Refinancing of the term loan is not yet agreed."],
        "stable": ["Trading is in line with budget and guidance is unchanged.", "Leverage is steady with comfortable covenant headroom.",
                   "Order book is flat and margins are holding.", "No change to the funding structure is expected."],
        "positive": ["Order book is strengthening and pricing is firm.", "Deleveraging is ahead of plan after asset disposals.",
                     "New contracts extend revenue visibility.", "Free cash flow is supporting early debt repayment."],
    }
    notes = []
    for i in range(n):
        p = rng.choice(phrases[outlook[i]], 2, replace=False)
        notes.append(f"Outlook {outlook[i]}. {p[0]} {p[1]} Sector: {SECTORS[sector[i]]}.")
    return X[:, :T_OBS], y, notes, sector, pd_true, outlook


class Portfolio:
    def __init__(self, quick=False, extra_test=0):
        """extra_test > 0 appends that many further hold-out borrowers from an independent draw (seed 12),
        leaving the original 400 unchanged. 400 test borrowers hold only ~17 defaults, too few to tell two
        good models apart; 3,600 extra (4,000 in total, ~170 defaults) narrows the AUC interval about 3x."""
        n_notes, n_train, n_test = (800, 400, 150) if quick else (2000, 600, 400)
        rng = np.random.default_rng(SEED)
        parts = [make_borrowers(n_notes + n_train + n_test, rng)]
        if extra_test:
            parts.append(make_borrowers(extra_test, np.random.default_rng(SEED + 1)))
        self.X, self.y = np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts])
        self.notes = [t for p in parts for t in p[2]]
        self.sector, self.pd_true, self.outlook = (np.concatenate([p[k] for p in parts]) for k in (3, 4, 5))
        self.idx_train = np.arange(n_notes, n_notes + n_train)
        self.idx_test = np.arange(n_notes + n_train, len(self.y))

    def state(self, i):
        """The JSON 'state' both decision models read: what a credit analyst sees today."""
        X, latest, prior = self.X, self.X[i, -1], self.X[i, -5]
        r3 = lambda v: round(float(v), 3)
        return {
            "borrower_id": int(i), "sector": SECTORS[self.sector[i]],
            "facility": {"type": "senior secured term loan", "tenor_years": 5, "amortising": True},
            "latest_quarter": dict(zip(FEATURES, map(r3, latest))),
            "change_over_4_quarters": dict(zip(FEATURES, map(r3, latest - prior))),
            "last_8_quarters_leverage_x": [r3(v) for v in X[i, :, 0]],
            "analyst_note": self.notes[i],
        }

    def scorecard_features(self, idx):
        return np.concatenate([self.X[idx, -1], self.X[idx, -1] - self.X[idx, -5]], 1)


# Byte-identical questions for both models: only the model changes between the two runs.
QUESTIONS = {
    "can_repay": {"type": "noul",
        "instructions": ("Will this corporate borrower be able to meet every scheduled interest and principal "
                         "payment on the facility over the next 12 months, without restructuring or default?"),
        "criteria": {"true": "Debt service is covered by earnings and liquidity, and the trend and outlook do not "
                             "point to a payment shortfall within 12 months.",
                     "false": "Leverage, weak interest cover, thin liquidity, a deteriorating trend or a negative "
                              "outlook make a missed payment, restructuring or default within 12 months likely."}},
    "main_risk": {"type": "choice",
        "instructions": "Which factor is the main risk to repayment?",
        "criteria": {"leverage": "Debt is high relative to earnings or rising.",
                     "liquidity": "Short-term liquidity or working capital is tight.",
                     "profitability": "Margins or interest cover are weak.",
                     "business outlook": "The qualitative outlook is deteriorating.",
                     "none material": "No material risk to repayment."}},
    "risk_grade": {"type": "score",
        "instructions": "Grade the borrower's overall credit quality.",
        "criteria": ["Strong: very low risk", "Good: low risk", "Satisfactory: moderate risk",
                     "Weak: high risk", "Very weak: default likely"]},
}
