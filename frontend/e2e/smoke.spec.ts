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

  await page.getByRole("link", { name: "Documentation" }).first().click();
  await expect(page).toHaveURL(/\/docs$/);
  await expect(
    page.getByRole("heading", { name: "The AI workspace for Oracle EPM implementation" }),
  ).toBeVisible();
});

test("public landing and documentation are accessible on desktop and mobile", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const viewport of [
    { width: 1440, height: 900, name: "desktop" },
    { width: 390, height: 844, name: "mobile" },
  ]) {
    await page.setViewportSize(viewport);
    for (const surface of [
      { name: "landing", path: "/" },
      { name: "documentation", path: "/docs#agent" },
    ]) {
      await page.goto(surface.path);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      await testInfo.attach(`${surface.name}-axe-${viewport.name}.json`, {
        body: Buffer.from(JSON.stringify(results, null, 2)),
        contentType: "application/json",
      });
      expect(
        results.violations.filter((violation) => violation.impact === "critical"),
      ).toEqual([]);
      expect(
        results.violations.filter((violation) => violation.impact === "serious"),
      ).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        ),
      ).toBeLessThanOrEqual(1);
    }
  }
});

test("landing sections stay inside the viewport at every responsive breakpoint", async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });

  for (const viewport of [
    { width: 1440, height: 900, name: "wide" },
    { width: 1280, height: 900, name: "medium-edge" },
    { width: 1179, height: 900, name: "reported-pane" },
    { width: 962, height: 844, name: "screenshot-width" },
    { width: 780, height: 844, name: "tablet-edge" },
    { width: 390, height: 844, name: "phone" },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByRole("main")).toBeVisible();

    const audit = await page.evaluate(() => {
      const viewportWidth = document.documentElement.clientWidth;
      const describe = (element: Element) => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName.toLowerCase(),
          className:
            typeof element.className === "string" ? element.className.slice(0, 100) : "",
          text: (element.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 100),
          left: Math.round(rect.left * 10) / 10,
          right: Math.round(rect.right * 10) / 10,
          width: Math.round(rect.width * 10) / 10,
        };
      };

      const outOfBounds = Array.from(document.querySelectorAll(".lp *"))
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return (
            style.display !== "none" &&
            rect.width > 1 &&
            rect.height > 1 &&
            (rect.left < -1 || rect.right > viewportWidth + 1)
          );
        })
        .map(describe);

      const layoutSurfaces = document.querySelectorAll(
        [
          ".lp-hero-copy",
          ".lp-hero-visual",
          ".lp-proof",
          ".lp-section-heading",
          ".lp-workflow-copy",
          ".lp-product-frame",
          ".lp-use-case-grid",
          ".lp-final-card",
          ".lp-footer-inner",
        ].join(","),
      );
      const uncontainedOverflow = Array.from(layoutSurfaces)
        .filter((element) => {
          const node = element as HTMLElement;
          const style = getComputedStyle(element);
          return (
            node.clientWidth > 0 &&
            node.scrollWidth > node.clientWidth + 1 &&
            style.overflowX !== "auto" &&
            style.overflowX !== "scroll" &&
            style.overflowX !== "hidden" &&
            style.overflowX !== "clip"
          );
        })
        .map(describe);

      const workflowColumns = Array.from(document.querySelectorAll(".lp-workflow")).map(
        (element) => getComputedStyle(element).gridTemplateColumns.split(" ").length,
      );

      return {
        documentOverflow:
          document.documentElement.scrollWidth - document.documentElement.clientWidth,
        outOfBounds,
        uncontainedOverflow,
        workflowColumns,
      };
    });

    expect(audit.documentOverflow, `${viewport.name} document overflow`).toBeLessThanOrEqual(1);
    expect(audit.outOfBounds, `${viewport.name} elements outside viewport`).toEqual([]);
    expect(audit.uncontainedOverflow, `${viewport.name} uncontained element overflow`).toEqual([]);

    if (viewport.width <= 1280) {
      expect(audit.workflowColumns, `${viewport.name} workflows should stack`).toEqual([1, 1, 1]);
    }

    if (["reported-pane", "screenshot-width", "phone"].includes(viewport.name)) {
      await testInfo.attach(`landing-layout-${viewport.name}.png`, {
        body: await page.screenshot(),
        contentType: "image/png",
      });
    }
  }
});

test("a user can deliberately continue without an Oracle tenant", async ({ page }) => {
  await page.goto("/app");

  await expect(page.getByRole("heading", { name: "Connect your Oracle EPM instance" })).toBeVisible();
  await page.getByRole("button", { name: "Not now" }).click();
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
