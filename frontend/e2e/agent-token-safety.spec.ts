import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures";

const token = {
  id: "token-browser-test",
  name: "Automation laptop",
  prefix: "epmw_browser",
  createdAt: "2026-07-23T12:00:00Z",
  lastUsedAt: null,
};

test("API token revoke is an accessible, explicit danger confirmation", async ({
  appPage,
}, testInfo) => {
  let revoked = false;
  let deleteRequests = 0;
  await appPage.route("**/api/ext-tokens**", async (route) => {
    const request = route.request();
    if (request.method() === "DELETE") {
      deleteRequests += 1;
      revoked = true;
      // A routed 204 is surfaced by Chromium as ERR_ABORTED even though the
      // application handles it; return an empty JSON success for this mock.
      await route.fulfill({ status: 200, json: {} });
      return;
    }
    await route.fulfill({ json: revoked ? [] : [token] });
  });

  await appPage.goto("/app/agent");
  const revokeButton = appPage.getByRole("button", { name: "Revoke Automation laptop" });
  await expect(revokeButton).toBeVisible();
  await revokeButton.click();

  expect(deleteRequests).toBe(0);
  const dialog = appPage.getByRole("alertdialog", {
    name: "Revoke “Automation laptop”?",
  });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("epmw_browser");
  await expect(dialog).toContainText("This action cannot be undone.");
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  await expect
    .poll(() =>
      dialog.evaluate((element) =>
        getComputedStyle(element.closest(".cds--modal") as Element).opacity,
      ),
    )
    .toBe("1");

  const axe = await new AxeBuilder({ page: appPage })
    .include('[role="alertdialog"]')
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  await testInfo.attach("token-revoke-dialog-axe.json", {
    body: Buffer.from(JSON.stringify(axe, null, 2)),
    contentType: "application/json",
  });
  expect(
    axe.violations.filter(({ impact }) => impact === "critical" || impact === "serious"),
  ).toEqual([]);

  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(revokeButton).toBeFocused();
  expect(deleteRequests).toBe(0);

  await revokeButton.click();
  await appPage
    .getByRole("alertdialog", { name: "Revoke “Automation laptop”?" })
    .getByRole("button", { name: /Revoke token$/ })
    .click();

  await expect(revokeButton).toBeHidden();
  expect(deleteRequests).toBe(1);
});

test.describe("phone-sized Browser Agent", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("token controls fit without horizontal overflow", async ({ appPage }) => {
    await appPage.route("**/api/ext-tokens**", (route) =>
      route.fulfill({ json: [token] }),
    );
    await appPage.goto("/app/agent");

    await expect(appPage.getByRole("button", { name: "Generate token" })).toBeVisible();
    await expect(appPage.getByRole("button", { name: "Revoke Automation laptop" })).toBeVisible();
    await expect
      .poll(() =>
        appPage.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        ),
      )
      .toBeLessThanOrEqual(1);
  });
});
