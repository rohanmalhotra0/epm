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

// Build the fetch init + URL for an authenticated backend call. Two modes:
//   • Autonomous  — an API token is set: call the token-gated /api/ext routes
//     with an Authorization: Bearer header. No cookies (works with no website
//     tab open).
//   • Integrated  — no token: call the normal routes with credentials:"include"
//     so the website's login-gate session cookie authenticates the request.
function authedRequest(config, subpath, init = {}) {
  const base = (config.backendUrl || "").replace(/\/+$/, "");
  const token = (config.apiToken || "").trim();
  const headers = { ...(init.headers || {}) };
  let path = subpath;
  let credentials = "omit";
  if (token) {
    path = subpath.replace("/api/", "/api/ext/");
    headers["authorization"] = `Bearer ${token}`;
  } else {
    credentials = "include";
  }
  return { url: `${base}${path}`, init: { ...init, headers, credentials } };
}

// Turn a fetch failure / bad status into a human, actionable message instead of
// a raw "Backend 404". `mode` is "autonomous" (token) or "integrated" (cookie).
function diagnose({ status, url, mode, networkErr }) {
  if (networkErr) {
    return `Can't reach the backend at ${url}. Check the Server URL in Settings → ` +
           `Advanced (it should be the EPM Wizard app's address) and your connection.`;
  }
  if (status === 401 || status === 403) {
    return mode === "autonomous"
      ? "API token was rejected (invalid, revoked, or for a different backend). " +
        "Generate a fresh token on the app's Browser Agent page and paste it in Settings."
      : "Not signed in. Open the EPM Wizard website and sign in (then press Test " +
        "connection), or paste an API token in Settings to run without the website.";
  }
  if (status === 404) {
    return `Reached a server at ${url}, but it has no agent API there. Point the ` +
           `Server URL at the EPM Wizard app itself (not a bare host or a different site).`;
  }
  if (status >= 500) return `Backend error (${status}). Try again shortly.`;
  return `Backend ${status}.`;
}

// Probe reachability + auth. Resolves { ok, mode, owner?, message }.
export async function testConnection(config) {
  const mode = (config.apiToken || "").trim() ? "autonomous" : "integrated";
  const { url, init } = authedRequest(config, "/api/whoami", { method: "GET" });
  let res;
  try {
    res = await fetch(url, init);
  } catch (err) {
    return { ok: false, mode, message: diagnose({ networkErr: err, url, mode }) };
  }
  if (res.ok) {
    let owner;
    try { owner = (await res.json()).owner; } catch { /* ignore */ }
    return {
      ok: true, mode, owner,
      message: mode === "autonomous"
        ? `Connected with your API token${owner ? ` as ${owner}` : ""}.`
        : `Connected via the website session${owner && owner !== "local" ? ` as ${owner}` : ""}.`,
    };
  }
  return { ok: false, mode, message: diagnose({ status: res.status, url, mode }) };
}

// Stream a single agent step. Calls handlers.onToken/onStep/onError/onDone.
export async function streamStep(config, body, handlers, signal) {
  const mode = (config.apiToken || "").trim() ? "autonomous" : "integrated";
  const { url, init } = authedRequest(config, "/api/agent/step", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  let response;
  try {
    response = await fetch(url, init);
  } catch (err) {
    handlers.onError?.(diagnose({ networkErr: err, url, mode }));
    return;
  }
  if (!response.ok) {
    handlers.onError?.(diagnose({ status: response.status, url, mode }));
    return;
  }
  await readSse(response, ({ event, data }) => {
    if (event === "token") handlers.onToken?.(data.text || "");
    else if (event === "step") handlers.onStep?.(data);
    else if (event === "error") handlers.onError?.(data.message || "agent error");
    else if (event === "done") handlers.onDone?.();
  }, signal);
}
