# EPM Wizard

**A local-first, ChatGPT-style AI workspace for Oracle Enterprise Performance
Management (EPM) implementation.** By default it runs entirely on your machine —
no hosted server, database, authentication service, or cloud infrastructure
required. Optional external AI providers are supported, but all application data,
project data, conversations, context, generated artifacts, deployment history,
and settings stay local. When you *do* want it hosted, a Fly.io deployment path
with an optional Google/GitHub login gate ships in `deploy/fly` (see
[Hosting](#hosting-optional)).

It looks and feels like a modern IBM enterprise AI product (IBM Carbon Design
System, IBM Plex typography) while staying conversational and simple. Beyond the
chat workspace it now also ships a **narrated browser-agent extension** and a
**fine-tuned EPM coder model** — see below.

> EPM Wizard is an independent implementation tool. IBM, Oracle, and their
> respective product names are trademarks of their respective owners. EPM Wizard
> is not made, endorsed, or sponsored by IBM or Oracle.

---

## Quick start

```bash
docker compose up --build
```

Then open **http://localhost:3000**.

That's it. EPM Wizard boots in **Demo Mode** with a deterministic local AI
provider and a fixture Planning application (`MCWPCF`), so the whole product is
usable with **zero configuration and no API key**. No Oracle tenant is contacted.

- Frontend (nginx serving the built SPA): `http://localhost:3000`
- Backend API (localhost-only): `http://127.0.0.1:8000` (Swagger at `/docs`)

### Human-style browser testing

An isolated Playwright + Chromium environment exercises the real frontend,
nginx proxy, FastAPI backend, streaming responses, accessibility, and
multi-user identity boundary without touching normal local data:

```bash
cd frontend
npm ci
npx playwright install chromium
npm run e2e
```

The harness also supports a one-time interactive OAuth session capture for
testing a deployed staging environment; credentials and MFA are never given to
the test runner or an agent. See
[`frontend/e2e/README.md`](frontend/e2e/README.md) for interactive modes,
failure traces/videos, and the OAuth workflow.

To use a real AI model or a real Oracle environment, open **Settings** in the UI
(no `.env` editing required). A `.env` is optional — see `.env.example`.

The workspace is organized as pages in the left rail — **Chat** (the primary
surface), **Contexts**, **Artifacts**, **Deployments**, **Skills**, **Explorer**,
**Data**, **Agent** (the browser agent) and **Settings** — plus a public
**Landing**, **Guide** and **Docs** page. You can also **dictate** any chat
message with the microphone button (Web Speech API) and have replies read back.

### Try these in the chat

- `Create an Actuals form with level-zero descendants of Total Payroll in rows`
- `move Entity to POV` · `hide March` · `use aliases` — then `deploy`
- `Visualize OEP_DCSH` — the Cube Architecture & Dimensionality Visualizer
- `What cubes and dimensions exist?`
- `Run the IR rule`
- Attach an LCM **Artifact Snapshot** zip to layer rule bodies, full hierarchies
  and variables on top of the live context (`/context merge snapshot`)
- `Create a business rule that copies Working to Final` — drafted grounded on
  the real rules in your context, with a visible "Grounded on" block
- Tap the **microphone** to dictate instead of typing
- `/help`

---

## What makes this more than a chatbot wrapper

The language model **never owns the deployable Oracle artifact**. It interprets
intent and proposes structured specifications; **deterministic application code**
does everything that must be correct and reproducible:

```
User request
  → intent recognition            (deterministic router + optional LLM)
  → relevant context retrieval     (local, identifier-first, no fuzzy substitution)
  → FormSpecification / RuleSpecification   (proposed, then Pydantic-validated)
  → tenant metadata validation     (cube/dimension/member existence, sizing)
  → interactive preview            (rendered in-chat)
  → user approval                  (explicit approval cards; PROD safeguards)
  → deterministic artifact generation   (safe XML, reproducible ZIP + checksums)
  → deployment                     (connector boundary; never shell)
  → post-deployment verification   ("verified" only after the form is confirmed)
  → complete local project history
```

There is **no** `subprocess.run(model_output, shell=True)`. Every executable
action maps to a typed, allowlisted backend function behind one connector
boundary.

---

## Application snapshots & RAG grounding

Two features turn EPM Wizard from "knows the API surface" into "knows **your**
application":

**1. LCM Artifact Snapshot upload.** Attach the zip produced by
`epmautomate exportSnapshot` + `downloadFile "Artifact Snapshot"` (chat
paperclip or Context tab → *Upload snapshot*). It is parsed deterministically,
fully in-memory — the application, cubes and dimensions come from the zip's own
manifest, so **any** Planning app works — and layered on top of the live
context as a new provenance-tracked version. This fills in exactly what the
REST/EPM Automate interfaces can't supply: full member hierarchies with
formulas, **Calculation Manager rule bodies and runtime prompts**, templates,
substitution/user variables, form references, FDMEE inventory.

**2. RAG-grounded generation.** When you ask for a new form or business rule,
the agent retrieves the most relevant artifacts from that context — real rule
scripts, templates, naming conventions — shows them in a visible **"Grounded
on"** block, and generates from them. Retrieval is deterministic pure-Python
BM25 (fully offline, works in Demo Mode) and upgrades to hybrid
lexical + embedding scoring when the configured provider supports embeddings
(any OpenAI-compatible endpoint). Rule drafts are **proposals only** — labelled,
never executed, never auto-deployed — saved as reviewable artifacts.

---

## Narrated browser agent (Chrome extension)

`extension/` is a real, loadable **Manifest V3 Chrome extension** that drives a
web app's UI while **narrating each step in a side panel** — "Claude-for-Chrome,
but domain-specific," targeting Oracle EPM Cloud. It runs the full
**plan → act → observe → narrate** loop against the EPM Wizard backend.

- **Launched from the app.** The **Agent** page detects the extension and hands
  it the backend URL, project id and goal — no manual setup. With no provider
  configured it uses the deterministic Mock provider, so the loop is demoable
  offline.
- **Enforced production-safety gate.** Destructive actions and any write on a
  production tenant are *held* for explicit human approval before they execute —
  a hard gate, not a prompt hint.
- **Excel-grounded agent context.** Choose an `.xlsm`, `.xlsx`, `.xlsb` or
  `.csv` in the extension and the agent can reason over its inert VBA source,
  formulas, sheets, named ranges, tables, pivots, charts and connections while
  operating EPM. Workbook content is treated as untrusted reference data and
  can be cleared at any time.
- **Store-ready.** Icons, a privacy policy, a listing pack and a packaging script
  are included.

> **Honesty note:** the Oracle-specific UI grounding (iframes, canvas/JET grids)
> is still stubbed and nothing here has been run against a live Oracle EPM
> tenant. Validate against a real Planning UI before trusting any driving
> behaviour. See [`extension/README.md`](extension/README.md).

---

## Fine-tuned EPM coder model

EPM Wizard can train and serve its own **coder** model. `epm-coder v1` is a LoRA
fine-tune of `Qwen/Qwen2.5-32B-Instruct` (Together AI) that turns plain-English
requests into validated `FormSpecification` JSON and applies natural-language
edits to existing specs — the first checkpoint from `OPENCLAW_PLAN.md` Phase 5.

The pipeline lives in `backend/scripts`:

- `export_training_data` — turn your local conversations, validated specs and
  uploaded snapshot rule bodies into training pairs (redacted on the way out).
- `generate_synthetic_corpus` — a guaranteed-correct synthetic corpus from the
  demo metadata.
- `launch_finetune` — upload the corpus and start the LoRA job via the official
  Together SDK (gated behind `--launch`); `--list-models` probes fine-tunable
  base models.

The standing recommendation is still to ship on **stock Qwen + RAG grounding**
first and only fine-tune if quality demands it. See
[docs/MODEL_CARD.md](docs/MODEL_CARD.md) for the trained model and
[docs/FINETUNING.md](docs/FINETUNING.md) for the runbook (and the cost caveats).

---

## Architecture

Hybrid: a local React frontend + a local FastAPI backend, orchestrated by Docker
Compose. Python + Pydantic own the **canonical schemas**; the frontend types are
generated from them.

```
Pydantic models  →  JSON Schema  →  TypeScript interfaces  →  Zod schemas
(backend/app/schemas)     (frontend/src/schemas/*)   (a drift test fails CI if they diverge)
```

### Backend (`backend/`, Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy · Alembic · SQLite)

| Area | Location | What it does |
|---|---|---|
| Canonical schemas | `app/schemas` | FormSpecification, RuleSpecification, ContextManifest, DeploymentPlan, ValidationReport, CubeArchitecture, chat blocks… |
| Codegen | `app/codegen.py`, `scripts/export_schema.py` | Pydantic → TS + Zod; guarded by `tests/test_schema_drift.py` |
| Persistence | `app/db`, `app/services` | SQLite + Alembic migrations; projects, conversations, artifacts, contexts, deployments, audit |
| Connector boundary | `app/connector` | The one authoritative EPM boundary: Demo, Oracle REST, and a restricted EPM Automate runner (allowlist, no shell) |
| Artifact engine | `app/artifacts` | Member resolution, validation, preview, deterministic XML render + round-trip parse, reproducible packaging |
| Context engine | `app/context` | Quick/deep context, local retrieval, portable `.epwcontext` packages, LCM snapshot-zip upload layered onto the live context |
| AI layer | `app/ai` | Provider-independent: deterministic **Mock** + Anthropic / OpenAI-compatible / Gemini / OpenRouter / Together (incl. the `epm-coder` fine-tune) adapters; embeddings for RAG (OpenAI-compatible, Mock) |
| RAG grounding | `app/rag` | `/forms` and `/rules` ground generation on the active context (snapshot rule bodies, templates, naming digests) — offline BM25 by default, hybrid with embeddings when configured |
| Agent | `app/agent` | Intent router, tool framework, skills, streaming orchestrator |
| Cube visualizer | `app/architecture` | Deterministic Cube Architecture, coverage, cell intersection, comparison, sizing, hierarchy |
| Fine-tuning | `scripts/export_training_data`, `scripts/generate_synthetic_corpus`, `scripts/launch_finetune` | Corpus export, synthetic corpus, and the gated Together LoRA launcher for the `epm-coder` model |
| API | `app/api` | FastAPI routes incl. SSE streaming chat |

### Frontend (`frontend/`, React · TypeScript · Vite · IBM Carbon · TanStack Query · Zustand · Zod)

Chat is the primary interface. Everything important renders **inline** as typed
blocks: form previews (an EPM-style grid), validation reports, deployment
plan/progress/result, member search, runtime-prompt forms, the cube map (SVG),
diffs, confirmations, downloadable files, and error diagnostics. Voice dictation
(Web Speech API) and text-to-speech read-back are built into the composer.

Alongside the workspace there is a public-facing surface: an animated **landing
page**, a **guide** ("how it works"), and public product **docs** — all served
in front of the optional login gate so they're reachable without signing in.

---

## Security & secrets

- Secrets are **never** sent to the model, logged, put in chat history, context
  packages, generated artifacts, or git. A centralized redactor scrubs every log
  line, tool result, error, and diagnostics bundle.
- API keys and remembered passwords go to a local **encrypted secret store**
  (Fernet), not SQLite. "Password in memory" auth keeps the password only for the
  session.
- Oracle sign-in supports **username/password** or **OAuth 2.0 client
  credentials** (an OCI IAM identity domain confidential application): supply the
  identity domain token URL, client ID, client secret and optional scope on the
  sign-in screen. The client secret is handled exactly like a password (process
  memory, or the encrypted store when remembered) and bearer tokens are cached
  in memory and auto-refreshed.
- Messages that look like a pasted credential are redacted before storage and the
  user is warned.
- Command arguments are strictly validated (no path traversal, no shell
  metacharacters); the runner uses subprocess **argument arrays**, never
  `shell=True`.
- Production deployments require a persistent PROD badge, an explicit confirmation
  phrase, passing validation, matching context, and an audit record.

See [docs/SECURITY.md](docs/SECURITY.md).

---

## Real Oracle environments

Demo Mode is the default and the only mode exercised by the test suite. To connect
a real environment, add it in **Settings → Oracle Environments** and click
**Connect** (a harmless read-only call authenticates you).

- Read-only metadata and rule execution use the **documented Oracle Planning REST
  API**.
- Automated form **deployment** to a live tenant is intentionally **not claimed**
  until the documented Migration dev workflow is validated against a development
  tenant — see [docs/ORACLE_ARTIFACT_RESEARCH.md](docs/ORACLE_ARTIFACT_RESEARCH.md).
  EPM Automate is not redistributed; mount/install it locally — see
  [docs/EPM_AUTOMATE.md](docs/EPM_AUTOMATE.md).

---

## Hosting (optional)

Local-first is the default, but EPM Wizard can be hosted. `deploy/fly` holds an
executable Fly.io target: a **public** frontend (nginx, scale-to-zero) and a
**private, always-warm** backend on Fly's `.internal` 6PN network, with an
**optional oauth2-proxy front door** (Google/GitHub OAuth + email allowlist) as
the only public entry point, and external Neon Postgres. `deploy-fly.sh`
bootstraps both apps idempotently; a GitHub Actions workflow auto-deploys on push
to `main`. The public landing/guide/docs pages sit in front of the login gate.
See [`deploy/fly/README.md`](deploy/fly/README.md) and
[docs/OPENCLAW_PLAN.md](docs/OPENCLAW_PLAN.md) for rationale and phased build
order.

---

## Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m scripts.export_schema          # regenerate frontend schemas from Pydantic
alembic upgrade head                      # or let the app do it on startup
uvicorn app.main:app --reload             # http://localhost:8000
pytest -q                                 # 500+ tests

# Frontend
cd frontend
npm install
npm run dev                               # http://localhost:3000 (proxies /api → :8000)
npm test                                  # vitest + RTL
npm run build                             # tsc + vite build
```

**Schema drift:** after changing any Pydantic model, run
`python -m scripts.export_schema` and commit the regenerated
`frontend/src/schemas/*`. `pytest tests/test_schema_drift.py` enforces this.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

---

## Testing

- **Backend:** `pytest` — 500+ tests covering schema validation, the deterministic
  artifact engine (resolver, validation, XML round-trip, reproducible packaging),
  connector security/injection, redaction, context + retrieval, the LCM snapshot
  parser and merge (zip-slip/bomb guards, provenance, real-fixture subset), the
  RAG index (chunking, BM25 determinism, hybrid embeddings, cache), embeddings
  adapters, the cube visualizer, form NLU, rule drafting, the full orchestrator
  loop (create → edit → coverage → deploy → verify, plus the production
  safeguard and rule execution), the fine-tuning corpus export/launcher, and the
  HTTP API incl. SSE streaming.
- **Frontend:** `vitest` + React Testing Library — 110+ tests: inline blocks
  (incl. snapshot summary and grounding sources), the cube map, the
  runtime-prompt form, deployment result, the composer (Enter/Shift+Enter,
  slash menu, stop, voice dictation, zip/spreadsheet uploads), the public
  landing/guide/docs pages, the browser-agent bridge, and graceful fallback for
  unknown block types.

---

## Data & persistence

Everything lives under a single local data directory (a named Docker volume
`epmw-data`, or `backend/data` in dev): the SQLite database, encrypted secret
store, generated artifact packages, context packages, uploaded snapshots, and
the per-version RAG index cache. Data survives browser refresh, container
restart, and machine restart. Export/import a project or a `.epwcontext` for
backup or team sharing.
