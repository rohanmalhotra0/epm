import AxeBuilder from "@axe-core/playwright";
import { expect } from "@playwright/test";
import {
  canPingAgent,
  fixtureOrigin,
  fixtureTabId,
  panelMessages,
  startRun,
  test,
} from "./extension.fixtures";

type RequestLog = {
  sequenceIndex: number;
  body: {
    observation?: Record<string, unknown>;
    history?: Array<{ action?: { type?: string }; result?: { ok?: boolean; detail?: string } }>;
  };
};

function collectNamedNodes(value: unknown, seen = new Set<unknown>()): Array<Record<string, unknown>> {
  if (!value || typeof value !== "object" || seen.has(value)) return [];
  seen.add(value);
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectNamedNodes(item, seen));
  }
  const object = value as Record<string, unknown>;
  const here = typeof object.name === "string" && "ref" in object ? [object] : [];
  return [
    ...here,
    ...Object.values(object).flatMap((item) => collectNamedNodes(item, seen)),
  ];
}

test("an installed MV3 extension injects only on Start and drives Oracle-like surfaces", async ({
  controlPage,
  extensionWorker,
  extensionId,
  oraclePage,
}) => {
  expect(extensionWorker.url()).toBe(`chrome-extension://${extensionId}/background/service-worker.js`);

  const tabId = await fixtureTabId(extensionWorker);
  expect(await canPingAgent(extensionWorker, tabId)).toBe(false);

  await oraclePage.bringToFront();
  await expect
    .poll(async () => {
      return extensionWorker.evaluate(async ({ expectedTabId }) => {
        const chromeApi = (
          globalThis as unknown as {
            chrome: {
              tabs: {
                query(query: Record<string, unknown>): Promise<Array<{ id?: number }>>;
              };
            };
          }
        ).chrome;
        return (await chromeApi.tabs.query({ active: true, lastFocusedWindow: true }))[0]?.id ===
          expectedTabId;
      }, { expectedTabId: tabId });
    })
    .toBe(true);

  await startRun(controlPage, "Exercise nested frame, shadow, JET, virtual grid, and canvas");

  await expect.poll(() => canPingAgent(extensionWorker, tabId)).toBe(true);
  await expect
    .poll(async () => {
      const messages = await panelMessages(controlPage);
      const terminal = [...messages].reverse().find((message) => message.type === "status");
      const status = (terminal?.data as { status?: string } | undefined)?.status;
      const error = [...messages].reverse().find((message) => message.type === "error");
      return error ? `error:${JSON.stringify(error.data)}` : status;
    }, { timeout: 60_000 })
    .toBe("done");

  const log = await fetch(`${fixtureOrigin}/__requests`).then(
    (response) => response.json() as Promise<RequestLog[]>,
  );
  expect(log.length).toBeGreaterThanOrEqual(7);

  const firstObservation = log[0]?.body.observation || {};
  const names = new Set(collectNamedNodes(firstObservation).map((node) => node.name));
  for (const expectedName of [
    "Refresh nested form",
    "Scenario",
    "Run business rule",
    "Account 1100",
  ]) {
    expect(names.has(expectedName), `snapshot should expose "${expectedName}"`).toBe(true);
  }

  const observations = log.map((entry) => entry.body.observation || {});
  const canvasObservation = observations.find((observation) =>
    JSON.stringify(observation).includes("Planning data grid"),
  );
  expect(canvasObservation, "snapshot should expose canvas metadata").toBeTruthy();

  const screenshotRequest = log.find((entry) =>
    /^data:image\/(?:png|jpeg|webp);base64,/.test(
      String(entry.body.observation?.screenshot || ""),
    ),
  );
  expect(String(screenshotRequest?.body.observation?.screenshot || "")).toMatch(
    /^data:image\/(?:png|jpeg|webp);base64,/,
  );
  const repeatedScreenshot = log.find((entry) => entry.sequenceIndex === 5);
  expect(repeatedScreenshot?.body.observation?.screenshotMeta).toMatchObject({
    duplicate: true,
  });
  expect(repeatedScreenshot?.body.observation?.screenshot).toBeFalsy();

  for (let index = 1; index < Math.min(log.length, 6); index += 1) {
    const prior = log[index]?.body.history?.at(-1);
    expect(prior?.result, `request ${index} should include the prior action result`).toMatchObject({
      ok: true,
    });
    expect(typeof prior?.result?.detail).toBe("string");
  }

  const eventLog = oraclePage.locator("#eventLog");
  await expect(eventLog).toHaveAttribute("data-nested-clicked", "true");
  await expect(eventLog).toHaveAttribute("data-shadow-typed", "true");
  await expect(eventLog).toHaveAttribute("data-jet-clicked", "true");
  await expect(eventLog).toHaveAttribute("data-virtual-row-clicked", "true");
  await expect(eventLog).toHaveAttribute("data-canvas-clicked", "true");

  await fetch(`${fixtureOrigin}/__reset`, { method: "POST" });
  const messageOffset = (await panelMessages(controlPage)).length;
  await oraclePage.bringToFront();
  await startRun(controlPage, "Record one deliberate failed action");
  await expect
    .poll(async () => {
      const messages = (await panelMessages(controlPage)).slice(messageOffset);
      const terminal = [...messages].reverse().find((message) => message.type === "status");
      return (terminal?.data as { status?: string } | undefined)?.status;
    })
    .toBe("done");
  const failureLog = await fetch(`${fixtureOrigin}/__requests`).then(
    (response) => response.json() as Promise<RequestLog[]>,
  );
  expect(failureLog).toHaveLength(2);
  expect(failureLog[1]?.body.history?.[0]?.result).toMatchObject({
    ok: false,
    detail: expect.stringMatching(/stale|not found/i),
  });
});

test("an untrusted page cannot replace the bound backend origin", async ({
  controlPage,
  extensionWorker,
}) => {
  await expect
    .poll(() =>
      extensionWorker.evaluate(async ({ durableKey }) => {
        const chromeApi = (
          globalThis as unknown as {
            chrome: { storage: { local: { get(key: string): Promise<Record<string, unknown>> } } };
          }
        ).chrome;
        const stored = await chromeApi.storage.local.get(durableKey);
        return (stored[durableKey] as { backendUrl?: string } | undefined)?.backendUrl;
      }, { durableKey: "epmw.durable" }),
    )
    .toBe(fixtureOrigin);

  const response = await controlPage.evaluate(async () => {
    const chromeApi = (
      globalThis as unknown as {
        chrome: { runtime: { sendMessage(message: unknown): Promise<unknown> } };
      }
    ).chrome;
    return chromeApi.runtime.sendMessage({
      kind: "site.configure",
      pageOrigin: "https://untrusted.example",
      data: {
        backendUrl: "https://attacker.example",
        projectId: "attacker-project",
      },
    });
  });
  expect(response).toMatchObject({ ok: false });

  const durable = await extensionWorker.evaluate(async ({ durableKey }) => {
    const chromeApi = (
      globalThis as unknown as {
        chrome: { storage: { local: { get(key: string): Promise<Record<string, unknown>> } } };
      }
    ).chrome;
    return (await chromeApi.storage.local.get(durableKey))[durableKey];
  }, { durableKey: "epmw.durable" }) as { backendUrl?: string; projectId?: string };
  expect(durable).toMatchObject({
    backendUrl: fixtureOrigin,
    projectId: "project-e2e",
  });
});

test("the side panel has named controls and its tabs work from the keyboard", async ({
  controlPage,
}, testInfo) => {
  await expect(controlPage.locator("#workspace")).not.toHaveClass(/\bhidden\b/);
  await expect(controlPage.getByRole("button", { name: "Settings" })).toBeVisible();
  await expect(controlPage.getByRole("textbox", { name: /Goal/ })).toBeVisible();

  const inspectTab = controlPage.getByRole("tab", { name: "Inspect workbook" });
  await inspectTab.focus();
  await controlPage.keyboard.press("Enter");
  await expect(inspectTab).toHaveAttribute("aria-selected", "true");
  await expect(controlPage.locator("#inspectView")).not.toHaveClass(/\bhidden\b/);

  const agentTab = controlPage.getByRole("tab", { name: "Agent" });
  await agentTab.focus();
  await controlPage.keyboard.press("Enter");
  await expect(agentTab).toHaveAttribute("aria-selected", "true");
  await expect(controlPage.locator("#agentView")).toBeVisible();

  const results = await new AxeBuilder({ page: controlPage })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  await testInfo.attach("extension-sidepanel-axe.json", {
    body: Buffer.from(JSON.stringify(results, null, 2)),
    contentType: "application/json",
  });
  expect(results.violations.filter((violation) => violation.impact === "critical")).toEqual([]);
});
