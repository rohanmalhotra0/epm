import { defineConfig } from "@playwright/test";

const fixturePort = Number.parseInt(process.env.E2E_EXTENSION_PORT || "14783", 10);
const fixtureOrigin =
  process.env.E2E_EXTENSION_ORIGIN?.trim().replace(/\/+$/, "") ||
  `http://127.0.0.1:${fixturePort}`;

export default defineConfig({
  testDir: "./e2e-extension",
  testMatch: "**/*.spec.ts",
  outputDir: "test-results/extension",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI
    ? [
        ["github"],
        ["html", { outputFolder: "playwright-report/extension", open: "never" }],
      ]
    : [
        ["list"],
        ["html", { outputFolder: "playwright-report/extension", open: "never" }],
      ],
  use: {
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  webServer: {
    command: `node e2e-extension/fixture-server.mjs --port ${fixturePort}`,
    url: `${fixtureOrigin}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    stdout: "pipe",
    stderr: "pipe",
  },
  projects: [{ name: "installed-extension" }],
});
