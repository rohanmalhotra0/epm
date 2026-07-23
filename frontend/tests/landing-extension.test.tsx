import { render, screen, within } from "@testing-library/react";
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
  });
});
