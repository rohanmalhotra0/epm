// The merged in-app guide (/guide): a static page combining the old "How to
// use" and "How it works" content. The page itself is pure static content, so
// it renders with only a router (for its <Link> CTAs) and no network.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GuidePage } from "../src/pages/GuidePage";
import { AppRoutes } from "../src/App";
import { Sidebar } from "../src/components/Sidebar";
import { useUi } from "../src/store/ui";

afterEach(cleanup);

function renderGuide() {
  return render(
    <MemoryRouter>
      <GuidePage />
    </MemoryRouter>,
  );
}

describe("GuidePage", () => {
  it("renders the hero headline as the page's single h1", () => {
    renderGuide();
    expect(
      screen.getByRole("heading", { level: 1, name: /You describe the change\..*Deterministic code ships it\./ }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("renders every major section heading", () => {
    renderGuide();
    for (const section of [
      "The one rule",
      "Five stages, start to verified",
      "Smaller tools that earn their keep",
      "What is guaranteed, and by what",
    ]) {
      expect(screen.getByRole("heading", { level: 2, name: section })).toBeInTheDocument();
    }
    for (const stage of ["Start", "Teach it your application", "Ask for the thing", "Approve and deploy", "Verify and keep"]) {
      expect(screen.getByRole("heading", { level: 3, name: stage })).toBeInTheDocument();
    }
  });

  it("renders the hero CTAs as real links", () => {
    renderGuide();
    expect(screen.getByRole("link", { name: "Connect your tenant" })).toHaveAttribute("href", "/settings");
    const openChat = screen.getAllByRole("link", { name: "Open the chat" });
    expect(openChat.length).toBeGreaterThanOrEqual(1);
    for (const link of openChat) expect(link).toHaveAttribute("href", "/");
  });

  it("shows example chat messages as styled chips with a You speaker label", () => {
    renderGuide();
    expect(
      screen.getByText("Create an Actuals form with level-zero descendants of Total Payroll in rows"),
    ).toBeInTheDocument();
    expect(screen.getByText("Create a business rule that copies Working to Final")).toBeInTheDocument();
    expect(screen.getByText("Visualize OEP_DCSH")).toBeInTheDocument();
    expect(screen.getByText("/context merge snapshot")).toBeInTheDocument();
    expect(screen.getByText("Run the IR rule")).toBeInTheDocument();
    expect(screen.getByText("/run-rule CopyWorkingToFinal")).toBeInTheDocument();
    expect(screen.getByText("Create a form from my spreadsheet layout")).toBeInTheDocument();
    const chips = document.querySelectorAll(".chat-example");
    expect(chips.length).toBeGreaterThanOrEqual(6);
    for (const chip of Array.from(chips)) {
      expect(chip.querySelector(".who")?.textContent).toBe("You");
    }
  });

  it("renders all three SVG diagrams inline with accessible labels", () => {
    renderGuide();
    expect(screen.getByRole("img", { name: /deterministic deployment pipeline diagram/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /rag grounding flow diagram/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /snapshot upload and merge flow diagram/i })).toBeInTheDocument();
    // and they really are inline <svg> elements in their dark containers
    expect(document.querySelectorAll(".guide-diagram svg").length).toBe(3);
  });

  it("labels pipeline stages inside the diagram", () => {
    renderGuide();
    const pipeline = screen.getByRole("img", { name: /deterministic deployment pipeline diagram/i });
    for (const stage of ["Intent router", "Proposed spec", "Pydantic validation", "Approval", "Verify"]) {
      expect(pipeline.textContent).toContain(stage);
    }
  });

  it("states the safety guarantees", () => {
    renderGuide();
    expect(screen.getByText(/Nothing deploys without your explicit approval/)).toBeInTheDocument();
    expect(screen.getByText(/Secrets never reach the model/)).toBeInTheDocument();
    expect(screen.getByText(/never auto-deployed/)).toBeInTheDocument();
  });
});

describe("guide navigation", () => {
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
            <Route path="/guide" element={<GuidePage />} />
            <Route path="*" element={<div />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("shows a single Guide entry in the sidebar nav, between Data and Settings", () => {
    renderNav();
    const guide = screen.getByRole("link", { name: "Guide" });
    expect(guide).toHaveAttribute("href", "/guide");
    // the two old entries are gone
    expect(screen.queryByRole("link", { name: /How to use/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /How it works/ })).toBeNull();
    const labels = Array.from(document.querySelectorAll(".sidebar-nav .nav-link")).map((el) =>
      (el.textContent ?? "").trim(),
    );
    expect(labels.filter((l) => l === "Guide")).toHaveLength(1);
    expect(labels.indexOf("Guide")).toBeGreaterThan(labels.indexOf("Data"));
    expect(labels.indexOf("Guide")).toBeLessThan(labels.indexOf("Settings"));
  });

  it("routes to the guide when the sidebar link is clicked", () => {
    renderNav();
    fireEvent.click(screen.getByRole("link", { name: "Guide" }));
    expect(screen.getByRole("heading", { level: 1, name: /You describe the change/ })).toBeInTheDocument();
  });
});

describe("legacy documentation URLs", () => {
  // The app's REAL route table: these tests fail if App.tsx drops the redirects.
  function renderAt(initialPath: string) {
    return render(
      <MemoryRouter initialEntries={[initialPath]}>
        <AppRoutes />
      </MemoryRouter>,
    );
  }

  it("redirects /how-to to /guide", async () => {
    renderAt("/how-to");
    expect(await screen.findByRole("heading", { level: 1, name: /You describe the change/ })).toBeInTheDocument();
  });

  it("redirects /how-it-works to /guide", async () => {
    renderAt("/how-it-works");
    expect(await screen.findByRole("heading", { level: 1, name: /You describe the change/ })).toBeInTheDocument();
  });
});
