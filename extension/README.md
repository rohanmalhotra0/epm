# EPM Wizard — Narrated Browser Agent (Chrome MV3 extension)

A **scaffold** for the Phase 4 headline feature (see `docs/OPENCLAW_PLAN.md`):
a Manifest V3 Chrome extension that drives a web app's UI while **narrating each
step in a side panel** — "Claude-for-Chrome, but domain-specific," targeting
Oracle EPM Cloud (Planning / Financial Consolidation).

It is a **real, loadable extension** that runs the full
**plan → act → observe → narrate** loop against the EPM Wizard backend. It is
**not** a hardened Oracle-specific agent — the genuinely hard Oracle-UI
heuristics are stubbed behind clean seams and marked below.

No build step. Plain ES modules + two classic content scripts. Load it as-is.

**New in 0.3.0**

- **Workbook inspector.** The panel's **Inspect workbook** tab opens an Excel
  file and shows *everything* — every VBA macro's source, the auto-run hooks
  (`Workbook_Open`, `Auto_Open`, `Worksheet_Change` …), sheets, named ranges,
  tables, pivots, charts and external data connections. Parse-only: macros are
  read, never run. See _Inspect a workbook_ below.

**In 0.2.0**

- **Seamless site integration.** Launched from the EPM Wizard web app, the
  extension auto-configures (backend URL + project id + goal) and opens its
  panel — no manual setup. See _Site integration_ below.
- **Enforced production-safety gate.** Destructive actions and any write on a
  production tenant are *held* for explicit human approval before they execute —
  a hard gate, not a prompt hint. See _Safety gate_ below.
- **Store-ready packaging.** Icons, a privacy policy, a listing pack, and a
  packaging script. See _Publishing_ below.

> **Honesty note:** nothing here has been run against a live Oracle EPM tenant.
> The Oracle-specific grounding (iframes, canvas/JET grids) is still stubbed.
> Validate against a real Planning UI before trusting any driving behaviour, and
> read the safety caveats before publishing publicly.

---

## Load unpacked (dev)

1. Start the backend so the agent loop has an endpoint:
   ```bash
   cd backend
   .venv/bin/python -m uvicorn app.main:app --reload --port 8000
   ```
   With no provider configured it uses the deterministic **MockProvider** — the
   loop still runs end to end (it will mostly take `screenshot` fallback steps,
   since the mock returns prose, not JSON actions). Configure a real
   OpenAI-compatible / vision provider in the app's Settings for genuine driving.

2. Open `chrome://extensions`, enable **Developer mode**, click
   **Load unpacked**, and select this `extension/` directory.

3. Open the target page (an Oracle EPM Planning tab, or any web page to try the
   mechanics). Click the extension's toolbar icon to open the **side panel**.

4. In the panel: open **⚙ Settings** and click **Sign in to EPM Wizard**. The
   extension ships pointed at the hosted app
   (`https://epmw-auth.fly.dev`) — nothing to configure. To run against a
   self-hosted or local backend (`http://localhost:8000`) instead, open
   **Advanced** and set the **Server URL**; you can also add an EPM Wizard
   **Project id** (selects that project's active AI provider) there. Optionally
   tick **Speak narration** for Web-Speech TTS.

5. Type a **goal** (e.g. *"Open the Actuals data form and set Scenario to
   Forecast"*) and press **Start**. Watch/pause/stop the run.

> **Permissions note:** the manifest requests `debugger` for the CDP
> screenshot/coordinate fallback. Chrome shows a *"… is debugging this browser"*
> banner while attached — expected for the scaffold (see stubs below).

---

## Site integration (zero-setup launch)

Launched from the EPM Wizard web app, the extension configures itself — no
typing a backend URL or project id.

- The app has a **Browser Agent** page (sidebar → *Browser Agent*, route
  `/agent`). It detects whether the extension is installed and offers a one-click
  **Launch agent on the current tab**.
- On launch, the app hands the extension its **backend URL** (the app's own
  origin, so the agent authenticates with your existing signed-in session) and
  your **current project id**, plus an optional **goal** to prefill.
- The transport is a content script (`content/site-bridge.js`) that runs only on
  the EPM Wizard origins (see `manifest.json` matches) and relays `window`
  CustomEvents to the service worker. The page never needs the extension's
  (unstable) id. Contract: `common/protocol.js` → `SITE`; app side:
  `frontend/src/agent/extensionBridge.ts`.

Opening the side panel programmatically needs a user gesture the relayed message
may not carry; if Chrome declines, the config is already saved and one click on
the toolbar icon opens the fully-wired panel.

To point the bridge at other origins, edit the second `content_scripts` entry in
`manifest.json` and `SITE_ORIGINS` in `common/protocol.js`.

## Safety gate (enforced)

The system prompt *asks* the model not to fire destructive Oracle actions. That
is advice, not a guarantee. `background/guardrails.js` turns it into a **hard
gate**: before every action executes, the service worker consults the guardrail
and, when it flags one, **holds** the action until you approve or skip it in the
panel. Nothing destructive fires on the model's word alone.

Two independent triggers:

1. **Destructive target** — the element about to be clicked/typed has an
   accessible name matching a destructive verb (deploy, delete, clear, drop,
   *run rule*, *refresh database*, push/promote/publish, consolidate, …). Held
   everywhere.
2. **Production context** — the tab looks like a production tenant (URL/title
   contains `prod`/`production`/`live`/…). On PROD, **any** write (click/type),
   including blind coordinate clicks whose target can't be read, is held.

Read-only actions (scroll, wait, screenshot, navigate, done) are never gated.
The gate is on by default and can be toggled in the panel's **⚙ Settings**
(*Enforce production-safety gate*). Tune the verb/PROD patterns at the top of
`guardrails.js`.

> This is a genuine guardrail but not a formal proof of safety: detection is by
> accessible-name and URL heuristics. Keep it on, and still supervise real runs.

## Inspect a workbook

The panel's **Inspect workbook** tab answers "what's in this Excel file and what
makes it move?" — without opening Excel, and without running anything.

- Switch to **Inspect workbook**, then drop (or pick) an `.xlsm` / `.xlsx` /
  `.xlsb` / `.csv`. The file is POSTed to the backend's stateless
  `POST /api/spreadsheet/inspect` (`backend/app/api/routes_spreadsheet.py`);
  nothing is written to the database.
- You get: a one-line summary; **every VBA macro's full source** (collapsible
  per module); the **auto-run triggers** that fire on their own
  (`Workbook_Open`, `Auto_Open`, `Worksheet_Change`, …); a per-sheet table
  (visibility, dimensions, formula/table/chart counts); named ranges; tables;
  pivot tables; charts; and external data connections (redacted).
- **Why a file, not a live desktop Excel session?** VBA source only exists
  inside the workbook file — no browser API (nor Microsoft's own Office.js
  add-in API) can read a running workbook's macro code. So reading macros
  *requires* the file; that's inherent, not a limitation of this tool.

Engine: `backend/app/spreadsheet/inspect.py` (VBA via `oletools`, structure via
`openpyxl` + direct OOXML-zip parsing for pivots/connections). It reuses the
same parse-only, redaction-first guarantees as the rest of the package —
macros are never compiled, interpreted or executed.

## Publishing (Chrome Web Store)

Store-readiness lives alongside the code:

- **Icons** — `icons/icon{16,32,48,128}.png`, referenced by `icons` and
  `action.default_icon`.
- **Privacy policy** — `PRIVACY.md` (host it publicly; paste the URL in the
  listing).
- **Listing pack** — `STORE_LISTING.md`: summary, description, single-purpose
  statement, per-permission justifications, data-usage disclosures, and a
  pre-submission checklist.
- **Package** — `scripts/package.sh` → `dist/epm-wizard-extension-<version>.zip`
  (manifest at the archive root; docs/scripts excluded).

```bash
./scripts/package.sh   # build the upload zip
```

Read the review-risk note at the top of `STORE_LISTING.md` first: the `debugger`
+ broad-host permissions and UI-driving behaviour draw scrutiny, and this has not
been validated on a live tenant.

---

## Architecture

Three MV3 contexts, mirroring Anthropic's own extension pattern and the research
in `OPENCLAW_PLAN.md` §6:

```
 ┌──────────────┐   Port (epmw-panel)   ┌──────────────────────┐
 │  Side panel  │ ───────────────────►  │   Service worker     │
 │ (narration   │ ◄─────────────────── │  (orchestration +    │
 │  UI, TTS)    │   state/token/step   │   CDP + backend conn) │
 └──────────────┘                       └───────┬──────┬───────┘
                                                 │      │
                          chrome.tabs.sendMessage │      │ chrome.debugger (CDP)
                                                 ▼      ▼
                                    ┌───────────────┐  Page.captureScreenshot
                                    │ Content script│  Input.dispatchMouseEvent
                                    │ (a11y snapshot│
                                    │  + ref actions)│        │  SSE
                                    └───────────────┘        ▼
                                                    POST /api/agent/step (FastAPI)
```

- **`background/service-worker.js`** — owns the agent session and the run loop
  (`plan→act→observe→narrate`), routes messages between panel and content
  script, holds the backend connection, and attaches the CDP debugger for the
  screenshot/coordinate fallback. Session state is persisted to
  `chrome.storage.session` after every step, so an MV3 worker restart lands the
  run in **PAUSED** (history preserved) rather than losing it.
  - `background/backend.js` — hand-rolled SSE reader over `fetch` (EventSource
    isn't available in a service worker).
  - `background/cdp.js` — `chrome.debugger` attach/detach, `Page.captureScreenshot`,
    `Input.dispatchMouseEvent`.
- **`content/content-script.js`** — builds the **accessibility-tree / DOM
  snapshot with stable integer `ref` ids** (the *primary* grounding — the agent
  targets `ref=42`, not pixels) and executes low-level actions **by ref**
  (click / type / scroll). Self-contained classic script (content scripts can't
  be ES modules via the manifest).
- **`sidepanel/`** — the "watch it work" chat/narration UI: streams tokens +
  steps, shows the current action, Start/Pause/Resume/Stop, and optional
  **SpeechSynthesis** voice narration (mirrors the main app's Web Speech TTS —
  no backend TTS).
- **`common/protocol.js`** — shared message-type constants (imported by the SW
  and panel; the constants are mirrored by hand in the classic content script).

### Grounding strategy

1. **Primary — accessibility tree with `ref` ids.** The content script walks the
   DOM for interactive/labelled elements, assigns stable refs, and reports role
   / name / value / rect. Actions reference elements by `ref`.
2. **Fallback — screenshot + coordinates (vision).** When the tree is empty or
   the model asks for a `screenshot`, the SW captures via CDP and attaches it to
   the observation as a data URL. The backend routes screenshot-bearing turns to
   the provider's **vision** role model (`AIMessage.images` →
   `app/ai/openai_compat.py`). Coordinate clicks go through
   `Input.dispatchMouseEvent`.

### Backend contract

`POST /api/agent/step` (SSE) — see `backend/app/api/routes_agent.py`. Request:
`{ goal, observation: { url, title, nodes, screenshot? }, history[], projectId? }`.
Stream: `start` → `token`* → `step` → `done`. The `step` payload is
`{ index, narration, action, done }`; `action.type ∈ {click,type,scroll,navigate,
screenshot,wait,done}`, grounded by `ref` (preferred) or `x/y`. A non-streaming
twin lives at `POST /api/agent/step/once`.

---

## What's scaffolded vs. what needs Oracle-specific hardening

**Works now (scaffold):**
- Loads as an unpacked MV3 extension; side panel opens from the toolbar icon.
- Full plan→act→observe→narrate loop over SSE, with Start/Pause/Resume/Stop.
- Accessibility-tree snapshot with stable `ref` ids; click/type/scroll by ref.
- CDP screenshot capture + coordinate-click fallback.
- Vision routing (screenshots → `AIMessage.images` → vision role model).
- Streaming narration UI + optional Web-Speech voice.
- MV3 worker-restart resilience (state persisted; resume from PAUSED).
- **Enforced production-safety gate** — destructive / PROD-write actions are
  held for explicit approval before executing (`background/guardrails.js`).
- **Zero-setup site integration** — the EPM Wizard web app configures and
  launches the agent (`content/site-bridge.js` ↔ `frontend/src/agent/`).
- **Store-ready** — icons, privacy policy, listing pack, packaging script.

**Stubbed / TODO — the multi-week Oracle ADF/JET hardening (~6–10 wks per §6):**
- **iframes.** Oracle EPM renders forms/task-flows in nested iframes. The
  content script snapshots only the **top document** (`all_frames:false`). Real
  coverage needs `all_frames:true`, per-frame `ref` namespacing, frame
  coordinate offsets, and cross-frame focus tracking.
  *(Seam: `content/content-script.js` `buildSnapshot`.)*
- **Canvas/JET data grids.** ADF/JET grids paint to `<canvas>` with no ARIA;
  their rows/cells never enter the accessibility tree. The agent must lean on
  the screenshot + coordinate path — the vision model's grid-cell grounding is
  the hard, un-built part.
- **Selector heuristics.** No mapping yet from Oracle's `af:`/`oj-` component
  roles, virtualized rows, or shadow DOM to stable refs; the accessible-name
  computation is a simplified accname, not the full ARIA algorithm.
  *(Seam: `roleOf` / `accessibleName` / `shouldInclude`.)*
- **Keyboard input by coordinate.** `Input.dispatchKeyEvent` isn't wired —
  typing works only through the content script by ref; the canvas-grid typing
  path is unimplemented. *(Seam: `background/cdp.js`.)*
- **CDP hardening.** Per-step naive attach/detach and the debugging banner; a
  real build keeps one session attachment, handles `onDetach` (user opens
  DevTools) by re-attaching, and may prefer `chrome.tabs.captureVisibleTab` for
  banner-free screenshots. *(Seam: `background/cdp.js`.)*
- **Agent prompt / action model.** The system prompt and `Action` schema live
  backend-side (`backend/app/agent/computer_use/`). EPM-specific compound
  gestures (POV member picker, form save workflow, drill-through) are *composed*
  from the primitive actions by the model — not yet encoded as skills, and not
  yet evaluated against a real tenant. Note: destructive/PROD actions are now
  **held by an enforced client-side gate** (`guardrails.js`) — but that gate is
  heuristic (accessible-name + URL matching), not a formal safety proof.
- **Auth / session.** The extension assumes you're already logged into the EPM
  tab; it does not handle Oracle SSO, session timeouts, or re-auth prompts.

Nothing here has been run against a live Oracle EPM tenant — validate against a
real Planning UI before trusting any driving behaviour.
