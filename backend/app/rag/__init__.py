"""Retrieval-augmented grounding over the active context version.

Lexical BM25 works fully offline and deterministically; when the active AI
provider supports embeddings (``capabilities["embeddings"]``) the ranking
upgrades to hybrid lexical+semantic scoring. The per-version index is cached
as JSON under ``Settings.rag_dir`` — safe because context versions are
immutable once persisted.
"""

from __future__ import annotations

from .chunker import Chunk, build_chunks, tokenize
from .index import RagIndex, build_rag_index, invalidate_rag_index, retrieve_grounding

__all__ = [
    "Chunk",
    "RagIndex",
    "build_chunks",
    "build_rag_index",
    "invalidate_rag_index",
    "retrieve_grounding",
    "tokenize",
]
