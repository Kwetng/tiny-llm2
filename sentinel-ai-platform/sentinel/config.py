"""Platform configuration: the model registry (pinned versions), per-use-case routing and budgets.

Every model is a registered, versioned asset. Changing a version is a model change and must go
through the evaluation gate (see evals/). Deployment names below are examples - pin the exact
model versions your tenancy offers.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE = Path(os.environ.get("SENTINEL_STATE_DIR", ROOT / "state"))
STATE.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str                 # local | azure_openai | vertex
    version: str                  # pinned; a change requires re-validation
    region: str
    gbp_per_1k_input: float
    gbp_per_1k_output: float
    max_risk_tier: str            # highest use-case tier this model is approved for
    deployment: str = ""          # Azure deployment name or Vertex model id


MODELS = {
    "local-extractive": ModelSpec("local-extractive", "local", "1.0.0", "on-premises", 0.0, 0.0, "high"),
    "azure-openai-chat": ModelSpec("azure-openai-chat", "azure_openai", os.environ.get("AZURE_OPENAI_MODEL_VERSION", "pinned-by-deployment"),
                                   os.environ.get("AZURE_OPENAI_REGION", "uksouth"), 0.0004, 0.0016, "medium",
                                   deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "chat-prod")),
    "vertex-gemini": ModelSpec("vertex-gemini", "vertex", os.environ.get("VERTEX_MODEL_VERSION", "pinned-by-model-id"),
                               os.environ.get("VERTEX_REGION", "europe-west2"), 0.0003, 0.0012, "medium",
                               deployment=os.environ.get("VERTEX_MODEL", "gemini-model-id")),
}

TIER_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class UseCase:
    id: str
    risk_tier: str
    route: tuple                  # models tried in order (primary, then fallbacks)
    daily_budget_gbp: float
    owner: str                    # accountable business owner (SM&CR mapping lives in governance/)
    human_review: bool = False


USE_CASES = {
    "policy_qa": UseCase("policy_qa", "medium", ("azure-openai-chat", "vertex-gemini", "local-extractive"), 50.0, "Head of Credit Risk Policy"),
    "csa_extraction": UseCase("csa_extraction", "high", ("local-extractive",), 20.0, "Head of Collateral Operations", human_review=True),
    "ops_agent": UseCase("ops_agent", "high", ("local-extractive",), 10.0, "COO, Corporate Banking", human_review=True),
}

RATE_LIMIT_PER_MINUTE = int(os.environ.get("SENTINEL_RATE_LIMIT", "30"))
GUARD_BLOCK_AT = 0.80             # guard probability at or above which a request is blocked
GUARD_FLAG_AT = 0.50              # ... flagged for review but allowed
LOG_FULL_TEXT = os.environ.get("SENTINEL_LOG_FULL_TEXT", "redacted")   # redacted | hash_only
