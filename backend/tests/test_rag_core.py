"""RAG core tests: chunker, BM25 determinism, JSON cache, hybrid embeddings."""

from __future__ import annotations

import json
import math

import pytest

from app.ai.base import AIProvider, ProviderError
from app.ai.mock import EMBEDDING_DIM, MockProvider, _hash_embedding
from app.config import get_settings
from app.connector import DemoConnector
from app.context import build_context
from app.rag import (
    build_chunks,
    build_rag_index,
    invalidate_rag_index,
    retrieve_grounding,
    tokenize,
)
from app.rag.chunker import CHUNK_OVERLAP, CHUNK_SIZE, MEMBER_SAMPLE_LIMIT, SNIPPET_LIMIT
from app.rag.index import _cache_path
from app.schemas import CANONICAL_MODELS, GroundingChunk
from app.schemas.chat import ChatBlockType
from app.services import context_store, projects


def _rec(kind, name, data=None, dimension=None, cube=None, alias=None, parent=None,
         application="MCWPCF", search=None):
    return {"kind": kind, "name": name, "dimension": dimension, "cube": cube, "alias": alias,
            "parent": parent, "application": application, "search_text": (search or name).lower(),
            "data": data if data is not None else {"name": name}}


def _persist(session, records, label="rag-test"):
    proj = projects.get_default_project(session)
    cv = context_store.persist_context(
        session, proj.id, "MCWPCF", "quick", label, {}, {}, records, activate=False)
    session.flush()
    return cv


class FailingEmbedProvider(MockProvider):
    """Claims embedding support but blows up — retrieval must fall back."""

    capabilities = {**MockProvider.capabilities, "embeddings": True}

    async def embed(self, texts, *, model=None):
        raise RuntimeError("embedding backend down")


# --- tokenizer ----------------------------------------------------------------


def test_tokenize_keeps_underscore_names_whole_and_split():
    toks = tokenize("Copy OCF_Daily to Final! x")
    assert "ocf_daily" in toks and "ocf" in toks and "daily" in toks
    assert "copy" in toks and "final" in toks
    assert "x" not in toks  # single-char tokens dropped


# --- chunker --------------------------------------------------------------------


def test_rule_body_chunking_with_overlap(session):
    body = "".join(f"line{i:04d} FIX[Working] Salaries = Salaries * 1.02; " for i in range(80))
    assert len(body) > 2 * CHUNK_SIZE
    cv = _persist(session, [_rec("rule", "CalcSalaries", cube="OEP_FS", data={
        "name": "CalcSalaries", "cube": "OEP_FS", "runtimePrompts": ["Entity"], "body": body})])
    chunks = build_chunks(context_store.get_records(session, cv.id))
    rule_chunks = [c for c in chunks if c.kind == "rule"]
    step = CHUNK_SIZE - CHUNK_OVERLAP
    expected = 1 + math.ceil((len(body) - CHUNK_SIZE) / step)
    assert len(rule_chunks) == expected > 1
    # every chunk carries the header (name/cube/prompts) + one body window
    pieces = [c.text.split("\n", 1)[1] for c in rule_chunks]
    assert pieces[0] == body[:CHUNK_SIZE]
    assert pieces[1][:CHUNK_OVERLAP] == pieces[0][-CHUNK_OVERLAP:]  # the overlap
    assert all(c.name == "CalcSalaries" and c.cube == "OEP_FS" for c in rule_chunks)
    assert all(len(c.snippet) <= SNIPPET_LIMIT for c in chunks)


def test_member_convention_digest(session):
    members = [_rec("member", f"OCF_Item{i:02d}", dimension="Account",
                    data={"name": f"OCF_Item{i:02d}", "dimension": "Account"})
               for i in range(MEMBER_SAMPLE_LIMIT + 10)]
    members.append(_rec("member", "NetIncome", dimension="Account", alias="Net Income",
                        data={"name": "NetIncome", "dimension": "Account"}))
    cv = _persist(session, members)
    chunks = build_chunks(context_store.get_records(session, cv.id))
    digests = [c for c in chunks if c.kind == "member"]
    assert len(digests) == 1  # one digest per dimension, never one chunk per member
    d = digests[0]
    assert d.name == "Account" and d.dimension == "Account"
    assert "OCF_" in d.text  # detected prefix convention
    assert "Net Income" in d.text  # alias included
    assert d.text.count("OCF_Item") <= MEMBER_SAMPLE_LIMIT


def test_variable_and_form_chunks(session):
    cv = _persist(session, [
        _rec("variable", "CurYr", data={"name": "CurYr", "value": "FY25", "planType": "OEP_FS"}),
        _rec("form", "OFS_Rolling Forecast", cube="OEP_FS",
             data={"name": "OFS_Rolling Forecast", "folder": "Forecast/Input", "cube": "OEP_FS"}),
        _rec("form", "Referenced Form", data={"name": "Referenced Form", "referencedOnly": True}),
    ])
    chunks = build_chunks(context_store.get_records(session, cv.id))
    var = next(c for c in chunks if c.kind == "variable")
    assert "CurYr" in var.text and "FY25" in var.text and "OEP_FS" in var.text
    stub = next(c for c in chunks if c.name == "Referenced Form")
    assert "referenced only" in stub.snippet
    real = next(c for c in chunks if c.name == "OFS_Rolling Forecast")
    assert "Forecast/Input" in real.text


def test_snippets_are_redacted(session):
    cv = _persist(session, [_rec("rule", "Leaky", data={
        "name": "Leaky", "body": "FIX(Working)\n// password = hunter22secret\nSalaries=1;\nENDFIX"})])
    chunks = build_chunks(context_store.get_records(session, cv.id))
    assert all("hunter22secret" not in c.snippet and "hunter22secret" not in c.text for c in chunks)


# --- BM25 ranking + determinism --------------------------------------------------


def _corpus_records():
    return [
        _rec("rule", "CopyWorkingToFinal", cube="OEP_FS", data={
            "name": "CopyWorkingToFinal", "cube": "OEP_FS", "runtimePrompts": ["Entity"],
            "body": 'DATACOPY "Working" TO "Final"; /* copy working version to final */'}),
        _rec("rule", "AggSalaries", cube="OEP_FS", data={
            "name": "AggSalaries", "cube": "OEP_FS", "body": "AGG(Account); Salaries aggregation;"}),
        _rec("template", "ClearTemplate", cube="OEP_FS", data={
            "name": "ClearTemplate", "cube": "OEP_FS", "body": "CLEARDATA Budget;"}),
        _rec("variable", "CurYr", data={"name": "CurYr", "value": "FY25"}),
    ]


async def test_bm25_ranking_and_determinism(session):
    cv = _persist(session, _corpus_records())
    first = await retrieve_grounding(session, cv.id, "copy working version to final", k=3)
    second = await retrieve_grounding(session, cv.id, "copy working version to final", k=3)
    assert first and first == second  # identical output across runs
    assert first[0].name == "CopyWorkingToFinal" and first[0].method == "lexical"
    assert first[0].score == 1.0  # normalized by the max score in the result set
    assert all(0.0 < c.score <= 1.0 for c in first)
    assert [c.score for c in first] == sorted((c.score for c in first), reverse=True)
    assert all(c.context_version == "rag-test" for c in first)


async def test_kind_filter_and_k(session):
    cv = _persist(session, _corpus_records())
    only_vars = await retrieve_grounding(session, cv.id, "CurYr FY25", kinds=["variable"], k=5)
    assert only_vars and all(c.kind == "variable" for c in only_vars)
    capped = await retrieve_grounding(session, cv.id, "OEP_FS", k=1)
    assert len(capped) == 1


async def test_missing_or_empty_context_returns_nothing(session):
    assert await retrieve_grounding(session, "does-not-exist", "anything") == []
    cv = _persist(session, [])
    assert await retrieve_grounding(session, cv.id, "anything") == []


# --- cache ------------------------------------------------------------------------


async def test_cache_round_trip_and_invalidate(session):
    cv = _persist(session, _corpus_records())
    idx1 = build_rag_index(session, cv.id)
    path = _cache_path(cv.id)
    assert path.exists() and path.parent == get_settings().rag_dir
    before = path.read_bytes()
    idx2 = build_rag_index(session, cv.id)  # served from cache
    assert path.read_bytes() == before
    assert [c.tokens for c in idx2.chunks] == [c.tokens for c in idx1.chunks]
    assert idx2.df == idx1.df and idx2.avgdl == idx1.avgdl and idx2.label == idx1.label
    r1 = await retrieve_grounding(session, cv.id, "copy working to final")
    r2 = await retrieve_grounding(session, cv.id, "copy working to final")
    assert r1 == r2
    invalidate_rag_index(cv.id)
    assert not path.exists()
    # corrupt cache is tolerated and rebuilt
    path.write_text("{not json", encoding="utf-8")
    idx3 = build_rag_index(session, cv.id)
    assert [c.tokens for c in idx3.chunks] == [c.tokens for c in idx1.chunks]
    invalidate_rag_index(cv.id)
    invalidate_rag_index(cv.id)  # idempotent


# --- embeddings / hybrid ------------------------------------------------------------


async def test_base_provider_embed_raises_and_capability_flag():
    assert AIProvider.capabilities["embeddings"] is False
    mock = MockProvider()
    assert mock.capabilities["embeddings"] is True
    class Bare(MockProvider):
        capabilities = {**MockProvider.capabilities, "embeddings": False}
        embed = AIProvider.embed
    with pytest.raises(ProviderError):
        await Bare().embed(["x"])


async def test_mock_embeddings_deterministic_and_normalized():
    mock = MockProvider()
    [a1], [a2] = await mock.embed(["OCF_Daily"]), await mock.embed(["OCF_Daily"])
    assert a1 == a2 == _hash_embedding("OCF_Daily")
    assert len(a1) == EMBEDDING_DIM
    assert math.isclose(math.sqrt(sum(v * v for v in a1)), 1.0, rel_tol=1e-9)
    [b] = await mock.embed(["something else"])
    assert b != a1


async def test_hybrid_changes_ranking_and_caches_vectors(session):
    # Lexically the rule wins (repeated tokens); semantically the variable chunk
    # text is byte-identical to the query, so hybrid must re-rank it on top.
    records = [
        _rec("rule", "NoisyRule", cube="OEP_FS", data={
            "name": "NoisyRule", "cube": "OEP_FS",
            "body": "CurYr FY25 " * 12 + "SET UPDATECALC OFF;"}),
        _rec("variable", "CurYr", data={"name": "CurYr", "value": "FY25"}),
        _rec("rule", "Unrelated", data={"name": "Unrelated", "body": "AGG(Entity);"}),
    ]
    cv = _persist(session, records, label="hybrid-test")
    query = "CurYr = FY25"

    lexical = await retrieve_grounding(session, cv.id, query, k=3)
    assert lexical[0].kind == "rule" and lexical[0].name == "NoisyRule"
    assert all(c.method == "lexical" for c in lexical)

    hybrid = await retrieve_grounding(session, cv.id, query, k=3, provider=MockProvider())
    assert hybrid[0].kind == "variable" and hybrid[0].name == "CurYr"
    assert hybrid[0].method == "hybrid"
    assert [c.name for c in hybrid] != [c.name for c in lexical]
    again = await retrieve_grounding(session, cv.id, query, k=3, provider=MockProvider())
    assert hybrid == again  # deterministic

    # chunk vectors are cached in the JSON keyed by the embedding model name
    cache = json.loads(_cache_path(cv.id).read_text(encoding="utf-8"))
    assert cache["embeddingModel"] and cache["embeddings"]
    assert len(cache["embeddings"]) == len(cache["chunks"])
    assert all(len(v) == EMBEDDING_DIM for v in cache["embeddings"])


async def test_provider_failure_falls_back_to_lexical(session):
    cv = _persist(session, _corpus_records(), label="fallback-test")
    lexical = await retrieve_grounding(session, cv.id, "copy working to final")
    degraded = await retrieve_grounding(session, cv.id, "copy working to final",
                                        provider=FailingEmbedProvider())
    assert degraded == lexical
    assert all(c.method == "lexical" for c in degraded)


# --- against a real DemoConnector context + synthetic snapshot rule bodies ----------


async def test_retrieve_grounding_on_demo_context_with_snapshot_rules(session):
    proj = projects.get_default_project(session)
    bundle = await build_context(DemoConnector(), "MCWPCF", mode="deep")
    records = list(bundle.records)
    records.append(_rec("rule", "OCF_CopyWorkingToFinal", cube="OEP_FS", data={
        "name": "OCF_CopyWorkingToFinal", "cube": "OEP_FS", "scriptType": "calc",
        "runtimePrompts": ["Entity", "Scenario"],
        "body": 'FIX({Entity}, {Scenario})\n  DATACOPY "OEP_Working" TO "OEP_Final";\nENDFIX',
        "source": "snapshot"}))
    cv = context_store.persist_context(session, proj.id, bundle.application, "hybrid",
                                       "snapshot-merged", {}, {}, records, activate=False)
    session.flush()

    out = await retrieve_grounding(session, cv.id, "create a rule that copies working to final",
                                   kinds=["rule", "template", "variable"], k=4)
    assert out and out[0].name == "OCF_CopyWorkingToFinal"
    assert "DATACOPY" in out[0].snippet
    assert all(c.kind in ("rule", "template", "variable") for c in out)
    assert all(c.context_version == "snapshot-merged" for c in out)

    with_members = await retrieve_grounding(session, cv.id, "Salaries account form",
                                            kinds=["form", "rule", "member", "variable"], k=5)
    assert with_members and all(c.kind in ("form", "rule", "member", "variable") for c in with_members)


# --- schema / block wiring -----------------------------------------------------------


def test_grounding_chunk_schema_and_block_wiring():
    assert CANONICAL_MODELS["GroundingChunk"] is GroundingChunk
    chunk = GroundingChunk(kind="rule", name="R1", snippet="s", score=0.5,
                           method="lexical", context_version="v1")
    dumped = chunk.model_dump(by_alias=True)
    assert dumped["contextVersion"] == "v1" and "context_version" not in dumped

    assert ChatBlockType.grounding_sources.value == "groundingSources"
    from app.agent import blocks
    block = blocks.grounding_sources({"query": "q", "purpose": "rule",
                                      "chunks": [dumped]})
    assert block.type == "groundingSources" and block.data["chunks"][0]["name"] == "R1"
