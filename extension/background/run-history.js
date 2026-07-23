// Pure helpers for the MV3 run loop. Kept free of chrome.* APIs so history
// compaction and action-outcome behavior are directly unit-testable.

export const HISTORY_LIMIT = 12;
export const WORKBOOK_CONTEXT_LIMIT = 60_000;

function boundedText(value, max) {
  const text = String(value || "");
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function normalizeActionResult(result, { gate = "allowed", durationMs = null } = {}) {
  return {
    ok: !!result?.ok,
    detail: boundedText(result?.detail, 2000),
    gate,
    ...(Number.isFinite(durationMs) ? { durationMs: Math.max(0, Math.round(durationMs)) } : {}),
  };
}

export function attachActionResult(step, result, options = {}) {
  return {
    ...step,
    raw: undefined,
    result: normalizeActionResult(result, options),
  };
}

function compactAction(action = {}) {
  return Object.fromEntries(Object.entries(action).filter(([key, value]) => {
    if (value == null || value === "") return false;
    if (key === "coordinateSpace" && value === "css") return false;
    if ((key === "deltaX" || key === "deltaY") && value === 0) return false;
    return true;
  }));
}

export function compactHistory(steps, limit = HISTORY_LIMIT) {
  return (Array.isArray(steps) ? steps : []).slice(-limit).map((step) => ({
    index: step.index,
    narration: boundedText(step.narration, 1000),
    action: compactAction(step.action),
    done: !!step.done,
    ...(step.result ? { result: normalizeActionResult(step.result, {
      gate: step.result.gate,
      durationMs: step.result.durationMs,
    }) } : {}),
  }));
}

export function shouldCaptureScreenshot(snapshot, requested = false) {
  if (requested) return true;
  const nodes = Array.isArray(snapshot?.nodes) ? snapshot.nodes : [];
  if (nodes.length === 0) return true;
  return nodes.some((node) => node?.canvas === true)
    || snapshot?.ariaPoor === true
    || snapshot?.needsScreenshot === true;
}

export function compactWorkbookContext(context, limit = WORKBOOK_CONTEXT_LIMIT) {
  if (!context) return null;
  const content = String(context.content || "");
  if (content.length <= limit) return context;
  return {
    ...context,
    content: `${content.slice(0, limit - 80)}\n[Workbook context capped for browser-agent latency.]`,
    truncated: true,
  };
}
