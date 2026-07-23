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
- It does **not** send your data to the extension's authors, to any analytics
  service, to any advertising network, or to any third party other than the
  backend URL you set.
- It stores only your settings (backend URL, project id, preferences) and the
  current run's transcript locally in the browser. Oracle passwords and client
  secrets are never written to extension storage.
- Nothing is sold. There is no tracking.

## What the extension accesses, and why

| Data | Why | Where it goes |
| --- | --- | --- |
| **Accessibility-tree snapshot** of the active tab (element roles, names, values, on-screen positions) | This is how the agent "sees" the page to decide the next action | POST to your configured backend, per step |
| **Screenshots** of the visible tab (captured via the Chrome Debugger API) | Fallback grounding when the accessibility tree is insufficient (e.g. canvas data grids) | POST to your configured backend, only when captured |
| **The goal you type** | Tells the agent what to do | POST to your configured backend |
| **Oracle EPM connection credentials** (password or OAuth client secret) | Establishes the same Oracle EPM backend connection offered by the website | Sent once to your configured EPM Wizard backend; never stored by the extension. If you select **Remember**, the backend stores it in its encrypted local secret store |
| **Excel workbook you choose** and its parsed context (sheets, formulas, sampled values, named ranges, tables, pivots, charts, connections and inert VBA source) | Gives the agent workbook-specific context while it works in EPM | The file is POSTed once to your configured backend for stateless inspection; the redacted, bounded result is kept in browser session storage and POSTed with each agent step until cleared |
| **Settings** (backend URL, project id, "speak narration", "enforce guardrails") | To run the agent the way you want | Stored locally in `chrome.storage` only |
| **Run transcript** (the steps taken this session) | Shown in the panel; preserved across a service-worker restart | Stored locally in `chrome.storage.session` only |

The extension talks to the page and to your backend. It never contacts a server
operated by the extension's authors.

## Permissions and how they are used

- **`debugger`** — to capture screenshots (`Page.captureScreenshot`) and, as a
  fallback, dispatch coordinate mouse clicks (`Input.dispatchMouseEvent`) on
  views that lack accessibility information. Chrome shows a "debugging this
  browser" banner while this is active. The extension does not read network
  traffic or inspect other tabs through this permission.
- **`activeTab` / `scripting` / `tabs`** — to inject the content script that
  reads the page and to act on the tab you are driving.
- **`sidePanel`** — to show the narration UI.
- **`storage`** — to keep your settings, run transcript and active redacted
  workbook context locally.
- **Host permissions (`https://*/*`, `http://localhost/*`)** — the target web
  app (e.g. Oracle EPM Cloud) can live on any HTTPS host, so the agent must be
  able to read and act on the page you choose. The extension only operates on
  the tab you actively drive.

## Data retention

- Settings persist until you change or clear them.
- The run transcript lives in session storage and is cleared when the browser
  session ends or you start a new run.
- The redacted workbook context lives in session storage until you click
  **Clear**, inspect a different workbook, or the browser session ends. The
  stateless inspection endpoint does not save the uploaded workbook.
- The extension keeps no server-side records of its own. Any retention on the
  backend is governed by that backend's own policy (for a self-hosted EPM Wizard
  deployment, that is you).

## Third parties

None. Data flows only between the page, the extension, and the backend URL you
configure. If you point the backend URL at a hosted EPM Wizard instance, that
instance's operator receives the observations you send it; choose a backend you
trust.

## Changes

Material changes to this policy will be reflected here with an updated date and
a new extension version.

## Contact

File an issue on the project's repository.
