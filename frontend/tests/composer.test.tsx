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

  it("uses clear actions without a shortcut legend", () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} conversationId="c1" />);
    expect(screen.getByRole("button", { name: "Attach files" })).toHaveTextContent("Attach");
    expect(screen.getByRole("button", { name: "Send" })).toHaveTextContent("Send");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.queryByText(/Enter to send/)).not.toBeInTheDocument();
  });

  it("enables send when a message is entered", () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} />);
    fireEvent.change(screen.getByLabelText("Message EPM Wizard"), { target: { value: "Inspect this form" } });
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("shows the slash-command menu", () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} />);
    const ta = screen.getByLabelText("Message EPM Wizard");
    fireEvent.change(ta, { target: { value: "/for" } });
    expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /\/forms/ })).toHaveAttribute("aria-selected", "true");
    expect(ta).toHaveAttribute("aria-activedescendant", "slash-command-0");
    expect(screen.queryByText(/Build, preview, edit and deploy/)).not.toBeInTheDocument();
  });

  it("shows a stop button while streaming", () => {
    const onStop = vi.fn();
    render(<Composer onSend={vi.fn()} streaming={true} onStop={onStop} />);
    expect(screen.getByRole("status")).toHaveTextContent("Working…");
    fireEvent.click(screen.getByLabelText("Stop"));
    expect(onStop).toHaveBeenCalled();
  });
});
