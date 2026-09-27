# ADR 0005: Agents get the least autonomy that solves the problem

**Status:** accepted

## Context
Operations teams want an assistant that can check covenants and collateral and then act. Agent failures are wrong actions, not just wrong answers.

## Decision
- Tools are typed READ, DRAFT or ACTION. ACTION tools, meaning anything external or irreversible, are never executed by the agent. They are queued for a human with the approver role, who must not be the requester.
- The agent runs with the requesting user's entitlements and within a step budget.
- Unsupported tasks are refused rather than improvised.
- The planner is a transparent rule-based workflow. An LLM planner can replace it, but the controls around it stay the same.

## Consequences
- Covenant escalation is prepared automatically in seconds, and sending and watchlisting remain human decisions. This covers GR-001 §2 and the EU AI Act Article 14 human-oversight expectation.
- Adding a new tool requires declaring its kind and entitlement check. That review is the natural place for a design-authority sign-off.
