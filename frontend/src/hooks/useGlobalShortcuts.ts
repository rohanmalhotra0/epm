// Global keyboard shortcuts:
//   Ctrl/Cmd+K        → command palette (works anywhere, including inputs)
//   Ctrl/Cmd+/        → focus the chat composer (works anywhere)
//   Ctrl/Cmd+Shift+O  → new chat (suppressed while typing in an input)

import { useEffect, useRef } from "react";

export interface ShortcutActions {
  togglePalette: () => void;
  newChat: () => void;
}

export function focusComposer() {
  document.querySelector<HTMLTextAreaElement>(".composer textarea")?.focus();
}

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable;
}

export function useGlobalShortcuts(actions: ShortcutActions) {
  // Keep the latest callbacks without re-registering the listener.
  const ref = useRef(actions);
  ref.current = actions;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (key === "k" && !e.shiftKey && !e.altKey) {
        e.preventDefault();
        ref.current.togglePalette();
        return;
      }
      if (key === "/" && !e.shiftKey && !e.altKey) {
        e.preventDefault();
        focusComposer();
        return;
      }
      if (key === "o" && e.shiftKey && !e.altKey && !isTypingTarget(e.target)) {
        e.preventDefault();
        ref.current.newChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
