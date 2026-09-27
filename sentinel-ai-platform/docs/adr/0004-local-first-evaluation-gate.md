# ADR 0004: A local model in every route, and an evaluation gate that runs without cloud access

**Status:** accepted

## Context
Evaluation must run on every change, including in CI and on engineers' laptops, without cloud credentials or spend. Business processes must also survive a provider outage.

## Decision
Every route ends with the deterministic local extractive model. CI runs the full evaluation gate against it. Each hosted model is enabled in a route only after it passes the same gate in a controlled environment, and its pinned version is recorded in the evidence pack.

## Consequences
- The gate is fast (seconds), free and reproducible, so it can block merges.
- Hosted models are still validated. The gate is the same; only the environment and credentials differ.
- The local model is conservative: it quotes rather than paraphrases and abstains readily. That is acceptable as a fallback but not as the main user experience.
