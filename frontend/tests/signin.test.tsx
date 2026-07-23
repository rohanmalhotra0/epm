import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { SignInGate } from "../src/components/SignIn";
import { useUi } from "../src/store/ui";

function renderSignInGate(pathname = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[pathname]}>
        <div className="app-shell">
          <header data-testid="app-header">Header</header>
          <div className="app-body" data-testid="app-body">
            <aside data-testid="app-sidebar">Sidebar</aside>
            <SignInGate>
              <main data-testid="app-content">
                Application content
                <textarea aria-label="Message EPM Wizard" />
              </main>
            </SignInGate>
          </div>
        </div>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SignInGate accessibility", () => {
  beforeEach(() => {
    localStorage.clear();
    useUi.setState({
      currentProjectId: "p1",
      oracleGateSkipped: false,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => [],
      })),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads chat behind a labelled connection dialog", async () => {
    renderSignInGate();

    const signIn = await screen.findByRole("dialog", { name: "Connect your Oracle EPM instance" });
    expect(signIn).toHaveAttribute("aria-modal", "true");
    expect(screen.getByTestId("app-content")).toBeInTheDocument();
    expect(screen.getByTestId("app-content")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByTestId("app-content")).toHaveProperty("inert", true);
    expect(screen.queryByText("Welcome to EPM Wizard")).not.toBeInTheDocument();

    expect(screen.getByLabelText("Instance URL")).toBeInTheDocument();
    expect(screen.getByLabelText("Authentication")).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.getByText("Advanced connection options")).toBeInTheDocument();
    await vi.waitFor(() => expect(screen.getByLabelText("Instance URL")).toHaveFocus());
  });

  it("keeps secondary fields in an advanced disclosure and preserves secret input types", async () => {
    renderSignInGate();
    const dialog = await screen.findByRole("dialog", { name: "Connect your Oracle EPM instance" });
    const disclosure = screen.getByText("Advanced connection options").closest("details");

    expect(disclosure).not.toBeNull();
    expect(disclosure).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Advanced connection options"));
    expect(disclosure).toHaveAttribute("open");
    expect(screen.getByLabelText("Application")).toBeInTheDocument();
    expect(screen.getByLabelText("Classification")).toBeInTheDocument();
    expect(screen.getByLabelText("Credentials file")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Authentication"), { target: { value: "oauth" } });
    expect(screen.getByLabelText("Token URL")).toBeInTheDocument();
    expect(screen.getByLabelText("Client ID")).toBeInTheDocument();
    expect(screen.getByLabelText("Client secret")).toHaveAttribute("type", "password");
    expect(dialog).toBeInTheDocument();
  });

  it("restores the app immediately after the user continues without Oracle", async () => {
    renderSignInGate();
    await screen.findByRole("dialog", { name: "Connect your Oracle EPM instance" });

    const header = screen.getByTestId("app-header");
    const sidebar = screen.getByTestId("app-sidebar");
    expect(header).toHaveAttribute("aria-hidden", "true");
    expect(sidebar).toHaveAttribute("aria-hidden", "true");
    expect(header).toHaveProperty("inert", true);
    expect(sidebar).toHaveProperty("inert", true);

    fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(await screen.findByTestId("app-content")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await vi.waitFor(() => expect(screen.getByLabelText("Message EPM Wizard")).toHaveFocus());
    expect(screen.queryByText("Welcome to EPM Wizard")).not.toBeInTheDocument();
    expect(header).not.toHaveAttribute("aria-hidden");
    expect(sidebar).not.toHaveAttribute("aria-hidden");
    expect(header).not.toHaveAttribute("inert");
    expect(sidebar).not.toHaveAttribute("inert");
  });

  it("dismisses with Escape and returns focus to chat", async () => {
    renderSignInGate();
    const dialog = await screen.findByRole("dialog", { name: "Connect your Oracle EPM instance" });

    fireEvent.keyDown(dialog, { key: "Escape", code: "Escape", keyCode: 27 });

    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await vi.waitFor(() => expect(screen.getByLabelText("Message EPM Wizard")).toHaveFocus());
  });

  it("dismisses from the close button and returns focus to chat", async () => {
    renderSignInGate();
    await screen.findByRole("dialog", { name: "Connect your Oracle EPM instance" });

    fireEvent.click(screen.getByRole("button", { name: "Connect later" }));

    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await vi.waitFor(() => expect(screen.getByLabelText("Message EPM Wizard")).toHaveFocus());
  });

  it("allows Settings through without layering a modal over it", async () => {
    renderSignInGate("/settings");

    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getByTestId("app-content")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
