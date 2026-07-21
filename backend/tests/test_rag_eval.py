"""RAG retrieval eval harness tests: in-process, deterministic, DB-free."""

from __future__ import annotations

from app.ai.mock import MockProvider
from scripts.eval_rag import (
    CASES,
    DEFAULT_GATE,
    build_eval_index,
    format_report,
    run_rag_eval,
)


def test_eval_index_is_built_in_memory_without_a_session():
    index = build_eval_index()
    assert index.chunks and index.context_version_id == "eval-rag-corpus"
    kinds = {c.kind for c in index.chunks}
    assert {"rule", "template", "form", "variable", "member"} <= kinds
    cubes = {c.cube for c in index.chunks if c.cube}
    assert {"OEP_FS", "OEP_WFP"} <= cubes
    # members collapse into one digest per dimension, never one chunk each
    assert sorted(c.name for c in index.chunks if c.kind == "member") == ["Account", "Department"]


async def test_lexical_retrieval_is_perfect_on_the_builtin_corpus():
    report = await run_rag_eval()
    assert report.mode == "lexical (BM25)"
    assert report.hit_at_k == 1.0
    assert report.hit_at_1 == 1.0 and report.mrr == 1.0  # every positive ranks first
    assert report.negative_pass_rate == 1.0  # negatives stay below the floor
    assert len(report.results) == len(CASES)


async def test_report_dict_has_the_documented_keys():
    report = await run_rag_eval()
    d = report.to_dict()
    assert {"mode", "k", "scoreFloor", "positives", "negatives",
            "hitAt1", "hitAtK", "mrr", "negativePassRate", "byTag", "cases"} <= set(d)
    assert d["positives"] + d["negatives"] == len(CASES)
    assert d["hitAt1"] == d["hitAtK"] == d["mrr"] == 1.0
    for case in d["cases"]:
        assert {"id", "query", "negative", "rank", "hitAtK", "passed", "top"} <= set(case)
    # rendering never crashes and carries the headline numbers
    text = format_report(report, verbose=True)
    assert "RAG retrieval eval" in text and "hit@5" in text and "100.0%" in text


async def test_eval_is_deterministic_across_runs():
    first = await run_rag_eval()
    second = await run_rag_eval()
    assert first.to_dict() == second.to_dict()


async def test_hybrid_mock_provider_still_meets_the_gate():
    report = await run_rag_eval(MockProvider())
    assert report.mode.startswith("hybrid")
    assert any(t["method"] in ("hybrid", "semantic")
               for r in report.results for t in r.top)
    assert report.hit_at_k >= DEFAULT_GATE  # the CI gate holds under hybrid scoring
    assert report.negative_pass_rate == 1.0  # semantic noise alone can't clear the floor
    again = await run_rag_eval(MockProvider())
    assert report.to_dict() == again.to_dict()  # hash embeddings are deterministic
