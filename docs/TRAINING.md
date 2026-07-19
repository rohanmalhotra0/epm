# Training EPM Wizard's model — the end-to-end runbook

How to build the corpus, tune a Granite model on IBM Cloud, prove it beats
the alternatives, and ship it. Infrastructure background is in
[`docs/IBM_CLOUD.md`](IBM_CLOUD.md); the executable pieces live in
[`deploy/ibm-cloud/`](../deploy/ibm-cloud/).

---

## 1. Overview: the two-tier model strategy

EPM Wizard uses two tiers of model:

- **Workhorse — a tuned Granite model.** Handles the high-volume, structured
  turns: intent parsing, `FormSpecification` / `RuleSpecification` generation.
  Small, cheap, fast, and trained on validated EPM structure.
- **Big hosted model — for open-ended turns.** A large catalog model on
  watsonx.ai answers the free-form advisory questions the small model
  shouldn't be trusted with.

One rule governs everything: **the eval harness gates every model change.**
No model — tuned, upgraded, or swapped — ships without beating the current
champion on the same corpus under `scripts.eval_nlu` (section 5). The
deterministic parser is the floor; anything that can't clear it doesn't ship.

The path order is deliberate:

1. **Path A** — watsonx.ai Tuning Studio (managed, 8B Granite). Try this first.
2. **Path B** — GPU VSI QLoRA (self-managed, up to ~32B Granite). Only if A
   falls short at the bake-off.

---

## 2. Build the corpus

Two sources, one format, all local. Run everything from `backend/`.

### 2.1 Synthetic corpus (the primary source)

Synthetic examples are generated *from the schema outward*: every label and
every spec on the output side is constructed, so it is valid by construction —
no mislabeled training signal, and coverage of rare intents you can dial up
at will. That is why synthetic is the bulk of the corpus, not the garnish.

```bash
cd backend
python -m scripts.generate_synthetic_corpus \
  --count 2000 \
  --out data/training/synthetic.jsonl \
  --format watsonx \
  --seed 7 \
  --edits-ratio 0.3 \
  --val-split 0.1
```

- `--seed 7` makes the corpus reproducible.
- `--edits-ratio 0.3` mixes in edit-style turns (modify an existing spec),
  not just create-from-scratch.
- `--val-split 0.1` writes a held-out `synthetic.val.jsonl` next to the main
  file. Keep it held out — it is the eval set for tuning.
- Use `--format chat` instead when producing the Path B corpus (section 6).

### 2.2 Real-usage export (the seasoning)

Real conversations and validated artifacts from your local EPM Wizard data.
Every string passes the central redactor before it is written.

```bash
python -m scripts.export_training_data \
  --out data/training/real.jsonl \
  --format watsonx
# optionally: --project <project-id> to scope to one project
```

### 2.3 Concatenate

The two outputs are concatenation-compatible (same format, same schema):

```bash
cat data/training/synthetic.jsonl data/training/real.jsonl \
  > data/training/corpus.jsonl
cp data/training/synthetic.val.jsonl data/training/corpus.val.jsonl
```

`corpus.jsonl` is the training set. `corpus.val.jsonl` is validation — never
train on it.

For Path B, repeat 2.1–2.3 with `--format chat` (the GPU kit consumes the
chat format).

---

## 3. Upload to COS

```bash
cd deploy/ibm-cloud
./upload_corpus.sh ../../backend/data/training/corpus.jsonl \
                   ../../backend/data/training/corpus.val.jsonl
```

The script creates the `epmw-training-data` bucket if needed, uploads, and
lists the bucket. Prereqs (ibmcloud CLI, COS plugin, instance CRN config) are
in the script header. Override `BUCKET` / `REGION` via env vars.

---

## 4. Path A — watsonx.ai Tuning Studio (managed, try first)

No GPUs to manage. Billing is per tuning run plus per-token inference.

1. **Connect the bucket to your watsonx.ai project.** In the watsonx project:
   *Manage → General → Storage* (or *Assets → New asset → Connection → Cloud
   Object Storage*), point it at the `epmw-training-data` bucket.
2. **Tune.** *New asset → Tune a foundation model*. Pick
   `granite-3-8b-instruct` as the base, select `corpus.jsonl` as training
   data (`{"input": ..., "output": ...}` is the format Tuning Studio ingests
   directly), start the run.
3. **Deploy to a deployment space.** When the run finishes, promote the tuned
   model to a deployment space. Note the **space ID** and the **tuned model /
   deployment ID**.
4. **Wire EPM Wizard.** In *Settings → AI Providers*, add or edit the
   `watsonx` provider:
   - API key: an IBM Cloud API key
   - Base URL: your regional endpoint, e.g. `https://us-south.ml.cloud.ibm.com`
   - Default model: the tuned model id from step 3

   Or via environment (see `.env.example`): set `WATSONX_API_KEY`,
   `WATSONX_URL`, and `WATSONX_SPACE_ID` (the deployment space **instead of**
   `WATSONX_PROJECT_ID`).

Do not switch traffic to it yet — first, the bake-off.

---

## 5. The bake-off

`scripts.eval_nlu` scores any LLM against the deterministic baseline on the
same corpus. The deterministic parser is the floor. Run all three contenders:

```bash
cd backend

# 1) Tuned Granite (Path A output; space-scoped)
python -m scripts.eval_nlu --strategy llm \
  --llm-provider-type watsonx \
  --llm-base-url https://us-south.ml.cloud.ibm.com \
  --llm-model <tuned-model-id> \
  --few-shot 4

# 2) Big hosted catalog model (e.g. mistralai/mistral-large or
#    meta-llama/llama-3-405b-instruct)
python -m scripts.eval_nlu --strategy llm \
  --llm-provider-type watsonx \
  --llm-base-url https://us-south.ml.cloud.ibm.com \
  --llm-model mistralai/mistral-large \
  --few-shot 4
```

Catalog model ids vary by region and change as the catalog evolves — check
the watsonx.ai **Resource hub** for what is actually deployable in your
region before quoting ids in a config.

**Ship whichever contender wins while clearing the `--min-coverage` gates.**
If nothing beats the deterministic baseline, ship nothing and keep the
baseline. Re-run this section after *every* corpus or model change — the
harness is the gate, not a one-time ceremony.

If the tuned 8B loses to the big hosted model by a wide margin *and* the
per-token cost of the big model is unacceptable, that is the trigger for
Path B.

---

## 6. Path B — GPU QLoRA (only if A falls short)

Full-control fine-tune on a VPC GPU VSI. Biggest sensible target: a ~32B
Granite. The kit lives in
[`deploy/ibm-cloud/training/`](../deploy/ibm-cloud/training/) with its own
README; summary:

1. **Provision** the instance:

   ```bash
   cd deploy/ibm-cloud/terraform
   terraform apply -var enable_gpu_training=true -var ssh_key_name=<key>
   # default profile gx3-24x120x1l4 (1x L4) suits the 8B target;
   # pass -var gpu_profile=<gx3d H100 profile> for the ~32B run
   ```

2. **Train** on the chat-format corpus (built in section 2, uploaded in
   section 3):

   ```bash
   # on the VSI, with deploy/ibm-cloud/training/ copied over:
   BUCKET=epmw-training-data TRAIN_KEY=corpus.jsonl VAL_KEY=corpus.val.jsonl \
     ./run_training.sh
   ```

   Artifacts (LoRA adapter, merged weights, metrics) land back in COS.

3. **Serve it**, one of two ways:
   - **Import into watsonx.ai as a custom foundation model** — durable,
     integrates with the same `watsonx` provider config as Path A. Beware
     the cost cliff: custom models require dedicated serving capacity
     (section 8).
   - **Serve OpenAI-compatible on the VSI** — `serve_openai_compat.sh`, then
     add a `generic` provider in Settings pointing at
     `http://<gpu_training_ip>:8080/v1`. Good for the bake-off; keeps the
     GPU meter running if left up.

4. **Bake it off** (section 5) before switching any traffic.

5. **Destroy the instance the same day** — it is the dominant cost line:

   ```bash
   cd deploy/ibm-cloud/terraform
   terraform apply -var enable_gpu_training=false
   ```

---

## 7. Hosting without a VPN

The default topology (`enable_vpn = false` in
`deploy/ibm-cloud/terraform/`) needs **nothing installed on the user's
machine**:

- The frontend is a **Code Engine public HTTPS endpoint** with **App ID
  (OIDC)** in front. Sign-in is an email invite from App ID's cloud
  directory; access is browser-only.
- Everything *behind* the app stays private: the backend is project-visibility
  only, and COS / the GPU VSI / watsonx calls never traverse the public
  internet from the app's perspective.
- This is the design for the corporate-laptop user: no VPN client, no admin
  rights, no installer — just a URL and a login.
- **Verify SSE streaming** through your corporate proxy early: chat responses
  stream as server-sent events, and some corporate proxies buffer or break
  long-lived responses. If streaming stalls behind the proxy, the app still
  works but responses arrive all-at-once.

The Client-to-Site VPN remains available for private-endpoint-only
deployments: `terraform apply -var enable_vpn=true` plus the two Secrets
Manager certificate CRNs (see `variables.tf`).

---

## 8. Cost table

Rough monthly orders of magnitude — check current IBM Cloud pricing before
budgeting:

| Line item | Rough cost | Notes |
|---|---|---|
| Code Engine (frontend + backend) | ~$0–10/mo idle | scales to zero; pay for active use |
| App ID | ~$0 at small scale | free tier covers a small team |
| COS (corpus + artifacts) | ~$1–5/mo | a few GB in the smart tier |
| watsonx.ai inference | pay-per-token | the big hosted model costs more per token than tuned 8B |
| Tuning Studio run | per-job | billed per tuning run, not monthly |
| GPU VSI (Path B) | **hourly** — roughly single-digit $/hr (L4) to tens of $/hr (H100) | **destroy the same day**; a forgotten H100 is a four-figure month |
| watsonx custom-model serving | **cost cliff** | imported custom models need *dedicated* serving capacity billed hourly — far above pay-per-token; only worth it if the tuned model carries real volume |
| Client-to-Site VPN (optional) | flat hourly per server | $0 in the default `enable_vpn=false` topology |

Everything lands in one resource group (`epmw-rg`), so the bill is a single
filtered view.
