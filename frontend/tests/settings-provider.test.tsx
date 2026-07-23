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

const environments = [
  {
    id: "env-dev",
    projectId: "p1",
    name: "Development",
    baseUrl: "https://dev.example.com",
    username: "dev-user",
    classification: "development",
    demo: false,
    connected: false,
  },
  {
    id: "env-prod",
    projectId: "p1",
    name: "Production",
    baseUrl: "https://prod.example.com",
    username: "prod-user",
    classification: "production",
    demo: false,
    connected: true,
  },
];

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
            return jsonResponse({ id: "pr1", name: "OpenAI", providerType: "openai", models: [], roleModels: {} }, 201);
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
    fireEvent.change(nameInput, { target: { value: "OpenAI" } });
    fireEvent.change(screen.getByPlaceholderText("Embedding model (RAG)"), {
      target: { value: "text-embedding-3-small" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await vi.waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => String(c[0]) === "/api/providers" && (c[1] as RequestInit)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.roleModels).toEqual({ embedding: "text-embedding-3-small" });
      expect(body.name).toBe("OpenAI");
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

  it("merges role model inputs (chat/fast/structured/code + embedding) into roleModels", async () => {
    renderPage();
    fireEvent.change(screen.getAllByPlaceholderText("Name")[0], { target: { value: "Multi" } });
    fireEvent.change(screen.getByPlaceholderText("Chat model"), { target: { value: "gpt-chat" } });
    fireEvent.change(screen.getByPlaceholderText("Fast model"), { target: { value: "gpt-fast" } });
    fireEvent.change(screen.getByPlaceholderText("Structured model"), { target: { value: "gpt-struct" } });
    fireEvent.change(screen.getByPlaceholderText("Code model"), { target: { value: "gpt-code" } });
    fireEvent.change(screen.getByPlaceholderText("Embedding model (RAG)"), { target: { value: "emb-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await vi.waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => String(c[0]) === "/api/providers" && (c[1] as RequestInit)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.roleModels).toEqual({
        chat: "gpt-chat",
        fast: "gpt-fast",
        structured: "gpt-struct",
        code: "gpt-code",
        embedding: "emb-1",
      });
      // Transient form-only fields must not leak into the payload.
      expect(body.chatModel).toBeUndefined();
      expect(body.embeddingModel).toBeUndefined();
    });
  });

  it("includes only the non-empty role model keys", async () => {
    renderPage();
    fireEvent.change(screen.getAllByPlaceholderText("Name")[0], { target: { value: "Partial" } });
    fireEvent.change(screen.getByPlaceholderText("Code model"), { target: { value: "only-code" } });
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await vi.waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => String(c[0]) === "/api/providers" && (c[1] as RequestInit)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.roleModels).toEqual({ code: "only-code" });
    });
  });

  it("sends roleModels.vision in the create-provider payload", async () => {
    renderPage();
    fireEvent.change(screen.getAllByPlaceholderText("Name")[0], { target: { value: "Vision" } });
    fireEvent.change(screen.getByPlaceholderText("Vision model (screenshots)"), {
      target: { value: "qwen2.5-vl:7b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await vi.waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (c) => String(c[0]) === "/api/providers" && (c[1] as RequestInit)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.roleModels).toEqual({ vision: "qwen2.5-vl:7b" });
      expect(body.visionModel).toBeUndefined();
    });
  });

  it("exposes persistent labels for provider and environment fields", async () => {
    renderPage();

    expect(await screen.findByLabelText("Provider name")).toHaveAttribute("id", "provider-name");
    expect(screen.getByLabelText("Provider type")).toHaveAttribute("id", "provider-type");
    expect(screen.getByLabelText("Base URL (optional)")).toHaveAttribute("id", "provider-base-url");
    expect(screen.getByLabelText("Default model")).toHaveAttribute("id", "provider-default-model");
    expect(screen.getByLabelText("API key")).toHaveAttribute("id", "provider-api-key");
    expect(screen.getByLabelText("Embedding model (RAG)")).toHaveAttribute("id", "provider-embedding-model");

    expect(screen.getByLabelText("Environment name")).toHaveAttribute("id", "environment-name");
    expect(screen.getByLabelText("Classification")).toHaveAttribute("id", "environment-classification");
    expect(screen.getByLabelText("Base URL")).toHaveAttribute("id", "environment-base-url");
    expect(screen.getByLabelText("Username")).toHaveAttribute("id", "environment-username");
    expect(screen.getByLabelText("Demo environment (no Oracle tenant)")).toHaveAttribute("id", "environment-demo");
  });

  it("names table scroll regions and gives every environment password a unique accessible name", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL) => {
        const u = String(url);
        if (u.includes("/api/providers")) return jsonResponse([]);
        if (u.includes("/api/diagnostics/logs")) return jsonResponse({ logs: [] });
        if (u.includes("/api/diagnostics")) return jsonResponse(diagnostics);
        if (u.includes("/environments")) return jsonResponse(environments);
        return jsonResponse([]);
      }),
    );

    renderPage();

    expect(await screen.findByRole("region", { name: "AI Providers" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("region", { name: "Oracle Environments" })).toHaveAttribute("tabindex", "0");
    expect(await screen.findByLabelText("Password for Development")).toHaveAttribute(
      "id",
      "environment-password-env-dev",
    );
    expect(screen.getByLabelText("Password for Production")).toHaveAttribute(
      "id",
      "environment-password-env-prod",
    );
  });
});
