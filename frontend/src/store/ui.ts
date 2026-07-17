import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  currentProjectId: string | null;
  sidebarCollapsed: boolean;
  theme: "g100" | "white";
  setProject: (id: string) => void;
  toggleSidebar: () => void;
  setTheme: (t: "g100" | "white") => void;
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      currentProjectId: null,
      sidebarCollapsed: false,
      theme: "g100",
      setProject: (id) => set({ currentProjectId: id }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setTheme: (theme) => set({ theme }),
    }),
    { name: "epmw-ui" },
  ),
);
