"""Entitlement-aware hybrid retrieval.

Pipeline: parse -> chunk by clause -> index (BM25 keyword + TF-IDF vector) -> FILTER BY
ENTITLEMENT -> score -> reciprocal-rank fusion -> top k.

The entitlement filter runs before scoring, so a chunk the user may not read can never be
ranked, returned, shown to a model or cited. The TF-IDF vectors stand in for embedding models
(Azure OpenAI or Vertex embeddings) so everything runs offline; swap VectorIndex to use them.
"""
import math, re
from collections import Counter
from dataclasses import dataclass

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer

from .config import DATA
from .identity import can_read
from .providers import tokens


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    heading: str
    text: str
    labels: dict


def load_corpus(folder=DATA / "policies"):
    chunks = []
    for path in sorted(folder.glob("*.md")):
        raw = path.read_text()
        _, front, body = raw.split("---", 2)
        meta = yaml.safe_load(front)
        labels = {k: meta.get(k) for k in ("business_line", "classification", "barrier")}
        for m in re.finditer(r"^### (\S+) ([^\n]+)\n(.+?)(?=^##|\Z)", body, flags=re.M | re.S):
            num, heading, text = m.group(1), m.group(2).strip(), " ".join(m.group(3).split())
            chunks.append(Chunk(f"{meta['id']} §{num}", meta["id"], meta["title"], heading, text,
                                {**labels, "owner": meta.get("owner"), "version": str(meta.get("version"))}))
    return chunks


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [tokens(d) for d in docs]
        self.k1, self.b = k1, b
        self.avg = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query, i):
        tf = Counter(self.docs[i]); dl = len(self.docs[i]); s = 0.0
        for t in tokens(query):
            if t in tf:
                s += self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avg))
        return s


class Retriever:
    def __init__(self, chunks=None):
        self.chunks = chunks or load_corpus()
        texts = [f"{c.title}. {c.heading}. {c.text}" for c in self.chunks]
        self.bm25 = BM25(texts)
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english").fit(texts)
        self.mat = self.vec.transform(texts)

    def search(self, user, query, k=5, min_score=0.0):
        allowed = [i for i, c in enumerate(self.chunks) if can_read(user, c.labels)]       # filter FIRST
        if not allowed:
            return []
        qv = self.vec.transform([query])
        dense = {i: float((self.mat[i] @ qv.T).toarray()[0, 0]) for i in allowed}
        sparse = {i: self.bm25.score(query, i) for i in allowed}
        rrf = Counter()
        for scores in (dense, sparse):
            for rank, i in enumerate(sorted(scores, key=scores.get, reverse=True)):
                if scores[i] > 0:
                    rrf[i] += 1 / (60 + rank)
        top = [i for i, s in rrf.most_common(k) if s > min_score]
        return [{"id": self.chunks[i].id, "doc_id": self.chunks[i].doc_id, "title": self.chunks[i].title,
                 "heading": self.chunks[i].heading, "text": self.chunks[i].text, "labels": self.chunks[i].labels,
                 "rank_score": round(rrf[i] * 60, 3), "bm25": round(sparse[i], 3), "cosine": round(dense[i], 3)} for i in top]
