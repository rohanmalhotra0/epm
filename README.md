# EPM Wizard

**A local-first, ChatGPT-style AI workspace for Oracle Enterprise Performance
Management (EPM) implementation.** It runs entirely on your machine — no hosted
server, database, authentication service, or cloud infrastructure. Optional
external AI providers are supported, but all application data, project data,
conversations, context, generated artifacts, deployment history, and settings
stay local.

It looks and feels like a modern IBM enterprise AI product (IBM Carbon Design
System, IBM Plex typography) while staying conversational and simple.

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

To use a real AI model or a real Oracle environment, open **Settings** in the UI
(no `.env` editing required). A `.env` is optional — see `.env.example`.

### Try these in the chat

- `Create an Actuals form with level-zero descendants of Total Payroll in rows`
- `move Entity to POV` · `hide March` · `use aliases` — then `deploy`
- `Visualize OEP_DCSH` — the Cube Architecture & Dimensionality Visualizer
- `What cubes and dimensions exist?`
- `Run the IR rule`
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
| Context engine | `app/context` | Quick/deep context, local retrieval, portable `.epwcontext` packages |
| AI layer | `app/ai` | Provider-independent: deterministic **Mock** + IBM watsonx.ai / Anthropic / OpenAI-compatible / Gemini adapters |
| Agent | `app/agent` | Intent router, tool framework, skills, streaming orchestrator |
| Cube visualizer | `app/architecture` | Deterministic Cube Architecture, coverage, cell intersection, comparison, sizing, hierarchy |
| API | `app/api` | FastAPI routes incl. SSE streaming chat |

### Frontend (`frontend/`, React · TypeScript · Vite · IBM Carbon · TanStack Query · Zustand · Zod)

Chat is the primary interface. Everything important renders **inline** as typed
blocks: form previews (an EPM-style grid), validation reports, deployment
plan/progress/result, member search, runtime-prompt forms, the cube map (SVG),
diffs, confirmations, downloadable files, and error diagnostics.

---

## Security & secrets

- Secrets are **never** sent to the model, logged, put in chat history, context
  packages, generated artifacts, or git. A centralized redactor scrubs every log
  line, tool result, error, and diagnostics bundle.
- API keys and remembered passwords go to a local **encrypted secret store**
  (Fernet), not SQLite. "Password in memory" auth keeps the password only for the
  session.
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

## All-IBM cloud deployment

EPM Wizard can run entirely on IBM Cloud: **watsonx.ai** for inference (a
first-class provider type in Settings), **Tuning Studio or GPU-as-a-Service**
for training on your own EPM data, **Code Engine** for hosting, and a
**Client-to-Site VPN** with email invites as the only way in.

- Architecture, request flow, and training paths: [docs/IBM_CLOUD.md](docs/IBM_CLOUD.md)
- Terraform + deploy script: [deploy/ibm-cloud/](deploy/ibm-cloud/)
- Export a redacted fine-tuning corpus from your local data:
  `python -m scripts.export_training_data` (from `backend/`)

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
pytest -q                                 # 50 tests

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

- **Backend:** `pytest` — 50 tests covering schema validation, the deterministic
  artifact engine (resolver, validation, XML round-trip, reproducible packaging),
  connector security/injection, redaction, context + retrieval, the cube
  visualizer, form NLU, the full orchestrator loop (create → edit → coverage →
  deploy → verify, plus the production safeguard and rule execution), and the HTTP
  API incl. SSE streaming.
- **Frontend:** `vitest` + React Testing Library — inline blocks, the cube map,
  the runtime-prompt form, deployment result, the composer (Enter/Shift+Enter,
  slash menu, stop), and graceful fallback for unknown block types.

---

## Data & persistence

Everything lives under a single local data directory (a named Docker volume
`epmw-data`, or `backend/data` in dev): the SQLite database, encrypted secret
store, generated artifact packages, and context packages. Data survives browser
refresh, container restart, and machine restart. Export/import a project or a
`.epwcontext` for backup or team sharing.
