import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LandingPage } from "../src/pages/LandingPage";

describe("landing page extension download", () => {
  it("offers the packaged extension from the public Browser Agent section", () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );

    const download = screen.getByRole("link", { name: /download chrome extension/i });
    expect(download).toHaveAttribute("href", "/epm-wizard-extension.zip");
    expect(download.getAttribute("download")).toMatch(
      /^epm-wizard-extension-\d+\.\d+\.\d+\.zip$/,
    );
  });
});
