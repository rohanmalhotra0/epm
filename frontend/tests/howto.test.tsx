// The two static documentation pages ("How to use" / "How it works") and
// their sidebar navigation entries. Both pages are pure static content, so
// they render without providers or network.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HowToPage } from "../src/pages/HowToPage";
import { HowItWorksPage } from "../src/pages/HowItWorksPage";
import { Sidebar } from "../src/components/Sidebar";
import { useUi } from "../src/store/ui";

afterEach(cleanup);

describe("HowToPage", () => {
  it("renders the guide heading and every task section", () => {
    render(<HowToPage />);
    expect(screen.getByRole("heading", { name: "How to use EPM Wizard" })).toBeInTheDocument();
    for (const section of [
      "Getting started",
      "Build a context",
      "Upload an Application Snapshot",
      "Create a form",
      "Create a business rule",
      "Run rules and runtime prompts",
      "Work from spreadsheets",
      "Visualize cube architecture",
      "Export and share",
      "Safety promises",
    ]) {
      expect(screen.getByRole("heading", { name: new RegExp(section) })).toBeInTheDocument();
    }
  });

  it("shows example chat messages as styled chips", () => {
    render(<HowToPage />);
    expect(
      screen.getByText("Create an Actuals form with level-zero descendants of Total Payroll in rows"),
    ).toBeInTheDocument();
    expect(screen.getByText("Create a business rule that copies Working to Final")).toBeInTheDocument();
    expect(screen.getByText("Visualize OEP_DCSH")).toBeInTheDocument();
    expect(screen.getByText("/context merge snapshot")).toBeInTheDocument();
    // chips carry the chat-example styling with a "You" speaker label
    const chips = document.querySelectorAll(".chat-example");
    expect(chips.length).toBeGreaterThanOrEqual(8);
  });

  it("states the safety promises", () => {
    render(<HowToPage />);
    expect(screen.getByText(/Nothing deploys without your explicit approval/)).toBeInTheDocument();
    expect(screen.getByText(/Secrets never reach the model/)).toBeInTheDocument();
    expect(screen.getByText(/never auto-deployed/)).toBeInTheDocument();
  });
});

describe("HowItWorksPage", () => {
  it("renders the architecture headings", () => {
    render(<HowItWorksPage />);
    expect(screen.getByRole("heading", { name: "How EPM Wizard works" })).toBeInTheDocument();
    for (const section of [
      "The LLM never owns the artifact",
      "The connector boundary",
      "RAG grounding",
      "Snapshot upload",
      "Context versions and provenance",
      "Security and redaction",
      "Local-first data",
    ]) {
      expect(screen.getByRole("heading", { name: section })).toBeInTheDocument();
    }
  });

  it("renders all three SVG diagrams with accessible labels", () => {
    render(<HowItWorksPage />);
    expect(
      screen.getByRole("img", { name: /deterministic deployment pipeline diagram/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /rag grounding flow diagram/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /snapshot upload and merge flow diagram/i })).toBeInTheDocument();
    // and they really are inline <svg> elements
    expect(document.querySelectorAll(".doc-diagram svg").length).toBe(3);
  });

  it("labels pipeline stages inside the diagram", () => {
    render(<HowItWorksPage />);
    const pipeline = screen.getByRole("img", { name: /deterministic deployment pipeline diagram/i });
    for (const stage of ["Intent router", "Proposed spec", "Pydantic validation", "Approval", "Verify"]) {
      expect(pipeline.textContent).toContain(stage);
    }
  });
});

describe("documentation navigation", () => {
  beforeEach(() => {
    useUi.setState({ currentProjectId: "p1", sidebarCollapsed: false });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as Response),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function renderNav(initialPath = "/") {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Sidebar />
          <Routes>
            <Route path="/how-to" element={<HowToPage />} />
            <Route path="/how-it-works" element={<HowItWorksPage />} />
            <Route path="*" element={<div />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("shows both entries in the sidebar nav, before Settings", () => {
    renderNav();
    const howTo = screen.getByRole("link", { name: /How to use/ });
    const howItWorks = screen.getByRole("link", { name: /How it works/ });
    expect(howTo).toHaveAttribute("href", "/how-to");
    expect(howItWorks).toHaveAttribute("href", "/how-it-works");
    const labels = Array.from(document.querySelectorAll(".sidebar-nav .nav-link")).map((el) =>
      (el.textContent ?? "").trim(),
    );
    expect(labels.indexOf("How to use")).toBeLessThan(labels.indexOf("Settings"));
    expect(labels.indexOf("How it works")).toBeLessThan(labels.indexOf("Settings"));
    expect(labels.indexOf("How to use")).toBeGreaterThan(labels.indexOf("Data"));
  });

  it("routes to the guide when 'How to use' is clicked", () => {
    renderNav();
    fireEvent.click(screen.getByRole("link", { name: /How to use/ }));
    expect(screen.getByRole("heading", { name: "How to use EPM Wizard" })).toBeInTheDocument();
  });

  it("routes to the architecture page when 'How it works' is clicked", () => {
    renderNav();
    fireEvent.click(screen.getByRole("link", { name: /How it works/ }));
    expect(screen.getByRole("heading", { name: "How EPM Wizard works" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /rag grounding flow diagram/i })).toBeInTheDocument();
  });
});
