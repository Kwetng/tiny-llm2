"""
jev_market.py - Jev client for market questions, plus an offline stand-in.

Jev (TypeSafe AI) is a "System One" decision model: it reads a JSON state and answers
typed questions with calibrated numbers (noul = probability, choice = category).
API format as used in github.com/pniessen/jev-test:

    POST https://api.typesafe.ai/v1/systemone
    {"model": "jev-latest", "state": {...}, "questions": {...}}

If TYPESAFE_API_KEY is not set, LocalMarketStandIn is used. It is NOT Jev: it is a
hand-written, zero-label trend + valuation rule with Jev's response format.
"""
import json, math, os, time, urllib.error, urllib.request

API_URL = "https://api.typesafe.ai/v1/systemone"

QUESTIONS = {
    "up_next_week": {"type": "noul",
        "instructions": "Given this snapshot of the Bitcoin market, will the Bitcoin price be higher in 7 days than it is now?",
        "criteria": {"true": "Trend, valuation, on-chain activity and risk appetite point to a higher price in a week.",
                     "false": "They point to a lower price in a week."}},
    "regime": {"type": "choice",
        "instructions": "Which market regime best describes Bitcoin right now?",
        "criteria": {"bull trend": "Prices rising steadily over recent months.",
                     "bear trend": "Prices falling steadily over recent months.",
                     "range-bound": "No clear direction.",
                     "capitulation": "A deep crash with very high volatility.",
                     "euphoria": "Prices far above the average cost basis of holders; overheated."}},
}


class JevClient:
    name = "Jev (TypeSafe AI, live API)"

    def __init__(self, api_key=None, model="jev-latest"):
        self.key, self.model = api_key or os.environ["TYPESAFE_API_KEY"], model

    def ask(self, state, questions=QUESTIONS):
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode()
        for attempt in range(5):
            req = urllib.request.Request(API_URL, data=body, headers={
                "Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.load(r)
                return {"model": data.get("model", self.model), "answers": data["answers"]}
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(0.5 * (attempt + 1)); continue
                raise RuntimeError(f"Jev HTTP {e.code}") from None
            except urllib.error.URLError:
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError("Jev request failed")


class LocalMarketStandIn:
    """NOT Jev. A fixed, zero-label rule: follow the 12-week and 4-week trend, lean against
    extreme valuation (MVRV), and be cautious when equity-market fear (VIX) is high."""
    name = "LOCAL STAND-IN (not Jev) - set TYPESAFE_API_KEY to use the real model"

    def ask(self, state, questions=QUESTIONS):
        s = state["snapshot"]
        m12, m4, mvrv, vix, addr, dd, vol = (s["return_12w"], s["return_4w"], s["mvrv"], s["vix"],
                                             s["active_addresses_change_4w"], s["drawdown_from_52w_high"], s["volatility_4w"])
        z = (2.0 * math.tanh(m12 / 0.25) + 1.0 * math.tanh(m4 / 0.10) - 1.2 * (mvrv > 3.2) + 1.0 * (mvrv < 1.0)
             - 0.5 * (vix > 30) + 0.4 * math.tanh(addr / 0.10) + 0.3)
        p = 1 / (1 + math.exp(-0.28 * z))
        if dd < -0.45 and vol > 0.9:
            regime = "capitulation"
        elif mvrv > 3.0:
            regime = "euphoria"
        elif m12 > 0.15:
            regime = "bull trend"
        elif m12 < -0.15:
            regime = "bear trend"
        else:
            regime = "range-bound"
        return {"model": "local-stand-in",
                "answers": {"up_next_week": {"noul": p, "confidence": abs(p - 0.5) * 2},
                            "regime": {"choice": regime, "probability": 0.6}}}


def get_jev(offline=False):
    if not offline and os.environ.get("TYPESAFE_API_KEY"):
        return JevClient()
    return LocalMarketStandIn()
