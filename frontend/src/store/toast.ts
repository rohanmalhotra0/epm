// Lightweight toast notifications. A zustand store plus a module-level `toast`
// helper so any layer (hooks, call sites) can raise a notification without React.

import { create } from "zustand";

export type ToastKind = "success" | "error" | "info" | "warning";

export interface Toast {
  id: string;
  kind: ToastKind;
  title: string;
  subtitle?: string;
}

interface ToastState {
  toasts: Toast[];
  push: (t: Omit<Toast, "id">) => string;
  dismiss: (id: string) => void;
}

const TTL: Record<ToastKind, number> = { success: 4500, info: 5000, warning: 7000, error: 9000 };

export const useToasts = create<ToastState>((set, get) => ({
  toasts: [],
  push: (t) => {
    const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }));
    setTimeout(() => get().dismiss(id), TTL[t.kind]);
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));

/** Raise a toast from anywhere (including outside React). */
export const toast = {
  success: (title: string, subtitle?: string) => useToasts.getState().push({ kind: "success", title, subtitle }),
  error: (title: string, subtitle?: string) => useToasts.getState().push({ kind: "error", title, subtitle }),
  info: (title: string, subtitle?: string) => useToasts.getState().push({ kind: "info", title, subtitle }),
  warning: (title: string, subtitle?: string) => useToasts.getState().push({ kind: "warning", title, subtitle }),
};
