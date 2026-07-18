"""Run the NLU evaluation harness and print a coverage report.

Usage (from backend/):
    python -m scripts.eval_nlu                 # human-readable report
    python -m scripts.eval_nlu --verbose       # + every failing case & missed check
    python -m scripts.eval_nlu --json          # machine-readable (CI, dashboards)
    python -m scripts.eval_nlu --min-coverage 0.65   # exit non-zero below floor

Point it at a different NLU by importing an alternative Strategy and passing it to
``run_eval`` — same corpus, comparable number. That is how the future
LLM-proposes / deterministic-validates path proves it beat the baseline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.eval.runner import format_report, run_eval


def main() -> None:
    parser = argparse.ArgumentParser(description="EPM Wizard NLU evaluation harness")
    parser.add_argument("--verbose", "-v", action="store_true", help="list every failing case")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--min-coverage", type=float, default=None,
                        help="exit with code 1 if overall coverage is below this fraction (0-1)")
    args = parser.parse_args()

    report = asyncio.run(run_eval())

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print(format_report(report, verbose=args.verbose))

    if args.min_coverage is not None and report.coverage < args.min_coverage:
        print(f"coverage {report.coverage:.3f} is below floor {args.min_coverage:.3f}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
