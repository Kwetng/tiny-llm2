"""Identity and entitlements.

The AI system always acts AS the calling user. Access is decided in code, before any content
reaches a model - the LLM is never the security boundary.

Document labels:
  business_line : group | corporate_banking | capital_markets
  classification: public < internal < confidential < restricted
  barrier       : optional information-barrier group (e.g. a private-side deal team)
"""
from dataclasses import dataclass, field

CLASS_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}


@dataclass(frozen=True)
class User:
    id: str
    name: str
    business_line: str
    clearance: str
    roles: frozenset = field(default_factory=frozenset)
    barriers: frozenset = field(default_factory=frozenset)


# Demo identities. In production these come from Entra ID / Cloud IAM tokens and HR entitlements.
USERS = {
    "tok-alice": User("alice", "Alice Morgan - Relationship Manager", "corporate_banking", "confidential", frozenset({"rm"})),
    "tok-bob": User("bob", "Bob Tanaka - Rates Trader", "capital_markets", "confidential", frozenset({"trader"})),
    "tok-carol": User("carol", "Carol Osei - Credit Risk Officer", "group", "confidential", frozenset({"risk_oversight"})),
    "tok-dan": User("dan", "Dan Ruiz - Project Heron deal team", "corporate_banking", "restricted", frozenset({"rm"}), frozenset({"heron"})),
    "tok-erin": User("erin", "Erin Walsh - Internal Audit", "group", "internal", frozenset({"audit"})),
    "tok-frank": User("frank", "Frank Ito - Operations Manager", "corporate_banking", "confidential", frozenset({"approver", "ops"})),
}


def authenticate(token: str):
    return USERS.get(token)


def can_read(user: User, labels: dict) -> bool:
    if CLASS_RANK[labels.get("classification", "internal")] > CLASS_RANK[user.clearance]:
        return False
    barrier = labels.get("barrier")
    if barrier and barrier not in user.barriers:
        return False                                  # information barrier: wall-crossed users only
    line = labels.get("business_line", "group")
    if line == "group" or line == user.business_line:
        return True
    return "risk_oversight" in user.roles and not barrier


def has_role(user: User, role: str) -> bool:
    return role in user.roles
