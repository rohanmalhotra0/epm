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
    manifest: { sections: [] },
    createdAt: "2026-07-01T00:00:00Z",
  },
  {
    id: "cv2",
    projectId: "p1",
    application: "Vision",
    label: "ctx-v2",
    mode: "snapshot",
    counts: { members: 120, forms: 8, rules: 5 },
    active: false,
    manifest: { sections: [] },
    createdAt: "2026-07-02T00:00:00Z",
  },
];

const diff = {
  versionA: { id: "cv2", label: "ctx-v2" },
  versionB: { id: "cv1", label: "ctx-v1" },
  kinds: {
    member: {
      added: [{ name: "New Account", dimension: "Account", cube: "OEP_FS" }],
      removed: [{ name: "Old Account", dimension: "Account", cube: "OEP_FS" }],
      changed: [{ name: "Salaries", dimension: "Account", before: { alias: "Sal" }, after: { alias: "Salaries" } }],
      addedTruncated: 3,
      removedTruncated: 0,
      changedTruncated: 0,
    },
  },
};

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

describe("ContextsPage detailed diff", () => {
  beforeEach(() => {
    useUi.setState({ currentProjectId: "p1" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        const u = String(url);
        if (u.includes("/diff")) return jsonResponse(diff);
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

  it("fetches and renders per-kind record diffs with +N more from truncated counts", async () => {
    renderPage();
    await screen.findByText("ctx-v2");
    fireEvent.click(screen.getByLabelText("Show details for ctx-v2"));
    expect(await screen.findByText("Detailed diff (vs. ctx-v1)")).toBeInTheDocument();
    // Per-kind panel header + counts (await the async diff fetch).
    expect(await screen.findByText("member")).toBeInTheDocument();
    expect(screen.getByText(/1 added · 1 removed · 1 changed/)).toBeInTheDocument();
    // Records surfaced by name · dimension.
    expect(screen.getByText("New Account · Account")).toBeInTheDocument();
    expect(screen.getByText("Old Account · Account")).toBeInTheDocument();
    expect(screen.getByText("Salaries · Account")).toBeInTheDocument();
    // Truncated overflow surfaced as "+N more".
    expect(screen.getByText(/\+3 more added/)).toBeInTheDocument();
    // Hits the diff endpoint with the ACTIVE version as baseline (A) and the
    // viewed version as B, so added/removed match the count-delta direction.
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    expect(
      fetchMock.mock.calls.some((c) => String(c[0]).includes("/api/contexts/cv1/diff?against=cv2")),
    ).toBe(true);
  });
});
