"""RAG grounding provenance (spec: grounded form & rule creation).

A ``GroundingChunk`` is one retrieved excerpt from the active context version,
with full provenance: what artifact it came from, how it was ranked (lexical
BM25, embedding cosine, or hybrid) and the context version label. Snippets are
redacted before they are ever stored or shown.
"""

from __future__ import annotations

from .common import CamelModel


class GroundingChunk(CamelModel):
    kind: str  # rule | template | form | member | variable | dimension
    name: str
    cube: str | None = None
    dimension: str | None = None
    snippet: str  # <= 700 chars, redacted, the matched content excerpt
    score: float  # final hybrid score, higher = better
    method: str  # "lexical" | "semantic" | "hybrid"
    context_version: str | None = None  # ContextVersion.label for provenance
