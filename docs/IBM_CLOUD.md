# EPM Wizard on IBM Cloud — the all-IBM deployment

This document maps the product vision to a concrete, end-to-end IBM stack:

> **Email invite + link → VPN → request to cloud.**
> Train an AI on EPM data on IBM Cloud, host the site on IBM Cloud,
> access it privately over an IBM VPN, and plug into Oracle EPM via the
> existing connector boundary. **All IBM.**

EPM Wizard stays local-first for development (`docker compose up --build`
still works unchanged). This is the hosted topology for teams.

---

## 1. Service mapping

| Need | IBM Cloud service | Where it lands in this repo |
|---|---|---|
| AI inference | **watsonx.ai** (IBM Granite models) | `backend/app/ai/watsonx.py` — a first-class provider, selectable in Settings like any other |
| AI training on EPM data | **watsonx.ai Tuning Studio**, or **GPU-as-a-Service** (VPC GPU profiles) for full fine-tunes | `backend/scripts/export_training_data.py` produces the corpus |
| Embeddings (RAG) | **watsonx.ai** embeddings (IBM Slate retriever models) | `backend/app/ai/watsonx.py` `embed()` + `backend/app/rag/` — grounds `/forms` and `/rules` on the active context; falls back to offline lexical retrieval when no embeddings provider is configured |
| Site hosting | **Code Engine** (serverless containers) — the existing frontend + backend images run as-is | `deploy/ibm-cloud/` |
| Container images | **Container Registry (ICR)** | `deploy/ibm-cloud/deploy-code-engine.sh` |
| Private access (optional) | **Client-to-Site VPN for VPC** (OpenVPN-based) — off by default, see §5 | `deploy/ibm-cloud/terraform/` (`enable_vpn`) |
| User invites & auth | **App ID** (cloud directory email invites, OIDC in front of the app) | fronting Code Engine / the ALB |
| Training data & artifact storage | **Cloud Object Storage (COS)** | corpus upload target |
| Secrets (Oracle creds, API keys) | **Secrets Manager** | replaces/backs the local Fernet store in hosted mode |
| VPN server certificates | **Secrets Manager** (certificates engine) | referenced by the VPN server |
| Observability | **Cloud Logs / Cloud Monitoring** | Code Engine integrations |
| Oracle EPM "API plug-in" | the **connector boundary** (`backend/app/connector/`) | `oracle_rest.py` + restricted `epm_automate.py` — already the one authoritative EPM integration point |

---

## 2. Request flow

```
  Email invite (App ID) ──► user clicks link, installs OpenVPN profile
                                        │
                                        ▼
                    ┌─ IBM Cloud Client-to-Site VPN server ─┐
                    │            (VPC, private subnet)       │
                    └────────────────────┬───────────────────┘
                                         │ private DNS name
                                         ▼
                     https://epm-wizard.<private-domain>
                                         │
                    ┌────────────────────┴───────────────────┐
                    │  Code Engine (project: epm-wizard)      │
                    │   ├─ app: epmw-frontend  (nginx SPA)    │
                    │   └─ app: epmw-backend   (FastAPI)      │
                    └───────┬───────────────────┬─────────────┘
                            │                   │
                            ▼                   ▼
                 watsonx.ai inference      Oracle EPM Cloud
                 (Granite / tuned model)   (Planning REST + EPM Automate,
                  WATSONX_PROJECT_ID        via the connector boundary)
                            ▲
                            │ embeddings (RAG retrieval)
                 RAG index on /data volume
                 (lexical BM25 offline; hybrid with
                  watsonx.ai text/embeddings when configured)
```

The diagram above shows the **VPN topology** (`enable_vpn = true`): Code
Engine apps use private (project-only / VPC) endpoints and the only way in is
the VPN. The email invite carries two things — the App ID sign-up link and
the OpenVPN client profile (or a link to download it from the VPN server's
client page).

**The default topology has no VPN** (`enable_vpn = false`): the frontend is a
Code Engine **public HTTPS endpoint with App ID (OIDC) as the security
boundary**, while the backend and everything behind it stay on private
endpoints. This is the laptop-friendly design — a corporate machine with no
VPN client and no admin rights needs only a browser and the App ID invite.

---

## 3. Training an AI on EPM data

> **The step-by-step training workflow — corpus build, upload, Tuning
> Studio, the eval bake-off, GPU QLoRA, and costs — is in
> [`docs/TRAINING.md`](TRAINING.md).** This section keeps the architectural
> overview.

### 3.1 Build the corpus (local, redacted)

The exporter turns what the team has already done in EPM Wizard —
conversations, validated `FormSpecification` / `RuleSpecification` artifacts,
**and the Calculation Manager rule/template bodies carried by the active
context version** (uploaded LCM snapshots) — into instruction/response pairs.
The snapshot-derived pairs are the strongest "EPM expert" signal: real
production calc-script/Groovy from your own application, phrased as
"write this rule" instructions. Every string passes through the central
redactor, so pasted credentials never enter the corpus.

```bash
cd backend
# watsonx.ai Tuning Studio format: {"input": ..., "output": ...}
python -m scripts.export_training_data --out data/training/epm-tuning.jsonl

# chat-style SFT (InstructLab / custom GPU fine-tune)
python -m scripts.export_training_data --format chat
```

The artifact pairs are the most valuable examples: the *output* side is
deterministic, Pydantic-validated EPM structure — exactly the behavior the
tuned model should imitate.

### 3.2 Path A — watsonx.ai Tuning Studio (managed, recommended first)

1. Upload `epm-tuning.jsonl` to a COS bucket connected to your watsonx.ai
   project.
2. In Tuning Studio, tune a Granite base model (e.g. `ibm/granite-3-8b-instruct`)
   on the corpus.
3. Deploy the tuned model to a **deployment space**.
4. Point EPM Wizard at it: set `WATSONX_SPACE_ID` (instead of
   `WATSONX_PROJECT_ID`) and select the tuned model id in Settings.

No GPUs to manage; billing is per tuning run + inference.

### 3.3 Path B — GPU-as-a-Service (full control)

For full fine-tunes or larger corpora, provision a VPC GPU virtual server
(gx3 profiles with NVIDIA L4/L40S, or gx3d with H100) in the same VPC:

1. `terraform apply` with `enable_gpu_training = true` (see
   `deploy/ibm-cloud/terraform/`).
2. Pull the corpus from COS onto the instance, fine-tune with your stack of
   choice (InstructLab — IBM's open-source tuning toolchain — works well with
   the `--format chat` export).
3. Either import the resulting model into watsonx.ai as a custom foundation
   model, or serve it on the instance behind the VPC private load balancer and
   add it in Settings as an `ollama`/`generic` (OpenAI-compatible) provider —
   still all inside IBM Cloud.
4. **Deprovision the GPU instance when the run finishes** — it is the dominant
   cost line.

### 3.4 Wire the app to watsonx.ai

In **Settings → AI Providers** add a provider of type `watsonx`:

- **API key** — an IBM Cloud API key (exchanged automatically for an IAM token)
- **Base URL** — your regional endpoint, e.g. `https://us-south.ml.cloud.ibm.com`
  (optionally `?project_id=<id>` appended)
- **Default model** — `meta-llama/llama-3-3-70b-instruct` (recommended:
  token-billed, 131k context, strong structured JSON and rule-script drafting
  at ~$0.00075/1k tokens), `ibm/granite-3-8b-instruct` for the lightest
  footprint, or your tuned model id. Prefer the shared token-billed catalog
  over deploy-on-demand — dedicated hourly deployments only pay off under
  sustained load.

Environment-variable fallbacks (see `.env.example`): `WATSONX_API_KEY`,
`WATSONX_URL`, `WATSONX_PROJECT_ID` / `WATSONX_SPACE_ID`,
`WATSONX_CHAT_MODEL_ID` (used when the provider profile sets no default
model; the Code Engine deploy script pins it to
`meta-llama/llama-3-3-70b-instruct`).

### 3.5 Retrieval-augmented generation (RAG)

When a user asks EPM Wizard to create a form or business rule, the agent
retrieves the most relevant artifacts from the **active context version** —
including snapshot-derived Calculation Manager rule bodies, templates, forms,
per-dimension member-naming digests and substitution variables — shows them in
a visible "Grounded on" block, and uses them to ground generation
(`backend/app/rag/`).

- **Offline by default** — retrieval is pure-Python lexical BM25, fully
  deterministic, no network and no extra service. This is what Demo Mode and
  the Mock provider use.
- **watsonx.ai upgrade** — when the active provider supports embeddings
  (watsonx.ai first-class, via `POST /ml/v1/text/embeddings`), scoring becomes
  hybrid lexical + cosine similarity. The embedding model resolves from
  `WATSONX_EMBEDDINGS_MODEL_ID` (default `ibm/slate-125m-english-rtrvr`); the
  deploy script injects it into the backend app. Embedding failures fall back
  silently to lexical — grounding never breaks form/rule creation.
- **Storage** — the index is a per-context-version JSON cache under the
  app's `/data` volume (`<EPMW_DATA_DIR>/rag/`), rebuilt automatically when
  missing; no additional IBM Cloud service is required. A future option is
  moving vectors into IBM Cloud Databases for PostgreSQL with pgvector once
  contexts outgrow the file cache.

---

## 4. Hosting on Code Engine

The repo's two existing images deploy unchanged. `deploy/ibm-cloud/deploy-code-engine.sh`
builds both, pushes them to ICR, and creates/updates the two Code Engine apps.

**Where the database lives** — pick one of three tiers (local runs are
unaffected: on a laptop or in compose the app stays SQLite-on-disk with zero
configuration):

1. **Ephemeral demo** — no volume, no database service. Every cold start is a
   fresh SQLite database. Fine for showing the app around, nothing else.
2. **Single-instance SQLite** — the default the deploy script sets up: SQLite
   on the `/data` store, `min-scale`/`max-scale` pinned to one backend
   instance, and backup discipline (the app snapshots the DB at startup and on
   demand via `POST /api/diagnostics/backups`; copy `<data>/backups` out to COS
   on a schedule). Right for a single admin or very small team.
3. **Managed PostgreSQL for real teams** — `terraform apply` with
   `enable_postgres = true` provisions IBM Cloud Databases for PostgreSQL
   (private endpoint), then set `EPMW_DATABASE_URL` in the `epmw-database`
   Code Engine secret (see the deploy script header for the exact command;
   ICD requires TLS — mount its CA cert from a secret and reference it via
   `sslmode=verify-full&sslrootcert=...`). The backend detects the URL, runs
   the same Alembic migrations on Postgres at startup, and can scale past one
   instance. File-level backup endpoints step aside in favour of ICD's own
   point-in-time backups.

Secrets (Oracle passwords, the watsonx API key) live in **Secrets Manager**
and are injected into the backend as Code Engine secrets — never baked into
images.

---

## 5. Access: App ID by default, VPN optional

**Default (`enable_vpn = false`):** the front door is the Code Engine public
HTTPS endpoint with **App ID (OIDC)** in front. Onboarding is just the App ID
email invite — nothing to install, which is what a locked-down corporate
laptop needs. See `docs/TRAINING.md` §7 for the user-facing notes (including
verifying SSE streaming through corporate proxies).

The App ID front door is fully scripted and needs **zero app-code changes**
(EPM Wizard itself stays local-first with no auth layer):

1. `terraform apply` — provisions the App ID instance (`enable_app_id = true`
   by default, `graduated-tier`: free for roughly the first 1,000 monthly
   active users) and an OIDC application, and exports `app_id_issuer_url`,
   `app_id_client_id`, `app_id_client_secret`, `app_id_tenant_id`.
2. Create the `epmw-appid` Code Engine secret from those outputs plus a random
   cookie secret (exact command in `deploy-code-engine.sh`'s comments).
3. `./deploy-code-engine.sh` — when the secret exists it deploys **oauth2-proxy**
   (`epmw-auth`) as the ONLY public app, flips the frontend to project-only
   visibility behind it, and prints the login-gated URL. Without the secret the
   frontend stays public with no login (dev/demo mode) and the script says so.
4. `./configure-app-id.sh` — one-time: registers the generated
   `/oauth2/callback` URL in App ID's redirect allowlist.
5. Invite users in **App ID → Cloud Directory → Users** (or federate your IdP
   in App ID — SAML/enterprise — with no change to the deployment).

`OAUTH2_PROXY_FLUSH_INTERVAL=1s` is set so chat SSE streams through the proxy
unbuffered.

**Optional VPN topology (`terraform apply -var enable_vpn=true`, plus the two
Secrets Manager certificate CRNs):** on top of the base VPC and private
subnet, `deploy/ibm-cloud/terraform/` then additionally provisions:

- a **Client-to-Site VPN server** with certificate auth (server + client
  certificates issued by Secrets Manager) and optional user-id auth via IAM,
- a security-group rule that only admits app traffic from the VPN client CIDR.

Onboarding a teammate (VPN topology):

1. Invite them in **App ID** (cloud directory email invite) — this is the
   "email invite + link".
2. Send the OpenVPN client profile (downloadable from the VPN server's
   client-configuration page).
3. They connect to the VPN and open the private URL; App ID handles sign-in
   in front of the app.

Offboarding is the reverse: revoke the client certificate / IAM user and the
App ID account. No app redeploy needed.

---

## 6. The Oracle EPM "API plug-in"

The plug-in already exists as the **connector boundary**
(`backend/app/connector/`) and stays the single integration point in the
hosted topology:

- `oracle_rest.py` — documented Oracle Planning REST API (read-only metadata,
  rule execution),
- `epm_automate.py` — restricted, allowlisted EPM Automate runner (argument
  arrays, never a shell),
- `demo.py` — the zero-config demo tenant.

In hosted mode the backend reaches Oracle EPM Cloud **outbound over HTTPS**
from the VPC — no inbound exposure — and Oracle credentials come from Secrets
Manager. All the existing safeguards (PROD confirmation phrase, validation
gates, audit records, post-deployment verification) apply unchanged.

---

## 7. Cost & sizing notes

- **Code Engine** scales to zero when idle — near-zero cost for a small team.
- **watsonx.ai** inference is pay-per-token; tuning runs are billed per job.
- **GPU VSIs** are hourly and expensive — provision for the training run,
  then destroy (`terraform destroy -target=...` or the toggle variable).
- **VPN server** is a flat hourly charge per server + data.
- Everything here fits in one resource group so the bill is one filterable view.

---

*See `deploy/ibm-cloud/README.md` for the step-by-step provisioning and
deployment commands.*
