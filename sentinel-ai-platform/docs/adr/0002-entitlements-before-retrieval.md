# ADR 0002: Enforce entitlements before retrieval, not in the prompt

**Status:** accepted

## Context
The policy library mixes group-wide, business-line and private-side (information-barrier) material. Telling a model "do not reveal restricted content" is not a control: models can be persuaded, and prompts can be injected.

## Decision
Every chunk carries its source document's labels (business line, classification, barrier). Retrieval filters to the chunks the calling user may read before any scoring. The model only ever sees entitled content, and the gateway rejects any citation that does not match a retrieved, entitled clause.

## Consequences
- A public-side trader cannot receive Project Heron content, even through a cleverly worded question. This is tested by golden cases A01–A06 and red-team cases R09–R10, and the gate allows zero leaks.
- Labels must be accurate at ingestion. A mislabelled document is the main residual risk, so document owners attest to labels, and labels are shown in citations.
- Retrieval quality is measured per user, because two users can legitimately get different answers to the same question.
