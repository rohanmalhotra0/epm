# GPU training kit (Path B)

Self-contained QLoRA fine-tuning kit for the VPC GPU VSI. Use it only if
Path A (watsonx.ai Tuning Studio) falls short — the full decision guide and
end-to-end runbook is [`docs/TRAINING.md`](../../../docs/TRAINING.md).

**Cost warning:** GPU VSIs bill hourly and are the dominant cost line
(roughly single-digit $/hr for an L4, tens of $/hr for H100). Provision,
train, upload, **destroy the same day**.

Everything in this folder runs on the VSI, never in the app backend; the
Python deps here stay out of `backend/requirements`.

## Runbook

1. **Provision** (from `deploy/ibm-cloud/terraform/`):

   ```bash
   terraform apply -var enable_gpu_training=true -var ssh_key_name=<vpc-ssh-key>
   # 8B target: default gx3-24x120x1l4 (1x L4 24 GB)
   # ~32B target: add -var gpu_profile=<gx3d H100 profile>
   ```

   SSH in (attach a floating IP temporarily, or come in over the VPC),
   install the NVIDIA driver if the image is minimal, install the `ibmcloud`
   CLI + `cloud-object-storage` plugin, log in, and copy this folder over
   (`scp -r deploy/ibm-cloud/training <vsi>:`).

2. **Train** — pulls the chat-format corpus from COS, fine-tunes, uploads
   the adapter (and merged weights) back to COS:

   ```bash
   BUCKET=epmw-training-data TRAIN_KEY=corpus.jsonl VAL_KEY=corpus.val.jsonl \
     ./run_training.sh
   ```

   `train_qlora.py` defaults to the 8B Granite instruct base; pass
   `--base-model` for the ~32B run (H100 required — VRAM table in the
   script header).

3. **Serve or import:**
   - Quick bake-off serving on the VSI:
     `./serve_openai_compat.sh ~/epmw-training/<run>/out/merged`
     then add it in EPM Wizard Settings as a `generic` provider at
     `http://<gpu_training_ip>:8080/v1` (details in the script header).
   - For anything durable: import the merged weights into watsonx.ai as a
     **custom foundation model** and serve it there
     (`docs/TRAINING.md` §6) — then the VSI has no reason to exist.

4. **Destroy the instance** as soon as artifacts are safely in COS:

   ```bash
   terraform apply -var enable_gpu_training=false
   ```

## Files

| File | What it does |
|---|---|
| `requirements.txt` | training deps (torch/transformers/peft/trl/bitsandbytes/datasets/accelerate) |
| `train_qlora.py` | 4-bit NF4 QLoRA SFT on the chat-format JSONL; `--merge` folds the adapter into full weights |
| `run_training.sh` | fresh-VSI end-to-end: venv → COS pull → train → COS upload |
| `serve_openai_compat.sh` | vLLM OpenAI-compatible server on `0.0.0.0:8080` for bake-offs |
