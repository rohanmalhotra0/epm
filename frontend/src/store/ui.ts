import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  currentProjectId: string | null;
  sidebarCollapsed: boolean;
  theme: "g100" | "white";
  // Oracle sign-in is optional: chat/AI works without a tenant. When the user
  // chooses "Continue without Oracle" the gate stays dismissed (persisted).
  oracleGateSkipped: boolean;
  setProject: (id: string) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setTheme: (t: "g100" | "white") => void;
  toggleTheme: () => void;
  skipOracleGate: () => void;
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      currentProjectId: null,
      sidebarCollapsed: false,
      theme: "g100",
      oracleGateSkipped: false,
      setProject: (id) => set({ currentProjectId: id }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((s) => ({ theme: s.theme === "g100" ? "white" : "g100" })),
      skipOracleGate: () => set({ oracleGateSkipped: true }),
    }),
    { name: "epmw-ui" },
  ),
);
