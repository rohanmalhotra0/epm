import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ContextsPage } from "../src/pages/SimplePages";
import { useUi } from "../src/store/ui";

const contexts = [
  {
    id: "cv1",
    projectId: "p1",
    application: "Vision",
    label: "ctx-v1",
    mode: "quick",
    counts: { members: 100, forms: 10, rules: 5 },
    active: true,
    manifest: {
      sections: [{ name: "Dimensions & members", status: "complete", count: 100 }],
    },
    createdAt: "2026-07-01T00:00:00Z",
  },
  {
    id: "cv2",
    projectId: "p1",
    application: "Vision",
    label: "ctx-v2",
    mode: "snapshot",
    counts: { members: 120, forms: 8, rules: 5, smartLists: 3 },
    active: false,
    manifest: {
      sections: [{ name: "Forms inventory", status: "partial", count: 8, note: "sampled" }],
      snapshot: {
        application: "Vision",
        provenance: { exportedBy: "epm_admin", exportedAt: "2026-06-30T12:00:00Z" },
      },
    },
    createdAt: "2026-07-02T00:00:00Z",
  },
];

function jsonResponse(data: unknown, status = 200, ok = true) {
  return { ok, status, statusText: ok ? "OK" : "Not Found", json: async () => data } as Response;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ContextsPage />
    </QueryClientProvider>,
  );
}

describe("ContextsPage version browser", () => {
  beforeEach(() => {
    useUi.setState({ currentProjectId: "p1" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        const u = String(url);
        if (u.includes("/contexts")) return jsonResponse(contexts);
        if (u.includes("/architecture")) return jsonResponse({ detail: "no active context" }, 404, false);
        return jsonResponse([]);
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("expands a version to show manifest sections and snapshot provenance", async () => {
    renderPage();
    expect(await screen.findByText("ctx-v2")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Show details for ctx-v2"));
    // Sections mirror ContextSummaryBlock fields: name, status, count, note.
    expect(screen.getByText("Forms inventory")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
    expect(screen.getByText(/\(8\)\s*sampled/)).toBeInTheDocument();
    // Snapshot provenance from manifest.snapshot.
    expect(screen.getByText("Snapshot provenance")).toBeInTheDocument();
    expect(screen.getByText("epm_admin")).toBeInTheDocument();
    expect(screen.getByText("2026-06-30T12:00:00Z")).toBeInTheDocument();
  });

  it("shows a count diff against the active version with +/− deltas", async () => {
    renderPage();
    await screen.findByText("ctx-v2");
    fireEvent.click(screen.getByLabelText("Show details for ctx-v2"));
    expect(screen.getByText("Compare with active (ctx-v1)")).toBeInTheDocument();
    // members: 100 → 120 (+20)
    expect(screen.getByText("100 → 120")).toBeInTheDocument();
    expect(screen.getByText("+20")).toBeInTheDocument();
    // forms: 10 → 8 (−2)
    expect(screen.getByText("10 → 8")).toBeInTheDocument();
    expect(screen.getByText("−2")).toBeInTheDocument();
    // smartLists only exists on this version: 0 → 3 (+3)
    expect(screen.getByText("0 → 3")).toBeInTheDocument();
    expect(screen.getByText("+3")).toBeInTheDocument();
    // rules unchanged: ±0
    expect(screen.getByText("5 → 5")).toBeInTheDocument();
    expect(screen.getByText("±0")).toBeInTheDocument();
  });

  it("does not offer a diff for the active version and toggles closed again", async () => {
    renderPage();
    await screen.findByText("ctx-v1");
    fireEvent.click(screen.getByLabelText("Show details for ctx-v1"));
    expect(screen.getByText("Dimensions & members")).toBeInTheDocument();
    expect(screen.queryByText(/Compare with active/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Hide details for ctx-v1"));
    expect(screen.queryByText("Dimensions & members")).not.toBeInTheDocument();
  });

  it("shows distinct loading, empty, and architecture-error states", async () => {
    let resolveContexts: ((value: Response) => void) | undefined;
    const pendingContexts = new Promise<Response>((resolve) => {
      resolveContexts = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        const u = String(url);
        if (u.includes("/contexts")) return pendingContexts;
        return jsonResponse({ detail: "no active context" }, 404, false);
      }),
    );

    renderPage();
    expect(screen.getByText("Loading context versions…")).toBeInTheDocument();
    resolveContexts?.(jsonResponse([]));
    expect(await screen.findByText(/No context yet\. Build one/)).toBeInTheDocument();
    expect(await screen.findByText("Architecture is not available yet")).toBeInTheDocument();
  });

  it("loads cube cards concurrently, preserves source order, and isolates a failed cube", async () => {
    const activeRequests = { current: 0, max: 0 };
    const architectures = {
      B: {
        application: "Vision",
        cube: "B",
        cubeType: "BSO",
        dimensionCount: 1,
        dimensions: [{ name: "Entity", type: "entity", group: "organization", memberCount: 10, rootMembers: [] }],
      },
      A: {
        application: "Vision",
        cube: "A",
        cubeType: "ASO",
        dimensionCount: 1,
        dimensions: [{ name: "Account", type: "account", group: "financial", memberCount: 20, rootMembers: [] }],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        const u = String(url);
        if (u.includes("/contexts")) return jsonResponse(contexts);
        if (!u.includes("/architecture")) return jsonResponse([]);
        const cube = new URL(u, "http://localhost").searchParams.get("cube");
        if (!cube) {
          return jsonResponse({ cubes: ["B", "A", "C"], cube: "B", architecture: architectures.B });
        }
        activeRequests.current += 1;
        activeRequests.max = Math.max(activeRequests.max, activeRequests.current);
        await new Promise((resolve) => setTimeout(resolve, cube === "B" ? 18 : cube === "A" ? 8 : 2));
        activeRequests.current -= 1;
        if (cube === "C") return jsonResponse({ detail: "cube unavailable" }, 500, false);
        const architecture = architectures[cube as "A" | "B"];
        return jsonResponse({ cubes: ["B", "A", "C"], cube, architecture });
      }),
    );

    renderPage();
    const cubeB = await screen.findByRole("button", { name: /Explore B, 1 dimensions/ });
    const cubeA = screen.getByRole("button", { name: /Explore A, 1 dimensions/ });
    expect(activeRequests.max).toBe(3);
    expect(cubeB.compareDocumentPosition(cubeA) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("Some cubes could not be loaded")).toBeInTheDocument();
    expect(screen.getByText("C", { selector: ".context-inline-state span" })).toBeInTheDocument();

    fireEvent.click(cubeA);
    expect(await screen.findByRole("region", { name: "A architecture" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Account, Account, 20 members$/ })).toBeInTheDocument();
  });
});
