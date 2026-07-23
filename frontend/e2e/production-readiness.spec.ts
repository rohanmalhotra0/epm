import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";
import { expect, test } from "./fixtures";

const SERIOUS_IMPACTS = new Set(["critical", "serious"]);

async function expectNoSeriousA11yViolations(
  page: Page,
  testInfo: TestInfo,
  surface: string,
  include: string,
) {
  const results = await new AxeBuilder({ page })
    .include(include)
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

  await testInfo.attach(`${surface}-axe-results.json`, {
    body: Buffer.from(JSON.stringify(results, null, 2)),
    contentType: "application/json",
  });

  const serious = results.violations
    .filter((violation) => violation.impact && SERIOUS_IMPACTS.has(violation.impact))
    .map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      help: violation.help,
      targets: violation.nodes.map((node) => node.target),
    }));

  expect(serious, `${surface} has serious or critical axe violations`).toEqual([]);
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect
    .poll(
      () =>
        page.evaluate(
          () =>
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
        ),
      { message: "document should not overflow the narrow viewport horizontally" },
    )
    .toBeLessThanOrEqual(1);
}

test("first run presents an accessible sign-in gate, then a focused welcome tour", async ({
  page,
}, testInfo) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    localStorage.removeItem("epmw-tour-done");
    localStorage.removeItem("epmw-ui");
  });
  await page.goto("/app", { waitUntil: "domcontentloaded" });

  const signIn = page.getByRole("dialog", { name: "Sign in to Oracle EPM" });
  await expect(signIn).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(page.getByRole("dialog", { name: /Welcome to EPM Wizard/ })).toHaveCount(0);
  await expect(signIn).toHaveAttribute("aria-modal", "true");
  await expect(signIn.getByLabel("Instance URL")).toBeFocused();
  await expect(signIn.getByLabel("Authentication")).toBeVisible();
  await expect(signIn.getByLabel("Username")).toBeVisible();
  await expect(
    signIn.getByRole("textbox", { name: "Password", exact: true }),
  ).toHaveAttribute("type", "password");
  await expectNoSeriousA11yViolations(page, testInfo, "oracle-sign-in", '[role="dialog"]');

  await signIn.getByRole("button", { name: /Continue without Oracle/ }).click();

  const tour = page.getByRole("dialog", { name: /Welcome to EPM Wizard/ });
  await expect(tour).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(signIn).toHaveCount(0);
  await expect(tour).toHaveAttribute("aria-modal", "true");
  await expect
    .poll(() =>
      page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]'))),
    )
    .toBe(true);

  // Keyboard focus must not escape to the app shell behind the modal.
  await tour.getByRole("button", { name: "Next" }).focus();
  await page.keyboard.press("Tab");
  await expect
    .poll(() =>
      page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]'))),
    )
    .toBe(true);

  // The tour is an explicit product choice, not an accidentally dismissible overlay.
  await page.keyboard.press("Escape");
  await expect(tour).toBeVisible();
  await expectNoSeriousA11yViolations(page, testInfo, "welcome-tour", '[role="dialog"]');

  await tour.getByRole("button", { name: "Skip tour" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByLabel("Message EPM Wizard")).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("epmw-tour-done")))
    .toBe("1");

  await page.reload();
  await expect(page.getByLabel("Message EPM Wizard")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("Skills and Explorer are first-class sidebar destinations", async ({ appPage }) => {
  const skills = appPage.getByRole("link", { name: "Skills", exact: true });
  const explorer = appPage.getByRole("link", { name: "Explorer", exact: true });

  await expect(skills).toBeVisible();
  await expect(explorer).toBeVisible();

  await skills.click();
  await expect(appPage).toHaveURL(/\/app\/skills$/);
  await expect(appPage.getByRole("heading", { name: "Skills", level: 2 })).toBeVisible();
  await expect(skills).toHaveAttribute("aria-current", "page");

  await explorer.click();
  await expect(appPage).toHaveURL(/\/app\/explorer$/);
  await expect(
    appPage.getByRole("heading", { name: "Metadata explorer", level: 2 }),
  ).toBeVisible();
  await expect(explorer).toHaveAttribute("aria-current", "page");
});

test("core keyboard shortcuts and command-palette navigation work without a mouse", async ({
  appPage,
}, testInfo) => {
  const composer = appPage.getByLabel("Message EPM Wizard");
  await composer.focus();

  await appPage.keyboard.press("Control+K");
  const palette = appPage.getByRole("dialog", { name: "Command palette" });
  const search = palette.getByLabel("Command palette search");
  await expect(palette).toBeVisible();
  await expect(search).toBeFocused();
  await expectNoSeriousA11yViolations(
    appPage,
    testInfo,
    "command-palette",
    '[aria-label="Command palette"]',
  );

  await appPage.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);

  await appPage.keyboard.press("Control+/");
  await expect(composer).toBeFocused();

  await appPage.keyboard.press("Control+K");
  await expect(search).toBeFocused();
  for (let index = 0; index < 4; index += 1) {
    await appPage.keyboard.press("ArrowDown");
  }
  await expect(appPage.locator(".cmdk-item.active")).toContainText("Skills");
  await appPage.keyboard.press("Enter");
  await expect(appPage).toHaveURL(/\/app\/skills$/);

  await appPage.keyboard.press("Control+K");
  await expect(search).toBeFocused();
  for (let index = 0; index < 5; index += 1) {
    await appPage.keyboard.press("ArrowDown");
  }
  await expect(appPage.locator(".cmdk-item.active")).toContainText("Explorer");
  await appPage.keyboard.press("Enter");
  await expect(appPage).toHaveURL(/\/app\/explorer$/);
});

test.describe("narrow viewport", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("landing and app navigation remain usable on a phone-sized screen", async ({
    appPage,
  }) => {
    await appPage.goto("/");
    await expect(appPage.getByRole("main")).toBeVisible();
    await expect(appPage.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(appPage.getByRole("link", { name: /Google/i }).first()).toBeVisible();
    await expectNoHorizontalOverflow(appPage);

    await appPage.goto("/app");
    await expect(appPage.getByLabel("Message EPM Wizard")).toBeVisible();
    const toggleSidebar = appPage.getByRole("button", { name: "Toggle sidebar" });
    await expect(toggleSidebar).toBeVisible();

    await toggleSidebar.click();
    await appPage.getByRole("link", { name: "Skills", exact: true }).click();
    await expect(appPage).toHaveURL(/\/app\/skills$/);
    await expect(appPage.getByRole("heading", { name: "Skills", level: 2 })).toBeVisible();

    const sidebar = appPage.locator(".epmw-sidebar");
    await expect(sidebar).toBeHidden();
    await expectNoHorizontalOverflow(appPage);
  });

  test("settings tables scroll internally without widening the page", async ({
    appPage,
  }) => {
    await appPage.goto("/app/settings");
    await expect(
      appPage.getByRole("heading", { name: "Settings", level: 2 }),
    ).toBeVisible();

    const providers = appPage.getByRole("region", { name: "AI Providers" });
    await expect(providers).toBeVisible();
    await expect
      .poll(() =>
        providers.evaluate(
          (element) => element.scrollWidth > element.clientWidth,
        ),
      )
      .toBe(true);
    await expectNoHorizontalOverflow(appPage);
  });
});
