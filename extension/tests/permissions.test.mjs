import assert from "node:assert/strict";
import { test } from "node:test";

import {
  currentSitePermission,
  requestCurrentSiteAccess,
} from "../sidepanel/permissions.js";

function chromeFor({
  tab = { id: 7, url: "https://planning.example.com/epm/app" },
  contains = false,
  request = true,
  addHostAccessRequest,
} = {}) {
  const calls = { contains: [], request: [], addHostAccessRequest: [] };
  return {
    calls,
    tabs: {
      async query(query) {
        assert.deepEqual(query, { active: true, lastFocusedWindow: true });
        return tab ? [tab] : [];
      },
    },
    permissions: {
      async contains(value) {
        calls.contains.push(value);
        return contains;
      },
      async request(value) {
        calls.request.push(value);
        return request;
      },
      ...(addHostAccessRequest === undefined ? {} : {
        async addHostAccessRequest(value) {
          calls.addHostAccessRequest.push(value);
          return addHostAccessRequest;
        },
      }),
    },
  };
}

test("current-site permission rejects missing, invalid, and non-web tab URLs before URL construction", () => {
  for (const value of [
    undefined,
    "",
    "not a url",
    "chrome://extensions",
    "file:///tmp/oracle.html",
    "http://planning.example.com/epm",
  ]) {
    assert.throws(() => currentSitePermission(value), /Oracle|current|valid|HTTPS/);
  }
});

test("current-site permission normalizes only the exact HTTPS origin", () => {
  assert.deepEqual(
    currentSitePermission("https://planning.example.com:8443/HyperionPlanning/faces/PlanningCentral"),
    {
      origin: "https://planning.example.com:8443",
      pattern: "https://planning.example.com:8443/*",
    },
  );
});

test("denied current-site grant adds no access and reports the exact origin", async () => {
  const chromeApi = chromeFor({ request: false });
  const result = await requestCurrentSiteAccess(chromeApi);
  assert.equal(result.granted, false);
  assert.equal(result.origin, "https://planning.example.com");
  assert.deepEqual(chromeApi.calls.request, [{
    origins: ["https://planning.example.com/*"],
  }]);
});

test("granted current-site access requests only the normalized origin", async () => {
  const chromeApi = chromeFor({ request: true });
  const result = await requestCurrentSiteAccess(chromeApi);
  assert.equal(result.granted, true);
  assert.equal(result.alreadyGranted, false);
  assert.deepEqual(chromeApi.calls.contains, [{
    origins: ["https://planning.example.com/*"],
  }]);
  assert.deepEqual(chromeApi.calls.request, [{
    origins: ["https://planning.example.com/*"],
  }]);
});

test("an already-granted origin is verified without another permission request", async () => {
  const chromeApi = chromeFor({ contains: true });
  const result = await requestCurrentSiteAccess(chromeApi);
  assert.equal(result.granted, true);
  assert.equal(result.alreadyGranted, true);
  assert.deepEqual(chromeApi.calls.request, []);
});

test("a hidden tab URL uses Chrome's current-tab host-access request when available", async () => {
  const chromeApi = chromeFor({
    tab: { id: 9 },
    addHostAccessRequest: undefined,
  });
  chromeApi.permissions.addHostAccessRequest = async (value) => {
    chromeApi.calls.addHostAccessRequest.push(value);
  };
  const result = await requestCurrentSiteAccess(chromeApi);
  assert.deepEqual(result, {
    granted: false,
    pendingBrowserApproval: true,
    tabId: 9,
  });
  assert.deepEqual(chromeApi.calls.addHostAccessRequest, [{ tabId: 9 }]);
  assert.deepEqual(chromeApi.calls.request, []);
});
