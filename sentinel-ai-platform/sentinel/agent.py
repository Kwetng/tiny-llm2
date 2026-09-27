"""Controlled operations agent.

Design rules (the least autonomy that solves the problem):
  - Tools are declared with a kind: READ, DRAFT (reversible) or ACTION (irreversible / external).
  - The agent acts as the requesting user: every tool checks that user's entitlements.
  - ACTION tools never run automatically. They are queued for a human approver, who must hold the
    'approver' role and must not be the requester (segregation of duties).
  - Budgets cap the number of steps; tool outputs are treated as data and screened by the guard.
  - Every step is traced and written to the audit log.

The planner here is a transparent rule-based workflow for three supported intents. An LLM
planner using function calling can replace plan() without changing the controls around it.
"""
import json, re, uuid
from dataclasses import dataclass

from .config import DATA
from .extract import extract_all
from .identity import User, has_role
from .pii import redact

MAX_STEPS = 6
CLIENTS = json.loads((DATA / "clients.json").read_text())


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str                 # READ | DRAFT | ACTION
    description: str


TOOLS = {t.name: t for t in [
    Tool("get_client_exposure", "READ", "Limit, utilisation, rating and covenant tests for a client"),
    Tool("search_policies", "READ", "Search policies the user is entitled to read"),
    Tool("check_csa_terms", "READ", "Extracted collateral terms for a client's CSA"),
    Tool("draft_email", "DRAFT", "Draft an internal email (not sent)"),
    Tool("send_email", "ACTION", "Send an email - needs human approval"),
    Tool("add_to_watchlist", "ACTION", "Add a client to the credit watchlist - needs human approval"),
]}


def _client_in(text):
    t = text.upper()
    for name in CLIENTS:
        if name.split()[0] in t:
            return name
    return None


def plan(task):
    """Return (intent, steps). Unknown tasks are refused rather than improvised."""
    t = task.lower(); client = _client_in(task)
    if client and re.search(r"covenant|breach|leverage test", t):
        return "covenant_check", [("get_client_exposure", {"client": client}),
                                  ("search_policies", {"query": "covenant breach escalation watchlist triggers"}),
                                  ("draft_email", {"client": client, "topic": "covenant"}),
                                  ("send_email", {"to": "credit.risk@bank.internal"}),
                                  ("add_to_watchlist", {"client": client})]
    if client and re.search(r"margin|collateral|csa|dispute", t):
        return "collateral_review", [("get_client_exposure", {"client": client}),
                                     ("check_csa_terms", {"client": client}),
                                     ("search_policies", {"query": "margin dispute escalation minimum transfer amount"})]
    return "unsupported", []


class Agent:
    def __init__(self, retriever, guard, audit):
        self.retriever, self.guard, self.audit = retriever, guard, audit
        self.pending = {}                                  # approval_id -> action

    def _entitled_client(self, user: User, client):
        c = CLIENTS[client]
        return c["business_line"] == user.business_line or has_role(user, "risk_oversight")

    def _run_tool(self, user, name, args, state):
        if name == "get_client_exposure":
            if not self._entitled_client(user, args["client"]):
                return "DENIED", f"{user.id} is not entitled to {args['client']}"
            c = CLIENTS[args["client"]]; state["client"] = c
            return "OK", {k: c[k] for k in ("rating", "limit_gbp", "utilised_gbp", "leverage_covenant", "leverage_tested", "watchlist")}
        if name == "search_policies":
            hits = self.retriever.search(user, args["query"], k=3)
            safe = [h for h in hits if self.guard.ask(h["text"])["prompt_injection"]["noul"] < 0.8]
            state["policies"] = safe
            return "OK", [h["id"] for h in safe]
        if name == "check_csa_terms":
            c = CLIENTS[args["client"]]
            rec = extract_all()[c["csa"]]
            return "OK", {"status": rec["status"], "mta": rec["fields"]["minimum_transfer_amount"]["value"],
                          "threshold_party_b": rec["fields"]["threshold_party_b"]["value"], "review_reasons": rec["review_reasons"]}
        if name == "draft_email":
            c = state.get("client") or {}
            breach = c.get("leverage_tested") and c.get("leverage_covenant") and c["leverage_tested"] > c["leverage_covenant"]
            if not breach:
                state["stop"] = "no covenant breach found - nothing to escalate"
                return "OK", "No breach: leverage within covenant"
            cites = ", ".join(h["id"] for h in state.get("policies", []))
            body = (f"Subject: Covenant breach - {args['client']}\n\nLeverage tested at {c['leverage_tested']}x against a covenant of "
                    f"{c['leverage_covenant']}x. Under {cites or 'the Corporate Credit Policy'} the breach must be reported to Credit Risk "
                    f"within 2 business days and the client added to the watchlist within 5 business days.\n\nPrepared by the operations "
                    f"agent for {user.name}; please review before sending.")
            state["draft"] = redact(body)[0]
            return "OK", state["draft"]
        raise KeyError(name)

    def run(self, user: User, task: str):
        run_id = uuid.uuid4().hex[:10]
        intent, steps = plan(task)
        trace, state, status = [], {}, "completed"
        if intent == "unsupported":
            status = "refused: task is outside the agent's approved workflows"
        for i, (name, args) in enumerate(steps):
            if i >= MAX_STEPS:
                status = "stopped: step budget reached"; break
            if state.get("stop"):
                status = f"completed: {state['stop']}"; break
            tool = TOOLS[name]
            if tool.kind == "ACTION":
                aid = uuid.uuid4().hex[:8]
                self.pending[aid] = {"run_id": run_id, "tool": name, "args": args, "requester": user.id, "draft": state.get("draft")}
                trace.append({"step": i + 1, "tool": name, "kind": tool.kind, "result": "AWAITING APPROVAL", "approval_id": aid})
                status = "awaiting approval"
                continue
            outcome, result = self._run_tool(user, name, args, state)
            trace.append({"step": i + 1, "tool": name, "kind": tool.kind, "args": args, "result": outcome, "output": result})
            if outcome == "DENIED":
                status = "stopped: permission denied"; break
        self.audit.append("agent_run", user=user.id, run_id=run_id, intent=intent, status=status,
                          steps=[{k: v for k, v in s.items() if k != "output"} for s in trace])
        return {"run_id": run_id, "intent": intent, "status": status, "trace": trace,
                "pending_approvals": [k for k, v in self.pending.items() if v["run_id"] == run_id]}

    def approve(self, approver: User, approval_id: str):
        item = self.pending.get(approval_id)
        if not item:
            return {"ok": False, "reason": "unknown approval id"}
        if not has_role(approver, "approver"):
            return {"ok": False, "reason": "approver role required"}
        if approver.id == item["requester"]:
            return {"ok": False, "reason": "segregation of duties: requester cannot approve their own action"}
        self.pending.pop(approval_id)
        self.audit.append("agent_action_approved", approver=approver.id, requester=item["requester"], tool=item["tool"],
                          args=item["args"], run_id=item["run_id"])
        return {"ok": True, "executed": item["tool"], "args": item["args"],
                "note": "Simulated: in production this calls the email / credit system with the approver's authority."}
