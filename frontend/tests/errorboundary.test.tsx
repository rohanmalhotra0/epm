import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorBoundary } from "../src/components/ErrorBoundary";
import { ACCEPTED_EXTENSIONS } from "../src/api/attachments";

function Boom({ explode }: { explode: boolean }): JSX.Element {
  if (explode) throw new Error("kaboom in render");
  return <div>all good</div>;
}

describe("ErrorBoundary", () => {
  // React logs the caught error to console.error; silence it for clean output.
  let spy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    spy = vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => spy.mockRestore());

  it("renders a recovery card instead of a blank screen when a child throws", () => {
    render(
      <ErrorBoundary>
        <Boom explode />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
    expect(screen.getByText(/kaboom in render/)).toBeInTheDocument();
    // Recovery affordances are present.
    expect(screen.getByText("Try again")).toBeInTheDocument();
    expect(screen.getByText("Reload app")).toBeInTheDocument();
  });

  it("renders children normally when nothing throws", () => {
    render(
      <ErrorBoundary>
        <Boom explode={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("all good")).toBeInTheDocument();
  });

  it("resets when resetKey changes (navigation recovers a crashed view)", () => {
    const { rerender } = render(
      <ErrorBoundary resetKey="/a">
        <Boom explode />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    // Simulate navigating to a different, healthy route.
    rerender(
      <ErrorBoundary resetKey="/b">
        <Boom explode={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("all good")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("'Try again' clears the error state", () => {
    // A component that throws once, then recovers, mimics a transient failure.
    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("transient");
      return <div>recovered</div>;
    }
    render(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    shouldThrow = false;
    fireEvent.click(screen.getByText("Try again"));
    expect(screen.getByText("recovered")).toBeInTheDocument();
  });
});

describe("attachment extension contract", () => {
  // The backend (backend/app/services/attachments.py) accepts exactly this set.
  // Advertising `.txt` here caused uploads that only failed after the round-trip.
  it("advertises only backend-accepted extensions (no .txt)", () => {
    expect(ACCEPTED_EXTENSIONS).toEqual([".xlsx", ".xlsm", ".csv", ".zip"]);
    expect(ACCEPTED_EXTENSIONS).not.toContain(".txt");
  });
});
