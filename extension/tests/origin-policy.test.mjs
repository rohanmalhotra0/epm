import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  evaluateSiteBridgeRequest,
  getSenderPageOrigin,
  normalizeBackendOrigin,
  TRUSTED_SITE_ORIGINS,
} from "../background/origin-policy.js";

const RUNTIME_ID = "epmw-test-extension";
const manifest = JSON.parse(
  readFileSync(new URL("../manifest.json", import.meta.url), "utf8"),
);

function sender(origin, overrides = {}) {
  return {
    id: RUNTIME_ID,
    origin,
    url: `${origin}/app/agent`,
    tab: { url: `${origin}/app/agent`, id: 7 },
    ...overrides,
  };
}

function request(pageOrigin, backendUrl, kind = "site.configure") {
  return {
    kind,
    pageOrigin,
    data: backendUrl == null ? {} : { backendUrl },
  };
}

test("trusted bridge origins match the manifest's narrow product origins", () => {
  assert.deepEqual(TRUSTED_SITE_ORIGINS, [
    "https://epmw-auth.fly.dev",
    "https://epmw-frontend.fly.dev",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
  ]);
});

test("manifest keeps broad page access and debugger optional", () => {
  assert.deepEqual(manifest.permissions, [
    "activeTab",
    "scripting",
    "sidePanel",
    "storage",
  ]);
  assert.deepEqual(manifest.optional_permissions, ["debugger"]);
  assert.deepEqual(manifest.optional_host_permissions, [
    "https://*/*",
    "http://localhost/*",
    "http://127.0.0.1/*",
  ]);
  assert.equal(manifest.permissions.includes("tabs"), false);

  assert.equal(manifest.content_scripts.length, 1);
  assert.deepEqual(manifest.content_scripts[0].js, ["content/site-bridge.js"]);
  assert.equal(manifest.content_scripts[0].all_frames, false);
  assert.deepEqual(
    [...manifest.content_scripts[0].matches].sort(),
    TRUSTED_SITE_ORIGINS.map((origin) => `${origin}/*`).sort(),
  );
  assert.deepEqual(
    [...manifest.host_permissions].sort(),
    TRUSTED_SITE_ORIGINS.map((origin) => `${origin}/*`).sort(),
  );
});

test("normalizes secure and loopback origins but rejects unsafe backend URLs", () => {
  assert.equal(normalizeBackendOrigin("https://wizard.example:443/"), "https://wizard.example");
  assert.equal(normalizeBackendOrigin("http://127.0.0.1:8123/"), "http://127.0.0.1:8123");
  assert.equal(normalizeBackendOrigin("http://localhost:8000"), "http://localhost:8000");

  for (const value of [
    "http://wizard.example",
    "http://[::1]:8000",
    "https://user:secret@wizard.example",
    "https://wizard.example/base",
    "https://wizard.example/?tenant=x",
    "javascript:alert(1)",
    "not a URL",
  ]) {
    assert.equal(normalizeBackendOrigin(value), null, value);
  }
});

test("derives the actual sender origin and rejects conflicting Chrome fields", () => {
  assert.equal(
    getSenderPageOrigin(sender("https://epmw-auth.fly.dev")),
    "https://epmw-auth.fly.dev",
  );
  assert.equal(
    getSenderPageOrigin(sender("https://epmw-auth.fly.dev", {
      tab: { url: "https://attacker.example/app" },
    })),
    null,
  );
});

test("allows the hosted site only to select its bound hosted backend", () => {
  const result = evaluateSiteBridgeRequest({
    message: request("https://epmw-auth.fly.dev", "https://epmw-auth.fly.dev/"),
    sender: sender("https://epmw-auth.fly.dev"),
    runtimeId: RUNTIME_ID,
    currentBackendUrl: "https://epmw-auth.fly.dev",
  });

  assert.equal(result.disposition, "allow");
  assert.equal(result.backendUrl, "https://epmw-auth.fly.dev");
  assert.equal(result.requiresApproval, false);
  assert.equal(result.clearCredentials, false);
});

test("allows the explicit local frontend-to-backend development binding", () => {
  const result = evaluateSiteBridgeRequest({
    message: request("http://127.0.0.1:3000", "http://127.0.0.1:8000"),
    sender: sender("http://127.0.0.1:3000"),
    runtimeId: RUNTIME_ID,
  });

  assert.equal(result.disposition, "allow");
  assert.equal(result.backendUrl, "http://127.0.0.1:8000");
});

test("requires extension-owned approval for a legitimate self-hosted backend", () => {
  const base = {
    message: request("https://epmw-auth.fly.dev", "https://epm.internal.example"),
    sender: sender("https://epmw-auth.fly.dev"),
    runtimeId: RUNTIME_ID,
    currentBackendUrl: "https://epmw-auth.fly.dev",
  };

  const pending = evaluateSiteBridgeRequest(base);
  assert.equal(pending.disposition, "confirm");
  assert.equal(pending.ok, false);
  assert.equal(pending.requiresApproval, true);
  assert.equal(pending.clearCredentials, true);

  const approved = evaluateSiteBridgeRequest({
    ...base,
    approvedBackendOrigin: "https://epm.internal.example",
  });
  assert.equal(approved.disposition, "allow");
  assert.equal(approved.backendUrl, "https://epm.internal.example");
  assert.equal(approved.clearCredentials, true);
});

test("clears credentials when replacing an invalid legacy backend value", () => {
  const result = evaluateSiteBridgeRequest({
    message: request("https://epmw-auth.fly.dev", "https://epmw-auth.fly.dev"),
    sender: sender("https://epmw-auth.fly.dev"),
    runtimeId: RUNTIME_ID,
    currentBackendUrl: "https://legacy.example/path-prefix",
  });
  assert.equal(result.disposition, "allow");
  assert.equal(result.originChanged, true);
  assert.equal(result.clearCredentials, true);
});

test("never accepts approval asserted inside untrusted page data", () => {
  const message = request("https://epmw-auth.fly.dev", "https://attacker.example");
  message.data.approvedBackendOrigin = "https://attacker.example";
  message.data.explicitApproval = true;

  const result = evaluateSiteBridgeRequest({
    message,
    sender: sender("https://epmw-auth.fly.dev"),
    runtimeId: RUNTIME_ID,
  });
  assert.equal(result.disposition, "confirm");
});

test("denies spoofed, untrusted, malformed, and insecure requests", () => {
  const cases = [
    {
      message: request("https://attacker.example", "https://epmw-auth.fly.dev"),
      sender: sender("https://epmw-auth.fly.dev"),
    },
    {
      message: request("https://epmw-auth.fly.dev", "https://epmw-auth.fly.dev"),
      sender: sender("https://epmw-auth.fly.dev", { id: "another-extension" }),
    },
    {
      message: request("https://attacker.example", "https://attacker.example"),
      sender: sender("https://attacker.example"),
    },
    {
      message: request("https://epmw-auth.fly.dev", "http://attacker.example"),
      sender: sender("https://epmw-auth.fly.dev"),
    },
    {
      message: request("https://epmw-auth.fly.dev", "https://epmw-auth.fly.dev/base"),
      sender: sender("https://epmw-auth.fly.dev"),
    },
  ];

  for (const entry of cases) {
    const result = evaluateSiteBridgeRequest({
      ...entry,
      runtimeId: RUNTIME_ID,
    });
    assert.equal(result.disposition, "deny", result.reason);
    assert.equal(result.ok, false);
  }
});

test("trusted launch without a backend update remains allowed", () => {
  const result = evaluateSiteBridgeRequest({
    message: request("http://localhost:3000", null, "site.launch"),
    sender: sender("http://localhost:3000"),
    runtimeId: RUNTIME_ID,
  });
  assert.equal(result.disposition, "allow");
  assert.equal(result.backendUrl, null);
});
