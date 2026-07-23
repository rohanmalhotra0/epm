import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures";

test("public landing and documentation work like a visitor", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /EPM work.*without the click maze/i }),
  ).toBeVisible();

  const hero = page.locator(".lp-hero");
  await expect(hero.getByRole("link", { name: "Download Chrome extension" })).toHaveAttribute(
    "href",
    "/epm-wizard-extension.zip",
  );
  await expect(hero.getByRole("link", { name: "Continue with Google" })).toHaveAttribute(
    "href",
    "/app",
  );

  await page.getByRole("link", { name: "Docs" }).first().click();
  await expect(page).toHaveURL(/\/docs$/);
  await expect(
    page.getByRole("heading", { name: "The AI workspace for Oracle EPM implementation" }),
  ).toBeVisible();
});

test("public landing is accessible on desktop and mobile", async ({ page }, testInfo) => {
  for (const viewport of [
    { width: 1440, height: 900, name: "desktop" },
    { width: 390, height: 844, name: "mobile" },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    await testInfo.attach(`landing-axe-${viewport.name}.json`, {
      body: Buffer.from(JSON.stringify(results, null, 2)),
      contentType: "application/json",
    });
    expect(results.violations.filter((violation) => violation.impact === "critical")).toEqual([]);
    expect(
      results.violations.filter((violation) => violation.impact === "serious"),
    ).toEqual([]);
  }
});

test("a user can deliberately continue without an Oracle tenant", async ({ page }) => {
  await page.goto("/app");

  await expect(page.getByRole("heading", { name: "Sign in to Oracle EPM" })).toBeVisible();
  await page.getByRole("button", { name: /Continue without Oracle/ }).click();
  await expect(page.getByLabel("Message EPM Wizard")).toBeVisible();
});

test("an agent can navigate the real app and complete a streamed chat turn", async ({
  appPage,
}) => {
  await appPage.getByRole("link", { name: "Settings" }).click();
  await expect(appPage.getByRole("heading", { name: "Settings" })).toBeVisible();

  await appPage.goto("/app");
  const composer = appPage.getByLabel("Message EPM Wizard");
  await composer.fill("/help");
  await appPage.getByRole("button", { name: "Send" }).click();

  await expect(appPage.getByText("What EPM Wizard can do", { exact: true })).toBeVisible();
  await expect(appPage.getByText("/context", { exact: true })).toBeVisible();
});

test("critical accessibility checks run against public and authenticated surfaces", async ({
  appPage,
}, testInfo) => {
  const results = await new AxeBuilder({ page: appPage })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

  await testInfo.attach("axe-results.json", {
    body: Buffer.from(JSON.stringify(results, null, 2)),
    contentType: "application/json",
  });

  const critical = results.violations.filter((violation) => violation.impact === "critical");
  expect(critical).toEqual([]);
});
