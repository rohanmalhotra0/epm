import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { LandingPage } from "../src/pages/LandingPage";

describe("landing page extension download", () => {
  it("leads with the packaged extension and hosted sign-in actions", () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );

    const headline = screen.getByRole("heading", { name: /EPM work,.*without the click maze/i });
    const hero = headline.closest("section");
    expect(hero).not.toBeNull();

    const download = within(hero!).getByRole("link", { name: /download chrome extension/i });
    expect(download).toHaveAttribute("href", "/epm-wizard-extension.zip");
    expect(download.getAttribute("download")).toMatch(
      /^epm-wizard-extension-\d+\.\d+\.\d+\.zip$/,
    );

    expect(within(hero!).getByRole("link", { name: /continue with google/i })).toHaveAttribute(
      "href",
      "/app",
    );
    expect(within(hero!).getByText(/Chrome 116\+/i)).toBeInTheDocument();
    expect(hero).not.toHaveTextContent("—");
  });

  it("lets keyboard users inspect the simulated run and exposes pressed state", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );

    const targetStage = screen.getByRole("button", { name: /02 REF 42 Actuals/i });
    expect(targetStage).toHaveAttribute("aria-pressed", "false");

    targetStage.focus();
    await user.keyboard("{Enter}");

    expect(targetStage).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Found the Scenario selector")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View verified output" })).toBeInTheDocument();
  });

  it("renders the final simulation state when reduced motion is requested", () => {
    const originalMatchMedia = window.matchMedia;
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: (query: string) => ({
        matches: query === "(prefers-reduced-motion: reduce)",
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        dispatchEvent: () => false,
      }),
    });

    try {
      const { container } = render(
        <MemoryRouter>
          <LandingPage />
        </MemoryRouter>,
      );

      expect(screen.queryByRole("button", { name: "Replay run" })).not.toBeInTheDocument();
      expect(container.querySelector(".lp-agent-run")).not.toHaveClass("is-running");
      expect(screen.getByText("Scenario is now set to Forecast")).toBeVisible();
    } finally {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        value: originalMatchMedia,
      });
    }
  });
});
