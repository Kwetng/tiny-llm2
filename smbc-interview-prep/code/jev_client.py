"""
jev_client.py - minimal client for Jev, TypeSafe AI's "System One" decision model.

Jev takes a text or JSON "state" plus one or more questions, and returns
calibrated numbers instead of generated text:
  - noul   : probability (0-1) that a yes/no proposition is true
  - choice : pick one of several named categories, with a probability
  - score  : a degree on an ordered scale of 2-10 levels

Request format (as used in the public benchmark github.com/pniessen/jev-test and
the llm-typesafe plugin):

    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer $TYPESAFE_API_KEY
    {"model": "jev-latest",
     "state": <string | object | array>,
     "questions": {"<id>": {"type": "noul"|"choice"|"score",
                            "instructions": "...",
                            "criteria": ...optional...}}}

    -> {"model": "...", "answers": {"<id>": {...}}, "usage": {"input_tokens": n, ...}}

For a noul question the answer holds the probability under the key "noul".

If TYPESAFE_API_KEY is not set (or --offline is used), LocalJevStandIn is used
instead. It is NOT Jev: it is a transparent, hand-written rule model with the same
response shape, so the rest of the pipeline can be run and tested anywhere.
"""
import json, math, os, time, urllib.error, urllib.request

API_URL = "https://api.typesafe.ai/v1/systemone"


class JevClient:
    """Calls the real Jev API."""
    name = "Jev (TypeSafe AI, live API)"

    def __init__(self, api_key=None, model="jev-latest", timeout=60):
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
                    time.sleep(0.6 * (attempt + 1)); continue
                raise RuntimeError(f"Jev HTTP {e.code}: {e.read()[:300]!r}") from None
            except urllib.error.URLError:
                time.sleep(0.6 * (attempt + 1))
        raise RuntimeError("Jev request failed after 5 attempts")


class LocalJevStandIn:
    """Offline stand-in with Jev's response shape. NOT Jev.

    Like Jev in this use, it is zero-shot: it uses no default labels. Its judgement
    is a fixed, hand-written expert rule over the ratios and the analyst note.
    """
    name = "LOCAL STAND-IN (not Jev) - set TYPESAFE_API_KEY to use the real model"

    NEG = ("softer orders", "narrowing", "contract loss", "absorbed cash", "not yet agreed")
    POS = ("strengthening", "ahead of plan", "revenue visibility", "early debt repayment")

    def __init__(self):
        self.input_tokens = 0

    def ask(self, state, questions):
        s = state if isinstance(state, dict) else json.loads(state)
        r, chg, note = s["latest_quarter"], s["change_over_4_quarters"], s["analyst_note"].lower()
        neg = sum(k in note for k in self.NEG)
        pos = sum(k in note for k in self.POS)
        logit = (3.2 - 0.55 * (r["leverage_x"] - 3.0) + 0.22 * (r["interest_cover_x"] - 4.5)
                 + 1.5 * (r["current_ratio"] - 1.4) + 8.0 * (r["ebitda_margin"] - 0.14)
                 - 0.45 * chg["leverage_x"] + 0.12 * chg["interest_cover_x"] - 0.7 * neg + 0.4 * pos)
        logit = 3.0 + 0.4 * (logit - 3.2)          # temper the rule's confidence (set by judgement, not fitted)
        p_repay = 1 / (1 + math.exp(-logit))
        answers = {}
        for qid, q in questions.items():
            if q["type"] == "noul":
                answers[qid] = {"noul": p_repay, "confidence": abs(p_repay - 0.5) * 2}
            elif q["type"] == "choice":
                cats = list(q["criteria"])
                pressure = {
                    cats[0]: (r["leverage_x"] - 3.0) / 1.5 + chg["leverage_x"],                 # leverage
                    cats[1]: (1.4 - r["current_ratio"]) / 0.3,                                  # liquidity
                    cats[2]: (0.14 - r["ebitda_margin"]) / 0.04 + (4.5 - r["interest_cover_x"]) / 2,  # profitability
                    cats[3]: neg - pos,                                                         # outlook
                }
                top = max(pressure, key=pressure.get)
                pick = top if pressure[top] > 0.8 else cats[-1]                                 # none material
                answers[qid] = {"choice": pick, "probability": min(0.95, 0.5 + 0.1 * max(pressure[top], 0))}
            elif q["type"] == "score":
                levels = len(q["criteria"])
                answers[qid] = {"score": min(levels, 1 + int((1 - p_repay) * levels * 2.5))}
        return {"model": "local-stand-in", "answers": answers}


def get_jev(offline=False):
    if not offline and os.environ.get("TYPESAFE_API_KEY"):
        return JevClient()
    return LocalJevStandIn()
