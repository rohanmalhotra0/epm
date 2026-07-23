import "@carbon/styles/css/styles.css";
import "./artifacts/artifacts.css";

import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SkeletonText, Theme } from "@carbon/react";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { SignInGate } from "./components/SignIn";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Toaster } from "./components/Toaster";
import { CommandPalette } from "./components/CommandPalette";
import { FirstRunTour } from "./components/FirstRunTour";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import { useConversations, useCreateConversation, useProjects } from "./api/hooks";
import { useUi } from "./store/ui";

const ChatPage = lazy(() => import("./pages/ChatPage").then(({ ChatPage }) => ({ default: ChatPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then(({ SettingsPage }) => ({ default: SettingsPage })));
const GuidePage = lazy(() => import("./pages/GuidePage").then(({ GuidePage }) => ({ default: GuidePage })));
const SkillsPage = lazy(() => import("./pages/SkillsPage").then(({ SkillsPage }) => ({ default: SkillsPage })));
const ExplorerPage = lazy(() => import("./pages/ExplorerPage").then(({ ExplorerPage }) => ({ default: ExplorerPage })));
const DataPage = lazy(() => import("./pages/DataPage").then(({ DataPage }) => ({ default: DataPage })));
const AgentPage = lazy(() => import("./pages/AgentPage").then(({ AgentPage }) => ({ default: AgentPage })));

// These four views live in one source module, so they intentionally share one
// on-demand chunk while remaining out of the initial app-shell download.
const loadSimplePages = () => import("./pages/SimplePages");
const ContextsPage = lazy(() => loadSimplePages().then(({ ContextsPage }) => ({ default: ContextsPage })));
const ArtifactsPage = lazy(() => loadSimplePages().then(({ ArtifactsPage }) => ({ default: ArtifactsPage })));
const DeploymentsPage = lazy(() => loadSimplePages().then(({ DeploymentsPage }) => ({ default: DeploymentsPage })));
const AboutPage = lazy(() => loadSimplePages().then(({ AboutPage }) => ({ default: AboutPage })));

const appQueryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: 1 } },
});

function RouteLoading() {
  return (
    <div className="page" role="status" aria-live="polite" aria-busy="true">
      <SkeletonText heading />
      <SkeletonText paragraph lineCount={3} />
      <span className="cds--visually-hidden">Loading view…</span>
    </div>
  );
}

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

/** The real route table, exported so tests exercise actual wiring (including redirects). */
export function AppRoutes() {
  return (
    <Suspense fallback={<RouteLoading />}>
      <Routes>
        <Route path="/" element={<ChatRedirect />} />
        <Route path="/c/:id" element={<ChatPage />} />
        <Route path="/contexts" element={<ContextsPage />} />
        <Route path="/artifacts" element={<ArtifactsPage />} />
        <Route path="/deployments" element={<DeploymentsPage />} />
        <Route path="/skills" element={<SkillsPage />} />
        <Route path="/explorer" element={<ExplorerPage />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="/agent" element={<AgentPage />} />
        <Route path="/guide" element={<GuidePage />} />
        {/* Old documentation URLs redirect to the merged guide. */}
        <Route path="/how-to" element={<Navigate to="/guide" replace />} />
        <Route path="/how-it-works" element={<Navigate to="/guide" replace />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

function AppShell() {
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
              <AppRoutes />
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

export function App() {
  return (
    <QueryClientProvider client={appQueryClient}>
      <AppShell />
    </QueryClientProvider>
  );
}
