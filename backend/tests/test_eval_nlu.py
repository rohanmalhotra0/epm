"""NLU evaluation harness — coverage floors wired into CI (spec sections 22, 25, 35).

Unlike ``test_form_nlu.py`` (exact assertions on a few phrasings), this runs the
whole golden corpus and guards *aggregate* coverage. The important floor is the
``supported`` tag: those are phrasings the parser is expected to handle, so any
drop there is a real regression. Overall/category floors are set below current
so ordinary corpus edits don't flap; raise them as the NLU genuinely improves.

Run the full report locally with:  python -m scripts.eval_nlu -v
"""

from __future__ import annotations

from app.eval.runner import run_eval


async def test_no_case_raises():
    """Every utterance must route/build without throwing — a crash is never OK."""
    report = await run_eval()
    assert not report.errored, [f"{c.id}: {c.error}" for c in report.errored]


async def test_supported_phrasings_do_not_regress():
    """The 'supported' corpus is the regression baseline; it must stay ~perfect."""
    report = await run_eval()
    supported = report.by_tag().get("supported", 1.0)
    assert supported >= 0.98, f"supported-tag coverage regressed to {supported:.3f}"


async def test_overall_coverage_floor():
    """A conservative floor across the whole corpus (headroom cases included)."""
    report = await run_eval()
    assert report.coverage >= 0.80, f"overall coverage {report.coverage:.3f} below floor"
    assert report.intent_coverage >= 0.80, f"intent coverage {report.intent_coverage:.3f} below floor"
    assert report.build_coverage >= 0.80, f"build coverage {report.build_coverage:.3f} below floor"
    assert report.edit_coverage >= 0.85, f"edit coverage {report.edit_coverage:.3f} below floor"
