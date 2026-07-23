import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { FirstRunTour } from "../src/components/FirstRunTour";
import { SignInGate } from "../src/components/SignIn";
import { useUi } from "../src/store/ui";

function renderFirstRun(pathname = "/") {
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
              <main data-testid="app-content">Application content</main>
            </SignInGate>
          </div>
          <FirstRunTour />
        </div>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SignInGate first-run accessibility", () => {
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

  it("exposes only the labelled sign-in dialog until the user chooses to continue", async () => {
    renderFirstRun();

    const signIn = await screen.findByRole("dialog", { name: "Sign in to Oracle EPM" });
    expect(signIn).toHaveAttribute("aria-modal", "true");
    expect(screen.queryByTestId("app-content")).not.toBeInTheDocument();
    expect(screen.queryByText("Welcome to EPM Wizard")).not.toBeInTheDocument();

    expect(screen.getByLabelText("Instance URL")).toBeInTheDocument();
    expect(screen.getByLabelText("Authentication")).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Application")).toBeInTheDocument();
    expect(screen.getByLabelText("Classification")).toBeInTheDocument();
  });

  it("makes the entire app-shell background inert and restores it before showing the tour", async () => {
    renderFirstRun();
    await screen.findByRole("dialog", { name: "Sign in to Oracle EPM" });

    const header = screen.getByTestId("app-header");
    const sidebar = screen.getByTestId("app-sidebar");
    expect(header).toHaveAttribute("aria-hidden", "true");
    expect(sidebar).toHaveAttribute("aria-hidden", "true");
    expect(header).toHaveProperty("inert", true);
    expect(sidebar).toHaveProperty("inert", true);

    fireEvent.click(screen.getByRole("button", { name: /Continue without Oracle/ }));

    expect(await screen.findByRole("dialog", { name: "Welcome to EPM Wizard" })).toBeInTheDocument();
    expect(screen.getByTestId("app-content")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Sign in to Oracle EPM" })).not.toBeInTheDocument();
    expect(header).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByTestId("app-body")).toHaveAttribute("aria-hidden", "true");
  });

  it("allows Settings through without layering the tour over it", async () => {
    renderFirstRun("/settings");

    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getByTestId("app-content")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
