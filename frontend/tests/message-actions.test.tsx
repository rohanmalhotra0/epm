import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { MessageView } from "../src/components/Message";
import { useToasts } from "../src/store/toast";

const writeText = vi.fn().mockResolvedValue(undefined);
Object.assign(navigator, { clipboard: { writeText } });

afterEach(() => {
  vi.clearAllMocks();
  act(() => useToasts.setState({ toasts: [] }));
});

describe("message actions", () => {
  it("copies the raw message content and raises a toast", async () => {
    render(
      <MessageView message={{ id: "m1", role: "assistant", content: "**bold** raw markdown" }} onAction={() => {}} />,
    );
    fireEvent.click(screen.getByLabelText("Copy message"));
    expect(writeText).toHaveBeenCalledWith("**bold** raw markdown");
    await waitFor(() => {
      expect(useToasts.getState().toasts.some((t) => t.title === "Copied to clipboard")).toBe(true);
    });
  });

  it("shows a copy button on user messages too", () => {
    render(<MessageView message={{ id: "m2", role: "user", content: "hello" }} onAction={() => {}} />);
    expect(screen.getByLabelText("Copy message")).toBeInTheDocument();
  });

  it("shows Regenerate only when a handler is provided", () => {
    const onRegenerate = vi.fn();
    const { rerender } = render(
      <MessageView message={{ id: "m3", role: "assistant", content: "answer" }} onAction={() => {}} onRegenerate={onRegenerate} />,
    );
    fireEvent.click(screen.getByLabelText("Regenerate response"));
    expect(onRegenerate).toHaveBeenCalled();

    rerender(<MessageView message={{ id: "m3", role: "assistant", content: "answer" }} onAction={() => {}} />);
    expect(screen.queryByLabelText("Regenerate response")).toBeNull();
  });
});
