// Shared message-type constants + defaults for the extension's three contexts
// (service worker, content script, side panel). Plain ES module — no build step.

// Side panel  <-> service worker (over a long-lived Port named "epmw-panel").
export const PANEL_PORT = "epmw-panel";

// Panel -> SW commands
export const CMD = Object.freeze({
  START: "start",     // { goal }
  PAUSE: "pause",
  RESUME: "resume",
  STOP: "stop",
  GET_STATE: "getState",
  SET_CONFIG: "setConfig", // { backendUrl, projectId, apiToken, enforceGuardrails }
  CONFIRM: "confirm",      // { id, approve } — resolve a held destructive action
  TEST_CONNECTION: "testConnection", // check backend reachability + auth
});

// SW -> panel events
export const EVT = Object.freeze({
  STATE: "state",       // { status, goal, steps, config }
  TOKEN: "token",       // { text }  transient "thinking" stream
  STEP: "step",         // { step }  a completed plan→act→narrate cycle
  ACTED: "acted",       // { ok, detail } result of executing the step's action
  STATUS: "status",     // { status }
  ERROR: "error",       // { message }
  LOG: "log",           // { line }
  CONFIRM: "confirm",   // { id, reason, label, action } destructive action held for approval
  CONN: "conn",         // { ok, mode, owner, message } result of TEST_CONNECTION
});

// Web page (EPM Wizard site) <-> extension, bridged by content/site-bridge.js
// over window CustomEvents so the page never needs the (unstable) extension id.
export const SITE = Object.freeze({
  // page -> extension
  PING: "epmw:ping",             // detail: {}
  CONFIGURE: "epmw:configure",   // detail: { backendUrl?, projectId?, goal? }
  LAUNCH: "epmw:launch",         // detail: { backendUrl?, projectId?, goal? }
  // extension -> page
  READY: "epmw:extension",       // detail: { installed:true, version }
});

// SW -> content script requests (chrome.tabs.sendMessage)
export const CS = Object.freeze({
  SNAPSHOT: "cs.snapshot",   // -> { url, title, nodes, notes }
  ACT: "cs.act",             // { action } -> { ok, detail }
  PING: "cs.ping",
});

// Agent run status values.
export const STATUS = Object.freeze({
  IDLE: "idle",
  RUNNING: "running",
  PAUSED: "paused",
  CONFIRM: "confirm",   // a destructive action is held, awaiting human approval
  DONE: "done",
  ERROR: "error",
});

// The hosted EPM Wizard app (the oauth2-proxy front door on Fly — the single
// public entry point that gates the app behind sign-in and proxies /api to the
// backend). This is the default the extension ships with, so the panel works
// against the real product out of the box with nothing to configure. Self-host
// or local dev? Override the Server URL under Settings → Advanced. The EPM
// Wizard site also overrides this to its own origin via the handshake
// (SITE.CONFIGURE) whenever you open the panel from a signed-in tab.
export const PROD_BACKEND_URL = "https://epmw-auth.fly.dev";

export const DEFAULT_CONFIG = Object.freeze({
  backendUrl: PROD_BACKEND_URL,
  // Optional EPM Wizard project id → selects that project's active provider.
  projectId: "",
  // Optional personal API token (epmw_…) for AUTONOMOUS use — drives the
  // token-gated /api/ext routes without a signed-in website tab. When empty the
  // agent uses INTEGRATED auth: the website session cookie (credentials:include)
  // authenticates the call while you're signed in. Generate one on the app's
  // Browser Agent page.
  apiToken: "",
  // Safety rail for the scaffold so a loop can't run away.
  maxSteps: 25,
  // Pause between steps (ms) so a human can watch.
  stepDelayMs: 700,
  // ENFORCED guardrail: hold destructive/irreversible actions (deploy, delete,
  // clear, run-rule, …) and any write while on a PROD tenant for explicit human
  // approval before they execute. This is a hard gate, not a prompt hint.
  enforceGuardrails: true,
});

// Origins the EPM Wizard web app is served from — the site-bridge content
// script runs only here, and only these origins may configure/launch the agent.
export const SITE_ORIGINS = Object.freeze([
  "https://epmw-auth.fly.dev",
  "https://epmw-frontend.fly.dev",
  "http://localhost:3000",
  "http://localhost:8000",
  "http://127.0.0.1:3000",
  "http://127.0.0.1:8000",
]);
