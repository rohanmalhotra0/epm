"""NLU evaluation harness (spec sections 22, 25, 35).

Measures how well the deterministic form-NLU and intent router turn natural
language into the correct :class:`FormSpecification` / skill. Unlike the
regression tests in ``tests/test_form_nlu.py`` (which assert a handful of exact
phrasings), this harness scores a *graded* golden corpus and reports **coverage
as a percentage**, so quality is measurable rather than pass/fail.

It exists to make two later improvements safe to attempt:

1. A hybrid LLM-proposes / deterministic-validates NLU path — plug an
   alternative :class:`Strategy` into :func:`run_eval` and compare its coverage
   against the deterministic baseline on the exact same corpus.
2. Deeper validation and clarifying-question behaviour — new expectations drop
   into the corpus and immediately show up in the numbers.

Entry points:
    from app.eval.runner import run_eval, format_report   # programmatic / tests
    python -m scripts.eval_nlu                             # CLI report
"""

from __future__ import annotations

from .corpus import BUILD_CASES, EDIT_CASES, INTENT_CASES
from .runner import EvalReport, run_eval
from .scorer import Check, Expect
from .strategy import DeterministicStrategy, Strategy

__all__ = [
    "BUILD_CASES",
    "EDIT_CASES",
    "INTENT_CASES",
    "EvalReport",
    "run_eval",
    "Check",
    "Expect",
    "DeterministicStrategy",
    "Strategy",
]
