# Improvement Ideas

**Status update (2026-07-19):** most items below are now implemented on this
branch — theme toggle, command palette + global search, keyboard shortcuts,
first-run tour, message copy/regenerate, conversation rename/pin/archive/
delete, Skills page, metadata explorer, artifact visual diff, deployment
script export, Ollama preset + model discovery, project export/import
bundles, DB backups + rotation, disk usage panel, diagnostics log viewer,
and impact analysis. Still open: the bigger bets (Chrome extension, local
vector retrieval, new artifact types, Playwright E2E), drag-and-drop
attachments, user-defined skills, soft-delete grace period, and eval corpus
growth.

A brainstorm of possible additions and improvements. Everything here respects
the core constraint: **EPM Wizard runs entirely locally**. No hosted services,
no cloud infrastructure. Optional external AI providers only.

Grouped by area, with quick wins called out at the end.

---

## 1. Chat & UX

- **Global search (SQLite FTS5).** Full-text search across conversations,
  messages, and artifacts. SQLite's FTS5 keeps it 100% local and fast. A
  `Ctrl+K` command palette could combine search with quick actions
  ("new form", "open settings", "switch project").
- **Conversation management.** Rename, pin, tag, archive, and delete
  conversations from the sidebar. Right now the sidebar is a flat list.
- **Message actions.** Copy-as-markdown, regenerate last response, edit &
  resend a prompt, and "branch from here" to fork a conversation.
- **Theme toggle.** Carbon ships g10 (light) and g90/g100 (dark) themes; the
  app currently has no theme switching. A toggle in the header persisted to
  local settings would be cheap and high-impact.
- **Keyboard shortcuts.** New chat, focus composer, toggle sidebar,
  approve/reject pending preview cards without the mouse.
- **First-run tour.** Demo Mode already makes the app usable instantly; a
  short dismissible onboarding overlay ("try these prompts") would help new
  users discover forms, the visualizer, and `/help`.
- **Drag-and-drop attachments.** Drop a CSV/Excel metadata export into the
  chat and have it parsed locally (openpyxl) into context — no upload to any
  service.

## 2. EPM feature depth

- **More artifact types.** Forms, rules, and reports exist. Natural next
  targets, in rough order of value: substitution variables, smart lists,
  member formulas, valid intersections, task lists, data maps, dashboards.
  Each fits the existing pattern: NLU → Pydantic spec → validation → preview
  → approval → deterministic render → deploy.
- **Rule-edit NLU parity.** Forms support conversational edits
  (`move Entity to POV`, `hide March`). Rules and reports could get the same
  edit verbs.
- **Metadata explorer page.** A browsable tree of cubes → dimensions →
  members outside the chat, powered by the existing context store. The
  Cube Architecture visualizer proves the data is there; a persistent
  explorer page makes it navigable.
- **Impact analysis ("what references X?").** Before renaming or removing a
  member, list every stored form/rule/report spec that references it. All
  specs are local and structured, so this is a pure local query.
- **Batch/template creation.** "Create one input form per quarter" style
  fan-out, plus a local template library of previously approved specs that
  can be re-instantiated with different members.
- **Visual artifact diff.** The compare skill exists; a side-by-side visual
  diff of two form versions (grid layout, added/removed rows) in the
  artifacts panel would make reviews much faster.
- **EPM Automate script export.** For every deployment, offer a downloadable
  `.sh`/`.ps1` of the equivalent EPM Automate commands. Useful for users who
  must run changes through a controlled change process — and it's pure
  deterministic codegen.
- **Snapshot management.** Local, scheduled tenant snapshot export via the
  existing EPM Automate runner, with retention/rotation. Backups stay on the
  user's disk.

## 3. Local-first infrastructure

- **Project export/import bundle.** One `.zip` containing project settings,
  conversations, context versions, artifacts, and deployment history —
  checksummed, importable on another machine. This is the local-first answer
  to "sync": explicit, portable backups instead of a cloud.
- **Local vector retrieval (optional).** Context retrieval is
  identifier-first today. An optional embedding layer using `sqlite-vec` and
  a small local embedding model (via Ollama, already supported by the
  OpenAI-compatible provider) would improve fuzzy questions like "which
  forms deal with headcount?" without any external calls.
- **Ollama presets in Settings.** The backend already speaks to Ollama
  (`app/ai/openai_compat.py`); Settings could surface a "Local model
  (Ollama)" preset with model auto-discovery from `/models`, so fully
  offline AI is a two-click setup instead of a config exercise.
- **Automatic DB backup.** Rotate timestamped copies of the SQLite database
  on startup or on a schedule; add a restore picker in Settings.
- **Disk usage & retention panel.** Show artifact/package sizes per project
  in Diagnostics, with cleanup controls (prune old packages, old context
  versions).

## 4. The Chrome extension idea (from ideas.md)

Feasible while staying local: the extension talks only to
`http://127.0.0.1:8000`. Notes:

- The backend would need CORS allowances for the extension origin plus a
  locally generated token so other local software can't hit the API.
- Screenshot-based context (explain the form on screen) requires a
  vision-capable provider; works with Anthropic/OpenAI keys, or locally with
  a vision model on Ollama (e.g. llava) — the provider abstraction already
  supports both paths.
- A smaller first step with most of the value: an "Explain this artifact"
  flow where the user pastes an exported form/rule XML or an Excel file and
  the existing parser + explain skill handle it. The extension then becomes
  a thin capture layer on top of an already-working backend feature.
- Excel macro analysis is doable offline with `openpyxl` + `oletools` (VBA
  extraction), feeding the extracted logic to the explain/forms skills.

## 5. Skills system (from ideas.md)

- **Skills page in the UI.** The registry already knows all 14 skills;
  `/help` renders them in chat. A dedicated page listing each skill with
  description, example prompts, and a "try it" button is mostly UI work.
- **User-defined skills.** A constrained local format (YAML/Markdown:
  trigger phrases + prompt template + allowed tools) loaded from a local
  directory. Keep them within the existing safety model: user skills can
  propose specs but never bypass validation, approval, or the connector
  boundary.

## 6. Quality & developer experience

- **Grow the eval corpus.** The NLU eval harness (`app/eval`) is a real
  asset; expanding it (report NLU, edit operations, adversarial phrasing)
  and gating CI on coverage/exact-rate regressions would protect quality as
  skills grow.
- **Playwright E2E against Demo Mode.** Demo Mode is deterministic, which
  makes it ideal for end-to-end tests: create form → edit → approve →
  deploy → verify, all headless and offline.
- **Log viewer in Diagnostics.** Surface recent backend logs (already
  structured via `app/logging.py`) in the Diagnostics panel so users don't
  need `docker compose logs`.
- **Undo / soft-delete.** Deleting a conversation or artifact should be
  recoverable for a grace period.

---

## Suggested quick wins

Small, high-value, low-risk — good next sessions:

1. Theme toggle (Carbon dark mode).
2. Conversation rename/pin/delete.
3. Skills page in the UI.
4. Ollama preset + model auto-discovery in Settings.
5. Global search with SQLite FTS5.
6. Project export/import bundle.

## Bigger bets

- Chrome extension (thin capture layer over existing backend).
- Local vector retrieval for context.
- New artifact types (substitution variables first — smallest spec).
- Playwright E2E suite on Demo Mode.

## Already done (from ideas.md)

- Text-to-speech: implemented (`frontend/src/tts/`).
- Speech-to-text: implemented (`frontend/src/stt/`).
- Skills overview: partially — `/help` in chat; no dedicated UI page yet.
