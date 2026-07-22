// CDP (Chrome DevTools Protocol) helpers via chrome.debugger — the FALLBACK
// grounding/actuation path for canvas / ARIA-poor views (Oracle ADF/JET grids)
// where ref-based content-script actions don't reach.
//
// Provides: attach/detach, Page.captureScreenshot (→ data URL), and coordinate
// mouse clicks via Input.dispatchMouseEvent.
//
// ─────────────────────────────────────────────────────────────────────────────
// STUB / TODO — CDP hardening (see extension/README.md):
//   * A visible "Extension is debugging this tab" banner appears while attached;
//     production UX may prefer chrome.tabs.captureVisibleTab for screenshots
//     (no banner) and only attach for input. This scaffold uses CDP for both.
//   * No key-event synthesis yet (Input.dispatchKeyEvent) — typing by
//     coordinate isn't implemented; typing goes through the content script by
//     ref. Add dispatchKeyEvent for the canvas-grid path.
//   * Attach/detach is per-step naive; a real build keeps one attachment for the
//     session and handles onDetach (user opened DevTools) by re-attaching.
// ─────────────────────────────────────────────────────────────────────────────

const PROTOCOL_VERSION = "1.3";

function sendCommand(target, method, params) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand(target, method, params || {}, (result) => {
      const err = chrome.runtime.lastError;
      if (err) reject(new Error(`${method}: ${err.message}`));
      else resolve(result);
    });
  });
}

export async function attach(tabId) {
  const target = { tabId };
  try {
    await new Promise((resolve, reject) => {
      chrome.debugger.attach(target, PROTOCOL_VERSION, () => {
        const err = chrome.runtime.lastError;
        // "Another debugger is already attached" is fine — reuse it.
        if (err && !/already attached/i.test(err.message)) reject(new Error(err.message));
        else resolve();
      });
    });
  } catch (err) {
    throw new Error(`CDP attach failed: ${err.message}`);
  }
  return target;
}

export async function detach(tabId) {
  return new Promise((resolve) => {
    chrome.debugger.detach({ tabId }, () => {
      void chrome.runtime.lastError; // ignore "not attached"
      resolve();
    });
  });
}

// Returns a PNG data URL. Attaches if needed; leaves attachment in place so a
// following coordinate click can reuse it.
export async function captureScreenshot(tabId) {
  const target = await attach(tabId);
  const { data } = await sendCommand(target, "Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  return `data:image/png;base64,${data}`;
}

// Dispatch a real mouse click at viewport coordinates (the canvas-grid path).
export async function clickAt(tabId, x, y) {
  const target = await attach(tabId);
  const base = { x, y, button: "left", clickCount: 1 };
  await sendCommand(target, "Input.dispatchMouseEvent", { type: "mouseMoved", ...base });
  await sendCommand(target, "Input.dispatchMouseEvent", { type: "mousePressed", ...base });
  await sendCommand(target, "Input.dispatchMouseEvent", { type: "mouseReleased", ...base });
  return { ok: true, detail: `CDP click at (${x}, ${y})` };
}
