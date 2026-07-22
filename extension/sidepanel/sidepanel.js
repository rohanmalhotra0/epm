// EPM Wizard side panel — the "watch it work" surface.
//
// Connects to the service worker over a long-lived Port, streams the agent's
// step-by-step narration, shows the current plan/action, and drives
// Start / Pause / Resume / Stop. Optional voice narration via the browser's
// SpeechSynthesis API (mirrors the main app's Web Speech TTS — no backend TTS).

import { CMD, EVT, PANEL_PORT, STATUS } from "../common/protocol.js";
import { initInspector } from "./inspector.js";

const $ = (id) => document.getElementById(id);
const els = {
  statusDot: $("statusDot"), statusText: $("statusText"),
  settings: $("settings"), settingsToggle: $("settingsToggle"),
  backendUrl: $("backendUrl"), projectId: $("projectId"),
  voiceToggle: $("voiceToggle"), guardToggle: $("guardToggle"), saveConfig: $("saveConfig"),
  goal: $("goal"), startBtn: $("startBtn"), pauseBtn: $("pauseBtn"),
  resumeBtn: $("resumeBtn"), stopBtn: $("stopBtn"),
  feed: $("feed"), emptyHint: $("emptyHint"),
  thinking: $("thinking"), thinkingText: $("thinkingText"),
  stepCount: $("stepCount"),
  confirm: $("confirm"), confirmReason: $("confirmReason"), confirmDetail: $("confirmDetail"),
  approveBtn: $("approveBtn"), rejectBtn: $("rejectBtn"),
  tabAgent: $("tabAgent"), tabInspect: $("tabInspect"),
  agentView: $("agentView"), inspectView: $("inspectView"),
};

let port = connect();
let renderedSteps = 0;
let thinkingBuffer = "";
let pendingConfirmId = null; // id of the destructive action currently held
let currentConfig = {};      // last config from the service worker
const VOICE_KEY = "epmw.voice";

// The workbook inspector reads the backend URL from live config (falling back to
// whatever is typed in the settings field).
initInspector({ getBackendUrl: () => currentConfig.backendUrl || els.backendUrl.value.trim() });

function connect() {
  const p = chrome.runtime.connect({ name: PANEL_PORT });
  p.onMessage.addListener(onMessage);
  // MV3 can recycle the service worker; reconnect so the panel keeps working.
  p.onDisconnect.addListener(() => { setTimeout(() => { port = connect(); }, 400); });
  p.postMessage({ cmd: CMD.GET_STATE });
  return p;
}

function send(cmd, data) { try { port.postMessage({ cmd, data }); } catch { port = connect(); port.postMessage({ cmd, data }); } }

// ── incoming events ──────────────────────────────────────────────────────────
function onMessage({ type, data }) {
  switch (type) {
    case EVT.STATE: applyState(data); break;
    case EVT.TOKEN: onToken(data.text); break;
    case EVT.STEP: onStep(data.step); break;
    case EVT.ACTED: onActed(data); break;
    case EVT.STATUS: setStatus(data.status); break;
    case EVT.ERROR: appendLine(data.message, "error"); hideThinking(); break;
    case EVT.LOG: appendLine(data.line, "log"); break;
    case EVT.CONFIRM: onConfirmRequest(data); break;
    default: break;
  }
}

function applyState(state) {
  setStatus(state.status);
  if (state.config) {
    currentConfig = state.config;
    els.backendUrl.value = state.config.backendUrl || "";
    els.projectId.value = state.config.projectId || "";
    els.guardToggle.checked = state.config.enforceGuardrails !== false;
  }
  // Re-render the persisted steps (e.g. after a worker restart / panel reopen).
  if (Array.isArray(state.steps)) {
    if (state.steps.length < renderedSteps) resetFeed();
    for (let i = renderedSteps; i < state.steps.length; i++) renderStep(state.steps[i]);
  }
  // Prefill the goal — a run's goal, or one handed over by the web app.
  if (!els.goal.value) els.goal.value = state.goal || state.pendingGoal || "";
}

// ── enforced-guardrail confirmation ──────────────────────────────────────────
function onConfirmRequest({ id, reason, label, action }) {
  pendingConfirmId = id;
  els.confirmReason.textContent = reason || "This action was flagged as risky.";
  els.confirmDetail.textContent = describeAction(action || {}) + (label ? ` · “${label}”` : "");
  els.confirm.classList.remove("hidden");
  hideThinking();
  if (els.voiceToggle.checked) speak("Confirmation needed. " + (reason || ""));
}

function resolveConfirm(approve) {
  if (pendingConfirmId == null) return;
  send(CMD.CONFIRM, { id: pendingConfirmId, approve });
  pendingConfirmId = null;
  els.confirm.classList.add("hidden");
}

function onToken(text) {
  thinkingBuffer += text;
  els.thinkingText.textContent = thinkingBuffer.slice(-140);
  els.thinking.classList.remove("hidden");
}

function onStep(step) {
  hideThinking();
  renderStep(step);
  if (els.voiceToggle.checked && step.narration) speak(step.narration);
}

function onActed(result) {
  const card = els.feed.lastElementChild;
  if (!card || !card.classList.contains("step")) return;
  const line = document.createElement("div");
  line.className = "acted " + (result.ok ? "ok" : "fail");
  line.textContent = (result.ok ? "✓ " : "✗ ") + (result.detail || "");
  card.appendChild(line);
}

// ── rendering ────────────────────────────────────────────────────────────────
function renderStep(step) {
  els.emptyHint?.classList.add("hidden");
  const action = step.action || {};
  const card = document.createElement("div");
  card.className = "step";

  const head = document.createElement("div");
  head.className = "head";
  const idx = document.createElement("span");
  idx.className = "idx";
  idx.textContent = `#${(step.index ?? renderedSteps) + 1}`;
  const badge = document.createElement("span");
  badge.className = "badge " + (action.type || "");
  badge.textContent = action.type || "action";
  head.append(idx, badge);

  const narration = document.createElement("div");
  narration.className = "narration";
  narration.textContent = step.narration || "";

  card.append(head, narration);

  const detail = describeAction(action);
  if (detail) {
    const d = document.createElement("div");
    d.className = "detail";
    d.textContent = detail;
    card.appendChild(d);
  }

  els.feed.appendChild(card);
  els.feed.scrollTop = els.feed.scrollHeight;
  renderedSteps++;
  els.stepCount.textContent = String(renderedSteps);
}

function describeAction(a) {
  switch (a.type) {
    case "click": return a.ref != null ? `click ref=${a.ref}` : `click (${a.x}, ${a.y})`;
    case "type": return `type ${JSON.stringify(a.text ?? "")} → ref=${a.ref}`;
    case "scroll": return `scroll Δy=${a.deltaY || 0}`;
    case "navigate": return `navigate → ${a.url}`;
    case "screenshot": return "capture screenshot (vision fallback)";
    case "wait": return `wait ${a.durationMs || 0}ms`;
    case "done": return "done";
    default: return "";
  }
}

function appendLine(text, kind) {
  const line = document.createElement("div");
  line.className = "line " + (kind || "log");
  line.textContent = text;
  els.feed.appendChild(line);
  els.feed.scrollTop = els.feed.scrollHeight;
}

function resetFeed() {
  els.feed.innerHTML = "";
  renderedSteps = 0;
  els.stepCount.textContent = "0";
}

function hideThinking() { thinkingBuffer = ""; els.thinking.classList.add("hidden"); }

// ── status → button state ────────────────────────────────────────────────────
function setStatus(status) {
  els.statusText.textContent = status;
  els.statusDot.className = "dot " + status;
  const running = status === STATUS.RUNNING;
  const paused = status === STATUS.PAUSED;
  const confirming = status === STATUS.CONFIRM;
  const active = running || paused || confirming;
  els.startBtn.disabled = active;
  els.pauseBtn.disabled = !(running || confirming);
  els.stopBtn.disabled = !active;
  els.pauseBtn.classList.toggle("hidden", paused);
  els.resumeBtn.classList.toggle("hidden", !paused);
  if (!running && !confirming) hideThinking();
  // Leaving the confirm state (resumed elsewhere, paused, stopped) drops the banner.
  if (!confirming) { pendingConfirmId = null; els.confirm.classList.add("hidden"); }
}

// ── voice (Web Speech) ───────────────────────────────────────────────────────
function speak(text) {
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05; u.pitch = 1.0;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  } catch { /* TTS unavailable — narration still shows visually */ }
}

// ── controls ─────────────────────────────────────────────────────────────────
els.startBtn.addEventListener("click", () => {
  const goal = els.goal.value.trim();
  if (!goal) { els.goal.focus(); return; }
  resetFeed();
  send(CMD.START, { goal });
});
els.pauseBtn.addEventListener("click", () => send(CMD.PAUSE));
els.resumeBtn.addEventListener("click", () => send(CMD.RESUME));
els.stopBtn.addEventListener("click", () => { send(CMD.STOP); window.speechSynthesis?.cancel(); });

els.approveBtn.addEventListener("click", () => resolveConfirm(true));
els.rejectBtn.addEventListener("click", () => resolveConfirm(false));

// ── view tabs (Agent / Inspect workbook) ─────────────────────────────────────
function showTab(which) {
  const inspect = which === "inspect";
  els.inspectView.classList.toggle("hidden", !inspect);
  els.agentView.classList.toggle("hidden", inspect);
  els.tabInspect.classList.toggle("active", inspect);
  els.tabAgent.classList.toggle("active", !inspect);
  els.tabInspect.setAttribute("aria-selected", String(inspect));
  els.tabAgent.setAttribute("aria-selected", String(!inspect));
}
els.tabAgent.addEventListener("click", () => showTab("agent"));
els.tabInspect.addEventListener("click", () => showTab("inspect"));

els.settingsToggle.addEventListener("click", () => els.settings.classList.toggle("hidden"));
els.saveConfig.addEventListener("click", () => {
  send(CMD.SET_CONFIG, {
    backendUrl: els.backendUrl.value.trim(),
    projectId: els.projectId.value.trim(),
    enforceGuardrails: els.guardToggle.checked,
  });
  els.settings.classList.add("hidden");
});

els.voiceToggle.addEventListener("change", () => {
  chrome.storage.local.set({ [VOICE_KEY]: els.voiceToggle.checked });
});
chrome.storage.local.get(VOICE_KEY).then((v) => { els.voiceToggle.checked = !!v[VOICE_KEY]; });
