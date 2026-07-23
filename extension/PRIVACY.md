# Privacy Policy — EPM Wizard: Narrated Browser Agent

_Last updated: 2026-07-23_

This Chrome extension ("the extension") drives a web application's user
interface on your behalf and narrates each step in a side panel. This policy
explains exactly what data it handles and where that data goes.

## The short version

- The extension sends what it "sees" on the page you point it at — an
  accessibility-tree snapshot (text: element roles, names, values, positions)
  and, when needed, a screenshot of the visible tab — to **a backend server that
  you configure**. By default that is the hosted EPM Wizard app
  (`https://epmw-auth.fly.dev`); when launched from an EPM Wizard web app it is
  that app's own origin, and you can point it at a self-hosted or local backend
  under Settings → Advanced.
- When you explicitly choose an Excel workbook, the file is sent to that same
  configured backend for parse-only inspection. The backend returns redacted
  workbook context (including formulas and inert VBA source), which is sent
  with each agent step until you clear it or end the browser session.
- The extension sends data only to the backend URL you configure. That backend
  may pass page and workbook context to its configured AI provider, so the
  backend operator's and AI provider's policies also apply. There is no
  extension analytics, advertising, or sale of data.
- It stores only your settings (backend URL, project id, preferences) and the
  current run's transcript locally in the browser. A personal API token, if
  supplied, is kept in browser session storage. Oracle passwords and client
  secrets are never written to extension storage.
- Nothing is sold. There is no tracking.

## What the extension accesses, and why

| Data | Why | Where it goes |
| --- | --- | --- |
| **Accessibility-tree snapshot** of the active tab (element roles, names, values, on-screen positions) | This is how the agent "sees" the page to decide the next action | POST to your configured backend, per step |
| **Screenshots** of the visible tab (captured with Chrome's visible-tab API, or optionally via the Chrome Debugger API) | Fallback grounding when the accessibility tree is insufficient (e.g. canvas data grids) | POST to your configured backend, only when captured |
| **The goal you type** | Tells the agent what to do | POST to your configured backend |
| **Oracle EPM connection credentials** (password or OAuth client secret) | Establishes the same Oracle EPM backend connection offered by the website | Sent once to your configured EPM Wizard backend; never stored by the extension. If you select **Remember**, the backend stores it in its encrypted local secret store |
| **Excel workbook you choose** and its parsed context (sheets, formulas, sampled values, named ranges, tables, pivots, charts, connections and inert VBA source) | Gives the agent workbook-specific context while it works in EPM | The file is POSTed once to your configured backend for stateless inspection; the redacted, bounded result is kept in browser session storage and POSTed with each agent step until cleared |
| **Settings** (backend URL, project id, "speak narration", "enforce guardrails") | To run the agent the way you want | Stored locally in `chrome.storage` only |
| **Personal API token** (optional) | Authenticates extension transport routes on the configured backend | Stored only in `chrome.storage.session`; the backend stores a one-way hash and shows the plaintext token once |
| **Run transcript** (the steps taken this session) | Shown in the panel; preserved across a service-worker restart | Stored locally in `chrome.storage.session` only |

The extension talks to the selected page and configured backend. The default
backend is the hosted EPM Wizard service named above; choosing a self-hosted
backend changes that destination.

## Permissions and how they are used

- **Install-time `debugger`, user-controlled canvas mode** — when you enable trusted canvas input, this can
  capture a CDP screenshot (`Page.captureScreenshot`) and dispatch coordinate
  mouse clicks (`Input.dispatchMouseEvent`) on views that lack accessibility
  information. Chrome shows a "debugging this browser" banner while active.
  The extension does not read network traffic through this permission. When
  Chrome withholds the active tab URL before a site grant, EPM Wizard also uses
  `debugger.getTargets()` without attaching, keeps only the URL whose tab ID
  matches the active tab, and discards all other target metadata after deriving
  the exact origin to request.
- **`activeTab` / `scripting`** — to inject the content script that reads the
  page and to act on the tab you are driving.
- **`sidePanel`** — to show the narration UI.
- **`storage`** — to keep your settings, run transcript and active redacted
  workbook context locally.
- **Optional site access (`https://*/*`, plus loopback HTTP)** — requested from
  the direct Grant/Save/Approve click when you choose an Oracle target or custom
  backend. Oracle EPM Cloud and self-hosted EPM Wizard can live on different
  HTTPS hosts. Plain HTTP is limited to `localhost` and `127.0.0.1`
  development; the manifest includes only known EPM Wizard origins by default.

## Data retention

- Settings persist until you change or clear them.
- The run transcript lives in session storage and is cleared when the browser
  session ends or you start a new run.
- A personal API token entered in the panel lives in session storage and is
  cleared when the browser session ends.
- The redacted workbook context lives in session storage until you click
  **Clear**, inspect a different workbook, or the browser session ends. The
  stateless inspection endpoint does not save the uploaded workbook.
- The extension keeps no server-side records of its own. Any retention on the
  backend is governed by that backend's own policy (for a self-hosted EPM Wizard
  deployment, that is you).

## Third parties

Data flows from the selected page to the configured backend. The backend may
send the goal, page observations, screenshots, and redacted workbook context to
the AI provider configured for that backend. Choose a backend and provider you
trust. The extension itself includes no analytics or advertising integrations
and does not sell data.

## Changes

Material changes to this policy will be reflected here with an updated date and
a new extension version.

## Contact

File an issue on the project's repository.
