import fs from "node:fs";
import path from "node:path";
import { expect, test as setup } from "@playwright/test";

const authStatePath = path.resolve(
  process.env.E2E_STORAGE_STATE || "playwright/.auth/user.json",
);

setup("capture an interactive OAuth session", async ({ page, baseURL }) => {
  setup.setTimeout(10 * 60_000);

  if (!process.env.E2E_BASE_URL || !baseURL) {
    throw new Error(
      "OAuth capture is only for a deployed environment. Set E2E_BASE_URL=https://your-host.",
    );
  }

  fs.mkdirSync(path.dirname(authStatePath), { recursive: true });
  const appUrl = new URL("/app", baseURL);

  // The headed browser intentionally pauses here for the human-controlled
  // provider/MFA step. No password, OAuth secret, or MFA seed enters the suite.
  await page.goto(appUrl.toString(), { waitUntil: "domcontentloaded" });
  await page.waitForURL(
    (url) => url.origin === appUrl.origin && url.pathname.startsWith("/app"),
    { timeout: 9 * 60_000 },
  );
  await expect(page.getByRole("button", { name: "Toggle sidebar" })).toBeVisible();
  await page.context().storageState({ path: authStatePath });
});
