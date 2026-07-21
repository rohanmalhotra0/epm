"""Pure-Python BM25 index with JSON cache and optional hybrid embedding scoring.

The index over one (immutable) context version is cached as JSON at
``get_settings().rag_dir / f"{context_version_id}.json"``: tokenized chunks,
document-frequency stats, and — once a provider with embedding support has been
used — the chunk vectors keyed by the embedding model name. Lexical retrieval
therefore works fully offline and deterministically; embeddings only ever
upgrade the ranking and any provider failure silently falls back to lexical.
"""

from __future__ import annotations

import json
import math
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..schemas.rag import GroundingChunk
from ..services import context_store
from .chunker import Chunk, build_chunks, tokenize

# Standard Okapi BM25 parameters.
BM25_K1 = 1.5
BM25_B = 0.75
# Bound the index: a huge snapshot must not turn every chat turn into a
# multi-hundred-MB JSON parse or an unbounded embedding upload.
MAX_CHUNKS = 4_000
# Context versions are immutable, so loaded indexes memoize safely in-process.
_MEMO: OrderedDict[str, "RagIndex"] = OrderedDict()
_MEMO_CAP = 8


def _cache_path(context_version_id: str) -> Path:
    return get_settings().rag_dir / f"{context_version_id}.json"


@dataclass
class RagIndex:
    context_version_id: str
    label: str | None = None
    chunks: list[Chunk] = field(default_factory=list)
    embedding_model: str | None = None
    embeddings: list[list[float]] | None = None
    # Negative cache: the model whose embed() failed for this corpus — skip
    # semantic scoring instead of re-uploading the corpus on every chat turn.
    embedding_failed_model: str | None = None
    # BM25 statistics, derived from the chunks.
    df: dict[str, int] = field(default_factory=dict)
    avgdl: float = 0.0
    _tf: list[Counter] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._recompute_stats()

    def _recompute_stats(self) -> None:
        self._tf = [Counter(c.tokens) for c in self.chunks]
        df: Counter = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        self.df = dict(df)
        lengths = [len(c.tokens) for c in self.chunks]
        self.avgdl = (sum(lengths) / len(lengths)) if lengths else 0.0

    def bm25_scores(self, query_tokens: list[str]) -> list[float]:
        """Raw Okapi BM25 score per chunk (k1=1.5, b=0.75)."""
        n = len(self.chunks)
        scores = [0.0] * n
        if not n or not query_tokens or self.avgdl <= 0:
            return scores
        for term in query_tokens:
            dfreq = self.df.get(term, 0)
            if dfreq == 0:
                continue
            idf = math.log(1.0 + (n - dfreq + 0.5) / (dfreq + 0.5))
            for i, tf in enumerate(self._tf):
                f = tf.get(term, 0)
                if not f:
                    continue
                dl = len(self.chunks[i].tokens)
                denom = f + BM25_K1 * (1.0 - BM25_B + BM25_B * dl / self.avgdl)
                scores[i] += idf * f * (BM25_K1 + 1.0) / denom
        return scores

    # --- JSON cache round-trip ------------------------------------------------

    def to_json(self) -> dict:
        return {
            "contextVersionId": self.context_version_id,
            "label": self.label,
            "chunks": [{
                "kind": c.kind, "name": c.name, "cube": c.cube, "dimension": c.dimension,
                "text": c.text, "snippet": c.snippet, "tokens": c.tokens,
            } for c in self.chunks],
            "df": self.df,
            "avgdl": self.avgdl,
            "embeddingModel": self.embedding_model,
            "embeddings": self.embeddings,
            "embeddingFailedModel": self.embedding_failed_model,
        }

    @classmethod
    def from_json(cls, payload: dict) -> RagIndex:
        chunks = [Chunk(kind=c["kind"], name=c["name"], cube=c.get("cube"),
                        dimension=c.get("dimension"), text=c.get("text", ""),
                        snippet=c.get("snippet", ""), tokens=list(c.get("tokens") or []))
                  for c in payload.get("chunks") or []]
        return cls(
            context_version_id=payload["contextVersionId"],
            label=payload.get("label"),
            chunks=chunks,
            embedding_model=payload.get("embeddingModel"),
            embeddings=payload.get("embeddings"),
            embedding_failed_model=payload.get("embeddingFailedModel"),
        )

    def save(self) -> None:
        path = _cache_path(self.context_version_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_json(), ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def _memoize(index: RagIndex) -> RagIndex:
    _MEMO[index.context_version_id] = index
    _MEMO.move_to_end(index.context_version_id)
    while len(_MEMO) > _MEMO_CAP:
        _MEMO.popitem(last=False)
    return index


def build_rag_index(session: Session, context_version_id: str) -> RagIndex:
    """Build (or load from cache) the retrieval index for one context version.
    Safe to memoize by id: versions are immutable once persisted. Without the
    in-process memo, every chat turn re-parsed the whole cache JSON — chunk
    texts, token lists and the full embedding matrix."""
    memoized = _MEMO.get(context_version_id)
    if memoized is not None:
        _MEMO.move_to_end(context_version_id)
        return memoized
    path = _cache_path(context_version_id)
    if path.exists():
        try:
            return _memoize(RagIndex.from_json(json.loads(path.read_text(encoding="utf-8"))))
        except Exception:  # corrupt/stale cache — rebuild below
            pass
    cv = context_store.get_context(session, context_version_id)
    if cv is None:
        return RagIndex(context_version_id=context_version_id)
    records = context_store.get_records(session, context_version_id)
    if not records:
        return RagIndex(context_version_id=context_version_id, label=cv.label)
    chunks = build_chunks(records)
    if len(chunks) > MAX_CHUNKS:
        chunks = chunks[:MAX_CHUNKS]
    index = RagIndex(context_version_id=context_version_id, label=cv.label, chunks=chunks)
    index.save()
    return _memoize(index)


def invalidate_rag_index(context_version_id: str) -> None:
    """Drop the cache file and memo (next build re-derives from the records)."""
    _MEMO.pop(context_version_id, None)
    _cache_path(context_version_id).unlink(missing_ok=True)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _embedding_model_name(provider) -> str:
    explicit = getattr(provider, "embeddings_model", None)
    if explicit:
        return str(explicit)
    return f"{getattr(provider, 'name', 'provider')}:default"


async def _semantic_scores(index: RagIndex, query: str, candidates: list[int], provider) -> dict[int, float] | None:
    """Cosine similarity (clamped to >= 0) per candidate, or None if the
    provider can't embed. Chunk vectors are cached in the index JSON keyed by
    the embedding model name; the query vector is computed per call."""
    if provider is None or not getattr(provider, "capabilities", {}).get("embeddings"):
        return None
    model_name = _embedding_model_name(provider)
    if index.embedding_failed_model == model_name:
        return None  # negative-cached: don't re-upload the corpus every turn
    if (index.embeddings is None or index.embedding_model != model_name
            or len(index.embeddings) != len(index.chunks)):
        try:
            embeddings = await provider.embed([c.text for c in index.chunks])
            if len(embeddings) != len(index.chunks):
                raise ValueError("provider returned a wrong number of embeddings")
        except Exception:
            index.embedding_failed_model = model_name
            index.save()
            raise
        index.embeddings = embeddings
        index.embedding_model = model_name
        index.embedding_failed_model = None
        index.save()
    qvec = (await provider.embed([query]))[0]
    return {i: max(0.0, _cosine(qvec, index.embeddings[i])) for i in candidates}


async def retrieve_grounding(
    session: Session,
    context_version_id: str,
    query: str,
    *,
    kinds: list[str] | None = None,
    k: int = 5,
    provider=None,
) -> list[GroundingChunk]:
    """Top-k grounding chunks for a query against one context version.

    Lexical BM25 (normalized to [0,1] by the max score in the result set) is
    always computed; when the provider supports embeddings the final score is
    ``0.5*bm25_norm + 0.5*cosine_norm`` (method "hybrid", or "semantic" for a
    chunk BM25 knew nothing about). Any provider/embedding failure falls back
    to lexical-only silently. Deterministic: ties break on (kind, name)."""
    if k <= 0:  # a non-positive budget asks for no rows (a bare slice would
        return []  # silently return all-but-|k| for negative k)
    index = build_rag_index(session, context_version_id)
    if not index.chunks:
        return []
    candidates = [i for i, c in enumerate(index.chunks) if not kinds or c.kind in kinds]
    if not candidates:
        return []

    raw = index.bm25_scores(tokenize(query))
    max_raw = max((raw[i] for i in candidates), default=0.0)
    bm25_norm = {i: (raw[i] / max_raw if max_raw > 0 else 0.0) for i in candidates}

    scores = dict(bm25_norm)
    methods = {i: "lexical" for i in candidates}
    try:
        cosines = await _semantic_scores(index, query, candidates, provider)
    except Exception:  # tolerant by contract: lexical-only on any failure
        cosines = None
    if cosines is not None:
        max_cos = max(cosines.values(), default=0.0)
        for i in candidates:
            cos_norm = cosines[i] / max_cos if max_cos > 0 else 0.0
            scores[i] = 0.5 * bm25_norm[i] + 0.5 * cos_norm
            methods[i] = "semantic" if bm25_norm[i] == 0.0 else "hybrid"

    ranked = sorted(
        (i for i in candidates if scores[i] > 0.0),
        key=lambda i: (-scores[i], index.chunks[i].kind, index.chunks[i].name),
    )
    return [
        GroundingChunk(
            kind=index.chunks[i].kind,
            name=index.chunks[i].name,
            cube=index.chunks[i].cube,
            dimension=index.chunks[i].dimension,
            snippet=index.chunks[i].snippet,
            score=round(scores[i], 6),
            method=methods[i],
            context_version=index.label,
        )
        for i in ranked[:k]
    ]
