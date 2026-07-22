"""Run the NLU evaluation harness and print a coverage report.

Usage (from backend/):
    python -m scripts.eval_nlu                 # human-readable report
    python -m scripts.eval_nlu --verbose       # + every failing case & missed check
    python -m scripts.eval_nlu --json          # machine-readable (CI, dashboards)
    python -m scripts.eval_nlu --min-coverage 0.65   # exit non-zero below floor

The bake-off referee: score the LLM-proposes / deterministic-validates strategy
on the identical corpus and compare against the deterministic baseline above.

    python -m scripts.eval_nlu --strategy llm --llm-provider-type openai \\
        --llm-model <model-id>                 # key from OPENAI_API_KEY
    python -m scripts.eval_nlu --strategy llm --llm-provider-type ollama \\
        --llm-base-url http://localhost:11434/v1 --llm-model <model-id>

Report format, ``--json`` and ``--min-coverage`` behave identically for every
strategy — same corpus, comparable number.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from app.eval.runner import format_report, run_eval

PROVIDER_TYPES = ("ollama", "openai", "generic", "anthropic", "gemini")


def _llm_strategy(args: argparse.Namespace):
    from app.eval.llm_strategy import LlmStrategy, provider_complete

    api_key = os.environ.get(args.llm_api_key_env) if args.llm_api_key_env else None
    complete = provider_complete(
        args.llm_provider_type,
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=api_key,
    )
    label = f"llm ({args.llm_provider_type}"
    if args.llm_model:
        label += f": {args.llm_model}"
    label += ")"
    return LlmStrategy(complete, few_shot=args.few_shot, name=label)


def main() -> None:
    parser = argparse.ArgumentParser(description="EPM Wizard NLU evaluation harness")
    parser.add_argument("--verbose", "-v", action="store_true", help="list every failing case")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--min-coverage", type=float, default=None,
                        help="exit with code 1 if overall coverage is below this fraction (0-1)")
    parser.add_argument("--strategy", choices=("deterministic", "llm"), default="deterministic",
                        help="which NLU strategy to score (default: deterministic)")
    parser.add_argument("--llm-provider-type", choices=PROVIDER_TYPES, default="openai",
                        help="AI provider backing --strategy llm (default: openai)")
    parser.add_argument("--llm-base-url", default=None,
                        help="provider base URL (defaults to the provider's standard endpoint)")
    parser.add_argument("--llm-model", default=None,
                        help="model id to evaluate (defaults to the provider's default model)")
    parser.add_argument("--llm-api-key-env", default=None,
                        help="env var to read the API key from (default: the provider's "
                             "standard vars, e.g. OPENAI_API_KEY / ANTHROPIC_API_KEY)")
    parser.add_argument("--few-shot", type=int, default=4,
                        help="number of few-shot examples in the LLM prompt (default: 4)")
    args = parser.parse_args()

    strategy = _llm_strategy(args) if args.strategy == "llm" else None
    report = asyncio.run(run_eval(strategy))

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print(format_report(report, verbose=args.verbose))

    if args.min_coverage is not None and report.coverage < args.min_coverage:
        print(f"coverage {report.coverage:.3f} is below floor {args.min_coverage:.3f}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
