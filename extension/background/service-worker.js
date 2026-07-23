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

import { connectEpmEnvironment, getExtensionAccess, streamStep, testConnection } from "./backend.js";
import * as cdp from "./cdp.js";
import { assessAction } from "./guardrails.js";
import {
  evaluateSiteBridgeRequest,
  normalizeBackendOrigin,
} from "./origin-policy.js";
import {
  attachActionResult,
  compactHistory,
  compactWorkbookContext,
  shouldCaptureScreenshot,
} from "./run-history.js";
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
let lastScreenshotHash = "";
let globalRefByTarget = new Map();
let nextGlobalRef = 1;
// Context from the most recent observation, so the guardrail can resolve a
// ref → accessible-name and the current tenant URL/title at execution time.
let lastObs = {
  url: "",
  title: "",
  refName: new Map(),
  refTarget: new Map(),
  coordinateTargets: [],
  viewport: null,
  screenshotMeta: null,
};

// ── open the side panel from the toolbar icon ────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: true }).catch(() => {});
});
chrome.runtime.onStartup?.addListener(() => {
  chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: true }).catch(() => {});
});

// ── state persistence ────────────────────────────────────────────────────────
function freshState() {
  return {
    status: STATUS.IDLE,
    goal: "",
    pendingGoal: "",
    steps: [],
    tabId: null,
    workbookContext: null,
    environment: null,
    pendingOriginChange: null,
    config: { ...DEFAULT_CONFIG },
  };
}

// Non-secret config lives in storage.local across browser restarts. API tokens
// stay only inside the session state and are cleared when the browser exits.
const DURABLE_KEY = "epmw.durable";
const DURABLE_FIELDS = ["backendUrl", "projectId", "enforceGuardrails"];

async function persistDurable(patch) {
  const keep = {};
  for (const k of DURABLE_FIELDS) if (k in patch) keep[k] = patch[k];
  if (!Object.keys(keep).length) return;
  const cur = (await chrome.storage.local.get(DURABLE_KEY))[DURABLE_KEY] || {};
  await chrome.storage.local.set({ [DURABLE_KEY]: { ...cur, ...keep } });
}

async function loadState() {
  if (state) return state;
  const stored = await chrome.storage.session.get(STATE_KEY);
  state = stored[STATE_KEY] || freshState();
  if (!("workbookContext" in state)) state.workbookContext = null;
  if (!("environment" in state)) state.environment = null;
  if (!("pendingOriginChange" in state)) state.pendingOriginChange = null;
  // Overlay durable config (token, backend URL, …) so it persists across
  // browser restarts even though run state is ephemeral session storage.
  const dur = (await chrome.storage.local.get(DURABLE_KEY))[DURABLE_KEY] || {};
  // API tokens from older releases are migrated into session-only state and
  // immediately removed from durable storage.
  if (dur.apiToken) {
    state.config.apiToken = dur.apiToken;
    delete dur.apiToken;
    await chrome.storage.local.set({ [DURABLE_KEY]: dur });
  }
  // One-time migration: earlier builds defaulted the backend to a local dev
  // server. Installs that still carry that stale default (never explicitly
  // pointed elsewhere) should follow the extension to the hosted app.
  if (dur.backendUrl === "http://localhost:8000") {
    delete dur.backendUrl;
    await persistDurable({ backendUrl: DEFAULT_CONFIG.backendUrl });
  }
  state.config = { ...state.config, ...dur };
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
    steps: state.steps, config: state.config, workbookContext: state.workbookContext || null,
    pendingOriginChange: state.pendingOriginChange || null,
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
  const originDecision = evaluateSiteBridgeRequest({
    message: msg,
    sender,
    runtimeId: chrome.runtime.id,
    currentBackendUrl: state.config.backendUrl,
  });
  if (originDecision.disposition === "deny") {
    return { ok: false, error: originDecision.reason };
  }
  if (originDecision.disposition === "confirm") {
    state.pendingOriginChange = {
      backendUrl: originDecision.backendUrl,
      pageOrigin: originDecision.pageOrigin,
      reason: originDecision.reason,
      projectId: typeof msg.data?.projectId === "string" ? msg.data.projectId : "",
      goal: typeof msg.data?.goal === "string" ? msg.data.goal : "",
      kind: msg.kind,
    };
    await saveState();
    broadcast(EVT.ORIGIN_CONFIRM, state.pendingOriginChange);
    sendState();
    try {
      const windowId = sender?.tab?.windowId;
      if (windowId != null) await chrome.sidePanel.open({ windowId });
    } catch {
      // The pending request remains visible the next time the panel opens.
    }
    return {
      ok: false,
      requiresApproval: true,
      requestedBackendUrl: originDecision.backendUrl,
      error: originDecision.reason,
    };
  }

  const data = msg.data || {};
  const patch = {};
  if (originDecision.backendUrl) patch.backendUrl = originDecision.backendUrl;
  if (typeof data.projectId === "string") patch.projectId = data.projectId;
  if (originDecision.clearCredentials) patch.apiToken = "";
  if (Object.keys(patch).length) {
    state.config = { ...state.config, ...patch };
    await persistDurable(patch);   // remember the site's backend URL / project
  }
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
      {
        const patch = { ...(msg.data || {}) };
        if ("backendUrl" in patch) {
          const backendUrl = normalizeBackendOrigin(patch.backendUrl);
          if (!backendUrl) {
            throw new Error("Server URL must be an HTTPS origin or a loopback HTTP origin.");
          }
          if (backendUrl !== normalizeBackendOrigin(state.config.backendUrl)) {
            patch.apiToken = "";
          }
          patch.backendUrl = backendUrl;
        }
        state.config = { ...state.config, ...patch };
        await persistDurable(patch);
      }
      await saveState();
      sendState();
      break;
    case CMD.CONFIRM_ORIGIN: {
      const pending = state.pendingOriginChange;
      state.pendingOriginChange = null;
      if (pending && msg.data?.approve) {
        const backendUrl = normalizeBackendOrigin(pending.backendUrl);
        if (!backendUrl) throw new Error("The requested backend origin is no longer valid.");
        const patch = { backendUrl, apiToken: "" };
        if (pending.projectId) patch.projectId = pending.projectId;
        state.config = { ...state.config, ...patch };
        if (pending.goal) state.pendingGoal = pending.goal;
        await persistDurable(patch);
        broadcast(EVT.ORIGIN_UPDATED, { ok: true, backendUrl });
      } else {
        broadcast(EVT.ORIGIN_UPDATED, { ok: false, detail: "Backend-origin change rejected." });
      }
      await saveState();
      sendState();
      break;
    }
    case CMD.SET_WORKBOOK_CONTEXT: {
      const context = msg.data?.workbookContext;
      if (!context || typeof context.content !== "string" || !context.content) {
        throw new Error("The workbook inspector did not provide usable AI context.");
      }
      if (context.content.length > 300_000) {
        throw new Error("Workbook AI context exceeds the safe session limit.");
      }
      state.workbookContext = context;
      await saveState();
      sendState();
      break;
    }
    case CMD.CLEAR_WORKBOOK_CONTEXT:
      state.workbookContext = null;
      await saveState();
      sendState();
      break;
    case CMD.CHECK_ACCESS: {
      const access = await getExtensionAccess(state.config);
      applyAccessToState(access);
      if (access.projectId && access.projectId !== state.config.projectId) {
        state.config.projectId = access.projectId;
        await persistDurable({ projectId: access.projectId });
        await saveState();
      }
      broadcast(EVT.ACCESS, access);
      break;
    }
    case CMD.CONNECT_EPM: {
      try {
        const access = await connectEpmEnvironment(state.config, msg.data || {});
        applyAccessToState(access);
        if (access.projectId && access.projectId !== state.config.projectId) {
          state.config.projectId = access.projectId;
          await persistDurable({ projectId: access.projectId });
          await saveState();
        }
        broadcast(EVT.ACCESS, access);
      } catch (error) {
        broadcast(EVT.ACCESS, {
          stage: error?.status === 401 || error?.status === 403 ? "oauth" : "epm",
          message: error?.message || "Could not connect to Oracle EPM.",
          error: true,
        });
      }
      break;
    }
    case CMD.TEST_CONNECTION: {
      const result = await testConnection(state.config);
      broadcast(EVT.CONN, result);
      break;
    }
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
  const access = await getExtensionAccess(state.config);
  applyAccessToState(access);
  if (access.projectId && access.projectId !== state.config.projectId) {
    state.config.projectId = access.projectId;
    await persistDurable({ projectId: access.projectId });
  }
  if (access.stage !== "ready") {
    await saveState();
    broadcast(EVT.ACCESS, access);
    broadcast(EVT.ERROR, {
      message: access.message || "Finish signing in to EPM Wizard and Oracle EPM before starting the agent.",
    });
    return;
  }
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) { broadcast(EVT.ERROR, { message: "No active tab to drive." }); return; }
  state.goal = goal;
  state.pendingGoal = "";   // consumed
  state.steps = [];
  state.tabId = tab.id;
  state.status = STATUS.RUNNING;
  pendingScreenshot = false;
  lastScreenshotHash = "";
  globalRefByTarget = new Map();
  nextGlobalRef = 1;
  await saveState();
  try {
    await ensureContentScript(tab.id);
  } catch (error) {
    state.status = STATUS.ERROR;
    await saveState();
    broadcast(EVT.ERROR, {
      message: `${error.message} Open Settings and grant the current Oracle site, or click the toolbar icon on that tab, then try again.`,
    });
    broadcast(EVT.STATUS, { status: state.status });
    return;
  }
  sendState();
  runLoop();
}

async function ensureContentScript(tabId) {
  // Agent code is injected only after the user presses Start. activeTab grants
  // the top document temporarily; optional host access covers approved Oracle
  // subframes without an always-on <all_urls> content script.
  try {
    const existing = await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: () => !!globalThis.__epmwAgent,
    });
    if (existing.length && existing.every((entry) => entry.result)) return;
  } catch {
    // Fall through to injection; restricted frames are reported below.
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      files: ["content/content-script.js"],
    });
  } catch (err) {
    broadcast(EVT.LOG, { line: `content script injection failed: ${err.message}` });
    throw new Error(`EPM Wizard cannot access this tab (${err.message}).`);
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
      await waitForPageStable(state.tabId, {
        quietMs: Math.max(80, Math.min(250, state.config.stepDelayMs || 120)),
        timeoutMs: 1600,
      });
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
    history: compactHistory(state.steps),
    projectId: state.config.projectId || null,
    workbookContext: compactWorkbookContext(state.workbookContext),
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

  finalStep = { ...finalStep, raw: undefined };
  state.steps.push(finalStep);
  await saveState();
  broadcast(EVT.STEP, { step: finalStep });

  // ENFORCED guardrail: hold destructive / PROD-write actions for explicit human
  // approval before they touch the page. Nothing fires on the model's word alone.
  const gate = await gateAction(finalStep.action || {});
  if (gate === "aborted") return null;              // paused/stopped while held
  if (gate === "rejected") {
    const result = { ok: false, detail: "blocked by safety guardrail — not executed" };
    finalStep = attachActionResult(finalStep, result, { gate: "rejected", durationMs: 0 });
    state.steps[state.steps.length - 1] = finalStep;
    broadcast(EVT.ACTED, result);
    await saveState();
    return finalStep;                                // skip execution, keep going
  }

  const startedAt = performance.now();
  const result = await executeAction(finalStep.action || {});
  finalStep = attachActionResult(finalStep, result, {
    gate,
    durationMs: performance.now() - startedAt,
  });
  state.steps[state.steps.length - 1] = finalStep;
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
  if (!state.config.enforceGuardrails) return "allowed";
  const label = action.ref != null ? (lastObs.refName.get(action.ref) || "") : "";
  const verdict = assessAction(action, {
    label,
    url: lastObs.url,
    title: lastObs.title,
    classification: state.environment?.classification,
    allowedOrigin: originOf(state.environment?.baseUrl),
  });
  if (!verdict.hold) return "allowed";

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
  return approved ? "approved" : "rejected";
}

// Build an Observation: accessibility snapshot (primary) + optional screenshot
// (fallback — captured when the model asked for one, or when the tree is empty).
async function capture() {
  let snapshot = { url: "", title: "", nodes: [], notes: null };
  try {
    snapshot = await snapshotAllFrames(state.tabId);
  } catch (err) {
    snapshot.notes = `accessibility snapshot unavailable (${err.message}); relying on screenshot`;
    pendingScreenshot = true;
  }
  const wantShot = shouldCaptureScreenshot(snapshot, pendingScreenshot);
  pendingScreenshot = false;
  if (wantShot) {
    try {
      const shot = await captureVisibleScreenshot(state.tabId, snapshot.viewport);
      snapshot.screenshot = shot.dataUrl;
      snapshot.screenshotMeta = shot.meta;
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
    refTarget: snapshot.refTarget || new Map(),
    coordinateTargets: snapshot.coordinateTargets || [],
    viewport: snapshot.viewport || null,
    screenshotMeta: snapshot.screenshotMeta || null,
  };
  delete snapshot.refTarget;
  delete snapshot.coordinateTargets;
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
      await ensureContentScript(state.tabId);
      await waitForPageStable(state.tabId, { quietMs: 180, timeoutMs: 2500 });
      return { ok: true, detail: `navigated to ${action.url}` };
    }
    // Coordinate actions use trusted CDP input only when the optional debugger
    // permission was granted explicitly. Otherwise the frame adapter attempts
    // a best-effort DOM/pointer dispatch and reports that limitation.
    if (action.ref == null && action.x != null && action.y != null) {
      const point = cdp.normalizeCoordinates(action.x, action.y, {
        coordinateSpace: action.coordinateSpace || "css",
        screenshotMeta: lastObs.screenshotMeta || {},
      });
      const cssAction = { ...action, ...point, coordinateSpace: "css" };
      const coordinateTarget = findCoordinateTarget(point.x, point.y);
      const localAction = coordinateTarget
        ? {
            ...cssAction,
            x: point.x - coordinateTarget.offsetX,
            y: point.y - coordinateTarget.offsetY,
          }
        : cssAction;
      if (await hasDebuggerPermission()) {
        if (type === "click") {
          return await cdp.clickAt(state.tabId, point.x, point.y);
        }
        if (type === "type" && typeof cdp.typeAt === "function") {
          return await cdp.typeAt(state.tabId, point.x, point.y, action.text || "");
        }
      }
      return await actInFrame(coordinateTarget?.frameId || 0, localAction);
    }
    if (action.ref != null) {
      const target = lastObs.refTarget.get(action.ref);
      if (!target) return { ok: false, detail: `ref ${action.ref} is stale; re-observe the page` };
      return await actInFrame(target.frameId, { ...action, ref: target.localRef });
    }
    return await actInFrame(0, action);
  } catch (err) {
    return { ok: false, detail: `action '${type}' failed: ${err.message}` };
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function actInFrame(frameId, action) {
  return chrome.tabs.sendMessage(
    state.tabId,
    { kind: CS.ACT, action },
    { frameId },
  );
}

async function snapshotAllFrames(tabId, reinjected = false) {
  let results = await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    func: () => globalThis.__epmwAgent?.snapshot?.() || null,
  });
  if (!reinjected && results.some((entry) => !entry.result && !entry.error)) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId, allFrames: true },
        files: ["content/content-script.js"],
      });
      results = await chrome.scripting.executeScript({
        target: { tabId, allFrames: true },
        func: () => globalThis.__epmwAgent?.snapshot?.() || null,
      });
    } catch (error) {
      console.warn("Could not inject the agent into a newly created frame", error);
    }
  }
  const frames = results
    .filter((entry) => entry.result && !entry.error)
    .sort((a, b) => a.frameId - b.frameId);
  if (!frames.length) throw new Error("no accessible document frames");

  const top = frames.find((entry) => entry.frameId === 0)?.result || frames[0].result;
  const frameOffsets = resolveFrameOffsets(frames);
  const nodes = [];
  const refTarget = new Map();
  const coordinateTargets = [];
  const notes = [];
  let ariaPoor = false;

  for (const entry of frames) {
    const frame = entry.result;
    const offset = frameOffsets.get(entry.frameId) || { x: 0, y: 0, complete: false };
    if (frame.notes) notes.push(`frame ${entry.frameId}: ${frame.notes}`);
    if (!offset.complete) notes.push(`frame ${entry.frameId}: top-level coordinate offset unavailable`);
    ariaPoor ||= !!frame.ariaPoor;
    for (const node of frame.nodes || []) {
      const localRef = node.ref;
      const targetKey = `${entry.frameId}:${localRef}`;
      let ref = globalRefByTarget.get(targetKey);
      if (!ref) {
        ref = nextGlobalRef++;
        globalRefByTarget.set(targetKey, ref);
      }
      const rect = Array.isArray(node.rect)
        ? [
            Number(node.rect[0] || 0) + Number(offset.x || 0),
            Number(node.rect[1] || 0) + Number(offset.y || 0),
            Number(node.rect[2] || 0),
            Number(node.rect[3] || 0),
          ]
        : null;
      nodes.push({
        ...node,
        ref,
        rect,
        frameId: String(entry.frameId),
        framePath: node.framePath || frame.framePath || `frame:${entry.frameId}`,
      });
      refTarget.set(ref, { frameId: entry.frameId, localRef });
      if (node.canvas && rect) {
        coordinateTargets.push({
          frameId: entry.frameId,
          offsetX: Number(offset.x || 0),
          offsetY: Number(offset.y || 0),
          rect,
        });
      }
    }
  }

  return {
    url: top.url || "",
    title: top.title || "",
    nodes,
    notes: notes.join("\n") || null,
    viewport: top.viewport || null,
    ariaPoor,
    needsScreenshot: frames.some((entry) => entry.result.needsScreenshot),
    refTarget,
    coordinateTargets,
  };
}

function resolveFrameOffsets(frames) {
  const offsets = new Map();
  const top = frames.find((entry) => entry.frameId === 0);
  if (top) offsets.set(0, { x: 0, y: 0, complete: true });

  for (const entry of frames) {
    const own = entry.result.frameOffset || entry.result.frame?.offsetToTop;
    if (own?.complete) offsets.set(entry.frameId, {
      x: Number(own.x || 0),
      y: Number(own.y || 0),
      complete: true,
    });
  }

  const claimed = new Set(offsets.keys());
  let progress = true;
  while (progress) {
    progress = false;
    for (const parent of frames) {
      const parentOffset = offsets.get(parent.frameId);
      if (!parentOffset?.complete) continue;
      for (const descriptor of parent.result.frame?.childFrames || []) {
        const child = frames.find((candidate) => (
          !claimed.has(candidate.frameId)
          && frameDescriptorMatches(parent.result.url, descriptor, candidate.result)
        ));
        if (!child) continue;
        offsets.set(child.frameId, {
          x: parentOffset.x + Number(
            descriptor.contentOffset?.x ?? descriptor.rect?.[0] ?? 0,
          ),
          y: parentOffset.y + Number(
            descriptor.contentOffset?.y ?? descriptor.rect?.[1] ?? 0,
          ),
          complete: true,
        });
        claimed.add(child.frameId);
        progress = true;
      }
    }
  }
  return offsets;
}

function frameDescriptorMatches(parentUrl, descriptor, childSnapshot) {
  if (descriptor.path && descriptor.path === childSnapshot.framePath) return true;
  if (!descriptor.src || !childSnapshot.url) return false;
  try {
    return new URL(descriptor.src, parentUrl).href === new URL(childSnapshot.url).href;
  } catch {
    return false;
  }
}

function findCoordinateTarget(x, y) {
  return lastObs.coordinateTargets
    .filter(({ rect }) => (
      x >= rect[0]
      && y >= rect[1]
      && x <= rect[0] + rect[2]
      && y <= rect[1] + rect[3]
    ))
    .sort((a, b) => (a.rect[2] * a.rect[3]) - (b.rect[2] * b.rect[3]))[0] || null;
}

async function waitForPageStable(tabId, options) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: async (waitOptions) => {
        if (globalThis.__epmwAgent?.waitForStable) {
          return globalThis.__epmwAgent.waitForStable(waitOptions);
        }
        return true;
      },
      args: [options],
    });
  } catch {
    await sleep(Math.min(options.timeoutMs, options.quietMs));
  }
}

async function captureVisibleScreenshot(tabId, viewport) {
  const tab = await chrome.tabs.get(tabId);
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
      format: "jpeg",
      quality: 68,
    });
    return optimizeScreenshot(dataUrl, {
      source: "tabs.captureVisibleTab",
      maxDimension: 1280,
      quality: 0.68,
      viewport,
    });
  } catch (error) {
    if (!(await hasDebuggerPermission())) throw error;
    const shot = await cdp.captureScreenshot(tabId, {
      format: "jpeg",
      quality: 68,
      maxDimension: 1280,
      withMetadata: true,
      deduplicate: true,
    });
    if (typeof shot === "string") {
      return { dataUrl: shot, meta: await screenshotMetadata(shot, "cdp") };
    }
    return {
      dataUrl: shot.dataUrl,
      meta: { source: "cdp", ...(shot.metadata || shot.meta || {}) },
    };
  }
}

async function optimizeScreenshot(dataUrl, {
  source,
  maxDimension,
  quality,
  viewport,
}) {
  const blob = await (await fetch(dataUrl)).blob();
  const bitmap = await createImageBitmap(blob);
  const scale = Math.min(1, maxDimension / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  let optimized = dataUrl;
  try {
    if (scale < 1 && typeof OffscreenCanvas !== "undefined") {
      const canvas = new OffscreenCanvas(width, height);
      canvas.getContext("2d").drawImage(bitmap, 0, 0, width, height);
      optimized = await blobToDataUrl(await canvas.convertToBlob({
        type: "image/jpeg",
        quality,
      }));
    }
  } catch {
    // The original compressed JPEG is still a valid fallback.
  }
  bitmap.close();
  const payload = optimized.slice(optimized.indexOf(",") + 1);
  const hash = cdp.hashImageData(payload);
  const duplicate = hash === lastScreenshotHash;
  lastScreenshotHash = hash;
  return {
    dataUrl: duplicate ? null : optimized,
    meta: {
      source,
      format: "jpeg",
      imageWidth: width,
      imageHeight: height,
      viewportWidth: viewport?.width || width,
      viewportHeight: viewport?.height || height,
      coordinateSpace: "css",
      scale,
      bytes: Math.floor(payload.length * 0.75),
      hash,
      duplicate,
    },
  };
}

async function blobToDataUrl(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const chunkSize = 32_768;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return `data:${blob.type || "image/jpeg"};base64,${btoa(binary)}`;
}

async function hasDebuggerPermission() {
  return chrome.permissions.contains({ permissions: ["debugger"] });
}

function applyAccessToState(access) {
  if (access?.stage !== "ready") return;
  state.environment = {
    id: access.environmentId || "",
    name: access.environmentName || "",
    baseUrl: access.environmentBaseUrl || "",
    classification: access.environmentClassification || "development",
  };
}

function originOf(url) {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

// Clean up the CDP attachment when the driven tab closes.
chrome.tabs.onRemoved.addListener((tabId) => { cdp.detach(tabId).catch(() => {}); });
