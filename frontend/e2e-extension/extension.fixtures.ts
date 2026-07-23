import { test as base, chromium, type BrowserContext, type Page, type Worker } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const extensionRoot = path.resolve(here, "../../extension");
export const fixtureOrigin =
  process.env.E2E_EXTENSION_ORIGIN?.trim().replace(/\/+$/, "") ||
  `http://127.0.0.1:${process.env.E2E_EXTENSION_PORT || "14783"}`;

type ExtensionFixtures = {
  extensionContext: BrowserContext;
  extensionWorker: Worker;
  extensionId: string;
  controlPage: Page;
  oraclePage: Page;
};

type ChromeApi = {
  runtime: {
    id: string;
    connect(options: { name: string }): {
      postMessage(message: unknown): void;
      onMessage: { addListener(listener: (message: unknown) => void): void };
    };
    sendMessage(message: unknown): Promise<unknown>;
  };
  storage: {
    local: {
      clear(): Promise<void>;
      get(key: string): Promise<Record<string, unknown>>;
      set(value: Record<string, unknown>): Promise<void>;
    };
    session: { clear(): Promise<void> };
  };
  tabs: {
    query(query: Record<string, unknown>): Promise<Array<{ id?: number; url?: string }>>;
    sendMessage(tabId: number, message: unknown): Promise<unknown>;
  };
};

export const test = base.extend<ExtensionFixtures>({
  extensionContext: async ({}, use, testInfo) => {
    const userDataDir = testInfo.outputPath("chromium-profile");
    const loadedExtensionRoot = testInfo.outputPath("unpacked-extension");
    fs.cpSync(extensionRoot, loadedExtensionRoot, { recursive: true });
    const manifestPath = path.join(loadedExtensionRoot, "manifest.json");
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as {
      host_permissions?: string[];
      permissions?: string[];
    };
    // Playwright cannot click browser-chrome toolbar actions, so it cannot
    // manufacture an activeTab grant. Pre-grant only the isolated fixture
    // origin in the temporary unpacked copy; the production manifest remains
    // unchanged and agent code still is not injected until Start.
    manifest.host_permissions = [
      ...(manifest.host_permissions || []),
      `${fixtureOrigin}/*`,
    ].filter((value, index, values) => values.indexOf(value) === index);
    // The real UI requests debugger only when a user chooses canvas control.
    // Browser-chrome permission prompts are likewise inaccessible to
    // Playwright, so pre-grant it in this temporary copy to exercise the CDP
    // screenshot and coordinate path.
    manifest.permissions = [...(manifest.permissions || []), "debugger"].filter(
      (value, index, values) => values.indexOf(value) === index,
    );
    fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    const context = await chromium.launchPersistentContext(userDataDir, {
      channel: "chromium",
      headless: process.env.PW_EXTENSION_HEADED !== "1" && !process.env.PWDEBUG,
      viewport: { width: 1280, height: 800 },
      args: [
        `--disable-extensions-except=${loadedExtensionRoot}`,
        `--load-extension=${loadedExtensionRoot}`,
        "--no-first-run",
        "--no-default-browser-check",
      ],
    });
    await use(context);
    await context.close();
  },

  extensionWorker: async ({ extensionContext }, use) => {
    let worker = extensionContext.serviceWorkers()[0];
    worker ||= await extensionContext.waitForEvent("serviceworker", { timeout: 20_000 });
    await use(worker);
  },

  extensionId: async ({ extensionWorker }, use) => {
    const id = new URL(extensionWorker.url()).host;
    if (!id) throw new Error(`Could not derive extension ID from ${extensionWorker.url()}`);
    await use(id);
  },

  controlPage: async ({ extensionContext, extensionWorker, extensionId }, use) => {
    await fetch(`${fixtureOrigin}/__reset`, { method: "POST" });
    await extensionWorker.evaluate(
      async ({ backendUrl }) => {
        const chromeApi = (globalThis as unknown as { chrome: ChromeApi }).chrome;
        await chromeApi.storage.local.clear();
        await chromeApi.storage.session.clear();
        await chromeApi.storage.local.set({
          "epmw.durable": {
            backendUrl,
            projectId: "project-e2e",
            apiToken: "",
            enforceGuardrails: false,
          },
        });
      },
      { backendUrl: fixtureOrigin },
    );

    const page = await extensionContext.newPage();
    await page.goto(`chrome-extension://${extensionId}/sidepanel/sidepanel.html`);
    await page.evaluate(() => {
      const chromeApi = (globalThis as unknown as { chrome: ChromeApi }).chrome;
      const port = chromeApi.runtime.connect({ name: "epmw-panel" });
      const target = globalThis as unknown as {
        __epmwE2ePort: typeof port;
        __epmwE2eMessages: unknown[];
      };
      target.__epmwE2ePort = port;
      target.__epmwE2eMessages = [];
      port.onMessage.addListener((message) => target.__epmwE2eMessages.push(message));
    });
    await page.evaluate(
      ({ backendUrl }) => {
        const target = globalThis as unknown as {
          __epmwE2ePort: { postMessage(message: unknown): void };
        };
        target.__epmwE2ePort.postMessage({
          cmd: "setConfig",
          data: {
            backendUrl,
            projectId: "project-e2e",
            enforceGuardrails: false,
            stepDelayMs: 0,
            maxSteps: 8,
          },
        });
      },
      { backendUrl: fixtureOrigin },
    );
    await use(page);
  },

  oraclePage: async ({ extensionContext, controlPage }, use) => {
    void controlPage;
    const page = await extensionContext.newPage();
    await page.goto(`${fixtureOrigin}/fixture/oracle-shell.html`);
    await page.bringToFront();
    await use(page);
  },
});

export async function fixtureTabId(worker: Worker): Promise<number> {
  return worker.evaluate(async () => {
    const chromeApi = (globalThis as unknown as { chrome: ChromeApi }).chrome;
    // Permission-minimized extensions cannot read tab URLs before activeTab is
    // granted. The fixture makes the Oracle page active before asking for its ID.
    const tabs = await chromeApi.tabs.query({ active: true, lastFocusedWindow: true });
    const tab = tabs[0];
    if (tab?.id == null) throw new Error(`Active fixture tab not found among ${JSON.stringify(tabs)}`);
    return tab.id;
  });
}

export async function canPingAgent(worker: Worker, tabId: number): Promise<boolean> {
  return worker.evaluate(async ({ targetTabId }) => {
    const chromeApi = (globalThis as unknown as { chrome: ChromeApi }).chrome;
    try {
      const response = await chromeApi.tabs.sendMessage(targetTabId, { kind: "cs.ping" });
      return Boolean((response as { ok?: boolean } | undefined)?.ok);
    } catch {
      return false;
    }
  }, { targetTabId: tabId });
}

export async function startRun(controlPage: Page, goal: string): Promise<void> {
  await controlPage.evaluate((runGoal) => {
    const goalField = document.querySelector<HTMLTextAreaElement>("#goal");
    const start = document.querySelector<HTMLButtonElement>("#startBtn");
    if (!goalField || !start) throw new Error("The side-panel Start controls are unavailable");
    goalField.value = runGoal;
    goalField.dispatchEvent(new Event("input", { bubbles: true }));
    start.click();
  }, goal);
}

export async function panelMessages(controlPage: Page): Promise<Array<Record<string, unknown>>> {
  return controlPage.evaluate(() => {
    const target = globalThis as unknown as { __epmwE2eMessages: Array<Record<string, unknown>> };
    return target.__epmwE2eMessages;
  });
}
