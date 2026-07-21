import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Theme } from "@carbon/react";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { SignInGate } from "./components/SignIn";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ChatPage } from "./pages/ChatPage";
import { AboutPage, ArtifactsPage, ContextsPage, DeploymentsPage } from "./pages/SimplePages";
import { SettingsPage } from "./pages/SettingsPage";
import { HowToPage } from "./pages/HowToPage";
import { HowItWorksPage } from "./pages/HowItWorksPage";
import { SkillsPage } from "./pages/SkillsPage";
import { ExplorerPage } from "./pages/ExplorerPage";
import { DataPage } from "./pages/DataPage";
import { Toaster } from "./components/Toaster";
import { CommandPalette } from "./components/CommandPalette";
import { FirstRunTour } from "./components/FirstRunTour";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import { useConversations, useCreateConversation, useProjects } from "./api/hooks";
import { useUi } from "./store/ui";

function ChatRedirect() {
  const projectId = useUi((s) => s.currentProjectId);
  const { data: conversations = [], isLoading } = useConversations(projectId ?? undefined);
  const create = useCreateConversation(projectId ?? undefined);
  const nav = useNavigate();

  useEffect(() => {
    if (!projectId || isLoading) return;
    if (conversations.length > 0) {
      nav(`/c/${conversations[0].id}`, { replace: true });
    } else {
      create.mutateAsync().then((c) => nav(`/c/${c.id}`, { replace: true }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, isLoading, conversations.length]);

  return <div className="main-col" />;
}

export function App() {
  const theme = useUi((s) => s.theme);
  const projectId = useUi((s) => s.currentProjectId);
  const setProject = useUi((s) => s.setProject);
  const { data: projects } = useProjects();
  const nav = useNavigate();
  const loc = useLocation();
  const createConv = useCreateConversation(projectId ?? undefined);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const newChat = () => {
    if (!projectId) return;
    createConv.mutateAsync().then((c) => nav(`/c/${c.id}`));
  };

  useGlobalShortcuts({
    togglePalette: () => setPaletteOpen((o) => !o),
    newChat,
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-carbon-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (projects && projects.length > 0 && (!projectId || !projects.find((p) => p.id === projectId))) {
      const def = projects.find((p) => p.isDefault) || projects[0];
      setProject(def.id);
    }
  }, [projects, projectId, setProject]);

  return (
    <Theme theme={theme}>
      <div className="app-shell">
        <Header />
        <div className="app-body">
          <Sidebar />
          <SignInGate>
            <ErrorBoundary resetKey={loc.pathname} label="this view">
              <Routes>
                <Route path="/" element={<ChatRedirect />} />
                <Route path="/c/:id" element={<ChatPage />} />
                <Route path="/contexts" element={<ContextsPage />} />
                <Route path="/artifacts" element={<ArtifactsPage />} />
                <Route path="/deployments" element={<DeploymentsPage />} />
                <Route path="/skills" element={<SkillsPage />} />
                <Route path="/explorer" element={<ExplorerPage />} />
                <Route path="/data" element={<DataPage />} />
                <Route path="/how-to" element={<HowToPage />} />
                <Route path="/how-it-works" element={<HowItWorksPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/about" element={<AboutPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </ErrorBoundary>
          </SignInGate>
        </div>
        <Toaster />
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onNewChat={() => {
            setPaletteOpen(false);
            newChat();
          }}
        />
        <FirstRunTour />
      </div>
    </Theme>
  );
}
