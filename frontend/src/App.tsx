import { useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Theme } from "@carbon/react";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { ChatPage } from "./pages/ChatPage";
import { AboutPage, ArtifactsPage, ContextsPage, DeploymentsPage, DiagnosticsPage } from "./pages/SimplePages";
import { SettingsPage } from "./pages/SettingsPage";
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
          <Routes>
            <Route path="/" element={<ChatRedirect />} />
            <Route path="/c/:id" element={<ChatPage />} />
            <Route path="/contexts" element={<ContextsPage />} />
            <Route path="/artifacts" element={<ArtifactsPage />} />
            <Route path="/deployments" element={<DeploymentsPage />} />
            <Route path="/diagnostics" element={<DiagnosticsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </Theme>
  );
}
