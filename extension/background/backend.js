// Backend client: streams one agent step from the FastAPI SSE endpoint
// (`POST /api/agent/step`, see backend/app/api/routes_agent.py).
//
// SSE is parsed by hand from the fetch ReadableStream — works in an MV3 service
// worker (EventSource is not available there, and only supports GET anyway).

// Parse a text/event-stream body, invoking onEvent({ event, data }) per record.
async function readSse(response, onEvent, signal) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    if (signal?.aborted) { await reader.cancel(); return; }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    // Records are separated by a blank line.
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      const dataLines = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      let data = {};
      if (dataLines.length) {
        try { data = JSON.parse(dataLines.join("\n")); } catch { data = { raw: dataLines.join("\n") }; }
      }
      onEvent({ event, data });
    }
  }
}

// Stream a single agent step. Calls handlers.onToken/onStep/onError/onDone.
export async function streamStep(config, body, handlers, signal) {
  const url = `${config.backendUrl.replace(/\/+$/, "")}/api/agent/step`;
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      // Send the session cookie so requests survive an oauth2-proxy login gate:
      // point backendUrl at the public entry (the auth app when the gate is up,
      // else the frontend) and, while signed in in this browser, the cookie
      // authenticates the call. Harmless when there's no gate.
      credentials: "include",
      signal,
    });
  } catch (err) {
    handlers.onError?.(`Cannot reach backend at ${url}: ${err.message}`);
    return;
  }
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    handlers.onError?.(`Backend ${response.status}: ${text.slice(0, 200)}`);
    return;
  }
  await readSse(response, ({ event, data }) => {
    if (event === "token") handlers.onToken?.(data.text || "");
    else if (event === "step") handlers.onStep?.(data);
    else if (event === "error") handlers.onError?.(data.message || "agent error");
    else if (event === "done") handlers.onDone?.();
  }, signal);
}
