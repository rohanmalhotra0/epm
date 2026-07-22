"""Launch (or dry-run) a Together AI LoRA fine-tune of the EPM coder model.

This is the Phase 5 launcher from ``docs/OPENCLAW_PLAN.md``: it ties the
existing corpus tooling to Together's fine-tuning REST API. It

1. **assembles a corpus** — either an existing JSONL you pass with ``--train``
   (and optional ``--val``), or a fresh, guaranteed-correct synthetic corpus
   built on the spot via :mod:`scripts.generate_synthetic_corpus` (``--build``);
2. **preflights** it — counts examples and refuses a corpus that is obviously
   too small to be worth a paid run (override with ``--force``);
3. **uploads** the file(s) to Together's ``/files`` endpoint; and
4. **creates a LoRA fine-tune job** on the base coder model, then prints the
   job id (and follows it to completion with ``--follow``).

Safety: **it does nothing billable unless you pass ``--launch``.** Without that
flag it is a dry run — it assembles and validates the corpus and prints the
exact upload + job plan, but never touches the network. Fine-tuning is cheap to
*run* but a served fine-tune can be expensive (see the cost cliff in
OPENCLAW_PLAN.md §1), so the paid step is opt-in, not the default.

The API key is read from ``--api-key``, else ``$TOGETHER_API_KEY``. It is never
logged or written anywhere.

Usage (from backend/):
    # Dry run on a fresh synthetic corpus — safe, no network, no cost:
    python -m scripts.launch_finetune --build

    # Dry run on your exported corpus:
    python -m scripts.launch_finetune --train data/training/epm-tuning.jsonl \
        --val data/training/epm-tuning.val.jsonl

    # Actually start the job (uploads + bills; needs `pip install -e '.[finetune]'`):
    TOGETHER_API_KEY=... python -m scripts.launch_finetune \
        --train data/training/epm-tuning.jsonl --launch --follow

    # Check an existing job:
    TOGETHER_API_KEY=... python -m scripts.launch_finetune --status ft-abc123
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

# Base coder model to LoRA. Per OPENCLAW_PLAN.md §1/§2 we fine-tune only the
# coder, and only onto a base confirmed for Together Serverless Multi-LoRA —
# override with --model once eligibility is verified against the live
# fine-tuning-models list.
DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"
DEFAULT_TRAIN_PATH = "data/training/synthetic.jsonl"
# Below this a paid run is almost certainly not worth it; --force overrides.
_MIN_EXAMPLES = 10
# Terminal Together job states (anything else is still in flight). Together's
# job status values include pending/queued/running/uploading/compressing plus
# these end states.
_TERMINAL_STATES = {"completed", "error", "failed", "cancelled", "user_error"}


@dataclass
class FinetuneConfig:
    """Everything needed to describe the job, independent of the network."""

    base_model: str = DEFAULT_BASE_MODEL
    n_epochs: int = 3
    n_checkpoints: int = 1
    batch_size: int = 8
    learning_rate: float = 1e-4
    lora: bool = True
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.0
    suffix: str = "epm-coder"
    extra: dict = field(default_factory=dict)


def resolve_api_key(explicit: str | None) -> str | None:
    """Explicit flag wins, else ``$TOGETHER_API_KEY``. Never printed."""
    if explicit:
        return explicit
    return os.environ.get("TOGETHER_API_KEY") or None


def count_examples(path: Path) -> int:
    """Number of non-blank JSONL records (each line is one training example)."""
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def build_job_payload(training_file_id: str, cfg: FinetuneConfig,
                      validation_file_id: str | None = None) -> dict:
    """The JSON body for ``POST /fine-tunes`` — pure, so it is unit-testable."""
    payload: dict = {
        "training_file": training_file_id,
        "model": cfg.base_model,
        "n_epochs": cfg.n_epochs,
        "n_checkpoints": cfg.n_checkpoints,
        "batch_size": cfg.batch_size,
        "learning_rate": cfg.learning_rate,
        "suffix": cfg.suffix,
    }
    if cfg.lora:
        payload.update({
            "lora": True,
            "lora_r": cfg.lora_r,
            "lora_alpha": cfg.lora_alpha,
            "lora_dropout": cfg.lora_dropout,
        })
    if validation_file_id:
        payload["validation_file"] = validation_file_id
    payload.update(cfg.extra)
    return payload


def _attr(obj, key: str):
    """Read ``key`` from an SDK response object or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _normalize_job(resp) -> dict:
    """Reduce an SDK fine-tune response to the fields the launcher uses.

    ``status`` may come back as a string or an enum — take ``.value`` when
    present so the terminal-state check compares plain strings.
    """
    status = _attr(resp, "status")
    return {
        "id": _attr(resp, "id"),
        "status": getattr(status, "value", status),
        "output_name": _attr(resp, "output_name"),
    }


class TogetherClient:
    """Wrapper over the official ``together`` SDK's three fine-tuning calls.

    The SDK owns Together's real upload protocol (a signed multi-step flow, not
    a plain multipart POST) and job API, so we don't hand-roll the wire format.
    The import is lazy so the module loads — and dry runs work — without the
    optional ``together`` package installed; unit tests substitute a fake with
    the same three methods and never construct this.
    """

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        try:
            from together import Together
        except ImportError as exc:  # pragma: no cover - exercised via the CLI
            raise SystemExit(
                "The 'together' package is required to --launch. Install it with:\n"
                "    pip install -e '.[finetune]'   (from backend/)"
            ) from exc
        self._client = Together(api_key=api_key, **({"base_url": base_url} if base_url else {}))

    def upload_file(self, path: Path, purpose: str = "fine-tune") -> str:
        # check=True validates the JSONL shape before the upload is billed.
        resp = self._client.files.upload(file=str(path), purpose=purpose, check=True)
        return _attr(resp, "id")

    def create_finetune(self, payload: dict) -> dict:
        return _normalize_job(self._client.fine_tuning.create(**payload))

    def get_finetune(self, job_id: str) -> dict:
        return _normalize_job(self._client.fine_tuning.retrieve(job_id))


def _build_synthetic(train_path: Path, val_split: float) -> dict:
    """Generate a fresh synthetic corpus at ``train_path`` (demo fixtures only)."""
    from scripts.generate_synthetic_corpus import generate

    return generate(train_path, val_split=val_split)


def poll_until_terminal(client: TogetherClient, job_id: str, *,
                        interval: float = 15.0, sleep=time.sleep,
                        max_polls: int = 100_000) -> dict:
    """Poll a job until it reaches a terminal state (or ``max_polls``)."""
    for _ in range(max_polls):
        job = client.get_finetune(job_id)
        if str(job.get("status", "")).lower() in _TERMINAL_STATES:
            return job
        sleep(interval)
    return client.get_finetune(job_id)


def run(args: argparse.Namespace) -> dict:
    """Orchestrate; returns a JSON-serializable summary. No network unless
    ``--launch``/``--status`` is set (and a key is present)."""
    api_key = resolve_api_key(args.api_key)
    cfg = FinetuneConfig(
        base_model=args.model, n_epochs=args.epochs, batch_size=args.batch_size,
        learning_rate=args.learning_rate, lora=not args.no_lora, suffix=args.suffix,
    )

    # Status-only lookup short-circuits everything else.
    if args.status:
        if not api_key:
            raise SystemExit("Set $TOGETHER_API_KEY (or --api-key) to check a job.")
        client = TogetherClient(api_key)
        job = (poll_until_terminal(client, args.status, interval=args.poll_interval)
               if args.follow else client.get_finetune(args.status))
        return {"action": "status", "jobId": args.status,
                "status": job.get("status"), "outputName": job.get("output_name")}

    # 1. Assemble the corpus.
    train_path = Path(args.train) if args.train else Path(DEFAULT_TRAIN_PATH)
    build_summary = None
    if args.build or not args.train:
        build_summary = _build_synthetic(train_path, args.val_split)
    if not train_path.exists():
        raise SystemExit(f"Training corpus not found: {train_path} "
                         "(pass --train, or --build to generate one).")
    val_path = Path(args.val) if args.val else None
    if build_summary and args.val_split > 0 and not val_path:
        held = build_summary.get("paths", {}).get("validation")
        val_path = Path(held) if held else None

    # 2. Preflight.
    n_examples = count_examples(train_path)
    if n_examples < _MIN_EXAMPLES and not args.force:
        raise SystemExit(
            f"Only {n_examples} training example(s) in {train_path} — below the "
            f"{_MIN_EXAMPLES} minimum. Add data or pass --force to launch anyway.")

    payload_preview = build_job_payload("<uploaded-training-file>", cfg,
                                        "<uploaded-val-file>" if val_path else None)
    summary: dict = {
        "action": "launch" if args.launch else "dry-run",
        "trainPath": str(train_path),
        "valPath": str(val_path) if val_path else None,
        "examples": n_examples,
        "baseModel": cfg.base_model,
        "jobPayload": payload_preview,
    }
    if build_summary:
        summary["corpusBuild"] = build_summary

    # 3. Dry run stops here — nothing billable happened.
    if not args.launch:
        summary["note"] = ("Dry run — no upload, no job, no cost. Re-run with "
                           "--launch to actually start the fine-tune.")
        if not api_key:
            summary["apiKey"] = "not set (needed for --launch)"
        return summary

    # 4. Launch: upload then create the job (this is the billable step).
    if not api_key:
        raise SystemExit("Set $TOGETHER_API_KEY (or --api-key) to --launch.")
    client = TogetherClient(api_key)
    train_file_id = client.upload_file(train_path)
    val_file_id = client.upload_file(val_path) if val_path else None
    job = client.create_finetune(build_job_payload(train_file_id, cfg, val_file_id))

    summary.update({
        "trainingFileId": train_file_id,
        "validationFileId": val_file_id,
        "jobId": job.get("id"),
        "status": job.get("status"),
    })
    if args.follow and job.get("id"):
        final = poll_until_terminal(client, job["id"], interval=args.poll_interval)
        summary["status"] = final.get("status")
        summary["outputName"] = final.get("output_name")
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--train", default=None, help="existing training JSONL (chat format)")
    p.add_argument("--val", default=None, help="optional validation JSONL")
    p.add_argument("--build", action="store_true",
                   help="generate a fresh synthetic corpus before launching")
    p.add_argument("--val-split", type=float, default=0.1,
                   help="held-out fraction when --build generates the corpus")
    p.add_argument("--model", default=DEFAULT_BASE_MODEL, help="base model to LoRA")
    p.add_argument("--suffix", default="epm-coder", help="fine-tuned model name suffix")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--learning-rate", type=float, default=1e-4)
    p.add_argument("--no-lora", action="store_true",
                   help="full fine-tune instead of LoRA (far pricier to serve)")
    p.add_argument("--launch", action="store_true",
                   help="actually upload + start the job (BILLABLE). Off = dry run.")
    p.add_argument("--follow", action="store_true", help="poll the job to completion")
    p.add_argument("--poll-interval", type=float, default=15.0, help="seconds between polls")
    p.add_argument("--status", default=None, help="look up an existing job id and exit")
    p.add_argument("--api-key", default=None, help="Together key (else $TOGETHER_API_KEY)")
    p.add_argument("--force", action="store_true",
                   help="launch even if the corpus is below the minimum size")
    return p


def main() -> None:
    args = build_parser().parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
