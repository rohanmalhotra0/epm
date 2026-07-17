import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Composer } from "../src/components/Composer";

describe("Composer", () => {
  it("sends on Enter and clears", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} streaming={false} onStop={() => {}} />);
    const ta = screen.getByLabelText("Message EPM Wizard") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "Create an Actuals form" } });
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("Create an Actuals form");
    expect(ta.value).toBe("");
  });

  it("does not send on Shift+Enter", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} streaming={false} onStop={() => {}} />);
    const ta = screen.getByLabelText("Message EPM Wizard");
    fireEvent.change(ta, { target: { value: "line" } });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("shows the slash-command menu", () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} />);
    const ta = screen.getByLabelText("Message EPM Wizard");
    fireEvent.change(ta, { target: { value: "/for" } });
    expect(screen.getByText("/forms")).toBeInTheDocument();
  });

  it("shows a stop button while streaming", () => {
    const onStop = vi.fn();
    render(<Composer onSend={vi.fn()} streaming={true} onStop={onStop} />);
    fireEvent.click(screen.getByLabelText("Stop"));
    expect(onStop).toHaveBeenCalled();
  });
});
