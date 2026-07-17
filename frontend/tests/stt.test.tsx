import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen, fireEvent } from "@testing-library/react";
import { Composer } from "../src/components/Composer";

// Minimal fake of the browser SpeechRecognition API.
let lastRec: any;
class FakeRecognition {
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  onstart: any = null;
  onend: any = null;
  onerror: any = null;
  onresult: any = null;
  constructor() {
    lastRec = this;
  }
  start() {
    this.onstart?.();
  }
  stop() {
    this.onend?.();
  }
  abort() {}
}

describe("speech-to-text dictation", () => {
  beforeEach(() => {
    (window as any).SpeechRecognition = FakeRecognition as any;
  });
  afterEach(() => {
    delete (window as any).SpeechRecognition;
    delete (window as any).webkitSpeechRecognition;
    lastRec = undefined;
  });

  it("shows a mic, starts listening, and dictates into the composer", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} streaming={false} onStop={() => {}} />);

    fireEvent.click(screen.getByLabelText("Dictate (voice input)"));
    expect(screen.getByLabelText("Stop dictation")).toBeInTheDocument();
    expect(screen.getByText(/Listening/)).toBeInTheDocument();

    // simulate a final transcript coming back from the recognizer
    act(() => {
      lastRec.onresult({
        resultIndex: 0,
        results: [{ isFinal: true, length: 1, 0: { transcript: "create an actuals form" } }],
      });
    });

    const ta = screen.getByLabelText("Message EPM Wizard") as HTMLTextAreaElement;
    expect(ta.value).toContain("create an actuals form");

    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("create an actuals form");
  });

  it("hides the mic when the browser has no speech recognition", () => {
    delete (window as any).SpeechRecognition;
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} />);
    expect(screen.queryByLabelText("Dictate (voice input)")).toBeNull();
  });
});
