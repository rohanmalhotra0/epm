"""Synthetic corpus generator: determinism, validity, honest tagging, formats."""

from __future__ import annotations

import json
import random

from app.agent.form_nlu import build_initial_spec
from app.artifacts import validate_form
from app.schemas.form_spec import FormSpecification
from app.training import synthetic
from app.training.synthetic import (
    Phrase,
    build_corpus,
    generate_edit_pair,
    generate_spec,
    pair_digest,
    phrase_spec,
    spec_to_json,
)
from scripts.export_training_data import SYSTEM_PROMPT
from scripts.generate_synthetic_corpus import generate


def _scenario_of(spec: FormSpecification) -> str | None:
    for am in spec.pov + spec.pages:
        if am.dimension == "Scenario":
            return am.selection.member
    return None


async def test_same_seed_identical_corpus(md):
    first, first_stats = build_corpus(md, 60, random.Random(7))
    second, second_stats = build_corpus(md, 60, random.Random(7))
    assert first == second
    assert first_stats == second_stats
    other, _ = build_corpus(md, 60, random.Random(8))
    assert other != first


async def test_generated_specs_always_validate(md):
    rng = random.Random(11)
    for _ in range(40):
        spec = generate_spec(md, rng)
        report = validate_form(spec, md)
        assert not report.blocking, [i.message for i in report.errors]


async def test_edit_pairs_change_spec_and_still_validate(md):
    rng = random.Random(3)
    made = 0
    for _ in range(60):
        spec = generate_spec(md, rng)
        pair = generate_edit_pair(spec, md, rng)
        if pair is None:
            continue
        made += 1
        old_json = spec_to_json(spec)
        assert old_json in pair.prompt  # input embeds the current spec verbatim
        assert pair.completion != old_json  # the edit really changed something
        new_spec = FormSpecification.model_validate(json.loads(pair.completion))
        assert not validate_form(new_spec, md).blocking
    assert made >= 20  # the edit path succeeds for most specs


async def test_phrase_tagging_runs_the_real_parser(md):
    rng = random.Random(5)
    tags: set[str] = set()
    for _ in range(30):
        spec = generate_spec(md, rng)
        for phrase in phrase_spec(spec, md, rng):
            parsed, _, _ = build_initial_spec(phrase.text, md, spec.application)
            reproduced = (
                parsed.cube == spec.cube
                and _scenario_of(parsed) == _scenario_of(spec)
                and bool(parsed.rows)
                and parsed.rows[0].dimension == spec.rows[0].dimension
                and parsed.rows[0].selection.type == spec.rows[0].selection.type
                and (parsed.rows[0].selection.member or "") == (spec.rows[0].selection.member or "")
            )
            assert phrase.tag == ("supported" if reproduced else "paraphrase")
            tags.add(phrase.tag)
    assert tags == {"supported", "paraphrase"}  # both kinds occur and are kept


async def test_corpus_pairs_are_unique_and_counted(md):
    pairs, stats = build_corpus(md, 120, random.Random(7), edits_ratio=0.3)
    assert len(pairs) == 120
    digests = {pair_digest(p.prompt, p.completion) for p in pairs}
    assert len(digests) == len(pairs)
    assert stats["buildPairs"] + stats["editPairs"] == len(pairs)
    assert stats["supported"] + stats["paraphrase"] == stats["buildPairs"]
    assert stats["editPairs"] > 0 and stats["buildPairs"] > 0


async def test_dedup_drops_repeated_pairs(md, monkeypatch):
    spec = generate_spec(md, random.Random(1))
    monkeypatch.setattr(synthetic, "generate_spec", lambda _md, _rng: spec)
    monkeypatch.setattr(
        synthetic, "phrase_spec",
        lambda _spec, _md, _rng: [Phrase(text="the same phrase", tag="paraphrase")])
    pairs, stats = build_corpus(md, 5, random.Random(7), edits_ratio=0.0)
    assert len(pairs) == 1  # every repeat is dropped by the sha256 dedup
    assert stats["duplicatesDropped"] > 0


def test_cli_instruct_format_matches_exporter(tmp_path):
    out = tmp_path / "syn.jsonl"
    summary = generate(out, count=40, fmt="instruct", seed=7, edits_ratio=0.25)
    records = [json.loads(line) for line in out.read_text().splitlines()]
    assert summary["examples"] == len(records) == 40
    assert all(set(r) == {"input", "output"} for r in records)
    # completions are the app's own camelCase spec JSON
    build = [r for r in records if not r["input"].startswith("Current form specification:")]
    edits = [r for r in records if r["input"].startswith("Current form specification:")]
    assert build and edits
    assert json.loads(build[0]["output"])["schemaVersion"]
    assert summary["supported"] + summary["paraphrase"] == summary["buildPairs"]
    assert summary["buildPairs"] + summary["editPairs"] == summary["examples"]


def test_cli_chat_format_matches_exporter(tmp_path):
    out = tmp_path / "syn-chat.jsonl"
    generate(out, count=20, fmt="chat", seed=7)
    records = [json.loads(line) for line in out.read_text().splitlines()]
    assert records
    for record in records:
        assert list(record) == ["messages"]
        assert [m["role"] for m in record["messages"]] == ["system", "user", "assistant"]
        assert record["messages"][0]["content"] == SYSTEM_PROMPT


def test_val_split_deterministic_and_disjoint(tmp_path):
    out1, out2 = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    summary = generate(out1, count=80, fmt="instruct", seed=7, val_split=0.2)
    generate(out2, count=80, fmt="instruct", seed=7, val_split=0.2)

    train1, val1 = out1.read_text(), (tmp_path / "a.val.jsonl").read_text()
    train2, val2 = out2.read_text(), (tmp_path / "b.val.jsonl").read_text()
    assert train1 == train2 and val1 == val2  # split by hash, not by order/run

    train_lines, val_lines = train1.splitlines(), val1.splitlines()
    assert len(train_lines) + len(val_lines) == summary["examples"] == 80
    assert summary["validationExamples"] == len(val_lines) > 0
    assert not set(train_lines) & set(val_lines)
    assert summary["paths"]["validation"].endswith("a.val.jsonl")
