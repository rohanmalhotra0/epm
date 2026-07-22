// Site bridge — the seam that makes the extension "just work" from the EPM
// Wizard web app. Runs ONLY on the EPM Wizard origins (see manifest matches),
// at document_start, so the page can detect and drive the extension with no
// manual setup and without ever knowing the (unstable) extension id.
//
// It is a pure relay between two worlds:
//   • page  ⇄  window CustomEvents  ⇄  this content script
//   • this content script  ⇄  chrome.runtime messages  ⇄  service worker
//
// Classic content script (can't import the shared module) — the SITE.* strings
// below mirror common/protocol.js by hand.

(() => {
  "use strict";

  const SITE = {
    PING: "epmw:ping",
    CONFIGURE: "epmw:configure",
    LAUNCH: "epmw:launch",
    READY: "epmw:extension",
  };

  const version = chrome.runtime.getManifest().version;

  // Synchronous presence marker so the page can detect the extension without
  // waiting for an event round-trip (e.g. on first paint).
  try { document.documentElement.dataset.epmwExtension = version; } catch { /* no <html> yet */ }

  function announce() {
    window.dispatchEvent(new CustomEvent(SITE.READY, { detail: { installed: true, version } }));
  }

  // Tell the SW to configure/launch; returns nothing (fire-and-forget with a
  // best-effort callback that just swallows a missing worker).
  function toWorker(kind, data) {
    try {
      chrome.runtime.sendMessage({ kind, data: data || {} }, () => void chrome.runtime.lastError);
    } catch { /* worker gone; it will rehydrate on next open */ }
  }

  window.addEventListener(SITE.PING, () => announce());

  window.addEventListener(SITE.CONFIGURE, (e) => {
    toWorker("site.configure", sanitize(e.detail));
  });

  window.addEventListener(SITE.LAUNCH, (e) => {
    toWorker("site.launch", sanitize(e.detail));
  });

  // Only forward the fields we understand — never trust arbitrary page detail.
  function sanitize(detail) {
    const d = detail || {};
    const out = {};
    if (typeof d.backendUrl === "string") out.backendUrl = d.backendUrl;
    if (typeof d.projectId === "string") out.projectId = d.projectId;
    if (typeof d.goal === "string") out.goal = d.goal.slice(0, 2000);
    return out;
  }

  // Announce now and once the DOM is ready (covers listeners attached late).
  announce();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", announce, { once: true });
  }
})();
