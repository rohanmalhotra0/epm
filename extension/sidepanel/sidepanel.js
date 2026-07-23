// EPM Wizard side panel — the "watch it work" surface.
//
// Connects to the service worker over a long-lived Port, streams the agent's
// step-by-step narration, shows the current plan/action, and drives
// Start / Pause / Resume / Stop. Optional voice narration via the browser's
// SpeechSynthesis API (mirrors the main app's Web Speech TTS — no backend TTS).

import { CMD, EVT, PANEL_PORT, PROD_BACKEND_URL, STATUS } from "../common/protocol.js";
import { initInspector } from "./inspector.js";
import { requestCurrentSiteAccess } from "./permissions.js";

const $ = (id) => document.getElementById(id);
const els = {
  accessView: $("accessView"), workspace: $("workspace"),
  oauthStep: $("oauthStep"), epmStep: $("epmStep"),
  oauthProgress: $("oauthProgress"), epmProgress: $("epmProgress"),
  signInAccess: $("signInAccess"), checkAccess: $("checkAccess"),
  oauthStatus: $("oauthStatus"), epmStatus: $("epmStatus"),
  accessBackendUrl: $("accessBackendUrl"), saveAccessServer: $("saveAccessServer"),
  credentialsFile: $("credentialsFile"), loadCredentials: $("loadCredentials"),
  epmBaseUrl: $("epmBaseUrl"), epmAuthMode: $("epmAuthMode"),
  epmTokenUrlWrap: $("epmTokenUrlWrap"), epmTokenUrl: $("epmTokenUrl"),
  epmIdentityLabel: $("epmIdentityLabel"), epmIdentity: $("epmIdentity"),
  epmApplication: $("epmApplication"), epmSecretLabel: $("epmSecretLabel"),
  epmSecret: $("epmSecret"), epmClassification: $("epmClassification"),
  epmScopeWrap: $("epmScopeWrap"), epmScope: $("epmScope"),
  epmRemember: $("epmRemember"), epmRememberLabel: $("epmRememberLabel"),
  connectEpm: $("connectEpm"), accountSummary: $("accountSummary"),
  statusDot: $("statusDot"), statusText: $("statusText"),
  settings: $("settings"), settingsToggle: $("settingsToggle"),
  backendUrl: $("backendUrl"), projectId: $("projectId"), apiToken: $("apiToken"),
  voiceToggle: $("voiceToggle"), guardToggle: $("guardToggle"), saveConfig: $("saveConfig"),
  testConn: $("testConn"), signIn: $("signIn"), connStatus: $("connStatus"),
  sitePermission: $("sitePermission"), sitePermissionStatus: $("sitePermissionStatus"),
  canvasPermission: $("canvasPermission"), canvasPermissionStatus: $("canvasPermissionStatus"),
  goal: $("goal"), startBtn: $("startBtn"), pauseBtn: $("pauseBtn"),
  resumeBtn: $("resumeBtn"), stopBtn: $("stopBtn"),
  feed: $("feed"), emptyHint: $("emptyHint"),
  thinking: $("thinking"), thinkingText: $("thinkingText"),
  stepCount: $("stepCount"),
  confirm: $("confirm"), confirmReason: $("confirmReason"), confirmDetail: $("confirmDetail"),
  confirmTitleText: $("confirmTitleText"),
  approveBtn: $("approveBtn"), rejectBtn: $("rejectBtn"),
  tabAgent: $("tabAgent"), tabInspect: $("tabInspect"),
  agentView: $("agentView"), inspectView: $("inspectView"),
  workbookContextBar: $("workbookContextBar"),
  workbookContextName: $("workbookContextName"),
  workbookContextDetail: $("workbookContextDetail"),
  clearWorkbookContext: $("clearWorkbookContext"),
};

let port = connect();
let renderedSteps = 0;
let thinkingBuffer = "";
let pendingConfirmId = null; // id of the destructive action currently held
let pendingConfirmMode = null; // "action" | "origin"
let pendingOriginChange = null;
let confirmReturnFocus = null;
let currentConfig = {};      // last config from the service worker
let currentWorkbookContext = null;
let accessState = { stage: "checking" };
let accessPoll = null;
const VOICE_KEY = "epmw.voice";

// The workbook inspector reads the backend URL from live config (falling back to
// whatever is typed in the settings field).
const inspector = initInspector({
  getConfig: () => ({
    backendUrl: currentConfig.backendUrl || els.backendUrl.value.trim(),
    apiToken: currentConfig.apiToken || els.apiToken.value.trim(),
  }),
  onWorkbookContext: (workbookContext) => {
    applyWorkbookContext(workbookContext);
    send(CMD.SET_WORKBOOK_CONTEXT, { workbookContext });
  },
});

function connect() {
  const p = chrome.runtime.connect({ name: PANEL_PORT });
  p.onMessage.addListener(onMessage);
  // MV3 can recycle the service worker; reconnect so the panel keeps working.
  p.onDisconnect.addListener(() => { setTimeout(() => { port = connect(); }, 400); });
  p.postMessage({ cmd: CMD.GET_STATE });
  p.postMessage({ cmd: CMD.CHECK_ACCESS });
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
    case EVT.ORIGIN_CONFIRM: onOriginConfirmRequest(data); break;
    case EVT.ORIGIN_UPDATED:
      appendLine(data.ok ? `Backend changed to ${data.backendUrl}.` : data.detail, data.ok ? "log" : "error");
      break;
    case EVT.CONN: onConnResult(data); break;
    case EVT.ACCESS: onAccessState(data); break;
    default: break;
  }
}

function applyState(state) {
  setStatus(state.status);
  if (state.config) {
    currentConfig = state.config;
    els.backendUrl.value = state.config.backendUrl || "";
    els.accessBackendUrl.value = state.config.backendUrl || "";
    els.projectId.value = state.config.projectId || "";
    els.apiToken.value = state.config.apiToken || "";
    els.guardToggle.checked = state.config.enforceGuardrails !== false;
    renderCanvasControl(state.config);
  }
  // Re-render the persisted steps (e.g. after a worker restart / panel reopen).
  if (Array.isArray(state.steps)) {
    if (state.steps.length < renderedSteps) resetFeed();
    for (let i = renderedSteps; i < state.steps.length; i++) renderStep(state.steps[i]);
  }
  // Prefill the goal — a run's goal, or one handed over by the web app.
  if (!els.goal.value) els.goal.value = state.goal || state.pendingGoal || "";
  applyWorkbookContext(state.workbookContext || null);
  if (state.pendingOriginChange) onOriginConfirmRequest(state.pendingOriginChange);
}

function applyWorkbookContext(context) {
  currentWorkbookContext = context || null;
  els.workbookContextBar.classList.toggle("hidden", !currentWorkbookContext);
  if (!currentWorkbookContext) {
    els.workbookContextName.textContent = "";
    els.workbookContextDetail.textContent = "";
    inspector?.showStoredContext(null);
    return;
  }

  els.workbookContextName.textContent = currentWorkbookContext.filename || "workbook";
  const counts = [
    `${currentWorkbookContext.sheetCount || 0} sheet${currentWorkbookContext.sheetCount === 1 ? "" : "s"}`,
    currentWorkbookContext.moduleCount
      ? `${currentWorkbookContext.moduleCount} VBA module${currentWorkbookContext.moduleCount === 1 ? "" : "s"}`
      : "no VBA modules",
    `${currentWorkbookContext.formulaCount || 0} extracted formula${currentWorkbookContext.formulaCount === 1 ? "" : "s"}`,
  ];
  els.workbookContextDetail.textContent =
    `Sent to the AI on every step · ${counts.join(" · ")}`
    + (currentWorkbookContext.truncated ? " · later sheet details capped" : "");
  inspector?.showStoredContext(currentWorkbookContext);
}

// ── mandatory Google OAuth → Oracle EPM onboarding ───────────────────────────
function showInlineStatus(element, kind, message) {
  element.textContent = message || "";
  element.className = `inline-status ${kind}`;
  element.classList.toggle("hidden", !message);
}

function setAccessBusy(message, target = els.oauthStatus) {
  showInlineStatus(target, "pending", message);
  els.checkAccess.disabled = true;
  els.signInAccess.disabled = true;
  els.connectEpm.disabled = true;
}

function clearAccessBusy() {
  els.checkAccess.disabled = false;
  els.signInAccess.disabled = false;
  els.connectEpm.disabled = false;
}

function checkMandatoryAccess(message = "Checking your access…") {
  setAccessBusy(message, accessState.stage === "epm" ? els.epmStatus : els.oauthStatus);
  send(CMD.CHECK_ACCESS);
}

function stopAccessPolling() {
  if (accessPoll != null) {
    clearInterval(accessPoll);
    accessPoll = null;
  }
}

function startAccessPolling() {
  stopAccessPolling();
  accessPoll = setInterval(() => send(CMD.CHECK_ACCESS), 1500);
  setTimeout(stopAccessPolling, 120000);
}

function onAccessState(next) {
  accessState = next || { stage: "error", message: "Could not check access." };
  clearAccessBusy();

  if (accessState.stage === "ready") {
    stopAccessPolling();
    els.accessView.classList.add("hidden");
    els.workspace.classList.remove("hidden");
    els.epmSecret.value = "";
    els.accountSummary.textContent = [
      accessState.owner && accessState.owner !== "local" ? accessState.owner : "EPM Wizard signed in",
      accessState.environmentName || "Oracle EPM connected",
      accessState.application || "",
    ].filter(Boolean).join(" · ");
    showInlineStatus(els.epmStatus, "ok", accessState.message || "Oracle EPM connected.");
    return;
  }

  els.workspace.classList.add("hidden");
  els.accessView.classList.remove("hidden");

  const showEpm = accessState.stage === "epm";
  els.oauthStep.classList.toggle("hidden", showEpm);
  els.epmStep.classList.toggle("hidden", !showEpm);
  els.oauthProgress.className = showEpm ? "complete" : "active";
  els.epmProgress.className = showEpm ? "active" : "";

  if (showEpm) {
    stopAccessPolling();
    showInlineStatus(
      els.epmStatus,
      accessState.error ? "err" : "ok",
      accessState.error
        ? accessState.message
        : `${accessState.owner && accessState.owner !== "local" ? `${accessState.owner} verified. ` : ""}${accessState.message || ""}`,
    );
    els.epmBaseUrl.focus();
    return;
  }

  const isError = accessState.stage === "error" || accessState.error;
  showInlineStatus(els.oauthStatus, isError ? "err" : "", accessState.message || "Sign in to continue.");
}

function normalizeBackendForUi(value) {
  let parsed;
  try {
    parsed = new URL(String(value || "").trim());
  } catch {
    throw new Error("Enter a complete EPM Wizard URL, including https://.");
  }
  const loopback = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
  if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && loopback)) {
    throw new Error("Use HTTPS, or HTTP only for localhost/127.0.0.1 development.");
  }
  if (
    parsed.username
    || parsed.password
    || parsed.pathname !== "/"
    || parsed.search
    || parsed.hash
  ) {
    throw new Error("The Server URL must be an origin without credentials, a path, query, or fragment.");
  }
  return parsed.origin;
}

async function ensureBackendAccess(value) {
  const backendUrl = normalizeBackendForUi(value);
  const origins = [`${backendUrl}/*`];
  if (!(await chrome.permissions.contains({ origins }))) {
    const granted = await chrome.permissions.request({ origins });
    if (!granted) throw new Error(`Chrome access to ${backendUrl} was not granted.`);
  }
  return backendUrl;
}

function websiteAppUrl() {
  const base = normalizeBackendForUi(
    els.accessBackendUrl.value.trim()
    || els.backendUrl.value.trim()
    || currentConfig.backendUrl
    || PROD_BACKEND_URL,
  );
  return `${base}/app`;
}

function openWebsiteSignIn() {
  let url;
  try {
    url = websiteAppUrl();
  } catch (error) {
    showInlineStatus(els.oauthStatus, "err", error.message);
    return;
  }
  chrome.tabs.create({ url });
  showInlineStatus(els.oauthStatus, "pending", "Finish signing in in the new tab. This panel will continue automatically.");
  startAccessPolling();
}

function setEpmAuthMode() {
  const oauth = els.epmAuthMode.value === "oauth";
  els.epmTokenUrlWrap.classList.toggle("hidden", !oauth);
  els.epmScopeWrap.classList.toggle("hidden", !oauth);
  els.epmIdentityLabel.textContent = oauth ? "Client ID" : "Username";
  els.epmIdentity.placeholder = oauth ? "confidential application client ID" : "you@example.com";
  els.epmIdentity.autocomplete = oauth ? "off" : "username";
  els.epmSecretLabel.textContent = oauth ? "Client secret" : "Password";
  els.epmSecret.autocomplete = oauth ? "off" : "current-password";
  els.epmRememberLabel.textContent = `Remember ${oauth ? "client secret" : "password"} on this machine (encrypted local store)`;
  showInlineStatus(els.epmStatus, "", "");
}

function applyCredentialsText(text) {
  const data = {};
  for (const raw of String(text || "").split("\n")) {
    const match = raw.trim().match(/^([A-Z_]+)=(.+)$/);
    if (match) data[match[1]] = match[2];
  }
  if (data.INSTANCE) els.epmBaseUrl.value = data.INSTANCE;
  if (data.USERNAME) els.epmIdentity.value = data.USERNAME;
  if (data.PASSWORD) els.epmSecret.value = data.PASSWORD;
  if (data.TOKEN_URL || data.CLIENT_ID) {
    els.epmAuthMode.value = "oauth";
    setEpmAuthMode();
  }
  if (data.TOKEN_URL) els.epmTokenUrl.value = data.TOKEN_URL;
  if (data.CLIENT_ID) els.epmIdentity.value = data.CLIENT_ID;
  if (data.CLIENT_SECRET) els.epmSecret.value = data.CLIENT_SECRET;
  if (data.SCOPE) els.epmScope.value = data.SCOPE;
  showInlineStatus(els.epmStatus, "ok", "Credentials loaded. Review them, then connect.");
}

async function readCredentialsFile(file) {
  if (!file || !file.name.toLowerCase().endsWith(".txt")) {
    showInlineStatus(els.epmStatus, "err", "Choose a .txt credentials file.");
    return;
  }
  applyCredentialsText(await file.text());
}

function currentEpmCredentials() {
  const oauth = els.epmAuthMode.value === "oauth";
  return {
    authMode: oauth ? "oauth" : "password",
    baseUrl: els.epmBaseUrl.value.trim(),
    username: oauth ? "" : els.epmIdentity.value.trim(),
    password: oauth ? "" : els.epmSecret.value,
    tokenUrl: oauth ? els.epmTokenUrl.value.trim() : "",
    clientId: oauth ? els.epmIdentity.value.trim() : "",
    clientSecret: oauth ? els.epmSecret.value : "",
    scope: oauth ? els.epmScope.value.trim() : "",
    application: els.epmApplication.value.trim(),
    classification: els.epmClassification.value,
    remember: els.epmRemember.checked,
  };
}

els.signInAccess.addEventListener("click", openWebsiteSignIn);
els.checkAccess.addEventListener("click", () => checkMandatoryAccess("Verifying your EPM Wizard sign-in…"));
els.saveAccessServer.addEventListener("click", async () => {
  try {
    const backendUrl = await ensureBackendAccess(els.accessBackendUrl.value);
    currentConfig = { ...currentConfig, backendUrl };
    els.accessBackendUrl.value = backendUrl;
    els.backendUrl.value = backendUrl;
    send(CMD.SET_CONFIG, { backendUrl });
    checkMandatoryAccess("Checking the selected EPM Wizard server…");
  } catch (error) {
    showInlineStatus(els.oauthStatus, "err", error.message);
    return;
  }
});
els.epmAuthMode.addEventListener("change", setEpmAuthMode);
els.loadCredentials.addEventListener("click", () => els.credentialsFile.click());
els.credentialsFile.addEventListener("change", async () => {
  await readCredentialsFile(els.credentialsFile.files?.[0]);
  els.credentialsFile.value = "";
});
els.epmStep.addEventListener("dragover", (event) => {
  event.preventDefault();
  els.epmStep.closest(".auth-shell")?.classList.add("drag-active");
});
els.epmStep.addEventListener("dragleave", () => {
  els.epmStep.closest(".auth-shell")?.classList.remove("drag-active");
});
els.epmStep.addEventListener("drop", async (event) => {
  event.preventDefault();
  els.epmStep.closest(".auth-shell")?.classList.remove("drag-active");
  await readCredentialsFile(event.dataTransfer?.files?.[0]);
});
els.epmStep.addEventListener("submit", (event) => {
  event.preventDefault();
  setAccessBusy("Connecting securely to Oracle EPM…", els.epmStatus);
  send(CMD.CONNECT_EPM, currentEpmCredentials());
});
setEpmAuthMode();

// ── enforced-guardrail confirmation ──────────────────────────────────────────
function onConfirmRequest({ id, reason, label, action }) {
  pendingConfirmId = id;
  pendingConfirmMode = "action";
  pendingOriginChange = null;
  els.confirmTitleText.textContent = "Confirm before it runs";
  els.rejectBtn.textContent = "Skip";
  els.approveBtn.textContent = "Approve & run";
  els.confirmReason.textContent = reason || "This action was flagged as risky.";
  els.confirmDetail.textContent = describeAction(action || {}) + (label ? ` · “${label}”` : "");
  showConfirmDialog();
  hideThinking();
  if (els.voiceToggle.checked) speak("Confirmation needed. " + (reason || ""));
}

function onOriginConfirmRequest(request) {
  if (!request?.backendUrl) return;
  pendingConfirmId = null;
  pendingConfirmMode = "origin";
  pendingOriginChange = request;
  els.confirmTitleText.textContent = "Approve backend change";
  els.rejectBtn.textContent = "Keep current server";
  els.approveBtn.textContent = "Use this server";
  els.confirmReason.textContent = request.reason || "A website requested a different backend.";
  els.confirmDetail.textContent = `${request.pageOrigin || "EPM Wizard"} → ${request.backendUrl}`;
  showConfirmDialog();
}

async function resolveConfirm(approve) {
  if (pendingConfirmMode === "origin" && pendingOriginChange) {
    if (approve) {
      try {
        await ensureBackendAccess(pendingOriginChange.backendUrl);
      } catch (error) {
        els.confirmReason.textContent = error.message;
        els.rejectBtn.focus();
        return;
      }
    }
    send(CMD.CONFIRM_ORIGIN, { approve });
    pendingOriginChange = null;
  } else if (pendingConfirmMode === "action" && pendingConfirmId != null) {
    send(CMD.CONFIRM, { id: pendingConfirmId, approve });
  } else {
    return;
  }
  pendingConfirmId = null;
  pendingConfirmMode = null;
  closeConfirmDialog();
}

function showConfirmDialog() {
  confirmReturnFocus = document.activeElement;
  if (typeof els.confirm.showModal === "function" && !els.confirm.open) {
    els.confirm.showModal();
  } else {
    els.confirm.setAttribute("open", "");
  }
  els.rejectBtn.focus();
}

function closeConfirmDialog() {
  if (typeof els.confirm.close === "function" && els.confirm.open) {
    els.confirm.close();
  } else {
    els.confirm.removeAttribute("open");
  }
  confirmReturnFocus?.focus?.();
  confirmReturnFocus = null;
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
  if (step.result) {
    const outcome = document.createElement("div");
    outcome.className = `acted ${step.result.ok ? "ok" : "fail"}`;
    outcome.textContent = `${step.result.ok ? "✓" : "✗"} ${step.result.detail || "Action completed."}`;
    card.appendChild(outcome);
  }

  els.feed.appendChild(card);
  els.feed.scrollTop = els.feed.scrollHeight;
  renderedSteps++;
  els.stepCount.textContent = String(renderedSteps);
}

function describeAction(a) {
  switch (a.type) {
    case "click": return a.ref != null ? `click ref=${a.ref}` : `click (${a.x}, ${a.y})`;
    case "type":
      return a.ref != null
        ? `type ${JSON.stringify(a.text ?? "")} → ref=${a.ref}`
        : `type ${JSON.stringify(a.text ?? "")} at (${a.x}, ${a.y})`;
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
  if (!confirming && pendingConfirmMode === "action") {
    pendingConfirmId = null;
    pendingConfirmMode = null;
    closeConfirmDialog();
  }
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
els.clearWorkbookContext.addEventListener("click", () => {
  applyWorkbookContext(null);
  send(CMD.CLEAR_WORKBOOK_CONTEXT);
});

els.approveBtn.addEventListener("click", () => resolveConfirm(true));
els.rejectBtn.addEventListener("click", () => resolveConfirm(false));
els.confirm.addEventListener("cancel", (event) => {
  event.preventDefault();
  resolveConfirm(false);
});

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

function currentSettings(backendUrl = els.backendUrl.value.trim()) {
  return {
    backendUrl,
    projectId: els.projectId.value.trim(),
    apiToken: els.apiToken.value.trim(),
    enforceGuardrails: els.guardToggle.checked,
  };
}

els.saveConfig.addEventListener("click", async () => {
  try {
    const backendUrl = await ensureBackendAccess(els.backendUrl.value);
    els.backendUrl.value = backendUrl;
    send(CMD.SET_CONFIG, currentSettings(backendUrl));
    els.settings.classList.add("hidden");
  } catch (error) {
    showConn("err", error.message);
  }
});

// Test connection: save first (so the SW tests the fields as shown), then probe.
els.testConn.addEventListener("click", async () => {
  try {
    const backendUrl = await ensureBackendAccess(els.backendUrl.value);
    els.backendUrl.value = backendUrl;
    send(CMD.SET_CONFIG, currentSettings(backendUrl));
    showConn("pending", "Testing connection…");
    send(CMD.TEST_CONNECTION);
  } catch (error) {
    showConn("err", error.message);
  }
});

// Open the protected app path (not the public landing page), which initiates
// the same Google OAuth flow used by the website.
els.signIn.addEventListener("click", () => {
  chrome.tabs.create({ url: websiteAppUrl() });
});

function showConn(kind, message) {
  els.connStatus.textContent = message;
  els.connStatus.className = "conn-status " + kind;
}

function onConnResult(result) {
  showConn(result.ok ? "ok" : "err", result.message || (result.ok ? "Connected." : "Connection failed."));
}

els.voiceToggle.addEventListener("change", () => {
  chrome.storage.local.set({ [VOICE_KEY]: els.voiceToggle.checked });
});
chrome.storage.local.get(VOICE_KEY).then((v) => { els.voiceToggle.checked = !!v[VOICE_KEY]; });

function renderCanvasControl(config = currentConfig) {
  const enabled = config?.canvasControlEnabled === true;
  els.canvasPermission.disabled = false;
  els.canvasPermission.textContent = enabled ? "Disable canvas control" : "Enable canvas control";
  els.canvasPermission.setAttribute("aria-pressed", String(enabled));
  showInlineStatus(
    els.canvasPermissionStatus,
    enabled ? "ok" : "pending",
    enabled
      ? "Canvas control is on. Chrome shows its debugger notice only while EPM Wizard is attached to a page."
      : "Canvas control is off. No debugger session is attached.",
  );
}

// The only runtime permission prompt is an exact current-origin host grant.
els.sitePermission.addEventListener("click", async () => {
  try {
    els.sitePermission.disabled = true;
    showInlineStatus(els.sitePermissionStatus, "pending", "Checking the current Oracle page…");
    const result = await requestCurrentSiteAccess(chrome);
    if (result.pendingBrowserApproval) {
      showInlineStatus(
        els.sitePermissionStatus,
        "pending",
        "Chrome is showing a site-access request in the address bar. Approve it there, then click this button again to verify access.",
      );
      return;
    }
    showInlineStatus(
      els.sitePermissionStatus,
      result.granted ? "ok" : "err",
      result.granted
        ? `Access granted only for ${result.origin}.`
        : `Chrome did not grant access to ${result.origin}. No page access was added.`,
    );
  } catch (error) {
    showInlineStatus(els.sitePermissionStatus, "err", error.message || "Could not request site access.");
  } finally {
    els.sitePermission.disabled = false;
  }
});

els.canvasPermission.addEventListener("click", async () => {
  try {
    const enabled = currentConfig.canvasControlEnabled !== true;
    if (enabled && !(await chrome.permissions.contains({ permissions: ["debugger"] }))) {
      throw new Error("Chrome has not granted the debugger permission required for trusted canvas input.");
    }
    els.canvasPermission.disabled = true;
    showInlineStatus(
      els.canvasPermissionStatus,
      "pending",
      enabled ? "Enabling trusted canvas input…" : "Disabling canvas input and detaching…",
    );
    send(CMD.SET_CANVAS_CONTROL, { enabled });
  } catch (error) {
    els.canvasPermission.disabled = false;
    showInlineStatus(els.canvasPermissionStatus, "err", error.message || "Could not enable canvas control.");
  }
});

chrome.permissions.contains({ permissions: ["debugger"] }).then((granted) => {
  if (granted) return;
  els.canvasPermission.disabled = true;
  showInlineStatus(
    els.canvasPermissionStatus,
    "err",
    "Chrome has not granted the debugger permission. Re-enable the extension and accept its requested permissions.",
  );
});
