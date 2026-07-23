import fs from "node:fs";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const remoteBaseUrl = process.env.E2E_BASE_URL?.trim().replace(/\/+$/, "");
const isRemote = Boolean(remoteBaseUrl);
const baseURL = remoteBaseUrl || "http://127.0.0.1:13000";
const authStatePath = path.resolve(
  process.env.E2E_STORAGE_STATE || "playwright/.auth/user.json",
);
const hasAuthState = fs.existsSync(authStatePath);
const slowMo = Number.parseInt(process.env.E2E_SLOW_MO || "0", 10);

export default defineConfig({
  testDir: "./e2e",
  outputDir: "test-results",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI
    ? [["github"], ["html", { outputFolder: "playwright-report", open: "never" }]]
    : [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL,
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    ignoreHTTPSErrors: process.env.E2E_IGNORE_HTTPS_ERRORS === "1",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    launchOptions: slowMo > 0 ? { slowMo } : undefined,
    // Local/CI has no OAuth proxy. This header simulates the identity that the
    // trusted proxy injects and exercises real multi-user backend scoping.
    extraHTTPHeaders: isRemote
      ? undefined
      : { "X-Forwarded-Email": process.env.E2E_USER_EMAIL || "agent-e2e@example.test" },
    // Remote/staging runs reuse a real OAuth session captured by e2e:auth.
    storageState: isRemote && hasAuthState ? authStatePath : undefined,
  },
  webServer: isRemote
    ? undefined
    : {
        command: "node e2e/start-stack.mjs",
        url: `${baseURL}/api/health`,
        reuseExistingServer: !process.env.CI,
        timeout: 5 * 60_000,
        stdout: "pipe",
        stderr: "pipe",
      },
  projects: [
    {
      name: "chromium",
      testIgnore: /.*\.setup\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        channel: "chromium",
      },
    },
    {
      name: "auth-capture",
      testMatch: /auth\.setup\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        channel: "chromium",
        storageState: { cookies: [], origins: [] },
        trace: "off",
        video: "off",
      },
    },
  ],
});
