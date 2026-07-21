"""Run the RAG retrieval-quality eval and print a ranking report.

Usage (from backend/):
    python -m scripts.eval_rag                 # human-readable report
    python -m scripts.eval_rag --verbose       # + per-case ranks and top results
    python -m scripts.eval_rag --json          # machine-readable (CI, dashboards)
    python -m scripts.eval_rag --provider mock # hybrid scoring (BM25 + MockProvider
                                               #   hash embeddings) instead of lexical
    python -m scripts.eval_rag --min-hit-at-k 0.9   # tighten the CI gate

Sibling of ``scripts.eval_nlu``: same report conventions, same CI contract
(``--json`` for machines, non-zero exit below the floor). The harness is fully
deterministic and DB-free — a built-in synthetic corpus (rules with bodies,
templates, forms, variables, members across two cubes) is chunked with
``app.rag.chunker.build_chunks`` and scored against a ``RagIndex`` constructed
directly from those chunks, so nothing is persisted and the user's database is
never touched. The scoring math mirrors ``app.rag.index.retrieve_grounding``
exactly (normalized BM25, optional 0.5/0.5 hybrid with embeddings, ties broken
on (kind, name)).

Metrics (the ``to_dict()`` keys are the stable contract):
    mode, k, scoreFloor, positives, negatives,
    hitAt1, hitAtK, mrr, negativePassRate, cases

* ``hit@1`` / ``hit@k`` — fraction of positive cases whose expected chunk is
  ranked first / within the top k.
* ``MRR`` — mean reciprocal rank of the expected chunk over positive cases.
* negatives pass when no chunk scores at or above ``SCORE_FLOOR`` (pure
  semantic noise tops out at 0.5, so the floor separates "some lexical
  evidence" from "no evidence" in both modes).

Gate: exit code 1 when hit@k falls below ``--min-hit-at-k`` (default 0.8).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field

from app.rag.chunker import build_chunks, tokenize
from app.rag.index import RagIndex, _cosine

DEFAULT_K = 5
SCORE_FLOOR = 0.6
DEFAULT_GATE = 0.8


# --- eval corpus (synthetic, deterministic, never persisted) -----------------


@dataclass(frozen=True)
class EvalRecord:
    """Duck-typed stand-in for a ContextRecord: exactly the attributes
    ``build_chunks`` reads, with no ORM and no session behind it."""

    kind: str
    name: str
    cube: str | None = None
    dimension: str | None = None
    alias: str | None = None
    data: dict | None = None


def _rule(name: str, cube: str, body: str, prompts: list[str] | None = None) -> EvalRecord:
    data = {"name": name, "cube": cube, "body": body}
    if prompts:
        data["runtimePrompts"] = prompts
    return EvalRecord("rule", name, cube=cube, data=data)


def _member(name: str, dimension: str, alias: str | None = None) -> EvalRecord:
    return EvalRecord("member", name, dimension=dimension, alias=alias,
                      data={"name": name, "dimension": dimension})


# Two cubes (OEP_FS financials, OEP_WFP workforce), realistic naming
# conventions, and rule/template bodies with searchable content. Kept small on
# purpose: every case failure should be explainable by reading this list.
CORPUS: list[EvalRecord] = [
    # --- rules ---
    _rule("OFS_CopyWorkingToFinal", "OEP_FS",
          'FIX({Entity})\n  DATACOPY "OEP_Working" TO "OEP_Final";\nENDFIX\n'
          "/* copy working version to final */", prompts=["Entity"]),
    _rule("OFS_AggFinancials", "OEP_FS",
          'AGG("Account", "Entity");\n/* aggregate financial statement totals */'),
    _rule("OFS_RollupCash", "OEP_FS",
          'FIX(@IDESCENDANTS("OCF_TotalCash"))\n  CALC DIM("Account");\nENDFIX\n'
          "/* roll up operating cash flow accounts */"),
    _rule("OWP_CalcSalaries", "OEP_WFP",
          'FIX({Scenario})\n  "Salaries" = "Salaries" * (1 + "MeritRate");\nENDFIX\n'
          "/* annual salary merit increase for workforce planning */", prompts=["Scenario"]),
    _rule("OWP_ClearHeadcount", "OEP_WFP",
          'FIX("OEP_Plan")\n  CLEARDATA "Headcount";\nENDFIX\n'
          "/* clear headcount data before each reload */"),
    # --- templates ---
    EvalRecord("template", "OFS_ClearBudget", cube="OEP_FS", data={
        "name": "OFS_ClearBudget", "cube": "OEP_FS",
        "body": 'CLEARDATA "Budget";\n/* wipe budget scenario data ahead of a fresh seed */'}),
    EvalRecord("template", "OWP_SeedNewHires", cube="OEP_WFP", data={
        "name": "OWP_SeedNewHires", "cube": "OEP_WFP",
        "body": '"Headcount" = "Headcount" + "NewHireRequisitions";\n'
                "/* seed approved new hire requisitions into plan headcount */"}),
    # --- forms ---
    EvalRecord("form", "OFS_Rolling Forecast", cube="OEP_FS", data={
        "name": "OFS_Rolling Forecast", "cube": "OEP_FS", "folder": "Forecast/Input",
        "description": "Rolling forecast input by entity and month"}),
    EvalRecord("form", "OFS_Income Statement", cube="OEP_FS", data={
        "name": "OFS_Income Statement", "cube": "OEP_FS", "folder": "Reports",
        "description": "Income statement review with variance columns"}),
    EvalRecord("form", "OWP_Headcount Plan", cube="OEP_WFP", data={
        "name": "OWP_Headcount Plan", "cube": "OEP_WFP", "folder": "Workforce/Input",
        "description": "Plan headcount and new hires by department"}),
    # --- variables ---
    EvalRecord("variable", "CurYr", data={"name": "CurYr", "value": "FY25", "planType": "OEP_FS"}),
    EvalRecord("variable", "NextYr", data={"name": "NextYr", "value": "FY26", "planType": "OEP_WFP"}),
    # --- members (collapse into one convention digest per dimension) ---
    _member("OCF_NetCash", "Account"),
    _member("OCF_OperatingCash", "Account"),
    _member("OCF_TotalCash", "Account", alias="Total Cash Flow"),
    _member("DEP_Sales", "Department"),
    _member("DEP_Engineering", "Department"),
]


# --- retrieval cases ---------------------------------------------------------


@dataclass(frozen=True)
class RetrievalCase:
    id: str
    query: str
    expect_kind: str | None  # None => negative case (expect no hit above floor)
    expect_name: str | None
    tags: tuple[str, ...] = ()

    @property
    def negative(self) -> bool:
        return self.expect_name is None


CASES: list[RetrievalCase] = [
    # exact artifact names
    RetrievalCase("name.rule_copy", "OFS_CopyWorkingToFinal",
                  "rule", "OFS_CopyWorkingToFinal", ("exact-name",)),
    RetrievalCase("name.template_seed", "show me OWP_SeedNewHires",
                  "template", "OWP_SeedNewHires", ("exact-name",)),
    RetrievalCase("name.form_income", "open the OFS_Income Statement form",
                  "form", "OFS_Income Statement", ("exact-name",)),
    # body-content retrieval
    RetrievalCase("body.datacopy", "which rule uses DATACOPY",
                  "rule", "OFS_CopyWorkingToFinal", ("body",)),
    RetrievalCase("body.clear_headcount", "clear headcount data before reload",
                  "rule", "OWP_ClearHeadcount", ("body",)),
    RetrievalCase("body.wipe_budget", "wipe the budget scenario ahead of the seed",
                  "template", "OFS_ClearBudget", ("body",)),
    RetrievalCase("body.salary_merit", "salary merit increase rule",
                  "rule", "OWP_CalcSalaries", ("body",)),
    RetrievalCase("body.cash_rollup", "roll up operating cash flow",
                  "rule", "OFS_RollupCash", ("body",)),
    # naming conventions / member digests
    RetrievalCase("member.ocf_prefix",
                  "which members use the OCF_ naming prefixes in the Account dimension",
                  "member", "Account", ("naming",)),
    RetrievalCase("member.alias", "Total Cash Flow", "member", "Account", ("naming", "alias")),
    # variables and forms by content
    RetrievalCase("variable.fy25", "which substitution variable holds FY25",
                  "variable", "CurYr", ("variable",)),
    RetrievalCase("form.rolling", "where do I enter the rolling forecast",
                  "form", "OFS_Rolling Forecast", ("form",)),
    # negatives: no chunk should clear the score floor
    RetrievalCase("negative.cooking", "grilled steak marinade recipe", None, None, ("negative",)),
    RetrievalCase("negative.travel", "airline baggage weight allowance", None, None, ("negative",)),
]


# --- scoring (mirrors app.rag.index.retrieve_grounding, minus the DB) --------


def build_eval_index() -> RagIndex:
    """The retrieval index over the built-in corpus — constructed directly from
    chunks, so no session, no cache file, no persistence."""
    return RagIndex(context_version_id="eval-rag-corpus", label="eval-rag",
                    chunks=build_chunks(CORPUS))


async def _rank(index: RagIndex, query: str, chunk_vecs: list[list[float]] | None,
                provider) -> list[tuple[int, float, str]]:
    """(chunk index, score, method) best-first — the exact production formula:
    BM25 normalized by the result-set max, hybrid ``0.5*bm25 + 0.5*cosine``
    when embeddings are available, zero-score chunks dropped, ties broken on
    (kind, name)."""
    raw = index.bm25_scores(tokenize(query))
    max_raw = max(raw, default=0.0)
    bm25_norm = [r / max_raw if max_raw > 0 else 0.0 for r in raw]

    scores = list(bm25_norm)
    methods = ["lexical"] * len(index.chunks)
    if chunk_vecs is not None and provider is not None:
        qvec = (await provider.embed([query]))[0]
        cos = [max(0.0, _cosine(qvec, v)) for v in chunk_vecs]
        max_cos = max(cos, default=0.0)
        for i in range(len(index.chunks)):
            cos_norm = cos[i] / max_cos if max_cos > 0 else 0.0
            scores[i] = 0.5 * bm25_norm[i] + 0.5 * cos_norm
            methods[i] = "semantic" if bm25_norm[i] == 0.0 else "hybrid"

    ranked = sorted((i for i in range(len(index.chunks)) if scores[i] > 0.0),
                    key=lambda i: (-scores[i], index.chunks[i].kind, index.chunks[i].name))
    return [(i, scores[i], methods[i]) for i in ranked]


# --- report ------------------------------------------------------------------


@dataclass
class CaseResult:
    id: str
    query: str
    negative: bool
    tags: tuple[str, ...]
    rank: int | None = None  # 1-based rank of the expected chunk (positives)
    hit_at_k: bool = False
    passed: bool = False  # positives: hit@k; negatives: floor held
    top: list[dict] = field(default_factory=list)  # head of the ranking, for --verbose


@dataclass
class RagEvalReport:
    mode: str
    k: int
    floor: float
    results: list[CaseResult] = field(default_factory=list)

    @property
    def _positives(self) -> list[CaseResult]:
        return [r for r in self.results if not r.negative]

    @property
    def _negatives(self) -> list[CaseResult]:
        return [r for r in self.results if r.negative]

    @property
    def hit_at_1(self) -> float:
        pos = self._positives
        return 0.0 if not pos else sum(1 for r in pos if r.rank == 1) / len(pos)

    @property
    def hit_at_k(self) -> float:
        pos = self._positives
        return 0.0 if not pos else sum(1 for r in pos if r.hit_at_k) / len(pos)

    @property
    def mrr(self) -> float:
        pos = self._positives
        return 0.0 if not pos else sum(1.0 / r.rank for r in pos if r.rank) / len(pos)

    @property
    def negative_pass_rate(self) -> float:
        neg = self._negatives
        return 1.0 if not neg else sum(1 for r in neg if r.passed) / len(neg)

    def by_tag(self) -> dict[str, float]:
        """tag -> pass rate, so a slipping capability (body vs naming vs …) shows."""
        agg: dict[str, list[int]] = {}
        for r in self.results:
            for tag in r.tags:
                agg.setdefault(tag, [0, 0])
                agg[tag][0] += int(r.passed)
                agg[tag][1] += 1
        return {t: (v[0] / v[1] if v[1] else 1.0) for t, v in sorted(agg.items())}

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "k": self.k,
            "scoreFloor": self.floor,
            "positives": len(self._positives),
            "negatives": len(self._negatives),
            "hitAt1": self.hit_at_1,
            "hitAtK": self.hit_at_k,
            "mrr": self.mrr,
            "negativePassRate": self.negative_pass_rate,
            "byTag": self.by_tag(),
            "cases": [
                {
                    "id": r.id, "query": r.query, "negative": r.negative,
                    "rank": r.rank, "hitAtK": r.hit_at_k, "passed": r.passed,
                    "top": r.top,
                }
                for r in self.results
            ],
        }


async def run_rag_eval(provider=None, k: int = DEFAULT_K,
                       floor: float = SCORE_FLOOR) -> RagEvalReport:
    """Score every retrieval case against the built-in corpus.

    ``provider=None`` scores lexical BM25 only; a provider with embedding
    support (e.g. ``MockProvider``) exercises the hybrid path. Deterministic
    for any deterministic provider — no randomness, no clock, no I/O."""
    index = build_eval_index()
    chunk_vecs = None
    if provider is not None and getattr(provider, "capabilities", {}).get("embeddings"):
        chunk_vecs = await provider.embed([c.text for c in index.chunks])
        mode = f"hybrid ({getattr(provider, 'name', 'provider')})"
    else:
        provider = None
        mode = "lexical (BM25)"

    report = RagEvalReport(mode=mode, k=k, floor=floor)
    for case in CASES:
        ranked = await _rank(index, case.query, chunk_vecs, provider)
        result = CaseResult(id=case.id, query=case.query, negative=case.negative,
                            tags=case.tags)
        result.top = [
            {"kind": index.chunks[i].kind, "name": index.chunks[i].name,
             "score": round(score, 6), "method": method}
            for i, score, method in ranked[:k]
        ]
        if case.negative:
            result.passed = all(score < floor for _, score, _ in ranked)
        else:
            for pos, (i, _score, _method) in enumerate(ranked, start=1):
                chunk = index.chunks[i]
                if chunk.kind == case.expect_kind and chunk.name == case.expect_name:
                    result.rank = pos
                    break
            result.hit_at_k = result.rank is not None and result.rank <= k
            result.passed = result.hit_at_k
        report.results.append(result)
    return report


# --- rendering ---------------------------------------------------------------


def _bar(frac: float, width: int = 20) -> str:
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled)


def _pct(frac: float) -> str:
    return f"{frac * 100:5.1f}%"


def format_report(report: RagEvalReport, verbose: bool = False) -> str:
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append(f"  RAG retrieval eval — mode: {report.mode}")
    lines.append("=" * 68)
    lines.append(f"  hit@1             {_bar(report.hit_at_1)}  {_pct(report.hit_at_1)}")
    lines.append(f"  hit@{report.k}             {_bar(report.hit_at_k)}  {_pct(report.hit_at_k)}")
    lines.append(f"  MRR               {_bar(report.mrr)}  {_pct(report.mrr)}")
    negs = [r for r in report.results if r.negative]
    held = sum(1 for r in negs if r.passed)
    lines.append(f"  negatives held    {held}/{len(negs)} below score floor {report.floor:.2f}")
    lines.append("")

    lines.append("  by tag                 pass rate")
    lines.append("  " + "-" * 40)
    for tag, rate in report.by_tag().items():
        lines.append(f"  {tag:<14} {_bar(rate, 14)} {_pct(rate)}")
    lines.append("")

    failing = [r for r in report.results if not r.passed]
    if failing:
        lines.append(f"  ✗ {len(failing)} failing case(s)")
        lines.append("  " + "-" * 58)
        for r in failing:
            what = "expected no hit above floor" if r.negative else f"rank {r.rank or '∅'}"
            lines.append(f"  ✗ {r.id}: {r.query!r} — {what}")
            for t in r.top[:3]:
                lines.append(f"        {t['kind']}/{t['name']}  {t['score']:.3f} ({t['method']})")
        lines.append("")

    if verbose:
        lines.append("  per-case ranking")
        lines.append("  " + "-" * 58)
        for r in report.results:
            mark = "✓" if r.passed else "✗"
            what = "negative" if r.negative else f"rank {r.rank or '∅'}"
            lines.append(f"  {mark} {r.id:<24} {what:<10} {r.query!r}")
            for t in r.top[:3]:
                lines.append(f"        {t['kind']}/{t['name']}  {t['score']:.3f} ({t['method']})")
        lines.append("")

    lines.append("=" * 68)
    return "\n".join(lines)


# --- CLI ----------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="EPM Wizard RAG retrieval eval harness")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="list every case with its top-ranked chunks")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--provider", choices=("mock",), default=None,
                        help="score hybrid retrieval with the deterministic MockProvider "
                             "embeddings (default: lexical BM25 only)")
    parser.add_argument("--k", type=int, default=DEFAULT_K,
                        help=f"retrieval depth for hit@k (default: {DEFAULT_K})")
    parser.add_argument("--min-hit-at-k", type=float, default=DEFAULT_GATE,
                        help="exit with code 1 if hit@k is below this fraction "
                             f"(default: {DEFAULT_GATE})")
    args = parser.parse_args()

    provider = None
    if args.provider == "mock":
        from app.ai.mock import MockProvider

        provider = MockProvider()

    report = asyncio.run(run_rag_eval(provider, k=args.k))

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print(format_report(report, verbose=args.verbose))

    if report.hit_at_k < args.min_hit_at_k:
        print(f"hit@{args.k} {report.hit_at_k:.3f} is below floor {args.min_hit_at_k:.3f}",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
