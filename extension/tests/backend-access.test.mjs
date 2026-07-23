import assert from "node:assert/strict";
import { after, test } from "node:test";
import {
  connectEpmEnvironment,
  getExtensionAccess,
  streamStep,
} from "../background/backend.js";

const realFetch = globalThis.fetch;
after(() => {
  globalThis.fetch = realFetch;
});

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const config = {
  backendUrl: "https://epmw-auth.example",
  projectId: "",
  apiToken: "epmw_token_must_not_bypass_oauth",
};

test("website OAuth is mandatory even when an API token is configured", async () => {
  globalThis.fetch = async () => json({ detail: "Unauthorized" }, 401);

  const access = await getExtensionAccess(config);

  assert.equal(access.stage, "oauth");
});

test("a signed-in user without a live Oracle connection receives the EPM gate", async () => {
  globalThis.fetch = async (url) => {
    if (url.endsWith("/api/whoami")) return json({ owner: "qa@example.com" });
    if (url.endsWith("/api/projects")) {
      return json([{ id: "project-1", name: "Default", isDefault: true }]);
    }
    if (url.endsWith("/api/projects/project-1/environments")) return json([]);
    throw new Error(`Unexpected URL: ${url}`);
  };

  const access = await getExtensionAccess(config);

  assert.equal(access.stage, "epm");
  assert.equal(access.projectId, "project-1");
  assert.equal(access.owner, "qa@example.com");
});

test("a live Oracle environment unlocks the extension", async () => {
  globalThis.fetch = async (url) => {
    if (url.endsWith("/api/whoami")) return json({ owner: "qa@example.com" });
    if (url.endsWith("/api/projects")) {
      return json([{ id: "project-1", name: "Default", isDefault: true }]);
    }
    if (url.endsWith("/api/projects/project-1/environments")) {
      return json([{
        id: "environment-1",
        name: "Oracle EPM (qa@example.com)",
        demo: false,
        connected: true,
        preferredApplication: "Vision",
      }]);
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  const access = await getExtensionAccess(config);

  assert.equal(access.stage, "ready");
  assert.equal(access.application, "Vision");
});

test("Oracle credentials are sent only to the one-time connect request", async () => {
  const requests = [];
  globalThis.fetch = async (url, init = {}) => {
    requests.push({ url, init });
    if (url.endsWith("/api/whoami")) return json({ owner: "qa@example.com" });
    if (url.endsWith("/api/projects")) {
      return json([{ id: "project-1", name: "Default", isDefault: true }]);
    }
    if (url.endsWith("/api/projects/project-1/environments") && (!init.method || init.method === "GET")) {
      return json([]);
    }
    if (url.endsWith("/api/projects/project-1/environments") && init.method === "POST") {
      return json({ id: "environment-1", name: "Oracle EPM (qa-client)" }, 201);
    }
    if (url.endsWith("/api/environments/environment-1/connect")) {
      return json({
        connected: true,
        message: "Connected.",
        application: "Vision",
      });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  const access = await connectEpmEnvironment(config, {
    authMode: "oauth",
    baseUrl: "https://planning-test.example.com",
    tokenUrl: "https://identity.example.com/oauth2/v1/token",
    clientId: "qa-client",
    clientSecret: "not-a-real-secret",
    scope: "",
    application: "",
    classification: "test",
    remember: false,
  });

  const bodies = requests
    .filter((request) => request.init.body)
    .map((request) => ({ url: request.url, body: JSON.parse(request.init.body) }));
  const createBody = bodies.find((request) => request.url.endsWith("/environments")).body;
  const connectBody = bodies.find((request) => request.url.endsWith("/connect")).body;

  assert.equal(access.stage, "ready");
  assert.equal(createBody.clientSecret, undefined);
  assert.equal(createBody.password, undefined);
  assert.equal(connectBody.password, "not-a-real-secret");
  assert.equal(JSON.stringify(config).includes("not-a-real-secret"), false);
});

test("an intentional request abort does not report a backend outage", async () => {
  const controller = new AbortController();
  const messages = [];
  globalThis.fetch = async (_url, init) => {
    controller.abort();
    throw new DOMException("This operation was aborted", "AbortError");
  };

  const result = await streamStep(
    { ...config, apiToken: "" },
    { goal: "Inspect", observation: {}, history: [] },
    { onError: (message) => messages.push(message) },
    controller.signal,
  );

  assert.deepEqual(result, { aborted: true });
  assert.deepEqual(messages, []);
});

test("a real request failure reports the browser cause and payload size", async () => {
  const messages = [];
  globalThis.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };

  const result = await streamStep(
    { ...config, apiToken: "" },
    { goal: "Inspect", observation: {}, history: [] },
    { onError: (message) => messages.push(message) },
  );

  assert.deepEqual(result, { ok: false });
  assert.match(messages[0], /TypeError: Failed to fetch/);
  assert.match(messages[0], /request \d+ KiB/);
});
