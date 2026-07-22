# Fine-tuning the EPM coder (Phase 5)

This is the runbook for `OPENCLAW_PLAN.md` §Phase 5: LoRA-fine-tune the coder
model on your own EPM corpus with Together AI. It is deliberately gated so the
**expensive** part never happens by accident — read §1 of the plan (the
"fine-tuning cost cliff") before you pass `--launch`.

> **Do you even need this?** The plan's standing recommendation is to ship on
> **stock Qwen2.5-Coder-32B + RAG grounding** first and only fine-tune if
> quality demands it *and* Together Serverless Multi-LoRA eligibility is
> confirmed for the base model. Fine-tuning is cheap to *run* (~$1–7); serving a
> fine-tune on a dedicated endpoint is ~$4,700/mo. Confirm serverless-LoRA
> before committing.

## The pieces

| Step | Tool |
|---|---|
| Export a corpus from your local data (conversations, validated specs, snapshot rule bodies) | `scripts.export_training_data` |
| Generate a guaranteed-correct synthetic corpus from the demo metadata | `scripts.generate_synthetic_corpus` |
| **Upload the corpus and start the LoRA job** | `scripts.launch_finetune` |

All commands run from `backend/`.

## 1. Assemble the corpus

From your own local data (redacted on the way out):

```bash
python -m scripts.export_training_data --out data/training/epm-tuning.jsonl
```

Or a fresh synthetic corpus (no local data needed — built from demo fixtures,
same seed → identical corpus, with a held-out validation split):

```bash
python -m scripts.generate_synthetic_corpus --count 2000 --val-split 0.1 \
    --out data/training/synthetic.jsonl
```

The two files share a record shape, so you can concatenate them into one corpus.

## 2. Dry run (safe — no upload, no cost)

The launcher does **nothing billable** unless you pass `--launch`. By default it
assembles + validates the corpus and prints the exact upload and job plan:

```bash
python -m scripts.launch_finetune --train data/training/epm-tuning.jsonl \
    --val data/training/epm-tuning.val.jsonl
```

Or let it build a synthetic corpus and dry-run in one shot:

```bash
python -m scripts.launch_finetune --build --val-split 0.1
```

It refuses a corpus below `MIN_EXAMPLES` (override with `--force`).

## 3. Launch (billable)

Set the key and pass `--launch`. `--follow` polls the job to completion:

```bash
export TOGETHER_API_KEY=...
python -m scripts.launch_finetune \
    --train data/training/epm-tuning.jsonl \
    --val   data/training/epm-tuning.val.jsonl \
    --launch --follow
```

Useful flags: `--model` (base model — default `Qwen/Qwen2.5-Coder-32B-Instruct`),
`--epochs`, `--batch-size`, `--learning-rate`, `--suffix` (fine-tuned model
name), `--no-lora` (full fine-tune — far pricier to serve).

## 4. Check a job later

```bash
python -m scripts.launch_finetune --status ft-abc123 --follow
```

## 5. Serve it

Once the job reports `completed`, point the Together provider's coder role at the
returned `outputName`. If (and only if) the base qualifies for Serverless
Multi-LoRA, this stays in the cheap serverless tier; otherwise it needs a
dedicated endpoint — the cost cliff. Verify eligibility against Together's live
`fine-tuning-models` list first.
