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
  SET_CONFIG: "setConfig", // { backendUrl, projectId }
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
  DONE: "done",
  ERROR: "error",
});

export const DEFAULT_CONFIG = Object.freeze({
  // The FastAPI backend. Same-origin dev default; override in the panel.
  backendUrl: "http://localhost:8000",
  // Optional EPM Wizard project id → selects that project's active provider.
  projectId: "",
  // Safety rail for the scaffold so a loop can't run away.
  maxSteps: 25,
  // Pause between steps (ms) so a human can watch.
  stepDelayMs: 700,
});
