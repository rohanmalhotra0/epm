# EPM Wizard — Narrated Browser Agent (Chrome MV3 extension)

A **scaffold** for the Phase 4 headline feature (see `docs/OPENCLAW_PLAN.md`):
a Manifest V3 Chrome extension that drives a web app's UI while **narrating each
step in a side panel** — "Claude-for-Chrome, but domain-specific," targeting
Oracle EPM Cloud (Planning / Financial Consolidation).

It is a **real, loadable extension** that runs the full
**plan → act → observe → narrate** loop against the EPM Wizard backend. The
Oracle-aware adapter covers nested frames, open Shadow DOM, JET/ADF semantics,
virtualized grids, and canvas fallback; an installed-extension harness exercises
those paths against deterministic fixtures.

No build step. Plain ES modules + two classic content scripts. Load it as-is,
or download the packaged ZIP from the public EPM Wizard landing page at
`/epm-wizard-extension.zip`.

**New in 0.6.4**

- **Reliable visual actions.** Vision responses use constrained action JSON,
  stale or invented refs are rejected before execution, and one bounded
  correction attempt can turn a visible screenshot target into a coordinate
  click instead of stopping early.
- **Truthful terminal status.** A grounding failure is shown as blocked/error;
  it is no longer displayed with a green `goal complete` result.

**New in 0.6.3**

- **Screenshot-loop protection.** A malformed visual-model response can no
  longer become an endless series of screenshots; the run stops with an
  explicit grounding error after the image has already been supplied.
- **Oracle grid scrolling.** Scroll actions can target a grid/list ref, report
  the actual movement, and fall back to a visible internal scroll region when
  Oracle keeps the document itself fixed.
- **Accurate connection errors.** Pause and Stop no longer misreport their
  intentional request cancellation as a backend outage.

**New in 0.6.2**

- **Reliable exact-origin access from the side panel.** When Chrome withholds
  `tabs.Tab.url`, EPM Wizard resolves only the debugger target matching the
  active tab ID, discards the other target metadata, and requests the exact
  current HTTPS origin. The non-interrupting Chrome toolbar fallback now
  explains where its **Allow** control actually appears.

**New in 0.6.1**

- **Correct Chrome permission flow.** Exact current-origin host grants now
  validate hidden, malformed, and restricted tab URLs before constructing a
  match pattern, with Chrome's address-bar host request used when the URL is not
  yet exposed.
- **Reliable canvas control.** Chrome's non-optional `debugger` permission is
  declared correctly at install time, while trusted input remains off by
  default and detaches on disable, pause, stop, completion, and worker unload.

**New in 0.6.0**

- **Minimum-by-default host access.** Only the EPM Wizard bridge origins are
  pre-granted. Target-site access is requested for the exact current origin
  after a direct user gesture. Chrome does not permit `debugger` as an optional
  permission, so it is declared at install time; trusted canvas control remains
  off in EPM Wizard until the user enables it.
- **Secure origin binding.** Bridge messages are checked against Chrome's
  sender document, hosted sites may select only bound backend origins silently,
  and self-hosted origin changes require confirmation in extension-owned UI.
  Backend-scoped credentials are cleared whenever the origin changes.
- **Oracle-aware page adapter.** Stable refs span nested frames; the snapshot
  traverses open Shadow DOM, recognizes JET/ADF components and virtualized
  grids, and describes canvas bounds for coordinate fallback.
- **Action outcomes and a faster loop.** Every attempted action records its
  success, failure, guardrail disposition, and duration. History and workbook
  context are bounded, page settling replaces fixed sleeps, and screenshots are
  compressed, resized, hashed, and skipped when a duplicate is detected.
- **Installed-extension E2E.** A persistent Chromium harness verifies
  user-triggered injection, nested frames, Shadow DOM, JET, virtualized grids,
  screenshots, canvas clicks, origin-spoof rejection, action-result history,
  keyboard use, and critical accessibility checks.

**New in 0.5.0**

- **Excel context for the AI agent.** Inspecting a workbook now automatically
  attaches its redacted, parse-only context to the browser agent. Every agent
  step can reason over extracted VBA source, auto-run hooks, formulas, sheet
  structure and samples, named ranges, tables, pivots, charts and connections
  while it works in EPM. The Agent tab shows the active workbook and provides a
  one-click **Clear** action.
- **Prompt-injection boundary.** Cells, formulas, connection text, VBA comments
  and VBA strings are explicitly treated as untrusted reference data, never as
  instructions to the agent.

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

> **Validation note:** the Oracle adapter is covered by unit tests and an
> installed-extension fixture suite, but nothing here has been run against a
> live Oracle EPM tenant. Validate against a real Planning UI before trusting
> production driving behaviour, and read the safety caveats before publishing.

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

4. Complete the panel's two-step access flow:
   1. **Sign in with Google**. The button opens the protected EPM Wizard app,
      which runs the same OAuth flow as the website. Return to the panel when
      the sign-in completes; it verifies the website session automatically.
   2. **Sign in to Oracle EPM** with the same form as the website (username and
      password or OCI IAM OAuth client credentials). The extension forwards the
      secret once to EPM Wizard and never stores it in extension storage.
      Selecting **Remember** uses EPM Wizard's encrypted local secret store.

   The extension ships pointed at the hosted app
   (`https://epmw-auth.fly.dev`) — nothing to configure. To run against a
   self-hosted or local app instead, expand **Use a self-hosted or local EPM
   Wizard** on the first sign-in screen and set the **Server URL**.

5. Type a **goal** (e.g. *"Open the Actuals data form and set Scenario to
   Forecast"*) and press **Start**. Watch/pause/stop the run.

> **Permissions note:** normal screenshots use `chrome.tabs.captureVisibleTab`.
> Access to the current HTTPS target site and any custom backend origin is
> requested from the direct Grant/Save/Approve click that needs it. Plain HTTP
> access is limited to loopback development. Chrome requires `debugger` to be
> accepted at install time, but EPM Wizard's trusted canvas control is off by
> default and detaches when disabled, paused, stopped, or unloaded. Chrome shows
> a *"… is debugging this browser"* banner only while attached.

---

## Site integration (zero-setup launch)

Launched from the EPM Wizard web app, the extension configures itself — no
typing a backend URL or project id.

- The app has a **Browser Agent** page (sidebar → *Browser Agent*, route
  `/app/agent`). It detects whether the extension is installed and offers a one-click
  **Launch agent on the current tab**.
- On launch, the app hands the extension its **backend URL** (the app's own
  origin), your **current project id**, and an optional **goal** to prefill.
  The service worker derives the actual page origin from Chrome rather than
  trusting event data. Hosted page/backend pairs are allowlisted; an unbound
  self-hosted backend opens an extension-owned confirmation dialog before any
  config is changed.
  The extension still verifies both the website OAuth session and a live Oracle
  EPM connection before unlocking agent controls.
- The transport is a content script (`content/site-bridge.js`) that runs only on
  the EPM Wizard origins (see `manifest.json` matches) and relays `window`
  CustomEvents to the service worker. The page never needs the extension's
  (unstable) id. Contract: `common/protocol.js` → `SITE`; app side:
  `frontend/src/agent/extensionBridge.ts`.

Opening the side panel programmatically needs a user gesture the relayed message
may not carry; if Chrome declines, the config is already saved and one click on
the toolbar icon opens the fully-wired panel.

To point the bridge at another product origin, add the exact origin to the
`content_scripts` entry in `manifest.json` and bind it explicitly in
`background/origin-policy.js`.

## Safety gate (default-on)

The system prompt *asks* the model not to fire destructive Oracle actions. That
is advice, not a guarantee. When enabled, `background/guardrails.js` turns it
into an enforced gate: before every action executes, the service worker consults the guardrail
and, when it flags one, **holds** the action until you approve or skip it in the
panel. Nothing destructive fires on the model's word alone.

Independent triggers:

1. **Destructive target** — the element about to be clicked/typed has an
   accessible name matching a destructive verb (deploy, delete, clear, drop,
   *run rule*, *refresh database*, push/promote/publish, consolidate, …). Held
   everywhere.
2. **Production context** — the connected environment classification is
   authoritative when available, with URL/title patterns only as a fallback.
   On PROD, **any** click/type write is held.
3. **Unknown coordinate write** — a coordinate-only click/type cannot be tied
   to a readable target and is held in every environment.
4. **Cross-origin navigation** — navigating away from the current origin is
   held before the target page loads.

Scroll, wait, screenshot, same-origin navigation, and done remain read-only.
The gate is on by default and can be toggled in the panel's **⚙ Settings**
(*Enforce production-safety gate*). Tune the verb/fallback PROD patterns at the
top of `guardrails.js`.

> This is a genuine guardrail but not a formal proof of safety: detection is by
> accessible-name plus environment metadata/URL heuristics. Keep it on, and
> still supervise real runs.

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
- Once inspection finishes, a bounded AI digest is attached automatically.
  Switch back to **Agent**, enter a goal such as _"Use this workbook to recreate
  the forecast form in EPM"_, and the agent receives that workbook context on
  every step. The active filename and extraction counts stay visible until you
  click **Clear** or inspect a different workbook.
- The AI digest prioritizes all VBA extracted under the parser's 200,000
  character safety cap, then includes workbook structure, formulas and sampled
  rows up to a 300,000 character session limit. If the latter limit is reached,
  the panel says so rather than silently implying the whole workbook fit.
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

Read the review-risk note at the top of `STORE_LISTING.md` first: the optional
`debugger` + broad-host permissions and UI-driving behaviour draw scrutiny, and
this has not been validated on a live tenant.

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
  script, holds the backend connection, aggregates frame snapshots, and uses
  opt-in CDP input only for coordinate-grounded controls. Session state is
  persisted to
  `chrome.storage.session` after every step, so an MV3 worker restart lands the
  run in **PAUSED** (history preserved) rather than losing it.
  - `background/backend.js` — hand-rolled SSE reader over `fetch` (EventSource
    isn't available in a service worker).
  - `background/cdp.js` — user-controlled `chrome.debugger` attachment,
    `Page.captureScreenshot`, `Input.dispatchMouseEvent`, keyboard events, and
    Unicode text insertion.
- **`content/content-script.js`** — builds the **accessibility-tree / DOM
  snapshot with stable integer `ref` ids** across accessible frames (the
  *primary* grounding — the agent targets `ref=42`, not pixels), recognizes
  Oracle JET/ADF/virtual-grid semantics, traverses open Shadow DOM, and executes
  low-level actions by ref or coordinate. It is injected only after Start.
- **`sidepanel/`** — the "watch it work" chat/narration UI: streams tokens +
  steps, shows the current action, Start/Pause/Resume/Stop, and optional
  **SpeechSynthesis** voice narration (mirrors the main app's Web Speech TTS —
  no backend TTS).
- **`common/protocol.js`** — shared message-type constants (imported by the SW
  and panel; the constants are mirrored by hand in the classic content script).

### Grounding strategy

1. **Primary — accessibility tree with `ref` ids.** The adapter walks accessible
   nested frames and open Shadow DOM, assigns locally stable refs that the
   service worker namespaces globally, and reports role/name/value/rect plus
   Oracle component and frame metadata. Actions reference elements by `ref`.
2. **Fallback — screenshot + coordinates (vision).** When the tree is empty,
   ARIA-poor, canvas-backed, or the model requests a screenshot, the worker
   captures a bounded JPEG with `captureVisibleTab` (CDP fallback when granted),
   records image/viewport scaling, and avoids resending a duplicate. The backend
   routes screenshot-bearing turns to its vision model. Optional CDP input
   handles real canvas mouse and text/keyboard events; without that permission,
   the frame adapter reports its best-effort pointer result.

### Backend contract

`POST /api/agent/step` (SSE) — see `backend/app/api/routes_agent.py`. Request:
`{ goal, observation: { url, title, nodes, viewport?, screenshot?,
screenshotMeta? }, history[], projectId?, workbookContext? }`.
Stream: `start` → `token`* → `step` → `done`. The `step` payload is
`{ index, narration, action, done }`; after execution the extension adds
`result: { ok, detail, gate, durationMs }` to history. `action.type ∈
{click,type,scroll,navigate,screenshot,wait,done}`, grounded by `ref`
(preferred) or `x/y` with explicit CSS/image coordinate space. A non-streaming
twin lives at `POST /api/agent/step/once`.

---

## Implemented and remaining validation

**Implemented:**

- Loads as an unpacked MV3 extension; side panel opens from the toolbar icon.
- Full plan→act→observe→narrate loop over SSE, with Start/Pause/Resume/Stop.
- Accessibility snapshots with stable refs across accessible nested frames and
  open Shadow DOM; click/type/scroll by ref.
- JET/ADF semantic metadata, virtualized-grid state, canvas bounds, and
  ARIA-poor fallback signals.
- Bounded visible-tab screenshots with image/viewport metadata, hashing, and
  duplicate suppression; optional CDP screenshot fallback.
- Optional CDP canvas click, Unicode coordinate typing, and keyboard dispatch.
- Vision routing (screenshots → `AIMessage.images` → vision role model).
- Action-result history for success, failure, guardrail approval/rejection, and
  duration; bounded history/workbook context and DOM-settling waits.
- Streaming narration UI + optional Web-Speech voice.
- MV3 worker-restart resilience (state persisted; resume from PAUSED).
- **Enforced production-safety gate** — destructive targets, PROD writes,
  blind coordinate writes, and cross-origin navigation are held before
  executing (`background/guardrails.js`).
- **Minimum permissions + origin binding** — no always-on target-site content
  script, per-site optional access, install-time debugger with canvas control
  off by default, verified bridge sender, confirmation for unbound backend
  origins, and credential clearing on change.
- **Zero-setup site integration** — the EPM Wizard web app configures and
  launches the agent (`content/site-bridge.js` ↔ `frontend/src/agent/`).
- **Installed-extension E2E** — persistent Chromium verifies injection,
  frames, Shadow DOM, JET, virtual grids, screenshots/canvas, origin rejection,
  result history, keyboard operation, and critical accessibility checks.
- **Store-ready** — icons, privacy policy, listing pack, packaging script.

**Still requires live-tenant qualification:**

- Oracle versions/themes can expose proprietary components differently from the
  fixtures. Extend adapter heuristics from captured, redacted tenant examples.
- Cross-origin subframes still require the user-granted host pattern, and Chrome
  internal/restricted frames cannot be injected.
- Compound EPM workflows (POV member picker, save/recalculate, rule launch,
  drill-through) remain model-composed primitives rather than deterministic
  domain skills.
- The extension validates the EPM Wizard backend connection but does not perform
  SSO inside the driven tab or resolve every session-timeout/re-auth screen.
- The safety gate reduces risk; it is not a formal proof of correct
  classification or harmless behavior.

Nothing here has been run against a live Oracle EPM tenant. Validate read-only
flows first, keep guardrails enabled, and supervise writes before production use.

## Test commands

```bash
node --test tests/*.test.mjs
cd ../frontend
npm run e2e:extension
```

The extension E2E command launches a clean persistent Chromium profile, installs
the extension, and runs a local fixture/backend. Because automation cannot click
Chrome's own permission prompts, the generated **test-only manifest copy**
pre-grants only the fixture origin; the production manifest remains
minimum-by-default.
