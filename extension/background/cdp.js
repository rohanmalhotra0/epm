// Chrome DevTools Protocol helpers for Oracle canvas/ARIA-poor controls.
//
// Ref-based DOM actions remain preferred. CDP is used only for the fallback
// path: a bounded, compressed screenshot and coordinate mouse/keyboard input.

const PROTOCOL_VERSION = "1.3";
const DEFAULT_MAX_DIMENSION = 1280;
const DEFAULT_JPEG_QUALITY = 72;
const screenshotHashes = new Map();

function sendCommand(target, method, params) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand(target, method, params || {}, (result) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(`${method}: ${error.message}`));
      else resolve(result);
    });
  });
}

export async function attach(tabId) {
  const target = { tabId };
  try {
    await new Promise((resolve, reject) => {
      chrome.debugger.attach(target, PROTOCOL_VERSION, () => {
        const error = chrome.runtime.lastError;
        if (error && !/already attached/i.test(error.message)) reject(new Error(error.message));
        else resolve();
      });
    });
  } catch (error) {
    throw new Error(`CDP attach failed: ${error.message}`);
  }
  return target;
}

export async function detach(tabId) {
  screenshotHashes.delete(tabId);
  return new Promise((resolve) => {
    chrome.debugger.detach({ tabId }, () => {
      void chrome.runtime.lastError;
      resolve();
    });
  });
}

export function hashImageData(data) {
  // Fast FNV-1a over the base64 payload. This is not a security primitive; it
  // only prevents resending an identical screenshot on consecutive turns.
  let hash = 0x811c9dc5;
  for (let index = 0; index < data.length; index += 1) {
    hash ^= data.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function imageDimensions(data, format) {
  try {
    const binary = atob(data);
    const byte = (index) => binary.charCodeAt(index) & 0xff;
    if (format === "png" && binary.length >= 24) {
      const read32 = (index) => (
        ((byte(index) << 24) >>> 0) +
        (byte(index + 1) << 16) +
        (byte(index + 2) << 8) +
        byte(index + 3)
      );
      return { width: read32(16), height: read32(20) };
    }
    if (format === "jpeg" && byte(0) === 0xff && byte(1) === 0xd8) {
      let offset = 2;
      while (offset + 8 < binary.length) {
        if (byte(offset) !== 0xff) {
          offset += 1;
          continue;
        }
        const marker = byte(offset + 1);
        const size = (byte(offset + 2) << 8) + byte(offset + 3);
        if (
          [0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]
            .includes(marker)
        ) {
          return {
            height: (byte(offset + 5) << 8) + byte(offset + 6),
            width: (byte(offset + 7) << 8) + byte(offset + 8),
          };
        }
        if (size < 2) break;
        offset += 2 + size;
      }
    }
  } catch {
    // Fall through to the layout-derived dimensions.
  }
  return null;
}

export function normalizeCoordinates(x, y, options = {}) {
  const metadata = options.screenshotMeta || options;
  const viewportWidth = Number(metadata.viewportWidth || metadata.width || 0);
  const viewportHeight = Number(metadata.viewportHeight || metadata.height || 0);
  const imageWidth = Number(metadata.imageWidth || 0);
  const imageHeight = Number(metadata.imageHeight || 0);
  const offsetX = Number(options.frameOffset?.x || metadata.frameOffsetX || 0);
  const offsetY = Number(options.frameOffset?.y || metadata.frameOffsetY || 0);
  const coordinateSpace = options.coordinateSpace || metadata.coordinateSpace || "css";

  let cssX = Number(x);
  let cssY = Number(y);
  if (
    coordinateSpace === "image" &&
    viewportWidth > 0 && viewportHeight > 0 &&
    imageWidth > 0 && imageHeight > 0
  ) {
    cssX *= viewportWidth / imageWidth;
    cssY *= viewportHeight / imageHeight;
  }
  cssX += offsetX;
  cssY += offsetY;

  if (!Number.isFinite(cssX) || !Number.isFinite(cssY)) {
    throw new TypeError("coordinate input requires finite x/y values");
  }
  if (viewportWidth > 0) cssX = Math.min(Math.max(0, cssX), Math.max(0, viewportWidth - 1));
  if (viewportHeight > 0) cssY = Math.min(Math.max(0, cssY), Math.max(0, viewportHeight - 1));
  return { x: Math.round(cssX), y: Math.round(cssY) };
}

async function viewportMetrics(target) {
  const metrics = await sendCommand(target, "Page.getLayoutMetrics");
  const viewport = metrics.cssVisualViewport || metrics.cssLayoutViewport || {};
  let deviceScaleFactor = 1;
  try {
    const result = await sendCommand(target, "Runtime.evaluate", {
      expression: "window.devicePixelRatio || 1",
      returnByValue: true,
    });
    deviceScaleFactor = Number(result?.result?.value) || 1;
  } catch {
    // Screenshot coordinate normalization remains valid through the explicit
    // image and viewport dimensions even if Runtime is unavailable.
  }
  return {
    viewportWidth: Math.max(1, Number(viewport.clientWidth) || 1),
    viewportHeight: Math.max(1, Number(viewport.clientHeight) || 1),
    pageX: Number(viewport.pageX) || 0,
    pageY: Number(viewport.pageY) || 0,
    deviceScaleFactor,
  };
}

// Default return value remains a data URL for backward compatibility. Pass
// `{ withMetadata: true }` to receive { dataUrl, metadata }; pass
// `{ deduplicate: true }` as well and a repeated image has dataUrl:null.
export async function captureScreenshot(tabId, options = {}) {
  const target = await attach(tabId);
  const viewport = await viewportMetrics(target);
  const maxDimension = Math.max(
    320,
    Number(options.maxDimension || options.maxWidth) || DEFAULT_MAX_DIMENSION,
  );
  const scale = Math.min(
    1,
    maxDimension / Math.max(viewport.viewportWidth, viewport.viewportHeight),
  );
  const format = options.format === "png" ? "png" : "jpeg";
  const quality = Math.min(90, Math.max(35, Number(options.quality) || DEFAULT_JPEG_QUALITY));
  const params = {
    format,
    captureBeyondViewport: false,
    fromSurface: true,
    optimizeForSpeed: true,
    clip: {
      x: viewport.pageX,
      y: viewport.pageY,
      width: viewport.viewportWidth,
      height: viewport.viewportHeight,
      scale,
    },
  };
  if (format === "jpeg") params.quality = quality;
  let response;
  try {
    response = await sendCommand(target, "Page.captureScreenshot", params);
  } catch (error) {
    // Older supported Chromium builds may not recognize optimizeForSpeed.
    if (!/invalid|parameter/i.test(error.message)) throw error;
    delete params.optimizeForSpeed;
    response = await sendCommand(target, "Page.captureScreenshot", params);
  }
  const { data } = response;
  const hash = hashImageData(data);
  const duplicate = screenshotHashes.get(tabId) === hash;
  screenshotHashes.set(tabId, hash);

  const measuredDimensions = imageDimensions(data, format);
  const imageWidth = measuredDimensions?.width ||
    Math.max(1, Math.round(viewport.viewportWidth * scale));
  const imageHeight = measuredDimensions?.height ||
    Math.max(1, Math.round(viewport.viewportHeight * scale));
  const metadata = {
    format,
    quality: format === "jpeg" ? quality : undefined,
    hash,
    duplicate,
    coordinateSpace: "image",
    imageWidth,
    imageHeight,
    viewportWidth: viewport.viewportWidth,
    viewportHeight: viewport.viewportHeight,
    deviceScaleFactor: viewport.deviceScaleFactor,
    scale,
    bytes: Math.floor(data.length * 0.75) - (data.endsWith("==") ? 2 : data.endsWith("=") ? 1 : 0),
  };
  const dataUrl = `data:image/${format};base64,${data}`;
  if (!options.withMetadata) return dataUrl;
  return {
    dataUrl: duplicate && options.deduplicate ? null : dataUrl,
    meta: metadata,
    metadata,
  };
}

async function dispatchClick(target, x, y) {
  const base = { x, y, button: "left", clickCount: 1 };
  await sendCommand(target, "Input.dispatchMouseEvent", { type: "mouseMoved", ...base });
  await sendCommand(target, "Input.dispatchMouseEvent", { type: "mousePressed", ...base });
  await sendCommand(target, "Input.dispatchMouseEvent", { type: "mouseReleased", ...base });
}

// Dispatch a real mouse click at CSS viewport coordinates. If coordinates came
// from the bounded image, set coordinateSpace:"image" and pass screenshotMeta.
export async function clickAt(tabId, x, y, options = {}) {
  const target = await attach(tabId);
  const point = normalizeCoordinates(x, y, options);
  await dispatchClick(target, point.x, point.y);
  return { ok: true, detail: `CDP click at (${point.x}, ${point.y})`, point };
}

export async function pressKey(tabId, key, options = {}) {
  const target = await attach(tabId);
  key = String(key || "");
  if (!key) throw new TypeError("key is required");
  const modifiers = Number(options.modifiers) || 0;
  const code = options.code || key;
  const text = options.text ?? (key.length === 1 ? key : undefined);
  const commonVirtualKeys = {
    Backspace: 8,
    Tab: 9,
    Enter: 13,
    Escape: 27,
    ArrowLeft: 37,
    ArrowUp: 38,
    ArrowRight: 39,
    ArrowDown: 40,
    Delete: 46,
  };
  const base = {
    key,
    code,
    modifiers,
    windowsVirtualKeyCode: Number(options.windowsVirtualKeyCode) || commonVirtualKeys[key] || 0,
    nativeVirtualKeyCode: Number(options.nativeVirtualKeyCode) || commonVirtualKeys[key] || 0,
  };
  await sendCommand(target, "Input.dispatchKeyEvent", { type: "keyDown", ...base, text });
  await sendCommand(target, "Input.dispatchKeyEvent", { type: "keyUp", ...base });
  return { ok: true, detail: `CDP key '${key}'` };
}

// Focus a coordinate (typically a canvas cell), then insert Unicode text. CDP's
// Input.insertText behaves like IME/paste input and is more reliable than
// synthesizing a key pair for every character. Enter/Tab can be committed with
// `options.commitKey`.
export async function typeAt(tabId, x, y, text, options = {}) {
  const target = await attach(tabId);
  const point = normalizeCoordinates(x, y, options);
  await dispatchClick(target, point.x, point.y);
  await sendCommand(target, "Input.insertText", { text: String(text ?? "") });
  if (options.commitKey) await pressKey(tabId, options.commitKey);
  return {
    ok: true,
    detail: `CDP typed ${String(text ?? "").length} character(s) at (${point.x}, ${point.y})`,
    point,
  };
}
