import { createReadStream } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const staticRoot = path.join(here, "fixtures");
const requestedPort = Number.parseInt(
  process.argv[process.argv.indexOf("--port") + 1] || process.env.E2E_EXTENSION_PORT || "14783",
  10,
);

const requests = [];
const runCounts = new Map();

function allowCors(request, response) {
  const origin = request.headers.origin || "*";
  response.setHeader("Access-Control-Allow-Origin", origin);
  response.setHeader("Access-Control-Allow-Credentials", "true");
  response.setHeader("Access-Control-Allow-Headers", "content-type, authorization");
  response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  response.setHeader("Vary", "Origin");
}

function json(response, status, body) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function flattenNodes(observation) {
  const groups = [
    observation?.nodes,
    ...(observation?.frames || []).map((frame) => frame?.nodes),
  ];
  return groups.flatMap((nodes) => (Array.isArray(nodes) ? nodes : []));
}

function flattenCanvases(observation) {
  const groups = [
    observation?.canvases,
    ...(observation?.frames || []).map((frame) => frame?.canvases),
  ];
  return groups.flatMap((items) => (Array.isArray(items) ? items : []));
}

function findNode(observation, name) {
  const wanted = name.toLowerCase();
  return flattenNodes(observation).find(
    (node) => String(node?.name || "").trim().toLowerCase() === wanted,
  );
}

function actionFor(body, sequenceIndex) {
  const observation = body?.observation || {};
  if (String(body?.goal || "").includes("deliberate failed action")) {
    return sequenceIndex === 0 ? { type: "click", ref: 999_999 } : { type: "done" };
  }
  if (sequenceIndex === 0) {
    const target = findNode(observation, "Refresh nested form");
    if (!target) return { type: "done" };
    return { type: "click", ref: target.ref };
  }
  if (sequenceIndex === 1) {
    const target = findNode(observation, "Scenario");
    if (!target) return { type: "done" };
    return { type: "type", ref: target.ref, text: "Forecast" };
  }
  if (sequenceIndex === 2) {
    const target = findNode(observation, "Run business rule");
    if (!target) return { type: "done" };
    return { type: "click", ref: target.ref };
  }
  if (sequenceIndex === 3) {
    const target = findNode(observation, "Account 1100");
    if (!target) return { type: "done" };
    return { type: "click", ref: target.ref };
  }
  if (sequenceIndex === 4) {
    return { type: "screenshot" };
  }
  if (sequenceIndex === 5) {
    const canvas = flattenCanvases(observation)[0];
    const canvasNode = flattenNodes(observation).find((node) => node?.canvas);
    const rect = canvas?.rect || canvas?.bounds || canvasNode?.rect;
    if (!Array.isArray(rect) || rect.length < 4) return { type: "done" };
    return {
      type: "click",
      x: Math.round(Number(rect[0]) + Number(rect[2]) / 2),
      y: Math.round(Number(rect[1]) + Number(rect[3]) / 2),
    };
  }
  return { type: "done" };
}

function streamStep(request, response, body) {
  const runKey = String(body.goal || "default");
  const sequenceIndex = runCounts.get(runKey) || 0;
  runCounts.set(runKey, sequenceIndex + 1);
  const action = actionFor(body, sequenceIndex);
  const done = action.type === "done";
  const step = {
    index: Array.isArray(body.history) ? body.history.length : sequenceIndex,
    narration: done ? "The fixture workflow is complete." : `Fixture action ${sequenceIndex + 1}.`,
    action,
    done,
  };

  requests.push({
    at: new Date().toISOString(),
    origin: request.headers.origin || "",
    authorization: request.headers.authorization || "",
    sequenceIndex,
    body,
    response: step,
  });

  response.writeHead(200, {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache",
    connection: "keep-alive",
  });
  response.write(`event: token\ndata: ${JSON.stringify({ text: step.narration })}\n\n`);
  response.write(`event: step\ndata: ${JSON.stringify(step)}\n\n`);
  response.end("event: done\ndata: {}\n\n");
}

function serveFixture(response, pathname) {
  const name = pathname.slice("/fixture/".length);
  if (!/^[a-z0-9-]+\.html$/i.test(name)) {
    json(response, 404, { error: "fixture not found" });
    return;
  }
  const target = path.join(staticRoot, name);
  response.writeHead(200, {
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
  });
  createReadStream(target)
    .on("error", () => {
      if (!response.headersSent) json(response, 404, { error: "fixture not found" });
      else response.destroy();
    })
    .pipe(response);
}

const server = createServer(async (request, response) => {
  allowCors(request, response);
  if (request.method === "OPTIONS") {
    response.writeHead(204);
    response.end();
    return;
  }

  const url = new URL(request.url || "/", `http://${request.headers.host}`);
  if (url.pathname === "/health") {
    json(response, 200, { ok: true });
    return;
  }
  if (url.pathname.startsWith("/fixture/")) {
    serveFixture(response, url.pathname);
    return;
  }
  if (url.pathname === "/api/whoami") {
    json(response, 200, { owner: "extension-e2e@example.test" });
    return;
  }
  if (url.pathname === "/api/projects") {
    json(response, 200, [{ id: "project-e2e", name: "Extension E2E", isDefault: true }]);
    return;
  }
  if (url.pathname === "/api/projects/project-e2e/environments") {
    json(response, 200, [
      {
        id: "environment-e2e",
        name: "Oracle EPM Fixture",
        baseUrl: `http://127.0.0.1:${requestedPort}`,
        classification: "development",
        connected: true,
        demo: false,
        preferredApplication: "Plan1",
      },
    ]);
    return;
  }
  if (url.pathname === "/api/agent/step" && request.method === "POST") {
    const body = await readJson(request);
    streamStep(request, response, body);
    return;
  }
  if (url.pathname === "/__requests") {
    json(response, 200, requests);
    return;
  }
  if (url.pathname === "/__reset" && request.method === "POST") {
    requests.length = 0;
    runCounts.clear();
    json(response, 200, { ok: true });
    return;
  }
  json(response, 404, { error: "not found" });
});

server.listen(requestedPort, "127.0.0.1", () => {
  process.stdout.write(`Extension fixture server listening on http://127.0.0.1:${requestedPort}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
