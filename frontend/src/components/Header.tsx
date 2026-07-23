import { useEffect, useState } from "react";
import { Modal, TextInput } from "@carbon/react";
import { Add, Asleep, Edit, Light, SidePanelClose, SidePanelOpen, Application, WatsonHealthAiResults } from "@carbon/icons-react";
import { useCreateProject, useEnvironments, useProjects, useProviders, useRenameProject } from "../api/hooks";
import { useUi } from "../store/ui";
import { ArtifactToggle } from "../artifacts/blocks";
import { TtsToggle } from "../tts/components";

export function Header() {
  const projectId = useUi((s) => s.currentProjectId);
  const setProject = useUi((s) => s.setProject);
  const toggle = useUi((s) => s.toggleSidebar);
  const setSidebarCollapsed = useUi((s) => s.setSidebarCollapsed);
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const theme = useUi((s) => s.theme);
  const toggleTheme = useUi((s) => s.toggleTheme);
  const { data: projects = [] } = useProjects();
  const { data: environments = [] } = useEnvironments(projectId ?? undefined);
  const { data: providers = [] } = useProviders();
  const createProject = useCreateProject();
  const renameProject = useRenameProject();
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  const project = projects.find((p) => p.id === projectId);
  const activeEnv = environments.find((e) => e.id === project?.activeEnvironmentId) || environments[0];
  const activeProvider = providers.find((p) => p.hasKey && p.providerType !== "mock") || providers[0];

  const onNewProject = () => {
    // Create a blank project immediately and switch to it; the user renames via
    // the pencil (matches the create-then-name pattern). Fixes the audit gap
    // where useCreateProject existed but was wired to nothing.
    createProject.mutate({ name: "New project" }, { onSuccess: (p) => setProject(p.id) });
  };

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 767px)");
    const closeForMobile = (matches: boolean) => {
      if (matches) setSidebarCollapsed(true);
    };
    closeForMobile(media.matches);
    const onChange = (event: MediaQueryListEvent) => closeForMobile(event.matches);
    media.addEventListener?.("change", onChange);
    return () => media.removeEventListener?.("change", onChange);
  }, [setSidebarCollapsed]);

  const openRenameProject = () => {
    if (!project) return;
    setRenameValue(project.name);
    setRenameOpen(true);
  };

  const submitRenameProject = () => {
    if (!project) return;
    const next = renameValue.trim();
    if (next && next !== project.name) {
      renameProject.mutate(
        { id: project.id, name: next },
        { onSuccess: () => setRenameOpen(false) },
      );
      return;
    }
    setRenameOpen(false);
  };

  return (
    <>
      <header className="epmw-header">
        <button className="conv-item" style={{ width: "auto", padding: 6 }} onClick={toggle} aria-label="Toggle sidebar">
          {collapsed ? <SidePanelOpen size={18} /> : <SidePanelClose size={18} />}
        </button>
        <div className="epmw-wordmark">
          <WatsonHealthAiResults size={20} className="spark" />
          <span className="epmw-wordmark-text">EPM&nbsp;Wizard</span>
        </div>
        <div className="meta project-meta">
          <Application size={14} />
          <select
            aria-label="Current project"
            value={projectId ?? ""}
            onChange={(e) => setProject(e.target.value)}
            style={{ background: "transparent", color: "inherit", border: "none", fontSize: 12, cursor: "pointer" }}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id} style={{ color: "#000" }}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            className="conv-item"
            style={{ width: "auto", padding: 4 }}
            onClick={openRenameProject}
            disabled={!project || renameProject.isPending}
            title="Rename project"
            aria-label="Rename project"
          >
            <Edit size={14} />
          </button>
          <button
            className="conv-item"
            style={{ width: "auto", padding: 4 }}
            onClick={onNewProject}
            disabled={createProject.isPending}
            title="New project"
            aria-label="New project"
          >
            <Add size={16} />
          </button>
        </div>
        <span className="spacer" />
        <div className="meta runtime-meta">
          {activeEnv && (
            <>
              <span className={`conn-dot ${activeEnv.connected ? "on" : "off"}`} />
              <span>{activeEnv.name}</span>
              <span className={`env-badge ${activeEnv.classification}`}>{activeEnv.classification}</span>
            </>
          )}
          <span style={{ opacity: 0.4 }}>|</span>
          <span title="Active model">
            {activeProvider ? `${activeProvider.name.split(" ")[0]} · ${activeProvider.defaultModel ?? "model"}` : "no provider"}
          </span>
        </div>
        <button
          className="epmw-tts-toggle"
          title={theme === "g100" ? "Switch to light theme" : "Switch to dark theme"}
          aria-label={theme === "g100" ? "Switch to light theme" : "Switch to dark theme"}
          onClick={toggleTheme}
        >
          {theme === "g100" ? <Light size={16} /> : <Asleep size={16} />}
        </button>
        <TtsToggle />
        <ArtifactToggle />
      </header>
      <Modal
        open={renameOpen}
        modalHeading="Rename project"
        primaryButtonText="Save"
        secondaryButtonText="Cancel"
        primaryButtonDisabled={!renameValue.trim() || renameProject.isPending}
        onRequestSubmit={submitRenameProject}
        onRequestClose={() => setRenameOpen(false)}
      >
        <TextInput
          id="rename-project"
          labelText="Project name"
          value={renameValue}
          onChange={(event) => setRenameValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && renameValue.trim() && !renameProject.isPending) {
              submitRenameProject();
            }
          }}
        />
      </Modal>
    </>
  );
}
