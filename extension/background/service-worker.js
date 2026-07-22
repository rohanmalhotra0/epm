// EPM Wizard — background service worker (MV3, type: module).
//
// Orchestrates the narrated agent session: owns the plan→act→observe→narrate
// loop, routes messages between the side panel and the content script, attaches
// the CDP debugger for screenshot/coordinate fallback, and holds the backend
// connection.
//
// MV3 ephemerality: the worker can be terminated between events. Session state
// is persisted to chrome.storage.session after every step, and the side-panel
// Port re-hydrates the panel on (re)connect. A run that is interrupted by a
// worker restart lands in PAUSED and can be resumed (history is preserved).

import { streamStep } from "./backend.js";
import * as cdp from "./cdp.js";
import { CMD, CS, DEFAULT_CONFIG, EVT, PANEL_PORT, STATUS } from "../common/protocol.js";

const STATE_KEY = "epmw.agentState";

// In-memory mirror; the durable copy lives in chrome.storage.session.
let state = null;
let ports = new Set();
let looping = false;         // reentrancy guard for the run loop
let abortController = null;   // aborts the in-flight SSE fetch on pause/stop
let pendingScreenshot = false; // capture a screenshot for the NEXT observation

// ── open the side panel from the toolbar icon ────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: true }).catch(() => {});
});
chrome.runtime.onStartup?.addListener(() => {
  chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: true }).catch(() => {});
});

// ── state persistence ────────────────────────────────────────────────────────
function freshState() {
  return { status: STATUS.IDLE, goal: "", steps: [], tabId: null, config: { ...DEFAULT_CONFIG } };
}

async function loadState() {
  if (state) return state;
  const stored = await chrome.storage.session.get(STATE_KEY);
  state = stored[STATE_KEY] || freshState();
  // A run interrupted by a worker restart resumes from PAUSED, never RUNNING.
  if (state.status === STATUS.RUNNING) state.status = STATUS.PAUSED;
  return state;
}

async function saveState() {
  await chrome.storage.session.set({ [STATE_KEY]: state });
}

// ── panel messaging ──────────────────────────────────────────────────────────
function broadcast(type, data) {
  for (const port of ports) {
    try { port.postMessage({ type, data }); } catch { /* port closed */ }
  }
}

function sendState() {
  broadcast(EVT.STATE, {
    status: state.status, goal: state.goal, steps: state.steps, config: state.config,
  });
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== PANEL_PORT) return;
  ports.add(port);
  loadState().then(() => sendState());
  port.onDisconnect.addListener(() => ports.delete(port));
  port.onMessage.addListener((msg) => handlePanelMessage(msg).catch((err) =>
    broadcast(EVT.ERROR, { message: String(err) })));
});

async function handlePanelMessage(msg) {
  await loadState();
  switch (msg.cmd) {
    case CMD.GET_STATE:
      sendState();
      break;
    case CMD.SET_CONFIG:
      state.config = { ...state.config, ...(msg.data || {}) };
      await saveState();
      sendState();
      break;
    case CMD.START:
      await startRun(msg.data?.goal || "");
      break;
    case CMD.PAUSE:
      state.status = STATUS.PAUSED;
      abortController?.abort();
      await saveState();
      broadcast(EVT.STATUS, { status: state.status });
      break;
    case CMD.RESUME:
      if (state.status === STATUS.PAUSED) { state.status = STATUS.RUNNING; await saveState(); runLoop(); }
      break;
    case CMD.STOP:
      state.status = STATUS.IDLE;
      abortController?.abort();
      await saveState();
      broadcast(EVT.STATUS, { status: state.status });
      break;
    default:
      break;
  }
}

// ── run control ──────────────────────────────────────────────────────────────
async function startRun(goal) {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) { broadcast(EVT.ERROR, { message: "No active tab to drive." }); return; }
  state.goal = goal;
  state.steps = [];
  state.tabId = tab.id;
  state.status = STATUS.RUNNING;
  pendingScreenshot = false;
  await saveState();
  await ensureContentScript(tab.id);
  sendState();
  runLoop();
}

async function ensureContentScript(tabId) {
  // The manifest content script only lands on newly-loaded pages; inject into a
  // page that was already open when the extension loaded.
  try {
    await chrome.tabs.sendMessage(tabId, { kind: CS.PING });
  } catch {
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content/content-script.js"] });
    } catch (err) {
      broadcast(EVT.LOG, { line: `content script injection failed: ${err.message}` });
    }
  }
}

async function runLoop() {
  if (looping) return;
  looping = true;
  try {
    while (state.status === STATUS.RUNNING) {
      if (state.steps.length >= state.config.maxSteps) {
        broadcast(EVT.LOG, { line: `Reached maxSteps (${state.config.maxSteps}); stopping.` });
        state.status = STATUS.DONE;
        break;
      }
      const step = await runOneStep();
      if (!step) break; // paused/stopped/errored mid-step
      if (step.done || step.action?.type === "done") {
        state.status = STATUS.DONE;
        break;
      }
      await sleep(state.config.stepDelayMs);
    }
  } catch (err) {
    state.status = STATUS.ERROR;
    broadcast(EVT.ERROR, { message: String(err) });
  } finally {
    looping = false;
    await saveState();
    broadcast(EVT.STATUS, { status: state.status });
  }
}

// Returns the completed Step, or null if the run was interrupted.
async function runOneStep() {
  const observation = await capture();
  if (state.status !== STATUS.RUNNING) return null;

  const body = {
    goal: state.goal,
    observation,
    history: state.steps,
    projectId: state.config.projectId || null,
  };

  abortController = new AbortController();
  let finalStep = null;
  await streamStep(state.config, body, {
    onToken: (text) => broadcast(EVT.TOKEN, { text }),
    onStep: (s) => { finalStep = s; },
    onError: (message) => broadcast(EVT.ERROR, { message }),
    onDone: () => {},
  }, abortController.signal);
  abortController = null;

  if (state.status !== STATUS.RUNNING) return null; // paused/stopped during stream
  if (!finalStep) { state.status = STATUS.ERROR; return null; }

  state.steps.push(finalStep);
  await saveState();
  broadcast(EVT.STEP, { step: finalStep });

  const result = await executeAction(finalStep.action || {});
  broadcast(EVT.ACTED, result);
  await saveState();
  return finalStep;
}

// Build an Observation: accessibility snapshot (primary) + optional screenshot
// (fallback — captured when the model asked for one, or when the tree is empty).
async function capture() {
  let snapshot = { url: "", title: "", nodes: [], notes: null };
  try {
    snapshot = await chrome.tabs.sendMessage(state.tabId, { kind: CS.SNAPSHOT });
  } catch (err) {
    snapshot.notes = `accessibility snapshot unavailable (${err.message}); relying on screenshot`;
    pendingScreenshot = true;
  }
  const wantShot = pendingScreenshot || (snapshot.nodes || []).length === 0;
  pendingScreenshot = false;
  if (wantShot) {
    try {
      snapshot.screenshot = await cdp.captureScreenshot(state.tabId);
    } catch (err) {
      broadcast(EVT.LOG, { line: `screenshot failed: ${err.message}` });
    }
  }
  return snapshot;
}

async function executeAction(action) {
  const type = action.type;
  try {
    if (type === "done") return { ok: true, detail: "goal complete" };
    if (type === "wait") { await sleep(action.durationMs || 500); return { ok: true, detail: "waited" }; }
    if (type === "screenshot") { pendingScreenshot = true; return { ok: true, detail: "will capture next observation" }; }
    if (type === "navigate") {
      await chrome.tabs.update(state.tabId, { url: action.url });
      await sleep(1000);
      await ensureContentScript(state.tabId);
      return { ok: true, detail: `navigated to ${action.url}` };
    }
    // Coordinate actions (no ref) → CDP fallback.
    if (type === "click" && action.ref == null && action.x != null && action.y != null) {
      return await cdp.clickAt(state.tabId, action.x, action.y);
    }
    // ref-based actions (and scroll) → content script.
    return await chrome.tabs.sendMessage(state.tabId, { kind: CS.ACT, action });
  } catch (err) {
    return { ok: false, detail: `action '${type}' failed: ${err.message}` };
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Clean up the CDP attachment when the driven tab closes.
chrome.tabs.onRemoved.addListener((tabId) => { cdp.detach(tabId).catch(() => {}); });
