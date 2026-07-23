import { expect, test } from "@playwright/test";

test("the local proxy simulation preserves multi-user project isolation", async ({
  playwright,
  baseURL,
}) => {
  test.skip(Boolean(process.env.E2E_BASE_URL), "Remote OAuth owns identity headers.");

  const marker = `alice-only-${Date.now()}`;
  const alice = await playwright.request.newContext({
    baseURL,
    extraHTTPHeaders: { "X-Forwarded-Email": "alice-e2e@example.test" },
  });
  const bob = await playwright.request.newContext({
    baseURL,
    extraHTTPHeaders: { "X-Forwarded-Email": "bob-e2e@example.test" },
  });

  try {
    const created = await alice.post("/api/projects", {
      data: { name: marker, description: "E2E identity boundary" },
    });
    expect(created.status()).toBe(201);

    const bobProjects = await bob.get("/api/projects");
    expect(bobProjects.ok()).toBeTruthy();
    const names = (await bobProjects.json()).map((project: { name: string }) => project.name);
    expect(names).not.toContain(marker);
  } finally {
    await alice.dispose();
    await bob.dispose();
  }
});
