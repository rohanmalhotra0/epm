"""QLoRA fine-tune a Granite model on the EPM Wizard chat-format corpus.

Runs on the VPC GPU training VSI (Path B in docs/TRAINING.md) — NOT inside the
EPM Wizard backend. Its dependencies live only in this folder's
requirements.txt.

Input is the ``--format chat`` JSONL produced by
``scripts.export_training_data`` / ``scripts.generate_synthetic_corpus``:
one ``{"messages": [{"role": ..., "content": ...}, ...]}`` object per line.
TRL's SFTTrainer detects this conversational format and applies the
tokenizer's chat template automatically.

VRAM guidance (batch size 1-2, seq len 2048, 4-bit NF4 base + LoRA):

    granite-3.1-8b-instruct   ~9-12 GB   -> 1x L4 24 GB   (gx3-24x120x1l4)  OK
    granite-3.1-8b, seq 4096  ~14-18 GB  -> 1x L4         still OK
    Granite ~32B class        ~26-40 GB  -> 1x H100 80 GB (gx3d profile)
                                            an L4 will OOM — use gx3d for 32B.

The 32B upgrade is a flag away:
    --base-model <the ~32B Granite instruct model id on Hugging Face>
plus a gx3d (H100) profile at terraform time. Nothing else changes.

Typical run (8B on an L4):
    python train_qlora.py \
        --train-file corpus.jsonl --val-file corpus.val.jsonl \
        --output-dir out/epmw-granite-8b-qlora --epochs 3 --merge
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, PeftModel, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

DEFAULT_BASE_MODEL = "ibm-granite/granite-3.1-8b-instruct"

# LoRA on all attention + MLP projections — the standard QLoRA recipe; adapting
# the MLP as well matters for structured-output tasks like spec generation.
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",   # attention
    "gate_proj", "up_proj", "down_proj",      # MLP
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-model", default=DEFAULT_BASE_MODEL,
                   help="HF model id. Default is 8B Granite; pass a ~32B Granite "
                        "instruct id on an H100 (gx3d) for the big run.")
    p.add_argument("--train-file", required=True, help="chat-format JSONL")
    p.add_argument("--val-file", default=None,
                   help="chat-format JSONL for per-epoch eval (the .val.jsonl "
                        "emitted by generate_synthetic_corpus --val-split)")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--epochs", type=float, default=3.0)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument("--max-seq-len", type=int, default=2048)
    p.add_argument("--batch-size", type=int, default=1,
                   help="per-device micro-batch; effective batch = this * grad-accum")
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--merge", action="store_true",
                   help="after training, merge the adapter into full weights "
                        "(<output-dir>/merged) for vLLM serving or watsonx "
                        "custom-model import")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not torch.cuda.is_available():
        raise SystemExit("No CUDA GPU visible — run this on the GPU VSI, not locally.")

    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

    # 4-bit NF4 quantized base with double quantization — the QLoRA setup.
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=compute_dtype,
    )
    model.config.use_cache = False  # incompatible with gradient checkpointing
    model = prepare_model_for_kbit_training(model)

    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=LORA_TARGET_MODULES,
        bias="none",
        task_type="CAUSAL_LM",
    )

    data_files = {"train": args.train_file}
    if args.val_file:
        data_files["validation"] = args.val_file
    dataset = load_dataset("json", data_files=data_files)

    sft_config = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        max_seq_length=args.max_seq_len,
        packing=False,
        bf16=compute_dtype is torch.bfloat16,
        fp16=compute_dtype is torch.float16,
        logging_steps=10,
        eval_strategy="epoch" if args.val_file else "no",
        save_strategy="epoch",
        save_total_limit=2,
        seed=args.seed,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("validation"),
        peft_config=peft_config,
        tokenizer=tokenizer,
    )

    trainer.train()

    adapter_dir = out_dir / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"Adapter saved to {adapter_dir}")

    metrics = {"train": trainer.state.log_history[-1] if trainer.state.log_history else {}}
    if args.val_file:
        metrics["eval"] = trainer.evaluate()
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

    if args.merge:
        # Reload the base un-quantized (fp16/bf16) and fold the adapter in.
        # Peak RAM/VRAM here is the full-precision model: fine for 8B on an
        # L4 host (offloads to CPU RAM via device_map="auto"); for 32B make
        # sure the VSI has the RAM of a gx3d profile.
        print("Merging adapter into full weights (this reloads the base model)...")
        del model, trainer
        torch.cuda.empty_cache()
        base = AutoModelForCausalLM.from_pretrained(
            args.base_model, torch_dtype=compute_dtype, device_map="auto",
        )
        merged = PeftModel.from_pretrained(base, str(adapter_dir)).merge_and_unload()
        merged_dir = out_dir / "merged"
        merged.save_pretrained(str(merged_dir), safe_serialization=True)
        tokenizer.save_pretrained(str(merged_dir))
        print(f"Merged model saved to {merged_dir} — ready for vLLM serving "
              f"(serve_openai_compat.sh) or watsonx custom-model import.")


if __name__ == "__main__":
    main()
