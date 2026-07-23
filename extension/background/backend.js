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

// Extension onboarding always uses the website session. API tokens remain
// supported for the agent transport, but they cannot bypass the product's
// Google OAuth gate or the Oracle EPM connection gate.
function websiteRequest(config, subpath, init = {}) {
  const base = (config.backendUrl || "").replace(/\/+$/, "");
  return {
    url: `${base}${subpath}`,
    init: {
      ...init,
      headers: { ...(init.headers || {}) },
      credentials: "include",
    },
  };
}

async function websiteJson(config, subpath, init = {}) {
  const { url, init: requestInit } = websiteRequest(config, subpath, init);
  let response;
  try {
    response = await fetch(url, requestInit);
  } catch {
    throw new Error(`Can't reach EPM Wizard at ${url}. Check the Server URL and your connection.`);
  }
  if (!response.ok) {
    let detail = response.statusText || `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      detail = body.detail || body.message || detail;
    } catch { /* response was not JSON */ }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function chooseProject(projects, preferredId) {
  return projects.find((project) => project.id === preferredId)
    || projects.find((project) => project.isDefault)
    || projects[0]
    || null;
}

// Resolve the mandatory two-stage access flow:
//   1. Google OAuth website session
//   2. Live Oracle EPM environment connection
// The returned object is intentionally secret-free and is safe to render or
// persist as ordinary UI state.
export async function getExtensionAccess(config) {
  let whoami;
  try {
    whoami = await websiteJson(config, "/api/whoami", { method: "GET" });
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      return {
        stage: "oauth",
        message: "Sign in with Google to continue to EPM Wizard.",
      };
    }
    return { stage: "error", message: error.message || "Could not check your EPM Wizard sign-in." };
  }

  try {
    const projects = await websiteJson(config, "/api/projects", { method: "GET" });
    const project = chooseProject(Array.isArray(projects) ? projects : [], config.projectId);
    if (!project) {
      return {
        stage: "error",
        owner: whoami?.owner,
        message: "Your EPM Wizard account has no project yet. Open the website once, then try again.",
      };
    }
    const environments = await websiteJson(
      config,
      `/api/projects/${encodeURIComponent(project.id)}/environments`,
      { method: "GET" },
    );
    const connected = (Array.isArray(environments) ? environments : []).find(
      (environment) => !environment.demo && environment.connected,
    );
    if (!connected) {
      return {
        stage: "epm",
        owner: whoami?.owner,
        projectId: project.id,
        projectName: project.name,
        message: "Connect your Oracle EPM environment to unlock the browser agent.",
      };
    }
    return {
      stage: "ready",
      owner: whoami?.owner,
      projectId: project.id,
      projectName: project.name,
      environmentName: connected.name,
      application: connected.preferredApplication || "",
      message: `Connected to ${connected.name}.`,
    };
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      return {
        stage: "oauth",
        message: "Your EPM Wizard sign-in expired. Sign in with Google again.",
      };
    }
    return { stage: "error", owner: whoami?.owner, message: error.message || "Could not check Oracle EPM access." };
  }
}

// Submit the same environment shape used by frontend/src/components/SignIn.tsx.
// The password/client secret is forwarded once to the backend and is never
// copied into extension config, local storage, session storage, or run logs.
export async function connectEpmEnvironment(config, form) {
  const oauth = form.authMode === "oauth";
  const baseUrl = String(form.baseUrl || "").trim().replace(/\/+$/, "");
  const username = String(form.username || "").trim();
  const tokenUrl = String(form.tokenUrl || "").trim();
  const clientId = String(form.clientId || "").trim();
  const secret = String(oauth ? form.clientSecret || "" : form.password || "");

  if (oauth) {
    if (!baseUrl || !tokenUrl || !clientId || !secret) {
      throw new Error("Instance URL, token URL, client ID and client secret are required.");
    }
  } else if (!baseUrl || !username || !secret) {
    throw new Error("Instance URL, username and password are required.");
  }

  const access = await getExtensionAccess(config);
  if (access.stage === "oauth") throw Object.assign(new Error(access.message), { status: 401 });
  if (access.stage === "error") throw new Error(access.message);
  if (access.stage === "ready") return access;

  const projectId = access.projectId;
  const environments = await websiteJson(
    config,
    `/api/projects/${encodeURIComponent(projectId)}/environments`,
    { method: "GET" },
  );
  let environment = (Array.isArray(environments) ? environments : []).find(
    (item) =>
      !item.demo
      && String(item.baseUrl || "").replace(/\/+$/, "") === baseUrl
      && (item.authMethod === "oauthClientCredentials") === oauth,
  );

  if (!environment) {
    environment = await websiteJson(
      config,
      `/api/projects/${encodeURIComponent(projectId)}/environments`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: `Oracle EPM (${oauth ? clientId : username})`,
          baseUrl,
          username: oauth ? undefined : username,
          authMethod: oauth
            ? "oauthClientCredentials"
            : form.remember
              ? "passwordStored"
              : "passwordInMemory",
          oauthTokenUrl: oauth ? tokenUrl : undefined,
          oauthClientId: oauth ? clientId : undefined,
          oauthScope: oauth ? String(form.scope || "").trim() || undefined : undefined,
          classification: form.classification || "development",
          preferredApplication: String(form.application || "").trim() || undefined,
          demo: false,
        }),
      },
    );
  }

  const result = await websiteJson(
    config,
    `/api/environments/${encodeURIComponent(environment.id)}/connect`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        password: secret,
        remember: !!form.remember,
      }),
    },
  );
  if (!result?.connected) {
    throw new Error(result?.detail || result?.message || "Could not connect. Check your credentials.");
  }
  return {
    stage: "ready",
    projectId,
    projectName: access.projectName,
    environmentName: environment.name,
    application: result.application || "",
    message: result.message || `Connected to ${environment.name}.`,
  };
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
