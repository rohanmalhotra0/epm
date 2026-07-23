import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { FirstRunTour, TOUR_FLAG } from "../src/components/FirstRunTour";
import { useUi } from "../src/store/ui";

function renderTour(pathname = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[pathname]}>
        <div className="app-shell">
          <main data-testid="app-background">Application content</main>
          <FirstRunTour />
        </div>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FirstRunTour", () => {
  beforeEach(() => {
    localStorage.clear();
    useUi.setState({
      currentProjectId: "p1",
      oracleGateSkipped: true,
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

  it("shows on first run and can be skipped (sets the flag)", async () => {
    renderTour();
    expect(await screen.findByText("Welcome to EPM Wizard")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Skip tour"));
    expect(localStorage.getItem(TOUR_FLAG)).toBe("1");
    expect(screen.queryByText("Welcome to EPM Wizard")).toBeNull();
  });

  it("walks through the steps and finishes with Done", async () => {
    renderTour();
    await screen.findByText("Welcome to EPM Wizard");
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("Sidebar & pages")).toBeInTheDocument();
    expect(screen.getByText(/Skills, Explorer/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("Command palette")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Done"));
    expect(localStorage.getItem(TOUR_FLAG)).toBe("1");
    expect(screen.queryByText("Command palette")).toBeNull();
  });

  it("does not show when the flag is already set", () => {
    localStorage.setItem(TOUR_FLAG, "1");
    renderTour();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not show until the Oracle gate is resolved", async () => {
    useUi.setState({ oracleGateSkipped: false });
    renderTour();

    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByText("Welcome to EPM Wizard")).not.toBeInTheDocument();

    act(() => useUi.getState().skipOracleGate());
    expect(await screen.findByText("Welcome to EPM Wizard")).toBeInTheDocument();
  });

  it("keeps the app inert and hidden while focus is trapped in the explicit-choice modal", async () => {
    renderTour();
    const dialog = await screen.findByRole("dialog", { name: "Welcome to EPM Wizard" });
    const background = screen.getByTestId("app-background");

    expect(background).toHaveAttribute("aria-hidden", "true");
    expect(background).toHaveProperty("inert", true);
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(dialog).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(background).not.toHaveAttribute("aria-hidden");
    expect(background).not.toHaveAttribute("inert");
  });

  it("stays out of the way when Settings is opened from the sign-in gate", async () => {
    useUi.setState({ oracleGateSkipped: false });
    renderTour("/settings");
    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
