import {
  expect,
  test as base,
  type ConsoleMessage,
  type Page,
} from "@playwright/test";

type Fixtures = {
  appPage: Page;
};

function stableAppState() {
  localStorage.setItem(
    "epmw-ui",
    JSON.stringify({ state: { oracleGateSkipped: true }, version: 0 }),
  );
}

function consoleError(message: ConsoleMessage): string {
  const location = message.location();
  const suffix = location.url ? ` (${location.url}:${location.lineNumber})` : "";
  return `console.${message.type()}: ${message.text()}${suffix}`;
}

export const test = base.extend<Fixtures>({
  appPage: async ({ page, baseURL }, use) => {
    const diagnostics: string[] = [];

    page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") diagnostics.push(consoleError(message));
    });
    page.on("requestfailed", (request) => {
      if (request.url().includes("/api/")) {
        diagnostics.push(
          `requestfailed: ${request.method()} ${request.url()} — ${request.failure()?.errorText}`,
        );
      }
    });
    page.on("response", (response) => {
      if (response.url().includes("/api/") && response.status() >= 500) {
        diagnostics.push(`server ${response.status()}: ${response.request().method()} ${response.url()}`);
      }
    });

    await page.addInitScript(stableAppState);
    await page.goto("/app", { waitUntil: "domcontentloaded" });

    const expectedOrigin = new URL(baseURL!).origin;
    const actual = new URL(page.url());
    if (actual.origin !== expectedOrigin || actual.pathname.startsWith("/oauth2")) {
      throw new Error(
        `The app redirected to OAuth (${page.url()}). For staging, run ` +
          "`E2E_BASE_URL=https://… npm run e2e:auth` once, then rerun the suite.",
      );
    }

    await expect(page.getByLabel("Message EPM Wizard")).toBeVisible();
    await use(page);

    expect.soft(diagnostics, "browser console/network diagnostics").toEqual([]);
  },
});

export { expect } from "@playwright/test";
