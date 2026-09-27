"""The AI gateway: the single, governed entry point for every model call.

Request pipeline for /v1/ask:
  authenticate -> rate limit -> input guard (prompt injection / scope) -> PII redaction
  -> entitlement-filtered retrieval -> context guard (indirect injection quarantine)
  -> model routing with fallback -> grounding check (citations must match retrieved clauses)
  -> output PII scan -> cost attribution -> tamper-evident audit record -> response

Run:  uvicorn sentinel.gateway:app --reload
"""
import re, time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import __version__
from .agent import Agent
from .audit import AuditLog, sha
from .config import GUARD_BLOCK_AT, GUARD_FLAG_AT, LOG_FULL_TEXT, MODELS, RATE_LIMIT_PER_MINUTE, STATE, USE_CASES
from .extract import extract_all
from .guard import get_guard
from .identity import User, authenticate, has_role
from .pii import redact
from .providers import ABSTAIN, route
from .rag import Retriever

CITE = re.compile(r"\[([A-Z]+-[A-Z0-9]+ §[\d.]+)\]")


class Platform:
    def __init__(self, audit_path=None):
        self.audit = AuditLog(audit_path or STATE / "audit.jsonl")
        self.guard = get_guard()
        self.retriever = Retriever()
        self.agent = Agent(self.retriever, self.guard, self.audit)
        self.calls = defaultdict(deque)
        self.counters = defaultdict(float)
        self.latencies = []

    def _rate_ok(self, user):
        q, now = self.calls[user.id], time.time()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MINUTE:
            return False
        q.append(now)
        return True

    def ask(self, user: User, question: str, use_case: str = "policy_qa"):
        t0 = time.time()
        if not self._rate_ok(user):
            self.counters["rate_limited"] += 1
            raise HTTPException(429, "Rate limit reached - try again in a minute")
        g = self.guard.ask(question)
        p_inj, p_oos = g["prompt_injection"]["noul"], g["out_of_scope"]["noul"]
        q_red, pii_types = redact(question)
        base = {"user": user.id, "business_line": user.business_line, "use_case": use_case, "question_hash": sha(question),
                "question": q_red if LOG_FULL_TEXT == "redacted" else None, "pii_redacted": pii_types,
                "guard": {"prompt_injection": round(p_inj, 3), "out_of_scope": round(p_oos, 3)}}
        if p_inj >= GUARD_BLOCK_AT:
            self.counters["blocked"] += 1
            rec = self.audit.append("request_blocked", **base, reason="possible prompt injection")
            return {"blocked": True, "answer": "This request was blocked by the AI safety policy. If you think this is wrong, "
                                               "contact the AI Engineering team quoting the request id.", "request_id": rec["event_id"]}

        hits = self.retriever.search(user, q_red, k=5)
        quarantined = [h["id"] for h in hits if self.guard.ask(h["text"])["prompt_injection"]["noul"] >= GUARD_BLOCK_AT]
        chunks = [h for h in hits if h["id"] not in quarantined]
        answer, model_id, usage, attempts = route(use_case, q_red, chunks)

        retrieved = {c["id"] for c in chunks}
        cited = CITE.findall(answer)
        invalid = [c for c in cited if c not in retrieved]
        abstained = answer.strip().startswith(ABSTAIN[:12])
        if invalid or (not cited and not abstained):             # ungrounded answer -> do not show it
            self.counters["grounding_failures"] += 1
            answer, abstained = ABSTAIN, True
        answer, out_pii = redact(answer)
        spec = MODELS[model_id]
        cost = usage["input_tokens"] / 1000 * spec.gbp_per_1k_input + usage["output_tokens"] / 1000 * spec.gbp_per_1k_output
        self.counters[f"cost_gbp:{user.business_line}"] += cost
        self.counters["requests"] += 1
        self.counters["abstained"] += abstained
        latency = round((time.time() - t0) * 1000, 1)
        self.latencies.append(latency)
        rec = self.audit.append("llm_request", **base, model=model_id, model_version=spec.version, route_attempts=attempts,
                                retrieved=[h["id"] for h in hits], quarantined=quarantined, citations=cited,
                                invalid_citations=invalid, abstained=abstained, output_pii=out_pii,
                                tokens=usage, cost_gbp=round(cost, 6), latency_ms=latency)
        return {"blocked": False, "answer": answer, "citations": list(dict.fromkeys(c for c in cited if c in retrieved)), "abstained": abstained,
                "model": model_id, "model_version": spec.version, "quarantined_sources": quarantined,
                "flags": (["possible prompt injection"] if p_inj >= GUARD_FLAG_AT else []) + (["possibly out of scope"] if p_oos >= GUARD_FLAG_AT else []),
                "request_id": rec["event_id"], "latency_ms": latency}

    def metrics(self):
        lat = sorted(self.latencies) or [0]
        return {"requests": int(self.counters["requests"]), "blocked": int(self.counters["blocked"]),
                "abstained": int(self.counters["abstained"]), "grounding_failures": int(self.counters["grounding_failures"]),
                "rate_limited": int(self.counters["rate_limited"]),
                "latency_ms": {"p50": lat[len(lat) // 2], "p95": lat[int(len(lat) * 0.95) - 1 if len(lat) > 1 else 0]},
                "cost_gbp_by_business_line": {k.split(":", 1)[1]: round(v, 4) for k, v in self.counters.items() if k.startswith("cost_gbp:")}}


# ----------------------------------------------------------------------------- HTTP API
app = FastAPI(title="Sentinel AI Gateway", version=__version__,
              description="Governed GenAI gateway: entitlement-aware RAG, CSA extraction and a controlled agent, with a tamper-evident audit trail.")
platform = Platform()


def current_user(authorization: str = Header(default="")) -> User:
    user = authenticate(authorization.removeprefix("Bearer ").strip())
    if not user:
        raise HTTPException(401, "Missing or unknown bearer token")
    return user


class AskIn(BaseModel):
    question: str
    use_case: str = "policy_qa"


class TaskIn(BaseModel):
    task: str


class ApproveIn(BaseModel):
    approval_id: str


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": __version__, "guard": platform.guard.name, "use_cases": list(USE_CASES)}


@app.post("/v1/ask")
def ask(body: AskIn, user: User = Depends(current_user)):
    if body.use_case not in USE_CASES:
        raise HTTPException(400, f"Unknown use case. Approved use cases: {', '.join(USE_CASES)}")
    return platform.ask(user, body.question, body.use_case)


@app.get("/v1/extract/csa")
def csa(user: User = Depends(current_user)):
    if not (has_role(user, "ops") or has_role(user, "risk_oversight")):
        raise HTTPException(403, "Collateral operations or risk oversight role required")
    records = extract_all()
    platform.audit.append("csa_extraction", user=user.id, references=list(records),
                          needs_review=[r for r, v in records.items() if v["status"].startswith("NEEDS")])
    return records


@app.post("/v1/agent/run")
def agent_run(body: TaskIn, user: User = Depends(current_user)):
    return platform.agent.run(user, body.task)


@app.post("/v1/agent/approve")
def agent_approve(body: ApproveIn, user: User = Depends(current_user)):
    return platform.agent.approve(user, body.approval_id)


@app.get("/v1/audit/verify")
def audit_verify(user: User = Depends(current_user)):
    if not has_role(user, "audit"):
        raise HTTPException(403, "Internal audit role required")
    ok, n, broken = platform.audit.verify()
    return {"chain_intact": ok, "records": n, "first_broken_record": broken}


@app.get("/v1/metrics")
def metrics(user: User = Depends(current_user)):
    if not (has_role(user, "audit") or has_role(user, "risk_oversight")):
        raise HTTPException(403, "Audit or risk oversight role required")
    return platform.metrics()
