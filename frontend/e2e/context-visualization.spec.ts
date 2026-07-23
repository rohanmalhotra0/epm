import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const contexts = [
  {
    id: "context-active",
    projectId: "project-e2e",
    application: "Vision",
    label: "vision-context-v4",
    mode: "quick",
    counts: { members: 64, forms: 8, rules: 4 },
    active: true,
    manifest: { sections: [] },
    createdAt: "2026-07-23T12:00:00Z",
  },
];

const architectures = {
  Plan1: {
    application: "Vision",
    cube: "Plan1",
    cubeType: "BSO",
    dimensionCount: 3,
    dimensions: [
      {
        name: "Account",
        type: "account",
        group: "financial",
        memberCount: 36,
        rootMembers: ["Account"],
        status: "available",
      },
      {
        name: "Entity",
        type: "entity",
        group: "organization",
        memberCount: 18,
        rootMembers: ["Total Entity"],
        status: "available",
      },
      {
        name: "Scenario",
        type: "scenario",
        group: "context",
        memberCount: 4,
        rootMembers: ["Scenario"],
        status: "available",
      },
    ],
  },
  Workforce: {
    application: "Vision",
    cube: "Workforce",
    cubeType: "BSO",
    dimensionCount: 2,
    dimensions: [
      {
        name: "Employee",
        type: "custom",
        group: "organization",
        memberCount: 128,
        rootMembers: ["All Employees"],
        status: "available",
      },
      {
        name: "Job",
        type: "custom",
        group: "custom",
        memberCount: 22,
        rootMembers: ["All Jobs"],
        status: "available",
      },
    ],
  },
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem(
      "epmw-ui",
      JSON.stringify({ state: { oracleGateSkipped: true }, version: 0 }),
    );
  });
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    let body: unknown = [];
    let status = 200;
    if (url.pathname === "/api/projects") {
      body = [{
        id: "project-e2e",
        name: "Visualization QA",
        description: "",
        isDefault: true,
        settings: {},
        createdAt: "2026-07-23T12:00:00Z",
        updatedAt: "2026-07-23T12:00:00Z",
      }];
    } else if (url.pathname === "/api/projects/project-e2e/contexts") {
      body = contexts;
    } else if (url.pathname === "/api/projects/project-e2e/architecture") {
      const cube = url.searchParams.get("cube") || "Plan1";
      const architecture = architectures[cube as keyof typeof architectures];
      if (!architecture) {
        status = 404;
        body = { detail: "cube not found" };
      } else {
        body = { cubes: ["Plan1", "Workforce"], cube, architecture };
      }
    }
    return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/app/contexts");
  await expect(page.getByRole("heading", { name: "Cube architecture" })).toBeVisible();
});

test("a keyboard and pointer user can explore, search, select, zoom, and pan", async ({ page }) => {
  const workforceCard = page.getByRole("button", { name: /Explore Workforce, 2 dimensions/ });
  await expect(workforceCard).toBeVisible();
  await workforceCard.focus();
  await workforceCard.press("Enter");

  const architecture = page.getByRole("region", { name: "Workforce architecture" });
  await expect(architecture).toBeVisible();
  const employee = page.getByRole("button", { name: /^Employee, Custom, 128 members$/ });
  await employee.focus();
  await employee.press("Enter");
  await expect(employee).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("complementary", { name: "Employee details" })).toContainText("All Employees");

  const search = page.getByRole("searchbox", { name: "Search dimensions" });
  await search.fill("job");
  await expect(page.getByText("1 of 2")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Job, Custom, 22 members$/ })).toBeVisible();
  await search.fill("");

  await expect(page.locator(".architecture-zoom-value")).toHaveText("100%");
  const viewport = page.getByRole("group", { name: /Interactive architecture for Workforce/ });
  await viewport.focus();
  await viewport.press("+");
  await expect(page.locator(".architecture-zoom-value")).toHaveText("115%");
  await viewport.press("0");
  await expect(page.locator(".architecture-zoom-value")).toHaveText("100%");

  const transform = page.locator(".architecture-pan-zoom");
  const beforeDrag = await transform.getAttribute("style");
  const box = await viewport.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width / 2 + 48, box!.y + box!.height / 2 + 24, { steps: 4 });
  await page.mouse.up();
  await expect(transform).not.toHaveAttribute("style", beforeDrag || "");
});

test("the visualization is accessible, reduced-motion aware, and mobile-safe", async ({
  page,
}, testInfo) => {
  await page.locator(".context-cube-card").last().evaluate((element) =>
    Promise.all(element.getAnimations().map((animation) => animation.finished)));
  const axeResults = await new AxeBuilder({ page })
    .include(".context-architecture-section")
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  await testInfo.attach("context-architecture-axe.json", {
    body: Buffer.from(JSON.stringify(axeResults, null, 2)),
    contentType: "application/json",
  });
  expect(
    axeResults.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious"),
  ).toEqual([]);

  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.getByRole("button", { name: /Explore Plan1, 3 dimensions/ })).toHaveCSS("animation-name", "none");

  await page.setViewportSize({ width: 390, height: 844 });
  const documentWidth = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(documentWidth.scroll).toBeLessThanOrEqual(documentWidth.client);

  await page.getByRole("button", { name: /Explore Plan1, 3 dimensions/ }).click();
  await expect(page.getByRole("region", { name: "Plan1 architecture" })).toBeVisible();
  const detailWidth = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(detailWidth.scroll).toBeLessThanOrEqual(detailWidth.client);
  await expect(page.locator(".architecture-node-enter").first()).toHaveCSS("animation-name", "none");
});
