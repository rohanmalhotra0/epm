import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FirstRunTour, TOUR_FLAG } from "../src/components/FirstRunTour";

describe("FirstRunTour", () => {
  beforeEach(() => localStorage.clear());

  it("shows on first run and can be skipped (sets the flag)", () => {
    render(<FirstRunTour />);
    expect(screen.getByText("Welcome to EPM Wizard")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Skip tour"));
    expect(localStorage.getItem(TOUR_FLAG)).toBe("1");
    expect(screen.queryByText("Welcome to EPM Wizard")).toBeNull();
  });

  it("walks through the steps and finishes with Done", () => {
    render(<FirstRunTour />);
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("Sidebar & pages")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("Command palette")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Done"));
    expect(localStorage.getItem(TOUR_FLAG)).toBe("1");
    expect(screen.queryByText("Command palette")).toBeNull();
  });

  it("does not show when the flag is already set", () => {
    localStorage.setItem(TOUR_FLAG, "1");
    const { container } = render(<FirstRunTour />);
    expect(container).toBeEmptyDOMElement();
  });
});
