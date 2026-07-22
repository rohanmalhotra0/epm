# EPM Wizard — Narrated Browser Agent (Chrome MV3 extension)

A **scaffold** for the Phase 4 headline feature (see `docs/OPENCLAW_PLAN.md`):
a Manifest V3 Chrome extension that drives a web app's UI while **narrating each
step in a side panel** — "Claude-for-Chrome, but domain-specific," targeting
Oracle EPM Cloud (Planning / Financial Consolidation).

It is a **real, loadable extension** that runs the full
**plan → act → observe → narrate** loop against the EPM Wizard backend. It is
**not** a hardened Oracle-specific agent — the genuinely hard Oracle-UI
heuristics are stubbed behind clean seams and marked below.

No build step. Plain ES modules + one classic content script. Load it as-is.

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

4. In the panel: open **⚙ Settings**, set the **Backend URL**
   (`http://localhost:8000` by default) and optionally an EPM Wizard
   **Project id** (selects that project's active AI provider). Optionally tick
   **Speak narration** for Web-Speech TTS.

5. Type a **goal** (e.g. *"Open the Actuals data form and set Scenario to
   Forecast"*) and press **Start**. Watch/pause/stop the run.

> **Permissions note:** the manifest requests `debugger` for the CDP
> screenshot/coordinate fallback. Chrome shows a *"… is debugging this browser"*
> banner while attached — expected for the scaffold (see stubs below).

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
  yet evaluated against a real tenant. Safety gating (don't click Deploy-to-PROD)
  is a prompt instruction only, not an enforced guardrail.
- **Auth / session.** The extension assumes you're already logged into the EPM
  tab; it does not handle Oracle SSO, session timeouts, or re-auth prompts.

Nothing here has been run against a live Oracle EPM tenant — validate against a
real Planning UI before trusting any driving behaviour.
