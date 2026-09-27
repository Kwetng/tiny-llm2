"""
scorer.py - scores ONE transaction with the exported model bundle, exactly as the batch pipeline does.

Steps for each transaction (same order as the guide):
  1. mini LLM surprise of the description (bits per character) and its percentile against normal text
  2. Jev: P(fraud) and fraud type (real API if TYPESAFE_API_KEY is set, otherwise the labelled stand-in)
  3. challenger: gradient-boosted trees on behaviour + the surprise score
  4. decision engine: combined risk -> band -> overrides that can only make the action stricter
  5. reason codes and the fixed customer message

The bundle is produced by:  python code/fraud_jev_llm.py --offline --export-bundle gcp/model_bundle
"""
import hashlib, json, math, os, time
from pathlib import Path

import joblib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from jev_client import get_jev

RANK = {"ALLOW": 0, "STEP-UP": 1, "HOLD": 2, "BLOCK": 3}


class _Block(nn.Module):
    def __init__(self, ne, nh, block):
        super().__init__()
        self.ne, self.nh = ne, nh
        self.ln1, self.ln2 = nn.LayerNorm(ne), nn.LayerNorm(ne)
        self.qkv, self.proj = nn.Linear(ne, 3 * ne), nn.Linear(ne, ne)
        self.ff = nn.Sequential(nn.Linear(ne, 4 * ne), nn.GELU(), nn.Linear(4 * ne, ne))
        self.register_buffer("mask", torch.tril(torch.ones(block, block)))

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(self.ln1(x)).split(self.ne, 2)
        q, k, v = (t.view(B, T, self.nh, C // self.nh).transpose(1, 2) for t in (q, k, v))
        a = F.softmax(((q @ k.transpose(-2, -1)) / math.sqrt(C // self.nh)).masked_fill(self.mask[:T, :T] == 0, float("-inf")), -1)
        x = x + self.proj((a @ v).transpose(1, 2).reshape(B, T, C))
        return x + self.ff(self.ln2(x))


class _MiniGPT(nn.Module):
    def __init__(self, vocab, ne, nh, nl, block):
        super().__init__()
        self.tok, self.pos = nn.Embedding(vocab, ne), nn.Embedding(block, ne)
        self.blocks = nn.Sequential(*[_Block(ne, nh, block) for _ in range(nl)])
        self.ln_f, self.head = nn.LayerNorm(ne), nn.Linear(ne, vocab)

    def forward(self, idx):
        return self.head(self.ln_f(self.blocks(self.tok(idx) + self.pos(torch.arange(idx.size(1))))))


class FraudScorer:
    def __init__(self, bundle_dir, offline=None):
        b = Path(bundle_dir)
        self.engine = json.load(open(b / "engine.json"))
        cfg = self.engine["mini_llm"]
        self.alphabet = cfg["alphabet"]
        self.stoi = {c: i for i, c in enumerate(self.alphabet)}
        torch.set_num_threads(max(1, int(os.environ.get("TORCH_THREADS", "1"))))
        self.gpt = _MiniGPT(len(self.alphabet), cfg["n_embd"], cfg["n_head"], cfg["n_layer"], cfg["block"])
        self.gpt.load_state_dict(torch.load(b / "mini_llm.pt", map_location="cpu", weights_only=True))
        self.gpt.eval()
        self.baseline = np.load(b / "baseline_surprise.npy")
        # joblib uses pickle: only load bundles this bank produced and stored in its own bucket
        self.challenger = joblib.load(b / "challenger.joblib")  # nosec B301
        if offline is None:
            offline = os.environ.get("JEV_OFFLINE", "").lower() in ("1", "true", "yes")
        self.jev = get_jev(offline=offline)
        self.cut = self.engine["thresholds"]
        self.ov = self.engine["overrides"]
        self.versions = self.engine["versions"]

    # ---- 1. mini LLM surprise ---------------------------------------------------------------
    @torch.no_grad()
    def surprise(self, description):
        seq = [self.stoi[c] for c in "\n" + description.upper()[:60] + "\n" if c in self.stoi]
        idx = torch.tensor([seq])
        nll = F.cross_entropy(self.gpt(idx[:, :-1])[0], idx[0, 1:], reduction="mean")
        bits = float(nll / math.log(2))
        pct = float(np.searchsorted(self.baseline, bits) / len(self.baseline) * 100)
        return bits, pct

    # ---- 2. Jev --------------------------------------------------------------------------------
    @staticmethod
    def jev_state(t):
        return {"transaction": {"amount_gbp": t["amount"], "channel": t["channel"], "description": t["description"],
                                "abroad": t["abroad"], "local_hour": round(t["hour"], 1)},
                "customer_context": {"median_amount_gbp": round(t["median"], 2), "amount_vs_customer_median": round(t["amount_ratio"], 2),
                                     "new_payee_or_merchant": t["new_payee"], "payee_account_age_days": t["payee_age"],
                                     "new_device": t["new_device"], "password_reset_last_24h": t["password_reset"],
                                     "minutes_since_login": None if t["mins_since_login"] is None else round(t["mins_since_login"], 1),
                                     "transactions_last_hour": t["txns_last_hour"], "unusual_hour_for_customer": t["unusual_hour"]}}

    # ---- 3. challenger features ------------------------------------------------------------------
    def features(self, t, s_bits):
        row = [math.log1p(t["amount"]), math.log1p(t["amount_ratio"]), *[t["channel"] == c for c in self.engine["channels"]],
               t["new_payee"], -1 if t["payee_age"] is None else t["payee_age"], t["new_device"], t["password_reset"],
               -1 if t["mins_since_login"] is None else t["mins_since_login"], t["txns_last_hour"], t["abroad"],
               t["hour"], t["unusual_hour"], s_bits]
        return np.array([row], dtype=float)

    # ---- 5. reason codes -------------------------------------------------------------------------
    @staticmethod
    def reason_codes(t, s_bits, s_pct):
        r = []
        if t["new_device"]: r.append("New device for this customer")
        if t["password_reset"]: r.append("Password reset in the last 24 hours")
        if t["mins_since_login"] is not None and t["mins_since_login"] < 5: r.append(f"Payment {t['mins_since_login']:.0f} minutes after login")
        if t["amount_ratio"] >= 5: r.append(f"Amount is {t['amount_ratio']:.0f}x the customer's median (£{t['median']:.0f})")
        if t["new_payee"]: r.append("First payment to this payee or merchant")
        if t["payee_age"] is not None and t["payee_age"] < 90: r.append(f"Payee account opened {t['payee_age']:.0f} days ago")
        if t["txns_last_hour"] >= 4: r.append(f"{t['txns_last_hour']} transactions in the last hour")
        if t["abroad"]: r.append("Merchant or payee abroad")
        if t["unusual_hour"]: r.append(f"Unusual time for this customer ({int(t['hour']):02d}:{int(t['hour'] % 1 * 60):02d})")
        if s_pct >= 99: r.append(f"Description unlike normal payments (mini LLM surprise {s_bits:.1f} bits/char)")
        if t["on_mule_list"]: r.append("Payee on shared mule-account list")
        return r or ["No unusual signals"]

    # ---- the whole decision ----------------------------------------------------------------------
    def score(self, tx):
        t0 = time.perf_counter()
        t = dict(tx)
        t["amount_ratio"] = t["amount"] / t["median"]
        s_bits, s_pct = self.surprise(t["description"])
        state = self.jev_state(t)
        jev = self.jev.ask(state, self.engine["questions"])["answers"]
        p_jev, jev_type = float(jev["is_fraud"]["noul"]), jev["fraud_type"]["choice"]
        p_chal = float(self.challenger.predict_proba(self.features(t, s_bits))[0, 1])
        risk = 0.5 * p_jev + 0.5 * p_chal

        # 4. decision engine: band first, then overrides that can only make it stricter
        action = next((a for a in ("BLOCK", "HOLD", "STEP-UP") if risk >= self.cut[a]), "ALLOW")
        overrides = []

        def lift(to, reason):
            nonlocal action
            if RANK[to] > RANK[action]:
                action = to
                overrides.append(reason)

        if t["on_mule_list"]:
            lift("BLOCK", "payee account is on the shared mule-account list")
        if t["channel"] != "faster_payment" and t["txns_last_hour"] >= self.ov["card_testing_txns_last_hour"]:
            lift("BLOCK", f"{t['txns_last_hour']} card transactions in the last hour (card-testing rule)")
        if (t["channel"] == "faster_payment" and t["new_payee"] and t["amount_ratio"] >= self.ov["llm_rule_amount_ratio"]
                and s_pct >= self.ov["llm_rule_surprise_percentile"]):
            lift("STEP-UP", "payment description is unlike normal payments (mini LLM surprise in the top 0.5%)")
        if max(p_jev, p_chal) >= self.ov["confident_model"]:
            lift("HOLD", "one model is very confident this is fraud")

        message = None
        if action == "STEP-UP":
            w = jev_type if jev_type != "genuine" else (
                "authorised push payment scam" if t["channel"] == "faster_payment" and t["new_payee"] else "genuine")
            message = self.engine["warnings"][w]
        return {"action": action, "risk": round(risk, 4), "p_jev": round(p_jev, 4), "jev_fraud_type": jev_type,
                "p_challenger": round(p_chal, 4), "llm_surprise_bits": round(s_bits, 3), "llm_surprise_percentile": round(s_pct, 2),
                "overrides": overrides, "reason_codes": self.reason_codes(t, s_bits, s_pct), "customer_message": message,
                "decision_model": self.jev.name, "model_versions": self.versions,
                "input_hash": hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()[:12],
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
