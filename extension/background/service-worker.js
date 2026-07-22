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
import { assessAction } from "./guardrails.js";
import { CMD, CS, DEFAULT_CONFIG, EVT, PANEL_PORT, STATUS } from "../common/protocol.js";

const STATE_KEY = "epmw.agentState";

// In-memory mirror; the durable copy lives in chrome.storage.session.
let state = null;
let ports = new Set();
let looping = false;         // reentrancy guard for the run loop
let abortController = null;   // aborts the in-flight SSE fetch on pause/stop
let pendingScreenshot = false; // capture a screenshot for the NEXT observation
let pendingConfirm = null;   // { id, resolve } while a destructive action is held
let confirmSeq = 0;          // monotonically-increasing id for confirm prompts
// Context from the most recent observation, so the guardrail can resolve a
// ref → accessible-name and the current tenant URL/title at execution time.
let lastObs = { url: "", title: "", refName: new Map() };

// ── open the side panel from the toolbar icon ────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: true }).catch(() => {});
});
chrome.runtime.onStartup?.addListener(() => {
  chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: true }).catch(() => {});
});

// ── state persistence ────────────────────────────────────────────────────────
function freshState() {
  return { status: STATUS.IDLE, goal: "", pendingGoal: "", steps: [], tabId: null, config: { ...DEFAULT_CONFIG } };
}

async function loadState() {
  if (state) return state;
  const stored = await chrome.storage.session.get(STATE_KEY);
  state = stored[STATE_KEY] || freshState();
  // A run interrupted by a worker restart resumes from PAUSED, never RUNNING —
  // and never stuck mid-confirmation (the held promise died with the worker).
  if (state.status === STATUS.RUNNING || state.status === STATUS.CONFIRM) {
    state.status = STATUS.PAUSED;
  }
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
    status: state.status, goal: state.goal, pendingGoal: state.pendingGoal || "",
    steps: state.steps, config: state.config,
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

// ── site handshake (from content/site-bridge.js on EPM Wizard origins) ────────
// The web app pre-configures the agent (backend URL + project id + goal) and
// asks to open the panel, so there is no manual setup. Only messages relayed by
// our own site-bridge content script (i.e. sender.id === our id) are honoured.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg.kind !== "string" || !msg.kind.startsWith("site.")) return false;
  if (sender.id !== chrome.runtime.id) return false; // only our own content scripts
  handleSiteMessage(msg, sender)
    .then((r) => sendResponse(r))
    .catch((err) => sendResponse({ ok: false, error: String(err) }));
  return true; // async response
});

async function handleSiteMessage(msg, sender) {
  await loadState();
  const data = msg.data || {};
  const patch = {};
  if (typeof data.backendUrl === "string" && data.backendUrl) patch.backendUrl = data.backendUrl;
  if (typeof data.projectId === "string") patch.projectId = data.projectId;
  if (Object.keys(patch).length) state.config = { ...state.config, ...patch };
  if (typeof data.goal === "string" && data.goal) state.pendingGoal = data.goal;
  await saveState();
  sendState();

  if (msg.kind !== "site.launch") return { ok: true, configured: true };

  // Best-effort open. Opening the side panel needs a user gesture the relayed
  // message may not carry; if it throws, the config is already saved and the
  // user opens the fully-wired panel with a single click on the toolbar icon.
  try {
    const windowId = sender?.tab?.windowId;
    if (windowId != null) await chrome.sidePanel.open({ windowId });
    return { ok: true, opened: true };
  } catch {
    return { ok: true, opened: false, hint: "Click the EPM Wizard toolbar icon to open the panel." };
  }
}

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
      resolveConfirm(false);   // release any held action; it will not execute
      await saveState();
      broadcast(EVT.STATUS, { status: state.status });
      break;
    case CMD.RESUME:
      if (state.status === STATUS.PAUSED) { state.status = STATUS.RUNNING; await saveState(); runLoop(); }
      break;
    case CMD.STOP:
      state.status = STATUS.IDLE;
      abortController?.abort();
      resolveConfirm(false);   // release any held action; it will not execute
      await saveState();
      broadcast(EVT.STATUS, { status: state.status });
      break;
    case CMD.CONFIRM:
      // The human approved (or rejected) a held destructive action.
      if (pendingConfirm && msg.data?.id === pendingConfirm.id) {
        resolveConfirm(!!msg.data.approve);
      }
      break;
    default:
      break;
  }
}

// Resolve a pending confirmation exactly once.
function resolveConfirm(approve) {
  if (!pendingConfirm) return;
  const { resolve } = pendingConfirm;
  pendingConfirm = null;
  resolve(approve);
}

// ── run control ──────────────────────────────────────────────────────────────
async function startRun(goal) {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) { broadcast(EVT.ERROR, { message: "No active tab to drive." }); return; }
  state.goal = goal;
  state.pendingGoal = "";   // consumed
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

  // ENFORCED guardrail: hold destructive / PROD-write actions for explicit human
  // approval before they touch the page. Nothing fires on the model's word alone.
  const gate = await gateAction(finalStep.action || {});
  if (gate === "aborted") return null;              // paused/stopped while held
  if (gate === "rejected") {
    broadcast(EVT.ACTED, { ok: false, detail: "blocked by safety guardrail — not executed" });
    await saveState();
    return finalStep;                                // skip execution, keep going
  }

  const result = await executeAction(finalStep.action || {});
  broadcast(EVT.ACTED, result);
  await saveState();
  return finalStep;
}

// Consult the guardrail and, when it flags an action, hold the run until the
// human approves or rejects it in the side panel.
//   "allow"    → safe (or guardrails off); execute normally
//   "rejected" → human declined; skip this action
//   "aborted"  → run was paused/stopped while the action was held
async function gateAction(action) {
  if (!state.config.enforceGuardrails) return "allow";
  const label = action.ref != null ? (lastObs.refName.get(action.ref) || "") : "";
  const verdict = assessAction(action, { label, url: lastObs.url, title: lastObs.title });
  if (!verdict.hold) return "allow";

  const id = ++confirmSeq;
  state.status = STATUS.CONFIRM;
  await saveState();
  broadcast(EVT.CONFIRM, { id, reason: verdict.reason, label: verdict.label || "", action });
  broadcast(EVT.STATUS, { status: STATUS.CONFIRM });

  const approved = await new Promise((resolve) => { pendingConfirm = { id, resolve }; });

  // A pause/stop while we were waiting flips the status away from CONFIRM.
  if (state.status !== STATUS.CONFIRM) return "aborted";
  state.status = STATUS.RUNNING;
  await saveState();
  broadcast(EVT.STATUS, { status: STATUS.RUNNING });
  return approved ? "allow" : "rejected";
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
  // Remember what the agent is looking at so the guardrail can resolve a target
  // element's name and the current tenant when the next action executes.
  lastObs = {
    url: snapshot.url || "",
    title: snapshot.title || "",
    refName: new Map((snapshot.nodes || []).map((n) => [n.ref, n.name || ""])),
  };
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
