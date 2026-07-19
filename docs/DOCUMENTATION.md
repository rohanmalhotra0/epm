# EPM Wizard — Complete Feature & Technical Documentation

EPM Wizard is a **local-first, ChatGPT-style AI workspace for Oracle Enterprise
Performance Management (EPM) implementation**. It runs entirely on your machine:
a React frontend and a FastAPI backend orchestrated by Docker Compose, with all
data in a local SQLite database. There is no hosted server, no cloud database,
and no account system. Optional external AI providers (Anthropic, OpenAI,
Gemini, watsonx.ai, Ollama, …) can be plugged in, but every piece of application
data — projects, conversations, contexts, artifacts, deployments, settings —
stays on disk locally.

The product looks and feels like a modern IBM enterprise AI tool (IBM Carbon
Design System, IBM Plex typography) while staying conversational and simple.

**The core design principle:** the language model *proposes*; deterministic
code *disposes*. The LLM interprets intent and suggests structured
specifications. Deterministic, tested Python owns everything that must be
correct: validation, member resolution, XML rendering, packaging, deployment,
and verification. There is no `subprocess.run(model_output, shell=True)`
anywhere — every executable action maps to a typed, allowlisted backend
function behind a single connector boundary.

```
User request
  → intent recognition            (deterministic router)
  → context retrieval             (local, identifier-first, no fuzzy substitution)
  → specification proposed        (Form / Rule / Report spec, Pydantic-validated)
  → tenant metadata validation    (cube/dimension/member existence, sizing)
  → interactive preview           (rendered in chat)
  → user approval                 (explicit approval cards; PROD safeguards)
  → deterministic generation      (safe XML, reproducible ZIP + checksums)
  → deployment                    (connector boundary; never a shell)
  → post-deployment verification  ("verified" only after the artifact is confirmed)
  → complete local history
```

---

# Part 1 — Feature Guide

## 1.1 Getting started

```bash
docker compose up --build
```

Open **http://localhost:3000**. The backend API runs localhost-only at
`http://127.0.0.1:8000` (Swagger at `/docs`).

On first launch you land on a **connection screen**. Two paths:

- **Connect a real Oracle EPM tenant**: instance URL, username, password,
  classification (development / test / production). The application name is
  auto-detected from the tenant. The password is held in process memory only —
  or, if you tick "Remember password on this machine", in an encrypted local
  store. It is never written to the database, chat, or logs.
- **Demo mode**: from Settings (reachable while gated), add a *Demo
  environment*. This uses a built-in fixture Planning application (`MCWPCF`)
  with 4 cubes, 10 dimensions, 80 members, 3 forms, and 4 business rules — the
  whole product works offline with zero configuration and no API key, powered
  by a deterministic local AI provider.

A one-time, dismissible **first-run tour** introduces the chat, the sidebar
pages, and the command palette.

## 1.2 The chat

Everything starts in chat. Responses stream token-by-token with live process
steps ("Understanding request → Searching EPM context → Validating form →
Generating preview"). The empty state greets you by time of day and offers
one-click suggestion cards.

- **Slash commands** with autocomplete: `/forms`, `/reports`, `/rules`,
  `/run-rule`, `/context`, `/architecture`, `/search`, `/explain`, `/compare`,
  `/deploy`, `/rollback`, `/epm-automate`, `/help`. Plain English works too —
  a deterministic intent router picks the right skill.
- **Interactive blocks**: replies are not just text. Forms render as grid
  previews, validation results as pass/fail reports, deployments as live
  step-by-step progress, cube maps as SVG diagrams, approvals as button cards.
  Clicking an action button records its value as a normal user message, so
  conversations stay reproducible.
- **Message actions**: copy any message as raw text; regenerate the last
  assistant reply; stop a streaming response mid-flight.
- **Voice**: dictate messages with browser speech-to-text (mic button in the
  composer, interim transcript preview), and have replies read aloud with
  text-to-speech (per-message speak button, or auto-speak with voice and speed
  settings).
- **Secret protection**: if a message looks like it contains a credential, it
  is redacted before storage and the app warns you.

## 1.3 Conversations and projects

- Conversations live in the sidebar: **create, rename, pin, archive, and
  delete** (with a danger confirmation). Pinned conversations sort first; an
  archived section expands on demand. Sidebar search matches titles *and*
  message content.
- Work is organized into **projects** (switcher in the header). Each project
  has its own environments, conversations, contexts, artifacts, and deployment
  history.
- The first user message auto-titles a new chat. Editing an earlier message
  branches the conversation.

## 1.4 The skills

The assistant's capabilities are packaged as 13 registered skills (browse them
all on the **Skills** page, with copyable example prompts):

| Skill | What it does |
|---|---|
| **Forms** (`/forms`) | Conversational form building — a resumable workflow: describe a form, get a preview + validation, edit it in plain English, then deploy with approval. |
| **Reports** (`/reports`) | Build formatted report grids with smart formatting (scale to millions, red negatives, conditional highlighting), optional charts, and download as HTML + CSV + JSON + Markdown. |
| **Rules** (`/rules`, `/run-rule`) | List business rules, discover their runtime prompts (rendered as a fill-in form with sensible defaults), and execute them with job polling and full history. |
| **Context** (`/context`) | Build a quick or deep local snapshot of your tenant's metadata; refresh with a diff of what changed; export/import portable `.epwcontext` packages. |
| **Architecture** (`/architecture`) | The Cube Architecture & Dimensionality Visualizer — SVG cube maps, dimension coverage for a form, "explain one data cell", cube comparison, hierarchy inspection. |
| **Deploy** (`/deploy`) | Verify deployed forms and check deployment status (real deploys run inside the Forms workflow with approval). |
| **Rollback** (`/rollback`) | Restore the most recent reversible deployment from its automatic backup, gated by a typed confirmation phrase. |
| **Search** (`/search`) | Deterministic metadata answers: what cubes/dimensions/forms/rules/variables exist; member search with match provenance (exact / alias / substring). |
| **Explain** (`/explain`) | Explain a business rule (source, runtime prompts, documented purpose) or a member formula — factual, never invented. |
| **Compare** (`/compare`) | Compare two cubes' dimensionality, or diff two context versions. |
| **EPM Automate** (`/epm-automate`) | A command advisor: builds safe, risk-classified EPM Automate plans (with encrypted-password login patterns and verify steps). It never executes commands. |
| **Help** (`/help`) | The in-chat capability catalog. |
| **Chat** | The fallback conversational skill, grounded in your tenant's actual metadata. |

## 1.5 Building a form (the flagship workflow)

> *"Create an Actuals form with level-zero descendants of Total Payroll in rows"*

1. The NLU infers the cube (payroll → Workforce), scenario (Actuals), row
   selection (level-zero descendants of Total Payroll) and builds a complete
   specification, stating every inference it made.
2. You get an in-chat **preview** (POV / Pages / Rows / Columns chips + a grid
   mock), a **validation report** (member existence, cube membership, size
   estimate with a 250k-cell warning), and action buttons.
3. **Edit conversationally**: "move Entity to POV", "hide March and April",
   "use aliases", "only show 5 rows", "attach the IR rule", "use descendants
   instead of children". Every edit shows a before/after diff and re-validates.
4. **Deploy** presents a deployment plan card: environment, classification,
   create vs update, whether an existing form will be overwritten (a backup is
   captured automatically), validation status. Production deployments demand
   typing an exact confirmation phrase.
5. Deployment runs a 12-step pipeline with live progress, then **verifies** the
   form actually exists with the right name, folder, and cube. "Imported"
   and "verified" are separate results — the app never claims success just
   because an import returned 0.
6. Everything is recorded: the spec, the rendered XML, the reproducible
   package (with SHA-256 checksums), the deployment record, and an audit entry.

You can also **download the package** without deploying, or open the form in
the **artifacts side panel** for inline editing.

## 1.6 Reports and the artifacts panel

Reports follow the same propose → preview → refine loop but produce download
packages rather than deployments. Preview values are deterministically sampled
(same spec always renders identically) and smart-formatted Oracle-style.

The **artifacts panel** (toggle in the header) is a Claude-style side panel:

- **View** a report grid with formatted values, totals, and notes, or a form's
  structural preview.
- **Edit with natural language at three scopes**: the whole artifact, one
  table, or one cell (click a cell → "set to 1200", "make this bold",
  "highlight red"). Quick-hint chips suggest common edits.
- **Download** report packages (HTML + CSV + JSON + Markdown in one zip).

## 1.7 Metadata pages

- **Explorer** (`/explorer`): browse the active context as a dimension →
  member hierarchy tree with filtering, aliases, member counts, and a detail
  card (parent, storage, source, context version).
- **Contexts** (`/contexts`): build quick/deep contexts, see counts and
  honest completeness per section (the app marks what it could *not* retrieve
  rather than guessing), export `.epwcontext` packages.
- **Artifacts** (`/artifacts`): the artifact library with downloads and a
  **visual diff** — select two artifacts of the same kind and see a
  field-level added/removed/changed comparison.
- **Deployments** (`/deployments`): full deployment history (result,
  verified, demo/live) plus per-deployment **EPM Automate script downloads**
  (`.sh` and `.ps1`) that reproduce the deployment as a reviewable script with
  environment-variable placeholders — never embedded credentials.

## 1.8 Data management and diagnostics

- **Data** (`/data`): export any project as a portable, checksummed zip bundle
  and import it on another machine (secrets are never included); create and
  list **database backups** (also taken automatically at startup, with
  rotation); see **disk usage** for the database, backups, and per-project
  artifacts.
- **Diagnostics** (in Settings): live subsystem health (database, storage, AI
  provider, Java/EPM Automate, context, redaction self-test), a filterable
  **log viewer** (all / warn+ / error) over an in-memory redacted ring buffer,
  and a downloadable redacted diagnostics bundle.

## 1.9 Settings

- **AI providers**: add and test providers of type `mock` (deterministic
  local), `anthropic`, `openai`, `openrouter`, `gemini`, `ollama`, `generic`
  (any OpenAI-compatible endpoint), and `watsonx` (IBM watsonx.ai). A
  one-click **Ollama preset** configures a local model, and **Detect models**
  auto-discovers what's installed. API keys go to the encrypted local secret
  store, never the database.
- **Oracle environments**: add environments with classification, connect and
  test, or use a demo environment.
- **Appearance**: dark (Carbon Gray 100) / light theme toggle, also in the
  header and command palette.

## 1.10 Everyday conveniences

- **Command palette** (`Ctrl/Cmd+K`): jump to any page, start a new chat,
  toggle the theme, or search across conversations, messages, and artifacts
  with grouped, keyboard-navigable results.
- **Shortcuts**: `Ctrl/Cmd+Shift+O` new chat, `Ctrl/Cmd+/` focus the composer.
- **Toasts** for every success/failure; production environments get a pulsing
  red badge in the header so you always know where you're pointed.

---

# Part 2 — Technical Reference

## 2.1 System architecture

```
┌────────────────────────── Browser ──────────────────────────┐
│  React 18 + TypeScript SPA (Vite, Carbon, react-query,      │
│  zustand)  —  SSE streaming chat, typed generated schemas   │
└──────────────┬──────────────────────────────────────────────┘
               │ /api/*  (dev: Vite proxy · prod: nginx → backend:8000)
┌──────────────▼──────────────────────────────────────────────┐
│  FastAPI backend (Python 3.12, Pydantic v2, SQLAlchemy 2)   │
│                                                             │
│  api/ (routers) → services/ (logic) → db/ (SQLite + WAL)    │
│  agent/  orchestrator · intent router · NLU · 13 skills     │
│  ai/     mock · anthropic · gemini · openai-compat · watsonx│
│  context/ engine · retrieval · .epwcontext packages         │
│  artifacts/ resolver · validation · preview · renderer ·    │
│             packager · parser  (deterministic pipeline)     │
│  connector/ ← THE ONE ORACLE BOUNDARY                       │
│    DemoConnector · OracleRestConnector · EpmAutomateRunner  │
│  security/ redaction · encrypted secret store               │
│  eval/    NLU evaluation harness                            │
└─────────────────────────────────────────────────────────────┘
        │                                    │
   SQLite (WAL) + files              Oracle EPM Cloud (optional)
   under EPMW_DATA_DIR               via documented REST + allowlisted
                                     EPM Automate commands only
```

**Repository layout**

```
backend/            FastAPI app, Alembic migrations, fixtures, tests
frontend/           React SPA, generated schemas, tests, nginx config
docs/               ARCHITECTURE, SECURITY, EPM_AUTOMATE, ORACLE_ARTIFACT_RESEARCH,
                    IBM_CLOUD, IMPROVEMENTS, this document
deploy/ibm-cloud/   Optional hosted deployment (Terraform + Code Engine)
docker-compose.yml  Two services: backend (localhost-only :8000), frontend (:3000)
```

## 2.2 Backend core

### Lifecycle

`app/main.py` builds the FastAPI app with a lifespan hook that configures
structured logging, runs Alembic migrations to head, seeds defaults (a default
project and the deterministic mock provider), and takes a startup database
backup (failure never blocks startup). CORS allows only the local frontend
origins. Routers mount in a fixed order: meta, projects, conversations,
environments, providers, context, artifacts, diagnostics, reports, settings.

### Configuration (`app/config.py`)

All settings use the `EPMW_` env prefix and load from the nearest `.env`.
Key settings: `EPMW_DATA_DIR` (default `./data`, `/data` in Docker) — parent of
the SQLite DB, artifacts, contexts, secrets, backups, and the EPM Automate
workdir; `EPMW_SECRET_MASTER_KEY` (optional stable encryption key);
`EPMW_EPMAUTOMATE_PATH` + `JAVA_HOME` (optional local runner);
`EPMW_ORACLE_METADATA_JOB` / `EPMW_ORACLE_METADATA_SNAPSHOT` (member import for
real tenants); `EPMW_BACKUP_KEEP` (backup rotation, default 5); CORS origins;
log level/format.

### Logging (`app/logging.py`)

structlog with a processor chain that **redacts every event before it is
rendered or buffered**: contextvars → level → ISO timestamp → redaction →
ring buffer → JSON/console. A 500-entry thread-safe in-memory ring buffer
(plus a stdlib handler mirroring uvicorn/library logs through `redact_text`)
feeds `GET /api/diagnostics/logs`. Nothing is persisted to disk.

### Database (`app/db/`)

Synchronous SQLite tuned for a single-user local app: WAL journal mode,
foreign keys on, 5s busy timeout, 32-hex UUID primary keys, UTC timestamps.
Fourteen models:

| Model | Purpose |
|---|---|
| `Project` | Top-level container; active environment + context pointers |
| `EnvironmentProfile` | Oracle tenant profiles (URL, user, classification, demo flag) — never passwords |
| `ProviderProfile` | AI provider config; `has_key` boolean only — keys live in the secret store |
| `Conversation` / `Message` | Chat history with pin/archive, blocks, process steps, branching (`parent_id` + `active`), usage |
| `Attachment` | Uploaded file metadata |
| `Artifact` | Versioned artifacts (formSpec, ruleSpec, xml, package, backup, …) with checksums and parent links |
| `ContextVersion` / `ContextRecord` | Tenant metadata snapshots + indexed record rows |
| `Deployment` | Full deployment history: approved / success / **verified** as separate fields, rollback linkage |
| `RuleExecution` | Business-rule run history with prompt values and job results |
| `Setting` | Scoped key/value settings |
| `AuditRecord` | Audit trail with operation class (readOnly … destructive) |
| `WorkflowState` | Resumable per-conversation skill state (e.g. the in-progress form) |

Alembic migrations run at startup (`render_as_batch` for SQLite-safe ALTERs).

### REST API surface

~60 endpoints across ten routers. The important groups:

| Area | Endpoints |
|---|---|
| Meta | `GET /api/health`, `/api/skills`, `/api/meta/skills` (catalog), `/api/tools`, `/api/schema` |
| Projects | CRUD + `GET .../search?q=` (global search) + `GET .../export` / `POST /api/projects/import` (bundles) + `GET .../impact?member=` |
| Conversations | list/create/PATCH (title/pinned/archived)/DELETE + `POST .../messages` (**SSE stream**) + `.../branch` (edit & re-stream) |
| Environments | CRUD + connect / disconnect / test |
| Providers | CRUD + per-provider test + `GET .../models` + `POST /api/providers/models/discover` (probe an unsaved endpoint, 8s timeout) |
| Context | list/build (quick/deep)/activate/delete + `.epwcontext` export/import + member search |
| Artifacts | list/get/download/delete + deployments list/get + `GET /api/deployments/{id}/script?format=sh\|ps1` + rule executions |
| Reports/edit | `POST /api/artifact/edit` (prompt edit at artifact/table/cell scope), form/report preview, report render + download |
| Diagnostics | report, logs, backups (list/create), disk usage, redacted bundle download |

SSE events: `title`, `process`, `token`, `block`, `toolCall`, `toolResult`,
`messageSaved`, `error`, `done`, `usage` — each `event:`/`data:` framed. The
chat route persists the (redacted) user message in its own transaction and
commits all reads before streaming so no WAL snapshot is held open during a
long AI turn.

### Services

Thin routers delegate to `app/services/`: conversations (incl. branch-on-edit
and auto-titling), projects, environments, providers (keys → secret store),
context_store (persist/activate/reconstruct `TenantMetadata` offline),
artifacts (auto-versioning with parent links), deployments, rule_executions,
settings/audit, search (escaped LIKE with match-centered snippets), impact
(generic JSON-path walk over stored specs, exact case-insensitive identifier
match), project_bundle (deterministic zip export; zip-slip-guarded,
checksum-verified import that remaps all IDs), backups (SQLite online backup
API + rotation), disk_usage, automate_script (deterministic `.sh`/`.ps1`
generation — text only, never executed).

## 2.3 The conversational agent

### Orchestrator (`app/agent/orchestrator.py`)

One deterministic skill runs per turn. The flow: detect intent → check for an
active **workflow** (forms/reports are resumable; "hide March" routes back
into the in-progress form; a slash command or clear topic switch deactivates
it) → build skill context (session, project, connector, provider, metadata
access) → run the skill in a background task, streaming its emissions through
a queue → persist the assistant message (content, blocks, process steps,
usage, skill) → upsert workflow state → emit `messageSaved` + `done`.
Connector errors and crashes surface as structured `errorDiagnostics` blocks
— the stream always terminates cleanly.

### Intent routing (`app/agent/intent.py`)

Fully deterministic and offline — no LLM in the router. Slash commands map
directly; ~12 ordered natural-language rules (EPM Automate vocabulary first,
then context, rules, forms, reports, architecture, deploy, rollback, compare,
search, explain, help) fall through to `chat`.

### Natural-language understanding (`form_nlu.py`, `report_nlu.py`)

Deterministic parsers turn phrases into precise spec operations: vocabulary
tables for scenarios/axes/selection functions (longest-match so "level-zero
descendants" wins over "descendants"), longest-substring member resolution
through names *and* aliases ("March" → member `Mar`), cube inference
(payroll → Workforce, cash → Daily Cash), reference-form cloning ("like
Actual Revenue Review"), and a rich edit-verb set: move/hide (by name or
ordinal)/alias/read-only/limit/remove dimension/reverse periods/attach rule
(whole-word matching so "IR" never matches "hire")/change scenario. The
report NLU adds smart-format vocabulary (millions, decimals, red negatives,
conditional highlighting), charts, and per-cell overrides. Every parse
returns human-readable inference/change strings that the skills display.

### Tools (`app/agent/tools.py`)

Fifteen typed, allowlisted tools with operation classes (readOnly →
execution → modifying); `run_business_rule` and `import_snapshot` require
approval. There is deliberately no generic command surface — unknown tool
names return a security error.

### The deployment pipeline (`app/agent/deploy.py`)

Twelve steps: auth → match → validate → overwrite-detect → backup → package →
package-validate → upload → import → poll → inventory → **verify**. A backup
artifact of any overwritten form enables `/rollback`. Verification requires
the connector to return the deployed form and every check to pass (exists,
name, folder, cube) — a field the connector didn't return counts as "could
not confirm", never a pass. `success` and `verified` are distinct fields all
the way to the UI. Production requires the typed confirmation phrase
(enforced and tested). Every deployment records artifacts, history, and an
audit entry.

## 2.4 AI provider layer (`app/ai/`)

A small provider abstraction (`AIProvider`: `list_models`, `test_connection`,
`stream`) with a registry that resolves the active provider and its key
(encrypted secret store first, then env vars). Providers:

| Provider | Notes |
|---|---|
| **mock** | Deterministic local provider (`epmw-local-1`); zero-config demo mode. Same input → same output. |
| **anthropic** | Messages API streaming; sampling params deliberately omitted for modern Claude models. |
| **gemini** | `streamGenerateContent` SSE. |
| **openai-compat** | One implementation covering OpenAI, OpenRouter, **Ollama** (default `http://localhost:11434/v1`), and any generic endpoint; requests usage in-stream. |
| **watsonx** | IBM watsonx.ai (Granite models): IBM Cloud API key → IAM token exchange with caching, project/space scoping, `chat_stream` SSE. |

`POST /api/providers/models/discover` probes any of these before saving a
profile — backing the Settings "Detect models" button. Chat always works:
resolution falls back to the mock provider when nothing else is configured.

## 2.5 Context engine (`app/context/`)

Builds local, versioned snapshots of tenant metadata through the connector:
applications, cubes, dimensions, variables, forms, rules, then members per
dimension. Every section carries an **honest completeness status**
(complete / partial / derived / unavailable / not-requested) — the app never
claims data it couldn't retrieve. Retrieval is identifier-first: matches are
ranked exact → case-insensitive → alias → prefix → substring, each carrying
its method and confidence; the assistant reports what it matched and how, and
never silently substitutes a similar member. Contexts export as deterministic
`.epwcontext` zips (per-file checksums, secret-scan assertion, human-readable
`context.md`) and can be imported on another machine.

## 2.6 The deterministic artifact pipeline (`app/artifacts/`)

- **Schemas**: `FormSpecification`, `RuleSpecification`, `ReportSpecification`
  (Pydantic v2, camelCase, `extra="forbid"` so hallucinated fields fail
  validation). Structural validators enforce non-empty rows/columns and
  one-axis-per-dimension. Eighteen member-selection types with per-type
  required fields.
- **Resolver**: turns selections into exact ordered member lists using outline
  operations (children/descendants/level-zero/ancestors/siblings/level-aware
  ranges) with cycle-breaking for malformed outlines. Unresolvable members
  raise errors with near-match candidates — no fuzzy substitution, ever.
- **Validation**: layered report (application, axis, selection, coverage,
  display, performance — 250k-cell warning, security — secret scan on
  names, deployment — identifier rules shared with the connector). Errors
  block; warnings don't.
- **Preview**: deterministic form grids (sample members, truncation flags,
  size estimates) and report grids with **hash-sampled stable values** so the
  same spec always renders identically without live data.
- **Renderer**: XML via ElementTree only (auto-escaping, fixed attribute
  order, member lists as child elements so commas survive round-trips) —
  same spec + renderer version → byte-identical output. Report renderer emits
  self-contained HTML (inline CSS, dependency-free SVG charts), CSV, JSON,
  Markdown.
- **Parser**: `defusedxml`-based (XXE-safe) parsing of normalized form XML and
  reference-form definitions; lossless round-trip is test-enforced.
- **Packager**: reproducible zips — fixed 1980 timestamps, sorted entries,
  per-file SHA-256 checksums in a manifest, plus the zip's own checksum
  recorded on the deployment.

## 2.7 The connector boundary (`app/connector/`)

The single authoritative Oracle integration point. The model never calls
Oracle; skills call typed connector methods classified read-only / execution /
modifying.

- **DemoConnector**: full boundary backed by the `MCWPCF` fixtures plus an
  in-process registry of "deployed" forms, so create → verify loops behave
  faithfully offline. Simulated jobs are clearly labelled; no tenant is ever
  contacted.
- **OracleRestConnector**: documented Planning REST only — applications,
  plan types (cubes), per-plan-type dimensions (handles Enterprise apps where
  app-level dimension routes 404), job definitions (rules), substitution
  variables, rule execution + polling. Members aren't exposed by Planning
  REST, so they're imported via an EPM Automate metadata-export job or an LCM
  snapshot (CSV parsing with hierarchy derivation), degrading gracefully to
  "members unavailable". **Form upload/import deliberately raise
  `not_supported`** until the documented Migration workflow is validated
  (`docs/ORACLE_ARTIFACT_RESEARCH.md`) — the app reports honestly instead of
  guessing.
- **EpmAutomateRunner**: a restricted local runner for the user-installed EPM
  Automate binary. Strict command **allowlist** (login, logout, listfiles,
  uploadfile, downloadfile, import/exportsnapshot, exportmetadata,
  runbusinessrule, getsubstvar, feedback, version), argument **arrays** only —
  never `shell=True` — fixed workdir, bounded timeouts, and stdout/stderr
  redaction before anything is returned or logged.
- **Argument validation**: identifiers reject shell metacharacters and `..`;
  filenames reject path separators; URLs must be http(s); prompt values are
  length-capped; paths are asserted to stay inside the workdir.
- **Connection registry**: passwords live in process memory (or the encrypted
  store if "remember" was chosen) and are registered with the redactor;
  connecting performs a harmless read-only auth check.

## 2.8 Security model

- **Redaction everywhere**: a central module scrubs registered secrets plus
  pattern-matched credentials (Bearer/Basic, `sk-…`, AWS/Google/GitHub/Slack
  keys, JWTs, `key=value` prose, URL userinfo, PEM blocks) from every log
  event, tool result, connector error, EPM Automate output, and the
  diagnostics bundle. Diagnostics runs a redaction self-test on every call.
- **Secret storage**: OS keychain → encrypted Fernet store
  (`data/secrets/secrets.enc`, atomic writes, 0600) → process memory. Raw
  passwords and API keys are never written to SQLite; the DB stores only
  `has_key` booleans.
- **No arbitrary execution**: no generic command endpoint, no shell
  interpolation, typed tools with operation classes, connector-level
  allowlists and argument validation.
- **Approval gating**: every Oracle-modifying action needs an explicit
  approval card; production also needs a typed confirmation phrase, passing
  validation, and context freshness — a vague earlier "yes" is never standing
  permission. All of it is audited.
- **Honest verification**: `success` ≠ `verified`; unverifiable fields are
  "could not confirm", never a pass.

## 2.9 Schema codegen (single source of truth)

Pydantic models are canonical. `CANONICAL_MODELS` (~80 models in fixed order)
→ `app/codegen.py` → three generated frontend files: `schemas.json` (JSON
Schema), `types.ts` (TypeScript interfaces), `zod.ts` (runtime validators).
`tests/test_schema_drift.py` regenerates in memory and fails if the committed
files differ byte-for-byte — the frontend can never hold a divergent schema.

## 2.10 Evaluation harness (`app/eval/`)

A golden corpus (intent routing, spec building, editing — grounded in the
demo tenant) is scored as **coverage** (fraction of atomic checks passing,
partial credit) and **exact rate**, broken down by category, check kind, and
`supported` vs `paraphrase` tags (the latter measures headroom). A `Strategy`
protocol wraps the deterministic NLU baseline so a future LLM-proposes/
deterministic-validates strategy can compete on the identical corpus. CLI:
`python -m scripts.eval_nlu [--verbose] [--json] [--min-coverage 0.8]` (CI
gate via exit code).

## 2.11 Frontend

**Stack**: React 18 + TypeScript (strict), Vite, Carbon Design System + IBM
Plex, react-query (server state), zustand (UI state, persisted), marked +
DOMPurify (sanitized Markdown), vitest + Testing Library (70+ tests). Dev
serves via Vite proxy; production is a two-stage Docker build served by nginx
with SSE-safe proxying (`proxy_buffering off`, 1h read timeout).

**Shell**: header (project switcher, environment/classification badges with a
pulsing production indicator, active model, theme toggle, TTS + artifacts
toggles), collapsible sidebar (conversation management + navigation), sign-in
gate (tenant connection, not app auth — Settings reachable while gated),
command palette, first-run tour, global shortcuts, toast system.

**Chat**: SSE consumption maps events to UI — `token` appends streamed text,
`process` updates the live stepper, `block` upserts by block id (so a
deployment-progress block updates in place). `onDone` invalidates the
relevant query caches and optionally speaks the reply. Aborts (stop/switch/
unmount) are silent by design.

**Block renderer**: a `switch` over ~25 block types → dedicated components:
form/report previews, validation reports, confirmation cards (buttons send
their value as user messages), deployment plan/progress/result, runtime-prompt
forms, member search tables, context summaries, diffs, error diagnostics,
downloadable files, and the five SVG architecture visualizations. Unknown
types render a safe JSON fallback.

**Artifacts panel**: a namespaced side panel with view/edit tabs, scoped
prompt editing (artifact / table / cell), quick-hint chips, change logs, and
report package downloads.

**Generated schemas**: `frontend/src/schemas/*` are generated files — over
100 types kept in lockstep with the backend by the drift test.

## 2.12 Demo fixture application (`backend/fixtures/mcw/`)

A deterministic synthetic Planning app, `MCWPCF`: cubes `OEP_FS` (Financials),
`OEP_WFP` (Workforce), `OEP_DCSH` (Daily Cash), `OEP_REP` (Reporting/ASO);
10 dimensions; 80 members with aliases, parents, storage, and levels; 3 fully
defined forms (usable as reference templates); 4 rules with runtime prompts
(including a Groovy `Add New Hire` and calc-script `IR`); 6 substitution/user
variables. Names are chosen so every documented example resolves end-to-end.

## 2.13 Optional IBM Cloud path (`deploy/ibm-cloud/`, `docs/IBM_CLOUD.md`)

Local-first remains the default, but the repo ships an optional all-IBM hosted
topology: watsonx.ai for inference (the `watsonx` provider), watsonx.ai Tuning
Studio or GPU instances for fine-tuning — fed by
`backend/scripts/export_training_data.py`, which exports **redacted** local
conversations and validated specs as JSONL (watsonx or chat format, deduped) —
Code Engine + Container Registry for hosting, and a VPC with Client-to-Site
VPN so nothing is exposed to the public internet. Terraform and a deploy
script are included. The Oracle integration point remains the same connector
boundary.

## 2.14 Development workflow

```bash
# Backend
cd backend && uv venv .venv --python 3.12 && uv pip install -e ".[dev]"
.venv/bin/python -m pytest tests -q          # full suite
python -m scripts.export_schema              # regenerate frontend schemas
python -m scripts.eval_nlu --verbose         # NLU eval report

# Frontend
cd frontend && npm ci
npm run typecheck && npm test && npm run build
```

Tests cover the API surface, the artifact pipeline (including lossless XML
round-trips and reproducible packaging), connector security (allowlists,
validation, redaction), the orchestrator (including the production-safeguard
test), NLU + eval, schema drift, providers (including watsonx), bundles/
backups/ops features, and the frontend's blocks, composer, sidebar, palette,
pages, and stores.

---

*See also: `docs/ARCHITECTURE.md` (design rationale), `docs/SECURITY.md`
(threat model), `docs/EPM_AUTOMATE.md` (runner setup),
`docs/ORACLE_ARTIFACT_RESEARCH.md` (why deployment is gated),
`docs/IBM_CLOUD.md` (hosted topology), `docs/IMPROVEMENTS.md` (roadmap).*
