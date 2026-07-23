import assert from "node:assert/strict";
import test from "node:test";

import {
  attachActionResult,
  compactHistory,
  compactWorkbookContext,
  doneActionResult,
  shouldCaptureScreenshot,
} from "../background/run-history.js";

test("action results are attached without retaining raw model output", () => {
  const step = attachActionResult(
    {
      index: 2,
      narration: "Clicking Save.",
      action: { type: "click", ref: 7 },
      raw: "{\"large\":\"model response\"}",
    },
    { ok: false, detail: "button was detached" },
    { gate: "allowed", durationMs: 18.6 },
  );

  assert.equal(step.raw, undefined);
  assert.deepEqual(step.result, {
    ok: false,
    detail: "button was detached",
    gate: "allowed",
    durationMs: 19,
  });
});

test("blocked done actions are failures instead of false goal completions", () => {
  assert.deepEqual(
    doneActionResult({
      type: "done",
      reason: "blocked: vision response did not contain a valid action",
    }),
    {
      ok: false,
      detail: "blocked: vision response did not contain a valid action",
    },
  );
  assert.deepEqual(doneActionResult({ type: "done" }), {
    ok: true,
    detail: "goal complete",
  });
});

test("history is bounded and compact", () => {
  const history = Array.from({ length: 15 }, (_, index) => ({
    index,
    narration: `step ${index}`,
    action: { type: "wait", durationMs: 1 },
    raw: "not sent",
    result: { ok: true, detail: "done", gate: "allowed" },
  }));

  const compact = compactHistory(history);
  assert.equal(compact.length, 12);
  assert.equal(compact[0].index, 3);
  assert.equal("raw" in compact[0], false);
  assert.equal(compact.at(-1).result.ok, true);
});

test("history omits default action fields that add no model context", () => {
  const [step] = compactHistory([{
    index: 0,
    narration: "Clicking Save.",
    action: {
      type: "click",
      ref: 7,
      coordinateSpace: "css",
      deltaX: 0,
      deltaY: 0,
      text: null,
    },
  }]);

  assert.deepEqual(step.action, { type: "click", ref: 7 });
});

test("canvas and empty observations request screenshot grounding", () => {
  assert.equal(shouldCaptureScreenshot({ nodes: [] }), true);
  assert.equal(shouldCaptureScreenshot({ nodes: [{ ref: 1, canvas: true }] }), true);
  assert.equal(shouldCaptureScreenshot({ nodes: [{ ref: 1 }] }), false);
  assert.equal(shouldCaptureScreenshot({ nodes: [{ ref: 1 }] }, true), true);
});

test("large workbook context is capped before each model request", () => {
  const context = compactWorkbookContext({
    filename: "large.xlsm",
    content: "x".repeat(90_000),
    truncated: false,
  });
  assert.equal(context.truncated, true);
  assert.ok(context.content.length <= 60_000);
  assert.match(context.content, /capped for browser-agent latency/);
});
