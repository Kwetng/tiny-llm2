"""
decision_models.py - one interface over three decision models.

  JevModel     Jev, TypeSafe AI's closed "System One" model, called over HTTPS (needs TYPESAFE_API_KEY).
  LayaModel    Laya, Convai Innovations' open-source (Apache-2.0) alternative, run in-process
               on your own machine (pip install laya; weights download from Hugging Face once).
  StandIn      a transparent hand-written rule with the same answer shape. It is NOT Jev and NOT Laya;
               it exists only so the harness can be tested where neither model is reachable.

Both real models take the same request: a state (text or JSON) plus typed questions
(noul = probability a statement is true, choice = pick an option, score = place on an ordered scale).
Their answers differ in small but important ways, which the adapters normalise:

  noul    Jev: answers[q]["noul"] = P(true)           Laya: answers[q]["noul"] = P(true)            (same)
  choice  Jev: answers[q]["choice"] (+ probability)   Laya: "choice" + "probabilities" per option
  score   Jev: answers[q]["score"]                    Laya: EXPECTED level on a 0-based scale (0..k-1),
                                                            so a 5-level grade comes back as 0.0-4.0

Every adapter returns the same normalised record:
  {"p_repay": float, "main_risk": str, "main_risk_p": float|None, "grade": float (1 = strong .. 5 = very weak),
   "raw": <the model's own answers>, "latency_ms": float}
"""
import json, math, os, time, urllib.error, urllib.request

JEV_URL = "https://api.typesafe.ai/v1/systemone"
# Jev's score answers were taken as 1-based in the Jev credit project. Confirm on your first live
# call and set JEV_SCORE_BASE=0 if Jev returns 0-based levels.
JEV_SCORE_BASE = int(os.environ.get("JEV_SCORE_BASE", "1"))


def _normalise(answers, score_base, latency_ms, model_id):
    mr = answers.get("main_risk", {})
    p_choice = mr.get("probability")
    if p_choice is None and isinstance(mr.get("probabilities"), dict):
        p_choice = mr["probabilities"].get(mr.get("choice"))
    score = answers.get("risk_grade", {}).get("score")
    grade = None if score is None else float(score) + (1 - score_base)
    return {"p_repay": float(answers["can_repay"]["noul"]), "main_risk": mr.get("choice"),
            "main_risk_p": None if p_choice is None else float(p_choice), "grade": grade,
            "raw": answers, "latency_ms": latency_ms, "model_id": model_id}


class JevModel:
    kind, label = "jev", "Jev (TypeSafe AI, cloud API)"

    def __init__(self, model="jev-latest", timeout=60):
        self.key, self.model, self.timeout = os.environ["TYPESAFE_API_KEY"], model, timeout
        self.input_tokens = 0

    def _open(self, req):
        if not req.full_url.startswith("https://"):
            raise ValueError("HTTPS only")
        return urllib.request.urlopen(req, timeout=self.timeout)  # nosec B310

    def ask(self, state, questions):
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode()
        for attempt in range(5):
            req = urllib.request.Request(JEV_URL, data=body, headers={
                "Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
            t0 = time.perf_counter()
            try:
                with self._open(req) as r:
                    data = json.load(r)
                ms = (time.perf_counter() - t0) * 1000
                self.input_tokens += data.get("usage", {}).get("input_tokens", 0)
                return _normalise(data["answers"], JEV_SCORE_BASE, ms, data.get("model", self.model))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(0.6 * (attempt + 1)); continue
                raise RuntimeError(f"Jev HTTP {e.code}: {e.read()[:300]!r}") from None
            except urllib.error.URLError:
                time.sleep(0.6 * (attempt + 1))
        raise RuntimeError("Jev request failed after 5 attempts")


class LayaModel:
    kind = "laya"

    def __init__(self, checkpoint="english", device=None, threads=None, router=None):
        """checkpoint: 'english' (421M, 512 tokens), 'typed-decisions' (421M, fine-tuned on typed decisions)
        or 'multilingual' (322M). Pass router= to inject a pre-built laya.Router (used by the tests)."""
        import torch
        if threads:                                   # Laya's own benchmark: pin inter-op threads to 1 on CPU
            torch.set_num_threads(threads)
            try:
                torch.set_num_interop_threads(1)
            except RuntimeError:
                pass
        if router is None:
            from laya import Router
            router = Router(device=device)
        self.router, self.checkpoint = router, checkpoint
        self.label = f"Laya ({checkpoint} checkpoint, local, open source)"
        self.input_tokens = 0

    def ask(self, state, questions):
        t0 = time.perf_counter()
        res = self.router.predict(state, questions, model=self.checkpoint)
        ms = (time.perf_counter() - t0) * 1000
        self.input_tokens += res.get("usage", {}).get("input_tokens", 0) if isinstance(res.get("usage"), dict) else 0
        model_id = res.get("routing", {}).get("repo", "laya") + ":" + res.get("routing", {}).get("model", self.checkpoint)
        return _normalise(res["answers"], 0, ms, model_id)      # Laya scores are 0-based expected levels


class StandIn:
    """Hand-written, zero-label rule with the Jev/Laya answer shape. NOT Jev and NOT Laya.
    `temper` changes how confident it is, so a dry run can exercise two different-looking slots."""
    kind = "stand-in"
    NEG = ("softer orders", "narrowing", "contract loss", "absorbed cash", "not yet agreed")
    POS = ("strengthening", "ahead of plan", "revenue visibility", "early debt repayment")

    def __init__(self, temper=0.4, name="A"):
        self.temper, self.name, self.label = temper, name, f"STAND-IN {name} (not Jev, not Laya)"
        self.input_tokens = 0

    def ask(self, state, questions):
        t0 = time.perf_counter()
        s = state if isinstance(state, dict) else json.loads(state)
        r, chg, note = s["latest_quarter"], s["change_over_4_quarters"], s["analyst_note"].lower()
        neg, pos = sum(k in note for k in self.NEG), sum(k in note for k in self.POS)
        logit = (3.2 - 0.55 * (r["leverage_x"] - 3.0) + 0.22 * (r["interest_cover_x"] - 4.5)
                 + 1.5 * (r["current_ratio"] - 1.4) + 8.0 * (r["ebitda_margin"] - 0.14)
                 - 0.45 * chg["leverage_x"] + 0.12 * chg["interest_cover_x"] - 0.7 * neg + 0.4 * pos)
        p = 1 / (1 + math.exp(-(3.0 + self.temper * (logit - 3.2))))
        cats = list(questions["main_risk"]["criteria"])
        pressure = {cats[0]: (r["leverage_x"] - 3.0) / 1.5 + chg["leverage_x"], cats[1]: (1.4 - r["current_ratio"]) / 0.3,
                    cats[2]: (0.14 - r["ebitda_margin"]) / 0.04 + (4.5 - r["interest_cover_x"]) / 2, cats[3]: neg - pos}
        top = max(pressure, key=pressure.get)
        answers = {"can_repay": {"noul": p},
                   "main_risk": {"choice": top if pressure[top] > 0.8 else cats[-1],
                                 "probability": min(0.95, 0.5 + 0.1 * max(pressure[top], 0))},
                   "risk_grade": {"score": min(5, 1 + int((1 - p) * 12.5))}}
        return _normalise(answers, 1, (time.perf_counter() - t0) * 1000, "stand-in-" + self.name)


def build(spec):
    """'jev' | 'laya' | 'laya:typed-decisions' | 'standin' | 'standin:0.8'"""
    kind, _, arg = spec.partition(":")
    if kind == "jev":
        if not os.environ.get("TYPESAFE_API_KEY"):
            raise SystemExit("Jev needs TYPESAFE_API_KEY (get one at typesafe.ai).")
        return JevModel()
    if kind == "laya":
        return LayaModel(checkpoint=arg or "english", threads=int(os.environ.get("LAYA_THREADS", "0")) or None)
    if kind == "standin":
        return StandIn(temper=float(arg or 0.4), name="B" if arg else "A")
    raise SystemExit(f"unknown model spec {spec!r}")
