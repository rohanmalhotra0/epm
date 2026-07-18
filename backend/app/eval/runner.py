"""Run the golden corpus through a strategy and aggregate coverage.

``coverage`` is the fraction of atomic checks that pass across the whole corpus
(partial credit per case); ``exact_rate`` is the fraction of cases that pass
*every* check. Both are reported overall, per category (intent / build / edit),
and per check-type (cube, rows.type, pov, display …) so a regression points at
the exact capability that slipped.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..artifacts import build_metadata_from_connector
from ..artifacts.metadata import TenantMetadata
from ..connector import DemoConnector
from .corpus import BUILD_CASES, EDIT_CASES, INTENT_CASES
from .scorer import Check, ScoredCase, score_spec
from .strategy import DeterministicStrategy, Strategy

APPLICATION = "MCWPCF"


@dataclass
class EvalReport:
    strategy: str
    cases: list[ScoredCase] = field(default_factory=list)

    # --- aggregate helpers ---
    def _subset(self, kind: str | None = None) -> list[ScoredCase]:
        return [c for c in self.cases if kind is None or c.kind == kind]

    def _coverage(self, cases: list[ScoredCase]) -> float:
        passed = sum(c.passed for c in cases)
        total = sum(c.total for c in cases)
        return 1.0 if total == 0 else passed / total

    def _exact_rate(self, cases: list[ScoredCase]) -> float:
        return 0.0 if not cases else sum(1 for c in cases if c.exact) / len(cases)

    @property
    def coverage(self) -> float:
        return self._coverage(self.cases)

    @property
    def exact_rate(self) -> float:
        return self._exact_rate(self.cases)

    @property
    def intent_coverage(self) -> float:
        return self._coverage(self._subset("intent"))

    @property
    def build_coverage(self) -> float:
        return self._coverage(self._subset("build"))

    @property
    def edit_coverage(self) -> float:
        return self._coverage(self._subset("edit"))

    @property
    def errored(self) -> list[ScoredCase]:
        return [c for c in self.cases if c.error]

    def by_kind(self) -> dict[str, tuple[float, float, int]]:
        """kind -> (coverage, exact_rate, n_cases)."""
        out: dict[str, tuple[float, float, int]] = {}
        for kind in ("intent", "build", "edit"):
            sub = self._subset(kind)
            out[kind] = (self._coverage(sub), self._exact_rate(sub), len(sub))
        return out

    def by_check_kind(self) -> dict[str, tuple[int, int]]:
        """check-type -> (passed, total), sorted worst-first."""
        agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for case in self.cases:
            for chk in case.checks:
                agg[chk.kind][0] += int(chk.ok)
                agg[chk.kind][1] += 1
        return {k: (v[0], v[1]) for k, v in
                sorted(agg.items(), key=lambda kv: (kv[1][0] / kv[1][1] if kv[1][1] else 1.0))}

    def by_tag(self) -> dict[str, float]:
        """tag -> coverage, so 'supported' vs 'paraphrase' headroom is visible."""
        agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for case in self.cases:
            for tag in case.tags:
                agg[tag][0] += case.passed
                agg[tag][1] += case.total
        return {k: (v[0] / v[1] if v[1] else 1.0) for k, v in sorted(agg.items())}

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "coverage": self.coverage,
            "exactRate": self.exact_rate,
            "byKind": {k: {"coverage": c, "exactRate": e, "cases": n}
                       for k, (c, e, n) in self.by_kind().items()},
            "byCheckKind": {k: {"passed": p, "total": t} for k, (p, t) in self.by_check_kind().items()},
            "byTag": self.by_tag(),
            "errored": [c.id for c in self.errored],
            "cases": [
                {
                    "id": c.id, "kind": c.kind, "utterance": c.utterance,
                    "passed": c.passed, "total": c.total, "exact": c.exact,
                    "error": c.error,
                    "failures": [
                        {"name": f.name, "expected": f.expected, "actual": f.actual}
                        for f in c.failures
                    ],
                }
                for c in self.cases
            ],
        }


async def _metadata() -> TenantMetadata:
    return await build_metadata_from_connector(DemoConnector(), APPLICATION)


def _run_intent(strategy: Strategy) -> list[ScoredCase]:
    cases: list[ScoredCase] = []
    for case in INTENT_CASES:
        sc = ScoredCase(id=f"intent.{case.utterance[:32]}", kind="intent", utterance=case.utterance)
        try:
            routed = strategy.route(case.utterance)
            sc.checks.append(Check("skill", routed == case.skill, case.skill, routed))
        except Exception as exc:  # a router crash is a real, reportable failure
            sc.error = f"{type(exc).__name__}: {exc}"
        sc.tags = case.tags
        cases.append(sc)
    return cases


def _run_build(strategy: Strategy, md: TenantMetadata) -> list[ScoredCase]:
    cases: list[ScoredCase] = []
    for case in BUILD_CASES:
        sc = ScoredCase(id=case.id, kind="build", utterance=case.utterance)
        try:
            spec = strategy.build(case.utterance, md, APPLICATION)
            sc.checks = score_spec(spec, case.expect, md)
        except Exception as exc:
            sc.error = f"{type(exc).__name__}: {exc}"
        sc.tags = case.tags
        cases.append(sc)
    return cases


def _run_edit(strategy: Strategy, md: TenantMetadata) -> list[ScoredCase]:
    cases: list[ScoredCase] = []
    for case in EDIT_CASES:
        sc = ScoredCase(id=case.id, kind="edit", utterance=f"{case.base!r} → {case.edit!r}")
        try:
            spec = strategy.build(case.base, md, APPLICATION)
            changed = strategy.edit(spec, case.edit, md)
            sc.checks = score_spec(spec, case.expect, md)
            sc.checks.append(Check("changed", changed == case.expect_changed,
                                   case.expect_changed, changed))
        except Exception as exc:
            sc.error = f"{type(exc).__name__}: {exc}"
        sc.tags = case.tags
        cases.append(sc)
    return cases


async def run_eval(strategy: Strategy | None = None) -> EvalReport:
    """Score the full corpus with ``strategy`` (deterministic baseline by default)."""
    strat = strategy or DeterministicStrategy()
    md = await _metadata()
    report = EvalReport(strategy=strat.name)
    report.cases += _run_intent(strat)
    report.cases += _run_build(strat, md)
    report.cases += _run_edit(strat, md)
    return report


# --- rendering -------------------------------------------------------------

def _bar(frac: float, width: int = 20) -> str:
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled)


def _pct(frac: float) -> str:
    return f"{frac * 100:5.1f}%"


def format_report(report: EvalReport, verbose: bool = False) -> str:
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append(f"  NLU eval — strategy: {report.strategy}")
    lines.append("=" * 68)
    lines.append(f"  overall coverage  {_bar(report.coverage)}  {_pct(report.coverage)}")
    lines.append(f"  exact-match rate  {_bar(report.exact_rate)}  {_pct(report.exact_rate)}")
    lines.append("")

    lines.append("  by category            coverage        exact     cases")
    lines.append("  " + "-" * 58)
    for kind, (cov, exact, n) in report.by_kind().items():
        lines.append(f"  {kind:<12}   {_bar(cov, 14)} {_pct(cov)}   {_pct(exact)}   {n:>3}")
    lines.append("")

    tags = report.by_tag()
    if tags:
        lines.append("  by tag                 coverage")
        lines.append("  " + "-" * 40)
        for tag, cov in tags.items():
            lines.append(f"  {tag:<14} {_bar(cov, 14)} {_pct(cov)}")
        lines.append("")

    lines.append("  weakest capabilities (check type: pass/total)")
    lines.append("  " + "-" * 50)
    for kind, (passed, total) in list(report.by_check_kind().items())[:10]:
        frac = passed / total if total else 1.0
        lines.append(f"  {kind:<20} {passed:>3}/{total:<3}  {_pct(frac)}")
    lines.append("")

    if report.errored:
        lines.append(f"  ⚠ {len(report.errored)} case(s) raised an exception:")
        for c in report.errored:
            lines.append(f"    - {c.id}: {c.error}")
        lines.append("")

    if verbose:
        failing = [c for c in report.cases if not c.exact and not c.error]
        if failing:
            lines.append("  failing cases (missed checks)")
            lines.append("  " + "-" * 58)
            for c in failing:
                lines.append(f"  ✗ [{c.kind}] {c.utterance}   ({c.passed}/{c.total})")
                for f in c.failures:
                    lines.append(f"        {f.name}: expected {f.expected!r}, got {f.actual!r}")
            lines.append("")

    lines.append("=" * 68)
    return "\n".join(lines)
