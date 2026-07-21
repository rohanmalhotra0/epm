import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "../src/pages/SettingsPage";
import { useUi } from "../src/store/ui";

const diagnostics = {
  appVersion: "0.0-test",
  activeProvider: "mock",
  activeModel: "mock-model",
  redactionHealthy: true,
  subsystems: [],
};

function jsonResponse(data: unknown, status = 200) {
  return { ok: true, status, statusText: "OK", json: async () => data } as Response;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage provider form", () => {
  beforeEach(() => {
    useUi.setState({ currentProjectId: "p1" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL, opts?: RequestInit) => {
        const u = String(url);
        if (u.includes("/api/providers")) {
          if (opts?.method === "POST") {
            return jsonResponse({ id: "pr1", name: "Watsonx", providerType: "watsonx", models: [], roleModels: {} }, 201);
          }
          return jsonResponse([]);
        }
        if (u.includes("/api/diagnostics/logs")) return jsonResponse({ logs: [] });
        if (u.includes("/api/diagnostics")) return jsonResponse(diagnostics);
        if (u.includes("/environments")) return jsonResponse([]);
        return jsonResponse([]);
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the embedding model input with its RAG helper text", async () => {
    renderPage();
    expect(await screen.findByPlaceholderText("Embedding model (RAG)")).toBeInTheDocument();
    expect(
      screen.getByText(/Used for hybrid RAG scoring; leave empty for the provider default/),
    ).toBeInTheDocument();
  });

  it("sends roleModels.embedding in the create-provider payload", async () => {
    renderPage();
    const nameInput = screen.getAllByPlaceholderText("Name")[0];
    fireEvent.change(nameInput, { target: { value: "Watsonx" } });
    fireEvent.change(screen.getByPlaceholderText("Embedding model (RAG)"), {
      target: { value: "ibm/slate-125m-english-rtrvr" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await vi.waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => String(c[0]) === "/api/providers" && (c[1] as RequestInit)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.roleModels).toEqual({ embedding: "ibm/slate-125m-english-rtrvr" });
      expect(body.name).toBe("Watsonx");
      // The transient form-only field must not leak into the payload.
      expect(body.embeddingModel).toBeUndefined();
    });
  });

  it("omits roleModels when the embedding model is left empty", async () => {
    renderPage();
    fireEvent.change(screen.getAllByPlaceholderText("Name")[0], { target: { value: "Plain" } });
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await vi.waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => String(c[0]) === "/api/providers" && (c[1] as RequestInit)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.roleModels).toBeUndefined();
    });
  });
});
