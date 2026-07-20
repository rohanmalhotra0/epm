# Architecture

EPM Wizard is a **hybrid, local-first** application: a local React frontend and a
local FastAPI backend, orchestrated by Docker Compose. No hosted services.

## Canonical schema ownership

Python + Pydantic are the single source of truth. The frontend never maintains a
second, independent schema.

```
backend/app/schemas/*.py   (Pydantic v2, camelCase JSON)
        │  app/codegen.py + scripts/export_schema.py
        ▼
frontend/src/schemas/schemas.json   (JSON Schema)
frontend/src/schemas/types.ts       (TypeScript interfaces)
frontend/src/schemas/zod.ts         (Zod runtime validation)
```

`tests/test_schema_drift.py` regenerates in memory and fails if the committed
frontend files differ. `CANONICAL_MODELS` in `app/schemas/__init__.py` is the
registry of exported models.

## The deterministic artifact principle

The LLM may interpret intent, ask questions, search context, and **propose** a
`FormSpecification` / `RuleSpecification`. It never owns the deployable artifact.
Deterministic code validates specs, resolves exact members, renders XML, builds
reproducible packages, uploads, imports, polls, and verifies.

```
Intent → Context retrieval → Spec (proposed) → Pydantic validation
       → tenant metadata validation → preview → approval
       → deterministic generation → package validation → deploy → verify → history
```

## Layers

### Connector boundary (`app/connector`)

One authoritative boundary. The model never calls EPM Automate or Oracle REST
directly; there is no generic command endpoint. Implementations:

- `DemoConnector` — fixtures under `backend/fixtures/mcw`, simulated jobs, an
  in-process registry so the *create → verify* loop is faithful.
- `OracleRestConnector` — documented Planning REST API for read-only metadata and
  rule execution. Modifying operations raise `not_supported` until validated (see
  Oracle research doc).
- `EpmAutomateRunner` — restricted local runner: strict command **allowlist**,
  subprocess **argument arrays** (never `shell=True`), timeouts, output redaction,
  diagnostics.

Operations are classified `readOnly | execution | modifying | destructive`;
modifying/destructive require explicit approval upstream.

### Artifact engine (`app/artifacts`)

- `metadata.py` — in-memory tenant outline (hierarchy ops, level-aware ranges).
- `resolver.py` — `MemberSelection` → exact ordered members. No fuzzy
  substitution; unknown members surface candidates.
- `validation.py` — schema/application/axis/selection/display/performance/security/
  deployment layers → `ValidationReport`.
- `preview.py` — deterministic grid preview.
- `renderer.py` — safe XML via ElementTree (stable ordering, no string concat),
  JSON, Markdown.
- `packager.py` — reproducible ZIP (fixed timestamps, sorted entries) + manifest +
  SHA-256 checksums. Same spec + renderer version → byte-identical package.
- `parser.py` — XML/definition → `FormSpecification` (round-trips `render_xml`
  exactly; enables reference-form cloning).

### Context engine (`app/context`)

Quick/deep context via the connector; each section is marked
`complete | partial | derived | unavailable | notRequested` honestly. Records are
persisted for **identifier-first** local retrieval (exact → case-insensitive →
alias → prefix → substring), each carrying full provenance. Portable
`.epwcontext` packages (ZIP with manifest + checksums, no secrets) for sharing.

**Application snapshot upload** (`app/context/snapshot.py`): an LCM/Migration
snapshot zip (what `exportSnapshot` + `downloadFile` produce) can be uploaded in
chat or on the Context tab. It is parsed deterministically and in-memory only —
application, cubes and dimensions are discovered from the zip's own `Export.xml`
and folder manifest, never assumed — extracting what the REST/EPM Automate
interfaces cannot supply: full member hierarchies with formulas, Calculation
Manager rule bodies and runtime prompts, substitution/user variables,
form/dashboard references, FDMEE inventory. The result is layered **on top of**
the connector-built context as a new provenance-tracked version
(`mode: hybrid`, or `snapshot` when standalone); every snapshot-derived record
carries `source: "snapshot"`, and prior versions are never mutated.

### AI layer (`app/ai`)

Provider-independent interface: model listing, connection test, streaming, tool
calling, structured output, cancellation, token usage, normalized errors. The
**Mock** provider is deterministic and needs no network, so the app is fully
usable offline; Anthropic / OpenAI-compatible (OpenAI, OpenRouter, Ollama) /
Gemini adapters are used when configured in the UI.

### Agent (`app/agent`)

- `intent.py` — deterministic router (slash commands + natural language).
- `tools.py` — narrow typed tool registry with operation classes.
- `skills/` — resumable workflows: `/forms`, `/rules`, `/context`,
  `/architecture`, `/deploy`, `/rollback`, `/search`, `/explain`, `/compare`,
  `/help`, plus a chat fallback.
- `deploy.py` — the deployment pipeline (validate → package → backup → import →
  poll → **verify** → record).
- `orchestrator.py` — selects a skill (respecting an active workflow), runs it
  while streaming process steps / tokens / typed blocks over SSE, persists the
  assistant message and workflow state.

### Cube Architecture visualizer (`app/architecture`)

Deterministic `CubeArchitecture`, form-coverage, cell-intersection,
cube-comparison, cross-dimensional sizing, and hierarchy inspection — all derived
from real metadata (unknown dimensions are labelled `custom`, never guessed).

## Streaming

`POST /api/conversations/{id}/messages` persists the (redacted) user message, then
returns `text/event-stream`. The orchestrator emits `title`, `process`, `token`,
`block`, `messageSaved`, `done`. Blocks carry a stable `id`; the client upserts by
id so a single progress block updates in place.

## Persistence

SQLite under one local data dir (Docker named volume `epmw-data`). Alembic
migrations; foreign keys enforced. Projects own conversations, environments,
contexts, artifacts, deployments, rule executions, settings, audit records, and
workflow state.
