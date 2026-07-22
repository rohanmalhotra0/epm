// EPM Wizard content script (classic script — content scripts can't be ES
// modules via the manifest, so this file is self-contained and imports nothing).
//
// Responsibilities:
//   1. Build an ACCESSIBILITY-TREE / DOM snapshot with stable integer `ref` ids
//      (the PRIMARY grounding per the research — the agent targets ref=42, not
//      pixels).
//   2. Execute low-level actions by ref: click / type / scroll.
//
// Screenshot capture + coordinate input are the FALLBACK and live in the
// service worker (CDP debugger), not here.
//
// ─────────────────────────────────────────────────────────────────────────────
// STUB / TODO — Oracle ADF/JET hardening (see extension/README.md):
//   * iframes: Oracle EPM renders forms/task-flows inside nested iframes. This
//     scaffold snapshots only the top document (manifest all_frames:false).
//     Real coverage needs all_frames + per-frame ref namespacing + frame
//     coordinate offsets.
//   * canvas grids: ADF/JET data grids paint to <canvas> with no ARIA — those
//     rows/cells won't appear in the tree; the agent must fall back to the
//     screenshot + coordinates path for them.
//   * virtualized rows, custom `af:`/`oj-` roles, and shadow DOM are not yet
//     mapped to stable refs.
// ─────────────────────────────────────────────────────────────────────────────

(() => {
  "use strict";

  // Mirror of common/protocol.js CS.* (kept in sync manually — content scripts
  // can't import the shared module).
  const CS = { SNAPSHOT: "cs.snapshot", ACT: "cs.act", PING: "cs.ping" };

  // ref -> Element registry, rebuilt on each snapshot. Refs are stable for the
  // window between a snapshot and the action that immediately follows it.
  let registry = new Map();
  let nextRef = 1;

  const INTERACTIVE_ROLES = new Set([
    "button", "link", "textbox", "combobox", "checkbox", "radio", "menuitem",
    "tab", "option", "switch", "searchbox", "listbox", "slider", "spinbutton",
  ]);

  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 1 || rect.height <= 1) return false;
    const style = window.getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none" || style.opacity === "0") {
      return false;
    }
    // Must intersect the viewport (the agent can scroll to reach the rest).
    return rect.bottom > 0 && rect.right > 0 &&
      rect.top < (window.innerHeight || 0) + 2000 && rect.left < (window.innerWidth || 0);
  }

  function roleOf(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {
      const t = (el.getAttribute("type") || "text").toLowerCase();
      if (["button", "submit", "reset", "image"].includes(t)) return "button";
      if (t === "checkbox") return "checkbox";
      if (t === "radio") return "radio";
      if (t === "search") return "searchbox";
      return "textbox";
    }
    return tag;
  }

  function accessibleName(el) {
    // Simplified accname: aria-label > aria-labelledby > <label for> / wrapping
    // label > placeholder > value > alt/title > trimmed text.
    const aria = el.getAttribute("aria-label");
    if (aria) return aria.trim();
    const labelledby = el.getAttribute("aria-labelledby");
    if (labelledby) {
      const text = labelledby.split(/\s+/).map((id) => {
        const n = document.getElementById(id);
        return n ? n.textContent : "";
      }).join(" ").trim();
      if (text) return text;
    }
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl && lbl.textContent.trim()) return lbl.textContent.trim();
    }
    const wrapping = el.closest("label");
    if (wrapping && wrapping.textContent.trim()) return wrapping.textContent.trim();
    const placeholder = el.getAttribute("placeholder");
    if (placeholder) return placeholder.trim();
    const alt = el.getAttribute("alt") || el.getAttribute("title");
    if (alt) return alt.trim();
    const text = (el.textContent || "").replace(/\s+/g, " ").trim();
    return text.slice(0, 120);
  }

  function shouldInclude(el) {
    const role = roleOf(el);
    if (INTERACTIVE_ROLES.has(role)) return true;
    if (el.hasAttribute("role")) return true;
    if (el.tabIndex >= 0 && el.tagName.toLowerCase() !== "body") return true;
    // A short labelled heading/cell helps the model orient.
    const tag = el.tagName.toLowerCase();
    if (["h1", "h2", "h3", "th"].includes(tag)) return true;
    if (role === "cell" || role === "gridcell" || tag === "td") return true;
    return false;
  }

  function buildSnapshot() {
    registry = new Map();
    nextRef = 1;
    const nodes = [];
    const all = document.querySelectorAll(
      "a,button,input,select,textarea,[role],[tabindex],h1,h2,h3,th,td",
    );
    for (const el of all) {
      if (!shouldInclude(el) || !isVisible(el)) continue;
      const ref = nextRef++;
      registry.set(ref, el);
      const rect = el.getBoundingClientRect();
      const node = {
        ref,
        role: roleOf(el),
        name: accessibleName(el),
        focused: el === document.activeElement,
        disabled: el.disabled === true || el.getAttribute("aria-disabled") === "true",
        rect: [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)],
      };
      const val = el.value;
      if (typeof val === "string" && val) node.value = val.slice(0, 120);
      nodes.push(node);
      if (nodes.length >= 200) break; // keep the payload sane for the scaffold
    }
    const notes = window.top !== window.self
      ? "This document is inside an iframe; nested EPM frames are not captured (scaffold)."
      : null;
    return { url: location.href, title: document.title, nodes, notes };
  }

  function setNativeValue(el, value) {
    // React/JET controlled inputs ignore a plain `.value =`; go through the
    // native setter then fire input/change so the framework's listeners run.
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(el, value); else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function execAction(action) {
    const type = action.type;
    if (type === "scroll") {
      window.scrollBy({ top: action.deltaY || 0, left: action.deltaX || 0, behavior: "smooth" });
      return { ok: true, detail: `scrolled ${action.deltaY || 0}px` };
    }
    if (type === "done" || type === "screenshot" || type === "wait" || type === "navigate") {
      // Handled by the service worker (or a no-op for the content script).
      return { ok: true, detail: `${type} handled by service worker` };
    }
    if (action.ref == null) {
      return { ok: false, detail: `content script needs a ref for '${type}' (coordinate path is CDP/service-worker)` };
    }
    const el = registry.get(action.ref);
    if (!el) return { ok: false, detail: `ref ${action.ref} not found in the current snapshot` };
    el.scrollIntoView({ block: "center", inline: "center" });
    if (type === "click") {
      el.focus?.();
      el.click();
      return { ok: true, detail: `clicked ref ${action.ref}` };
    }
    if (type === "type") {
      el.focus?.();
      if ("value" in el) setNativeValue(el, action.text ?? "");
      else el.textContent = action.text ?? "";
      return { ok: true, detail: `typed into ref ${action.ref}` };
    }
    return { ok: false, detail: `unsupported content-script action '${type}'` };
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    try {
      if (msg?.kind === CS.PING) { sendResponse({ ok: true }); return; }
      if (msg?.kind === CS.SNAPSHOT) { sendResponse(buildSnapshot()); return; }
      if (msg?.kind === CS.ACT) { sendResponse(execAction(msg.action || {})); return; }
    } catch (err) {
      sendResponse({ ok: false, detail: String(err) });
    }
    return true; // keep the channel open for the sync response above
  });
})();
