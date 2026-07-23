import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

import {
  captureScreenshot,
  detachAll,
  hashImageData,
  hasAttachedTab,
  imageDimensions,
  normalizeCoordinates,
  typeAt,
} from "../background/cdp.js";

class FakeElement {
  constructor(tagName, attributes = {}, children = []) {
    this.tagName = tagName.toUpperCase();
    this.attributes = { ...attributes };
    this.children = children;
    this.nodeType = 1;
    this.className = attributes.class || "";
    this.id = attributes.id || "";
    this.textContent = attributes.text || "";
    this.tabIndex = Number(attributes.tabindex ?? -1);
    this.disabled = false;
    this.isConnected = true;
    this.parentElement = null;
    this.shadowRoot = null;
    this.clientWidth = 200;
    this.clientHeight = 50;
    this.scrollWidth = 200;
    this.scrollHeight = 50;
    this.scrollLeft = 0;
    this.scrollTop = 0;
    for (const child of children) child.parentElement = this;
  }

  getAttribute(name) {
    return Object.hasOwn(this.attributes, name) ? String(this.attributes[name]) : null;
  }

  hasAttribute(name) {
    return Object.hasOwn(this.attributes, name);
  }

  getBoundingClientRect() {
    return { x: 10, y: 20, left: 10, top: 20, right: 210, bottom: 70, width: 200, height: 50 };
  }

  getRootNode() {
    return this.ownerDocument;
  }

  closest() {
    return null;
  }

  querySelector() {
    return null;
  }

  querySelectorAll() {
    return [];
  }

  scrollIntoView() {}

  scrollBy({ left = 0, top = 0 }) {
    this.scrollLeft = Math.max(
      0,
      Math.min(this.scrollWidth - this.clientWidth, this.scrollLeft + left),
    );
    this.scrollTop = Math.max(
      0,
      Math.min(this.scrollHeight - this.clientHeight, this.scrollTop + top),
    );
  }
}

async function loadContentAdapter(documentElement) {
  const listeners = [];
  const document = {
    documentElement,
    title: "Oracle Planning",
    activeElement: null,
    getElementById: () => null,
    querySelectorAll: () => [],
  };
  const context = {
    __EPMW_TEST__: true,
    chrome: {
      runtime: {
        onMessage: { addListener: (listener) => listeners.push(listener) },
      },
    },
    document,
    location: { href: "https://planning.example.com/epm" },
    innerWidth: 1200,
    innerHeight: 800,
    scrollX: 0,
    scrollY: 0,
    devicePixelRatio: 2,
    frames: [],
    performance,
    getComputedStyle: () => ({ visibility: "visible", display: "block", opacity: "1" }),
    HTMLInputElement: class {},
    HTMLTextAreaElement: class {},
    Event: class {},
    InputEvent: class {},
    MutationObserver: class {},
    requestAnimationFrame: () => 1,
    cancelAnimationFrame: () => {},
  };
  context.window = context;
  context.self = context;
  context.top = context;
  for (const child of documentElement.children) child.ownerDocument = document;
  const source = await readFile(
    new URL("../content/content-script.js", import.meta.url),
    "utf8",
  );
  vm.runInNewContext(source, context, { filename: "content-script.js" });
  return context;
}

test("Oracle JET/ADF helpers infer semantic roles and state", async () => {
  const root = new FakeElement("html");
  const context = await loadContentAdapter(root);
  const helpers = context.__epmwAgentTest;

  const jetInput = new FakeElement("oj-input-text", { "label-hint": "Scenario" });
  const adfButton = new FakeElement("div", { class: "AFCommandButton", "data-afr-rk": "cb1" });
  const selectedTab = new FakeElement("div", {
    role: "tab",
    "aria-selected": "true",
    "aria-posinset": "2",
    "aria-setsize": "5",
  });

  assert.equal(helpers.roleOf(jetInput), "textbox");
  assert.equal(helpers.accessibleName(jetInput), "Scenario");
  assert.equal(helpers.oracleComponentOf(jetInput), "oj-input-text");
  assert.equal(helpers.roleOf(adfButton), "button");
  assert.equal(helpers.oracleComponentOf(adfButton), "adf:div");
  assert.deepEqual(
    { ...helpers.stateOf(selectedTab) },
    { selected: true, posinset: 2, setsize: 5 },
  );
});

test("snapshot crosses open shadow roots and keeps element refs stable", async () => {
  const shadowButton = new FakeElement("button", { text: "Run Rule" });
  const host = new FakeElement("div");
  host.shadowRoot = { mode: "open", children: [shadowButton] };
  shadowButton.parentElement = host;
  const root = new FakeElement("html", {}, [host]);
  const context = await loadContentAdapter(root);

  const first = context.__epmwAgent.snapshot();
  const second = context.__epmwAgent.snapshot();
  const firstButton = first.nodes.find((node) => node.name === "Run Rule");
  const secondButton = second.nodes.find((node) => node.name === "Run Rule");

  assert.equal(first.frame.path, "top");
  assert.equal(first.framePath, "top");
  assert.deepEqual({ ...first.frameOffset }, { x: 0, y: 0, complete: true });
  assert.equal(first.frame.viewport.deviceScaleFactor, 2);
  assert.equal(first.viewport.deviceScaleFactor, 2);
  assert.equal(firstButton.role, "button");
  assert.equal(firstButton.ref, secondButton.ref);
});

test("canvas metadata identifies an unlabeled grid-like canvas", async () => {
  const canvas = new FakeElement("canvas", { id: "planning-grid" });
  canvas.width = 1600;
  canvas.height = 400;
  const root = new FakeElement("html", {}, [canvas]);
  const context = await loadContentAdapter(root);

  const metadata = context.__epmwAgentTest.canvasMetadata(
    canvas,
    7,
    canvas.getBoundingClientRect(),
  );

  assert.equal(metadata.ref, 7);
  assert.equal(metadata.ariaPoor, true);
  assert.equal(metadata.gridLike, true);
  assert.equal(metadata.bitmapScaleX, 8);
  assert.equal(context.__epmwAgent.snapshot().nodes[0].canvasMeta.bitmapScaleX, 8);
});

test("ARIA-poor Oracle grid is exposed as a coordinate-grounded surface", async () => {
  const grid = new FakeElement("oj-data-grid", { "label-hint": "Planning form" });
  const root = new FakeElement("html", {}, [grid]);
  const context = await loadContentAdapter(root);

  const snapshot = context.__epmwAgent.snapshot();
  const gridNode = snapshot.nodes.find((node) => node.name === "Planning form");

  assert.equal(snapshot.grids[0].ariaPoor, true);
  assert.equal(gridNode.canvas, true);
  assert.equal(gridNode.grid.ariaPoor, true);
  assert.equal(gridNode.grid.virtualized, true);
  assert.equal(snapshot.ariaPoor, true);
  assert.equal(snapshot.needsScreenshot, true);
});

test("a ref-grounded scroll moves an internal Oracle grid and reports boundaries", async () => {
  const grid = new FakeElement("div", {
    role: "grid",
    "aria-label": "Accounts results",
    "aria-rowcount": "200",
  });
  grid.scrollHeight = 650;
  const root = new FakeElement("html", {}, [grid]);
  const context = await loadContentAdapter(root);
  const gridNode = context.__epmwAgent.snapshot().nodes.find(
    (node) => node.name === "Accounts results",
  );

  const moved = context.__epmwAgent.act({
    type: "scroll",
    ref: gridNode.ref,
    deltaY: 300,
  });
  assert.equal(moved.ok, true);
  assert.match(moved.detail, /Δy=300/);
  assert.equal(grid.scrollTop, 300);

  grid.scrollTop = 600;
  const boundary = context.__epmwAgent.act({
    type: "scroll",
    ref: gridNode.ref,
    deltaY: 300,
  });
  assert.equal(boundary.ok, false);
  assert.match(boundary.detail, /scrollable area|boundary/);
});

test("coordinate normalization maps bounded image pixels into CSS viewport space", () => {
  assert.deepEqual(
    normalizeCoordinates(640, 360, {
      coordinateSpace: "image",
      screenshotMeta: {
        imageWidth: 1280,
        imageHeight: 720,
        viewportWidth: 1600,
        viewportHeight: 900,
      },
      frameOffset: { x: 20, y: 10 },
    }),
    { x: 820, y: 460 },
  );
  assert.throws(() => normalizeCoordinates(Number.NaN, 4), /finite x\/y/);
  assert.equal(hashImageData("same-image"), hashImageData("same-image"));
  assert.notEqual(hashImageData("same-image"), hashImageData("other-image"));
  assert.deepEqual(
    imageDimensions(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZbTQAAAAASUVORK5CYII=",
      "png",
    ),
    { width: 1, height: 1 },
  );
});

test("CDP screenshot is bounded JPEG with repeat-image metadata", async () => {
  const commands = [];
  globalThis.chrome = {
    runtime: { lastError: null },
    debugger: {
      attach: (_target, _version, callback) => callback(),
      detach: (_target, callback) => callback(),
      sendCommand: (_target, method, params, callback) => {
        commands.push({ method, params });
        if (method === "Page.getLayoutMetrics") {
          callback({ cssVisualViewport: { clientWidth: 1600, clientHeight: 900, pageX: 0, pageY: 0 } });
        } else if (method === "Runtime.evaluate") {
          callback({ result: { value: 2 } });
        } else if (method === "Page.captureScreenshot") {
          callback({ data: "c2FtZS1qcGVn" });
        } else {
          callback({});
        }
      },
    },
  };

  const first = await captureScreenshot(91, { withMetadata: true, deduplicate: true });
  const second = await captureScreenshot(91, { withMetadata: true, deduplicate: true });

  assert.match(first.dataUrl, /^data:image\/jpeg;base64,/);
  assert.equal(first.metadata.imageWidth, 1280);
  assert.equal(first.metadata.imageHeight, 720);
  assert.equal(first.metadata.deviceScaleFactor, 2);
  assert.equal(first.metadata.duplicate, false);
  assert.equal(second.metadata.duplicate, true);
  assert.equal(second.dataUrl, null);
  assert.equal(hasAttachedTab(91), true);
  assert.equal(
    commands.find((command) => command.method === "Page.captureScreenshot").params.quality,
    72,
  );
});

test("coordinate typing focuses the normalized canvas point then inserts text", async () => {
  const commands = [];
  globalThis.chrome.debugger.sendCommand = (_target, method, params, callback) => {
    commands.push({ method, params });
    callback({});
  };

  const result = await typeAt(91, 320, 180, "42", {
    coordinateSpace: "image",
    screenshotMeta: {
      imageWidth: 1280,
      imageHeight: 720,
      viewportWidth: 1600,
      viewportHeight: 900,
    },
  });

  assert.deepEqual(result.point, { x: 400, y: 225 });
  assert.equal(commands.filter((command) => command.method === "Input.dispatchMouseEvent").length, 3);
  assert.deepEqual(
    commands.find((command) => command.method === "Input.insertText").params,
    { text: "42" },
  );
});

test("disabling canvas control detaches every tab with an active CDP session", async () => {
  const detached = [];
  globalThis.chrome.debugger.detach = (target, callback) => {
    detached.push(target.tabId);
    callback();
  };

  await detachAll();

  assert.deepEqual(detached, [91]);
  assert.equal(hasAttachedTab(91), false);
});
