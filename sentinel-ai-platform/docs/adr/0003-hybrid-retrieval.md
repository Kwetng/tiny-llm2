# ADR 0003: Hybrid retrieval with rank fusion

**Status:** accepted

## Context
Banking questions mix meaning ("who approves large exposures?") with exact terms (clause numbers, "PV01", "MTA", "SONIA"). Pure vector search misses exact identifiers; pure keyword search misses paraphrases.

## Decision
Run keyword (BM25) and vector search over the entitled chunks and combine them with reciprocal-rank fusion. Chunk by clause, so each citation points to one clause. In this repository TF-IDF vectors stand in for embeddings so everything runs offline; production swaps in Azure OpenAI or Vertex embeddings behind the same interface.

## Consequences
- Changing the embedding model, chunking or fusion is a model change (GR-002 §3.1) and must pass the evaluation gate.
- Re-embedding the corpus is the real cost of switching vendors, so vectors are versioned with the index.
