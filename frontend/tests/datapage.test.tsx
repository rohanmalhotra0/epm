import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataPage } from "../src/pages/DataPage";
import { useUi } from "../src/store/ui";

const backups = [
  { filename: "epmw-backup-20260718.zip", sizeBytes: 1536, createdAt: "2026-07-18T10:00:00Z" },
];
const disk = {
  dbBytes: 1048576,
  backupsBytes: 2048,
  projects: [{ projectId: "p1", name: "Demo project", artifactBytes: 512, artifactCount: 3 }],
};
const projects = [
  { id: "p1", name: "Demo project", isDefault: true, settings: {}, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z" },
];

function jsonResponse(data: unknown, status = 200) {
  return { ok: true, status, json: async () => data } as Response;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DataPage />
    </QueryClientProvider>,
  );
}

describe("DataPage", () => {
  beforeEach(() => {
    useUi.setState({ currentProjectId: "p1" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL, opts?: RequestInit) => {
        const u = String(url);
        if (u.includes("/api/diagnostics/backups")) {
          if (opts?.method === "POST") {
            return jsonResponse({ filename: "epmw-backup-new.zip", sizeBytes: 10, createdAt: "2026-07-19T00:00:00Z" }, 201);
          }
          return jsonResponse(backups);
        }
        if (u.includes("/api/diagnostics/disk")) return jsonResponse(disk);
        if (u.includes("/api/projects")) return jsonResponse(projects);
        return jsonResponse([]);
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders backups with human-readable sizes", async () => {
    renderPage();
    expect(await screen.findByText("epmw-backup-20260718.zip")).toBeInTheDocument();
    expect(screen.getByText("1.5 KB")).toBeInTheDocument();
  });

  it("renders disk usage summary and per-project sizes", async () => {
    renderPage();
    expect(await screen.findByText("1.0 MB")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
    expect(await screen.findByText("512 B")).toBeInTheDocument();
    expect(screen.getAllByText("Demo project").length).toBeGreaterThan(0);
  });

  it("posts a new backup from the Back up now button", async () => {
    renderPage();
    await screen.findByText("epmw-backup-20260718.zip");
    fireEvent.click(screen.getByText("Back up now"));
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await vi.waitFor(() => {
      const posted = fetchMock.mock.calls.some(
        (c) => String(c[0]).includes("/api/diagnostics/backups") && (c[1] as RequestInit)?.method === "POST",
      );
      expect(posted).toBe(true);
    });
  });

  it("offers export and import controls", async () => {
    renderPage();
    expect(await screen.findByText("Export project")).toBeInTheDocument();
    // Carbon's FileUploaderButton renders the label twice (button + hidden label).
    expect(screen.getAllByText("Import project").length).toBeGreaterThan(0);
  });
});
