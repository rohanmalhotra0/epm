import { describe, it, expect, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { Toaster } from "../src/components/Toaster";
import { toast, useToasts } from "../src/store/toast";

afterEach(() => {
  act(() => useToasts.setState({ toasts: [] }));
});

describe("notifications", () => {
  it("renders a toast raised from anywhere", () => {
    render(<Toaster />);
    act(() => {
      toast.success("Connected to Oracle EPM", "MCWPCF");
    });
    expect(screen.getByText("Connected to Oracle EPM")).toBeInTheDocument();
    expect(screen.getByText("MCWPCF")).toBeInTheDocument();
  });

  it("shows nothing when there are no toasts", () => {
    const { container } = render(<Toaster />);
    expect(container).toBeEmptyDOMElement();
  });
});
