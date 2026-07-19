"""Generate a synthetic fine-tuning corpus (JSONL) from the demo metadata.

Manufactures guaranteed-correct pairs for "natural-language request →
FormSpecification JSON" plus edit pairs "current spec + edit instruction →
new spec JSON" using :mod:`app.training.synthetic`:

- every spec is built against real TenantMetadata (DemoConnector fixtures)
  and kept only if ``validate_form`` reports no blocking errors;
- every phrasing is honestly tagged supported/paraphrase by running the
  deterministic parser on it;
- edit labels come from actually running ``form_nlu.apply_edit``.

Output is byte-compatible with ``scripts.export_training_data`` (same record
shapes, SYSTEM prompt, redaction and sha256 dedup), so the files can simply
be concatenated into one corpus. Same seed → identical corpus.

Usage (from backend/):
    python -m scripts.generate_synthetic_corpus --count 2000 --out data/training/synthetic.jsonl
    python -m scripts.generate_synthetic_corpus --format chat --seed 7 --edits-ratio 0.3 --val-split 0.1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from pathlib import Path

from app.artifacts import build_metadata_from_connector
from app.connector import DemoConnector
from app.training.synthetic import TrainingPair, build_corpus, pair_digest
from scripts.export_training_data import _to_record

DEFAULT_APPLICATION = "MCWPCF"
_VAL_HASH_BUCKETS = 10_000


def _is_validation(pair: TrainingPair, val_split: float) -> bool:
    """Deterministic split: hash of the pair decides the side, not its order."""
    bucket = int(pair_digest(pair.prompt, pair.completion)[:8], 16) % _VAL_HASH_BUCKETS
    return bucket < int(round(val_split * _VAL_HASH_BUCKETS))


def _write(path: Path, pairs: list[TrainingPair], fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for pair in pairs:
            fh.write(json.dumps(_to_record(pair.prompt, pair.completion, fmt),
                                ensure_ascii=False) + "\n")


def generate(out_path: Path, count: int = 2000, fmt: str = "watsonx", seed: int = 7,
             edits_ratio: float = 0.3, val_split: float = 0.0,
             application: str = DEFAULT_APPLICATION) -> dict:
    """Write the synthetic JSONL corpus; returns summary counts."""
    md = asyncio.run(build_metadata_from_connector(
        DemoConnector(application=application), application))
    pairs, stats = build_corpus(md, count, random.Random(seed), edits_ratio=edits_ratio)

    train_pairs: list[TrainingPair] = []
    val_pairs: list[TrainingPair] = []
    for pair in pairs:
        (val_pairs if val_split > 0 and _is_validation(pair, val_split) else train_pairs).append(pair)

    _write(out_path, train_pairs, fmt)
    paths = {"train": str(out_path)}
    if val_split > 0:
        val_path = out_path.with_suffix(".val.jsonl")
        _write(val_path, val_pairs, fmt)
        paths["validation"] = str(val_path)

    return {
        "examples": len(pairs),
        "buildPairs": stats["buildPairs"],
        "editPairs": stats["editPairs"],
        "supported": stats["supported"],
        "paraphrase": stats["paraphrase"],
        "duplicatesDropped": stats["duplicatesDropped"],
        "validationRejected": stats["validationRejected"],
        "trainExamples": len(train_pairs),
        "validationExamples": len(val_pairs),
        "paths": paths,
        "format": fmt,
        "seed": seed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=2000, help="number of pairs to emit")
    parser.add_argument("--out", default="data/training/synthetic.jsonl", help="output JSONL path")
    parser.add_argument("--format", choices=["watsonx", "chat"], default="watsonx")
    parser.add_argument("--seed", type=int, default=7, help="corpus seed (same seed → identical corpus)")
    parser.add_argument("--edits-ratio", type=float, default=0.3,
                        help="fraction of pairs that are edit pairs (0-1)")
    parser.add_argument("--val-split", type=float, default=0.0,
                        help="hold out this fraction into <name>.val.jsonl (deterministic by hash)")
    args = parser.parse_args()

    summary = generate(Path(args.out), count=args.count, fmt=args.format, seed=args.seed,
                       edits_ratio=args.edits_ratio, val_split=args.val_split)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
