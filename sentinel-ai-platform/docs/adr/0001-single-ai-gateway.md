# ADR 0001: One AI gateway for every model call

**Status:** accepted

## Context
Teams across Capital Markets and Corporate Banking want to use large language models. Without a common entry point, each team would handle authentication, logging, data protection and vendor keys differently, and Model Risk Management would have to review each implementation separately.

## Decision
All model calls go through the Sentinel gateway. Applications never hold provider keys and never call Azure OpenAI or Vertex AI directly. Network rules enforce this: the model endpoints are private and only the gateway's managed identity has the model-user role.

## Consequences
- Controls (entitlements, PII redaction, guard, grounding, audit, cost attribution) are built once and inherited by every use case.
- Model changes are made in one place (`sentinel/config.py`) and go through one evaluation gate.
- The gateway is a critical dependency: it must run in at least two zones, with its own SLO and on-call rota.
- Abstracting at the gateway, not everywhere, avoids a lowest-common-denominator wrapper around every cloud AI service.
