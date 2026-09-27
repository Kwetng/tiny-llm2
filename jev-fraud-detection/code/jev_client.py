"""
jev_client.py - minimal Jev client for transaction fraud scoring.

Jev (TypeSafe AI) is a "System One" decision model: it reads a text or JSON
"state" and answers typed questions with calibrated numbers:
  noul   -> probability (0-1) that a yes/no proposition is true
  choice -> one of several named categories, with a probability
  score  -> a level on an ordered scale

API (as used in github.com/pniessen/jev-test and the llm-typesafe plugin):

    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer $TYPESAFE_API_KEY
    {"model": "jev-latest", "state": {...}, "questions": {"<id>": {"type": ..., "instructions": ..., "criteria": ...}}}
    -> {"model": "...", "answers": {"<id>": {...}}, "usage": {"input_tokens": n}}

If TYPESAFE_API_KEY is not set, or --offline is passed, LocalFraudStandIn is used.
It is NOT Jev: it is a transparent, hand-written rule model that returns answers in
Jev's format, so the whole pipeline can be run and tested anywhere.
"""
import json, math, os, time, urllib.error, urllib.request

API_URL = "https://api.typesafe.ai/v1/systemone"


class JevClient:
    name = "Jev (TypeSafe AI, live API)"

    def __init__(self, api_key=None, model="jev-latest", timeout=30):
        self.key = api_key or os.environ["TYPESAFE_API_KEY"]
        self.model, self.timeout = model, timeout
        self.input_tokens = 0

    def ask(self, state, questions):
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode()
        for attempt in range(5):
            req = urllib.request.Request(API_URL, data=body, headers={
                "Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.load(r)
                self.input_tokens += data.get("usage", {}).get("input_tokens", 0)
                return {"model": data.get("model", self.model), "answers": data["answers"]}
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(0.5 * (attempt + 1)); continue
                raise RuntimeError(f"Jev HTTP {e.code}: {e.read()[:300]!r}") from None
            except urllib.error.URLError:
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError("Jev request failed after 5 attempts")


class LocalFraudStandIn:
    """Offline stand-in with Jev's response format. NOT Jev.

    Zero-shot like Jev: no labels are used. The judgement is a fixed, hand-written
    rule over the behavioural signals, plus a short list of scam phrases in the
    payment description (a real language-understanding model would read the text
    far more flexibly than a keyword list).
    """
    name = "LOCAL STAND-IN (not Jev) - set TYPESAFE_API_KEY to use the real model"

    SCAM_PHRASES = ("safe account", "hmrc", "crypto", "investment", "bank details", "customs fee",
                    "security team", "protect savings", "trading platform", "gift card", "giftcard", "voucher")

    def __init__(self):
        self.input_tokens = 0

    def ask(self, state, questions):
        t, c = state["transaction"], state["customer_context"]
        desc = t["description"].lower()
        payment = t["channel"] == "faster_payment"
        scam_words = any(p in desc for p in self.SCAM_PHRASES)
        age = c["payee_account_age_days"]
        young_payee = age is not None and age < 90
        ratio = c["amount_vs_customer_median"]

        s = -5.2
        s += 1.5 * c["new_device"] + 1.3 * c["password_reset_last_24h"]
        s += 0.8 * (payment and c["minutes_since_login"] is not None and c["minutes_since_login"] < 5)
        s += 0.30 * min(c["transactions_last_hour"], 12)
        s += 0.9 * (c["new_payee_or_merchant"] and ratio > 5)
        s += 0.4 * math.log1p(ratio)
        s += 0.9 * young_payee + 0.6 * t["abroad"] + 0.5 * c["unusual_hour_for_customer"]
        s += 1.8 * scam_words
        p = 1 / (1 + math.exp(-0.75 * s))

        # fraud-type choice from which pattern dominates
        ato = 1.5 * c["new_device"] + 1.3 * c["password_reset_last_24h"] + (payment and (c["minutes_since_login"] or 99) < 5)
        card = 0.3 * c["transactions_last_hour"] + (t["channel"] == "card_online") + 0.6 * t["abroad"]
        app = 1.8 * scam_words + 0.9 * young_payee + (payment and c["new_payee_or_merchant"] and ratio > 5 and not c["new_device"])
        scores = {"card fraud (card not present)": card, "account takeover": ato, "authorised push payment scam": app}
        kind = max(scores, key=scores.get) if p >= 0.2 else "genuine"

        answers = {}
        for qid, q in questions.items():
            if q["type"] == "noul":
                answers[qid] = {"noul": p, "confidence": abs(p - 0.5) * 2}
            elif q["type"] == "choice":
                answers[qid] = {"choice": kind, "probability": 0.5 + 0.45 * abs(p - 0.5) * 2}
        return {"model": "local-stand-in", "answers": answers}


def get_jev(offline=False):
    if not offline and os.environ.get("TYPESAFE_API_KEY"):
        return JevClient()
    return LocalFraudStandIn()
