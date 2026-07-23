// Oracle-aware page adapter for the EPM Wizard Chrome extension.
//
// This remains a classic, self-contained content script because MV3 manifest
// content scripts cannot import the extension's ES modules. It deliberately
// exposes a small isolated-world API as `globalThis.__epmwAgent` so the service
// worker can execute it in every frame with chrome.scripting.executeScript,
// aggregate the results, namespace refs with Chrome frame ids, and route the
// next action back to the frame that produced the ref.

(() => {
  "use strict";

  const API_VERSION = 2;
  if (globalThis.__epmwAgent?.version === API_VERSION) return;

  // Mirror of common/protocol.js CS.*.
  const CS = { SNAPSHOT: "cs.snapshot", ACT: "cs.act", PING: "cs.ping" };
  const MAX_NODES = 400;
  const MAX_VISITED_ELEMENTS = 50_000;

  // Element refs stay stable for the lifetime of an element, rather than being
  // renumbered on every snapshot. Refs are local to a frame. The service worker
  // owns the global frame-id namespace because only it knows Chrome frame ids.
  let registry = new Map();
  const refByElement = new WeakMap();
  let nextRef = 1;

  const INTERACTIVE_ROLES = new Set([
    "button", "link", "textbox", "combobox", "checkbox", "radio", "menuitem",
    "tab", "option", "switch", "searchbox", "listbox", "slider", "spinbutton",
    "treeitem",
  ]);

  const ORIENTATION_ROLES = new Set([
    "grid", "table", "treegrid", "row", "rowgroup", "gridcell", "cell",
    "columnheader", "rowheader",
  ]);

  const JET_ROLE = new Map([
    ["oj-button", "button"],
    ["oj-c-button", "button"],
    ["oj-input-text", "textbox"],
    ["oj-c-input-text", "textbox"],
    ["oj-input-password", "textbox"],
    ["oj-text-area", "textbox"],
    ["oj-input-number", "spinbutton"],
    ["oj-slider", "slider"],
    ["oj-switch", "switch"],
    ["oj-checkboxset", "group"],
    ["oj-radioset", "radiogroup"],
    ["oj-select-single", "combobox"],
    ["oj-select-many", "combobox"],
    ["oj-combobox-one", "combobox"],
    ["oj-combobox-many", "combobox"],
    ["oj-menu", "menu"],
    ["oj-menu-button", "button"],
    ["oj-tab-bar", "tablist"],
    ["oj-navigation-list", "navigation"],
    ["oj-tree-view", "tree"],
    ["oj-table", "grid"],
    ["oj-data-grid", "grid"],
    ["oj-c-table", "grid"],
    ["oj-list-view", "listbox"],
    ["oj-dialog", "dialog"],
    ["oj-popup", "dialog"],
  ]);

  function tagNameOf(el) {
    return String(el?.tagName || "").toLowerCase();
  }

  function classText(el) {
    if (typeof el?.className === "string") return el.className;
    return el?.getAttribute?.("class") || "";
  }

  function oracleComponentOf(el) {
    const tag = tagNameOf(el);
    if (tag.startsWith("oj-")) return tag;
    const classes = classText(el);
    const jet = classes.match(/\boj-(?:c-)?[\w-]+/i);
    if (jet) return jet[0].toLowerCase();
    if (
      el?.hasAttribute?.("data-afr-rk") ||
      el?.hasAttribute?.("data-afr-fid") ||
      /\b(?:AF|af_)(?:Button|Input|Table|Tree|Panel|Select|Command|Link|Menu|Grid)\w*/.test(classes)
    ) {
      return `adf:${tag || "component"}`;
    }
    return null;
  }

  function inferredAdfRole(el) {
    const text = `${classText(el)} ${el?.getAttribute?.("data-afr-rk") || ""}`;
    if (/(?:Button|CommandButton|commandButton)/i.test(text)) return "button";
    if (/(?:CommandLink|Link)/i.test(text)) return "link";
    if (/(?:Input|TextArea|RichTextEditor)/i.test(text)) return "textbox";
    if (/(?:Select|Choice|Combo)/i.test(text)) return "combobox";
    if (/(?:CheckBox)/i.test(text)) return "checkbox";
    if (/(?:Radio)/i.test(text)) return "radio";
    if (/(?:TreeTable|DataGrid|Table)/i.test(text)) return "grid";
    if (/(?:Tree)/i.test(text)) return "tree";
    if (/(?:MenuItem)/i.test(text)) return "menuitem";
    if (/(?:Tab)/i.test(text)) return "tab";
    return null;
  }

  function roleOf(el) {
    const explicit = el?.getAttribute?.("role");
    if (explicit) return explicit.trim().split(/\s+/)[0].toLowerCase();

    const tag = tagNameOf(el);
    const jetRole = JET_ROLE.get(tag);
    if (jetRole) return jetRole;
    if (tag.startsWith("oj-")) {
      if (/button/.test(tag)) return "button";
      if (/input|text-area/.test(tag)) return "textbox";
      if (/select|combobox/.test(tag)) return "combobox";
      if (/table|data-grid/.test(tag)) return "grid";
    }
    const adfRole = inferredAdfRole(el);
    if (adfRole) return adfRole;

    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "table") return "table";
    if (tag === "tr") return "row";
    if (tag === "th") return "columnheader";
    if (tag === "td") return "cell";
    if (tag === "canvas") return "img";
    if (tag === "input") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (["button", "submit", "reset", "image"].includes(type)) return "button";
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "range") return "slider";
      if (type === "number") return "spinbutton";
      if (type === "search") return "searchbox";
      return "textbox";
    }
    return tag || "generic";
  }

  function rootById(el, id) {
    const root = el?.getRootNode?.();
    return root?.getElementById?.(id) || document.getElementById(id);
  }

  function cssEscape(value) {
    if (globalThis.CSS?.escape) return globalThis.CSS.escape(value);
    return String(value).replace(/["\\]/g, "\\$&");
  }

  function accessibleName(el) {
    const directAttributes = [
      "aria-label", "label-hint", "label", "data-afr-label", "data-label",
    ];
    for (const attr of directAttributes) {
      const value = el.getAttribute?.(attr);
      if (value?.trim()) return value.trim().slice(0, 160);
    }

    const labelledby = el.getAttribute?.("aria-labelledby");
    if (labelledby) {
      const text = labelledby.split(/\s+/)
        .map((id) => rootById(el, id)?.textContent || "")
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      if (text) return text.slice(0, 160);
    }

    if (el.id) {
      const root = el.getRootNode?.() || document;
      const label = root.querySelector?.(`label[for="${cssEscape(el.id)}"]`);
      if (label?.textContent?.trim()) return label.textContent.trim().slice(0, 160);
    }

    const wrapping = el.closest?.("label");
    if (wrapping?.textContent?.trim()) return wrapping.textContent.trim().slice(0, 160);

    for (const attr of ["placeholder", "alt", "title", "value"]) {
      const value = el.getAttribute?.(attr);
      if (value?.trim()) return value.trim().slice(0, 160);
    }

    const text = (el.textContent || "").replace(/\s+/g, " ").trim();
    return text.slice(0, 160);
  }

  function isVisible(el) {
    const rect = el.getBoundingClientRect?.();
    if (!rect || rect.width <= 1 || rect.height <= 1) return false;
    const style = globalThis.getComputedStyle?.(el);
    if (
      style &&
      (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0)
    ) {
      return false;
    }
    // Include some below-viewport content so the model can choose what to scroll
    // toward without serializing an entire virtualized Oracle table.
    return rect.bottom > -500 && rect.right > 0 &&
      rect.top < (window.innerHeight || 0) + 2000 &&
      rect.left < (window.innerWidth || 0);
  }

  function stateOf(el) {
    const state = {};
    const booleanAttributes = [
      "checked", "selected", "expanded", "pressed", "readonly", "required",
      "invalid", "busy", "hidden",
    ];
    for (const name of booleanAttributes) {
      const aria = el.getAttribute?.(`aria-${name}`);
      if (aria != null) state[name] = aria === "true" ? true : aria === "false" ? false : aria;
    }
    if (el.disabled === true || el.getAttribute?.("aria-disabled") === "true") {
      state.disabled = true;
    }
    for (const name of ["level", "posinset", "setsize", "rowindex", "colindex", "rowcount", "colcount"]) {
      const raw = el.getAttribute?.(`aria-${name}`);
      if (raw != null && raw !== "") {
        const number = Number(raw);
        state[name] = Number.isFinite(number) ? number : raw;
      }
    }
    const current = el.getAttribute?.("aria-current");
    if (current) state.current = current;
    const orientation = el.getAttribute?.("aria-orientation");
    if (orientation) state.orientation = orientation;
    return state;
  }

  function elementRef(el) {
    let ref = refByElement.get(el);
    if (!ref) {
      ref = nextRef++;
      refByElement.set(el, ref);
    }
    return ref;
  }

  function isOracleCandidate(el) {
    return tagNameOf(el).startsWith("oj-") || oracleComponentOf(el) != null;
  }

  function shouldInclude(el) {
    const role = roleOf(el);
    if (INTERACTIVE_ROLES.has(role) || ORIENTATION_ROLES.has(role)) return true;
    if (el.hasAttribute?.("role") || isOracleCandidate(el)) return true;
    if (el.tabIndex >= 0 && tagNameOf(el) !== "body") return true;
    return ["h1", "h2", "h3", "canvas"].includes(tagNameOf(el));
  }

  function candidatePriority(el) {
    const role = roleOf(el);
    if (el === document.activeElement || INTERACTIVE_ROLES.has(role)) return 0;
    if (
      tagNameOf(el) === "canvas" ||
      ["h1", "h2", "h3", "grid", "table", "treegrid"].includes(role) ||
      isOracleCandidate(el)
    ) {
      return 1;
    }
    return 2;
  }

  // Walk light DOM and every open shadow root. querySelectorAll does not cross
  // shadow boundaries, and Oracle JET increasingly encapsulates controls there.
  function collectCandidates() {
    const candidates = [];
    const stack = document.documentElement ? [document.documentElement] : [];
    let visited = 0;
    while (stack.length && visited < MAX_VISITED_ELEMENTS) {
      const el = stack.pop();
      if (!el || el.nodeType !== 1) continue;
      visited += 1;
      if (shouldInclude(el)) candidates.push(el);

      const lightChildren = el.children ? Array.from(el.children) : [];
      for (let i = lightChildren.length - 1; i >= 0; i -= 1) stack.push(lightChildren[i]);
      if (el.shadowRoot?.mode === "open") {
        const shadowChildren = Array.from(el.shadowRoot.children || []);
        for (let i = shadowChildren.length - 1; i >= 0; i -= 1) stack.push(shadowChildren[i]);
      }
    }
    return { candidates, visited, truncated: stack.length > 0 };
  }

  function currentFramePath() {
    if (window.top === window.self) return "top";
    const indexes = [];
    let current = window;
    for (let depth = 0; depth < 16 && current !== current.top; depth += 1) {
      try {
        const parent = current.parent;
        let index = -1;
        for (let i = 0; i < parent.frames.length; i += 1) {
          if (parent.frames[i] === current) {
            index = i;
            break;
          }
        }
        indexes.unshift(index >= 0 ? String(index) : "?");
        current = parent;
      } catch {
        indexes.unshift("?");
        break;
      }
    }
    return `top/${indexes.join("/")}`;
  }

  function topOffset() {
    let x = 0;
    let y = 0;
    let complete = true;
    let current = window;
    for (let depth = 0; depth < 16 && current !== current.top; depth += 1) {
      try {
        const frameElement = current.frameElement;
        if (!frameElement) {
          complete = false;
          break;
        }
        const rect = frameElement.getBoundingClientRect();
        x += rect.left + (frameElement.clientLeft || 0);
        y += rect.top + (frameElement.clientTop || 0);
        current = current.parent;
      } catch {
        complete = false;
        break;
      }
    }
    return { x: Math.round(x), y: Math.round(y), complete };
  }

  function childFrames(framePath) {
    const frames = [];
    for (const el of document.querySelectorAll("iframe,frame")) {
      if (!isVisible(el)) continue;
      const rect = el.getBoundingClientRect();
      let index = -1;
      try {
        for (let i = 0; i < window.frames.length; i += 1) {
          if (window.frames[i] === el.contentWindow) {
            index = i;
            break;
          }
        }
      } catch {
        // The descriptor still helps even if Chrome denies contentWindow access.
      }
      frames.push({
        index,
        path: `${framePath}/${index >= 0 ? index : "?"}`,
        name: el.getAttribute("name") || el.getAttribute("title") || "",
        src: el.getAttribute("src") || "",
        rect: roundRect(rect),
        contentOffset: {
          x: Math.round(rect.left + (el.clientLeft || 0)),
          y: Math.round(rect.top + (el.clientTop || 0)),
        },
      });
    }
    return frames;
  }

  function roundRect(rect) {
    return [
      Math.round(rect.x),
      Math.round(rect.y),
      Math.round(rect.width),
      Math.round(rect.height),
    ];
  }

  function gridMetadata(el, ref, rect) {
    const role = roleOf(el);
    const rows = Array.from(el.querySelectorAll?.('[role="row"],tr,[aria-rowindex]') || [])
      .filter(isVisible);
    const indexes = rows
      .map((row) => Number(row.getAttribute("aria-rowindex")))
      .filter(Number.isFinite);
    const rowCount = Number(el.getAttribute("aria-rowcount")) || null;
    const colCount = Number(el.getAttribute("aria-colcount")) || null;
    const renderedFirstRow = indexes.length ? Math.min(...indexes) : null;
    const renderedLastRow = indexes.length ? Math.max(...indexes) : null;
    const semanticCells = el.querySelectorAll?.(
      '[role="gridcell"],[role="cell"],[role="columnheader"],[role="rowheader"],td,th',
    )?.length || 0;
    const horizontal = el.scrollWidth > el.clientWidth;
    const vertical = el.scrollHeight > el.clientHeight;
    return {
      ref,
      role,
      rect: roundRect(rect),
      rowCount,
      colCount,
      renderedRows: rows.length,
      renderedFirstRow,
      renderedLastRow,
      ariaPoor: rows.length === 0 && semanticCells === 0,
      virtualized: Boolean(
        (rowCount && rowCount > rows.length) ||
        tagNameOf(el) === "oj-data-grid" ||
        el.hasAttribute("data-oj-context") ||
        /virtual|datagrid|table-scroller/i.test(classText(el)),
      ),
      orientation: {
        rows: "vertical",
        columns: "horizontal",
        scroll: horizontal ? (vertical ? "both" : "horizontal") : (vertical ? "vertical" : "none"),
      },
      scrollPosition: {
        x: Math.round(el.scrollLeft || 0),
        y: Math.round(el.scrollTop || 0),
        maxX: Math.max(0, Math.round(el.scrollWidth - el.clientWidth)),
        maxY: Math.max(0, Math.round(el.scrollHeight - el.clientHeight)),
      },
    };
  }

  function canvasMetadata(el, ref, rect) {
    const context = `${el.id || ""} ${classText(el)} ${accessibleName(el)}`;
    const parentContext = `${el.parentElement?.id || ""} ${classText(el.parentElement)}`;
    const labelled = Boolean(
      el.getAttribute("aria-label") ||
      el.getAttribute("aria-labelledby") ||
      el.getAttribute("role"),
    );
    return {
      ref,
      rect: roundRect(rect),
      bitmapWidth: Number(el.width) || 0,
      bitmapHeight: Number(el.height) || 0,
      cssWidth: Math.round(rect.width),
      cssHeight: Math.round(rect.height),
      bitmapScaleX: rect.width ? Number(((Number(el.width) || 0) / rect.width).toFixed(3)) : 1,
      bitmapScaleY: rect.height ? Number(((Number(el.height) || 0) / rect.height).toFixed(3)) : 1,
      ariaPoor: !labelled,
      gridLike: /grid|table|sheet|cell|adf|jet|epm|planning/i.test(`${context} ${parentContext}`),
      name: accessibleName(el),
    };
  }

  function buildSnapshot() {
    registry = new Map();
    const nodes = [];
    const grids = [];
    const canvases = [];
    const framePath = currentFramePath();
    const offset = topOffset();
    const { candidates, visited, truncated } = collectCandidates();
    // Dense financial grids can contain hundreds of rendered cells. Preserve
    // actionable controls, grid hosts, and canvas bounds before spending the
    // payload budget on orientation-only rows/cells.
    const orderedCandidates = candidates
      .map((element, order) => ({ element, order, priority: candidatePriority(element) }))
      .sort((a, b) => a.priority - b.priority || a.order - b.order)
      .map(({ element }) => element);

    for (const el of orderedCandidates) {
      if (!isVisible(el)) continue;
      const ref = elementRef(el);
      registry.set(ref, el);
      const rect = el.getBoundingClientRect();
      const role = roleOf(el);
      const state = stateOf(el);
      const oracleComponent = oracleComponentOf(el);
      const tag = tagNameOf(el);
      const node = {
        ref,
        role,
        name: accessibleName(el),
        focused: el === document.activeElement || el.shadowRoot?.activeElement === el,
        disabled: state.disabled === true,
        rect: roundRect(rect),
        framePath,
      };
      if (offset.complete) {
        node.topRect = [
          Math.round(rect.x + offset.x),
          Math.round(rect.y + offset.y),
          Math.round(rect.width),
          Math.round(rect.height),
        ];
      }
      if (oracleComponent) node.oracleComponent = oracleComponent;
      if (Object.keys(state).length) node.state = state;
      if (tag === "canvas") node.canvas = true;
      const value = el.value ?? el.getAttribute?.("value");
      if (typeof value === "string" && value) node.value = value.slice(0, 160);

      if (["grid", "table", "treegrid"].includes(role)) {
        const grid = gridMetadata(el, ref, rect);
        grids.push(grid);
        node.grid = {
          rowCount: grid.rowCount,
          colCount: grid.colCount,
          renderedRows: grid.renderedRows,
          renderedFirstRow: grid.renderedFirstRow,
          renderedLastRow: grid.renderedLastRow,
          ariaPoor: grid.ariaPoor,
          virtualized: grid.virtualized,
          orientation: grid.orientation,
        };
        // The backend's existing `canvas` flag means "coordinate-grounded
        // surface"; reuse it for a JET/ADF grid with no semantic rows/cells.
        if (grid.ariaPoor) node.canvas = true;
      }
      if (tag === "canvas") {
        const canvas = canvasMetadata(el, ref, rect);
        canvases.push(canvas);
        node.canvasMeta = {
          bitmapWidth: canvas.bitmapWidth,
          bitmapHeight: canvas.bitmapHeight,
          cssWidth: canvas.cssWidth,
          cssHeight: canvas.cssHeight,
          bitmapScaleX: canvas.bitmapScaleX,
          bitmapScaleY: canvas.bitmapScaleY,
          ariaPoor: canvas.ariaPoor,
          gridLike: canvas.gridLike,
        };
      }
      nodes.push(node);
      if (nodes.length >= MAX_NODES) break;
    }

    const notes = [];
    if (window.top !== window.self) notes.push(`frame ${framePath}`);
    if (
      canvases.some((canvas) => canvas.ariaPoor) ||
      grids.some((grid) => grid.ariaPoor)
    ) {
      notes.push("ARIA-poor canvas/grid detected; use a screenshot and surface bounds for coordinate actions");
    }
    if (grids.some((grid) => grid.virtualized)) {
      notes.push("virtualized Oracle grid detected; only rendered rows are represented");
    }
    if (truncated || nodes.length >= MAX_NODES) {
      notes.push(`snapshot truncated after ${visited} visited elements / ${nodes.length} nodes`);
    }

    const frame = {
      path: framePath,
      parentPath: framePath === "top" ? null : framePath.replace(/\/[^/]+$/, ""),
      isTop: window.top === window.self,
      offsetToTop: offset,
      viewport: {
        width: window.innerWidth || 0,
        height: window.innerHeight || 0,
        scrollX: window.scrollX || 0,
        scrollY: window.scrollY || 0,
        deviceScaleFactor: window.devicePixelRatio || 1,
      },
      childFrames: childFrames(framePath),
    };
    const ariaPoor = canvases.some((canvas) => canvas.ariaPoor) ||
      grids.some((grid) => grid.ariaPoor);
    return {
      url: location.href,
      title: document.title,
      nodes,
      grids,
      canvases,
      frame,
      // Top-level aliases keep the wire contract compact for the service
      // worker while `frame` retains the richer adapter metadata.
      framePath,
      frameOffset: offset,
      viewport: frame.viewport,
      ariaPoor,
      needsScreenshot: ariaPoor,
      notes: notes.length ? notes.join("; ") : null,
    };
  }

  function findEditable(el) {
    if (!el) return el;
    if (
      ["input", "textarea"].includes(tagNameOf(el)) ||
      el.isContentEditable
    ) {
      return el;
    }
    const selector = "input,textarea,[contenteditable='true'],[role='textbox']";
    return el.shadowRoot?.querySelector(selector) || el.querySelector?.(selector) || el;
  }

  function setNativeValue(el, value) {
    if (el.isContentEditable) {
      el.textContent = value;
      el.dispatchEvent(new InputEvent("input", {
        bubbles: true,
        inputType: "insertText",
        data: value,
      }));
      return;
    }
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : el instanceof HTMLInputElement
        ? HTMLInputElement.prototype
        : null;
    const setter = proto && Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(el, value);
    else if ("value" in el) el.value = value;
    else el.textContent = value;
    el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  }

  function canScrollElement(el, deltaX, deltaY) {
    if (!el) return false;
    const maxX = Math.max(0, el.scrollWidth - el.clientWidth);
    const maxY = Math.max(0, el.scrollHeight - el.clientHeight);
    const canX = deltaX > 0 ? el.scrollLeft < maxX : deltaX < 0 ? el.scrollLeft > 0 : false;
    const canY = deltaY > 0 ? el.scrollTop < maxY : deltaY < 0 ? el.scrollTop > 0 : false;
    return canX || canY;
  }

  function scrollableFromRef(el, deltaX, deltaY) {
    if (!el) return null;
    const candidates = [el];
    for (let parent = el.parentElement; parent; parent = parent.parentElement) {
      candidates.push(parent);
    }
    candidates.push(...Array.from(el.querySelectorAll?.("*") || []));
    return candidates.find((candidate) => canScrollElement(candidate, deltaX, deltaY)) || null;
  }

  function largestVisibleScrollable(deltaX, deltaY) {
    const candidates = Array.from(document.querySelectorAll("*"))
      .filter((candidate) => isVisible(candidate) && canScrollElement(candidate, deltaX, deltaY))
      .map((candidate) => {
        const rect = candidate.getBoundingClientRect();
        const visibleWidth = Math.max(0, Math.min(innerWidth, rect.right) - Math.max(0, rect.left));
        const visibleHeight = Math.max(0, Math.min(innerHeight, rect.bottom) - Math.max(0, rect.top));
        return { candidate, area: visibleWidth * visibleHeight };
      })
      .sort((a, b) => b.area - a.area);
    return candidates[0]?.candidate || null;
  }

  function scrollTarget(action) {
    const deltaX = Number(action.deltaX) || 0;
    const deltaY = Number(action.deltaY) || 0;
    if (action.ref != null) {
      const referenced = registry.get(action.ref);
      if (!referenced || !referenced.isConnected) {
        return { error: `local ref ${action.ref} is stale or not present in this frame` };
      }
      const target = scrollableFromRef(referenced, deltaX, deltaY);
      if (!target) return { error: `ref ${action.ref} has no scrollable area in the requested direction` };
      return { target, label: `local ref ${action.ref}` };
    }

    const page = document.scrollingElement || document.documentElement;
    if (canScrollElement(page, deltaX, deltaY)) return { target: page, label: "page" };

    // Oracle ADF/JET frequently keeps the document fixed and scrolls an
    // internal virtualized grid. When no ref was supplied and the page itself
    // cannot move, use the largest visible scrollable region instead.
    const nested = largestVisibleScrollable(deltaX, deltaY);
    return nested
      ? { target: nested, label: "largest visible scroll region" }
      : { error: "no visible scrollable area can move in the requested direction" };
  }

  function execAction(action) {
    const type = action.type;
    if (type === "scroll") {
      const resolved = scrollTarget(action);
      if (resolved.error) return { ok: false, detail: resolved.error };
      const target = resolved.target;
      const beforeX = target.scrollLeft || 0;
      const beforeY = target.scrollTop || 0;
      target.scrollBy({
        top: Number(action.deltaY) || 0,
        left: Number(action.deltaX) || 0,
        behavior: action.behavior === "smooth" ? "smooth" : "auto",
      });
      const movedX = Math.round((target.scrollLeft || 0) - beforeX);
      const movedY = Math.round((target.scrollTop || 0) - beforeY);
      const moved = movedX !== 0 || movedY !== 0;
      return {
        ok: moved,
        detail: moved
          ? `scrolled ${resolved.label} by Δx=${movedX}, Δy=${movedY} in ${currentFramePath()}`
          : `${resolved.label} did not move; it may be at a scroll boundary`,
      };
    }
    if (type === "done" || type === "screenshot" || type === "wait" || type === "navigate") {
      return { ok: true, detail: `${type} handled by service worker` };
    }
    if (action.ref == null) {
      return {
        ok: false,
        detail: `frame content adapter needs a local ref for '${type}'`,
      };
    }
    const el = registry.get(action.ref);
    if (!el || !el.isConnected) {
      return { ok: false, detail: `local ref ${action.ref} is stale or not present in this frame` };
    }
    el.scrollIntoView?.({ block: "center", inline: "center" });
    if (type === "click") {
      el.focus?.();
      el.click();
      return { ok: true, detail: `clicked local ref ${action.ref} in ${currentFramePath()}` };
    }
    if (type === "type") {
      const editable = findEditable(el);
      editable.focus?.();
      setNativeValue(editable, action.text ?? "");
      return { ok: true, detail: `typed into local ref ${action.ref} in ${currentFramePath()}` };
    }
    return { ok: false, detail: `unsupported content-script action '${type}'` };
  }

  // Wait until page mutations and layout frames have been quiet long enough.
  // This gives the service worker an event-driven replacement for fixed sleeps.
  function waitForStable(options = {}) {
    const quietMs = Math.max(32, Number(options.quietMs) || 180);
    const timeoutMs = Math.max(quietMs, Number(options.timeoutMs) || 2500);
    if (!globalThis.MutationObserver || !document.documentElement) {
      return Promise.resolve({ ok: true, stable: true, elapsedMs: 0, fallback: true });
    }
    return new Promise((resolve) => {
      const started = performance.now();
      let lastMutation = started;
      let animationFrame = 0;
      let finished = false;
      const observer = new MutationObserver(() => {
        lastMutation = performance.now();
      });
      observer.observe(document.documentElement, {
        subtree: true,
        childList: true,
        attributes: true,
        characterData: true,
      });

      const finish = (stable) => {
        if (finished) return;
        finished = true;
        observer.disconnect();
        if (animationFrame) cancelAnimationFrame(animationFrame);
        resolve({
          ok: true,
          stable,
          timedOut: !stable,
          elapsedMs: Math.round(performance.now() - started),
          quietMs: Math.round(performance.now() - lastMutation),
        });
      };
      const check = (now) => {
        if (now - lastMutation >= quietMs) return finish(true);
        if (now - started >= timeoutMs) return finish(false);
        animationFrame = requestAnimationFrame(check);
      };
      animationFrame = requestAnimationFrame(check);
    });
  }

  const api = Object.freeze({
    version: API_VERSION,
    snapshot: buildSnapshot,
    act: execAction,
    waitForStable,
  });
  globalThis.__epmwAgent = api;

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    try {
      if (msg?.kind === CS.PING) {
        sendResponse({ ok: true, version: API_VERSION, framePath: currentFramePath() });
        return false;
      }
      if (msg?.kind === CS.SNAPSHOT) {
        sendResponse(buildSnapshot());
        return false;
      }
      if (msg?.kind === CS.ACT) {
        sendResponse(execAction(msg.action || {}));
        return false;
      }
    } catch (error) {
      sendResponse({ ok: false, detail: String(error?.message || error) });
    }
    return false;
  });

  // Test-only access is inert in normal extension pages and avoids exporting
  // production globals beyond the intentionally supported agent API.
  if (globalThis.__EPMW_TEST__) {
    globalThis.__epmwAgentTest = {
      accessibleName,
      canvasMetadata,
      oracleComponentOf,
      roleOf,
      stateOf,
    };
  }
})();
