import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Sidebar } from "../src/components/Sidebar";
import { useUi } from "../src/store/ui";

// jsdom has no ResizeObserver; Carbon's OverflowMenu expects one.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as Record<string, unknown>).ResizeObserver = ResizeObserverStub;

const active = [
  { id: "c2", projectId: "p1", title: "Beta", pinned: false, archived: false, createdAt: "2026-07-01T00:00:00Z", updatedAt: "2026-07-02T00:00:00Z" },
  { id: "c1", projectId: "p1", title: "Alpha", pinned: true, archived: false, createdAt: "2026-06-01T00:00:00Z", updatedAt: "2026-06-01T00:00:00Z" },
];
const withArchived = [
  ...active,
  { id: "c3", projectId: "p1", title: "Old chat", pinned: false, archived: true, createdAt: "2026-05-01T00:00:00Z", updatedAt: "2026-05-01T00:00:00Z" },
];

function jsonResponse(data: unknown) {
  return { ok: true, status: 200, json: async () => data } as Response;
}

function renderSidebar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Sidebar conversation management", () => {
  beforeEach(() => {
    useUi.setState({ currentProjectId: "p1", sidebarCollapsed: false });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        const u = String(url);
        if (u.includes("include_archived=true")) return jsonResponse(withArchived);
        if (u.includes("/conversations")) return jsonResponse(active);
        return jsonResponse([]);
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("lists conversations pinned-first", async () => {
    renderSidebar();
    await screen.findByText("Alpha");
    const titles = Array.from(document.querySelectorAll(".conv-list .conv-item .title")).map(
      (el) => el.textContent,
    );
    expect(titles).toEqual(["Alpha", "Beta"]);
    expect(screen.getByRole("button", { name: "Alpha Pinned" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Beta" })).toBeInTheDocument();
  });

  it("shows a per-conversation overflow menu with management actions", async () => {
    renderSidebar();
    await screen.findByText("Alpha");
    fireEvent.click(screen.getAllByLabelText("Options for Alpha")[0]);
    expect(await screen.findByText("Rename")).toBeInTheDocument();
    expect(screen.getByText("Unpin")).toBeInTheDocument();
    expect(screen.getByText("Archive")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
  });

  it("opens a danger confirm modal before deleting", async () => {
    renderSidebar();
    await screen.findByText("Beta");
    fireEvent.click(screen.getAllByLabelText("Options for Beta")[0]);
    fireEvent.click(await screen.findByText("Delete"));
    expect(screen.getByText('Delete "Beta"?')).toBeInTheDocument();
    expect(screen.getByText(/permanently deletes/)).toBeInTheDocument();
  });

  it("expands the archived section and fetches archived conversations", async () => {
    renderSidebar();
    await screen.findByText("Alpha");
    expect(screen.queryByText("Old chat")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Archived"));
    expect(await screen.findByText("Old chat")).toBeInTheDocument();
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("include_archived=true"))).toBe(true);
  });

  it("links to every page promised by the first-run tour", async () => {
    renderSidebar();
    await screen.findByText("Alpha");

    expect(screen.getByRole("complementary", { name: "Workspace sidebar" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skills" })).toHaveAttribute("href", "/skills");
    expect(screen.getByRole("link", { name: "Explorer" })).toHaveAttribute("href", "/explorer");
  });

  it("closes the sidebar after mobile navigation", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: true,
        media: "(max-width: 767px)",
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    renderSidebar();
    await screen.findByText("Alpha");

    fireEvent.click(screen.getByRole("link", { name: "Explorer" }));
    expect(useUi.getState().sidebarCollapsed).toBe(true);
  });
});
