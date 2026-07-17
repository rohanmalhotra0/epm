import { SidePanelClose, SidePanelOpen, Application, WatsonHealthAiResults } from "@carbon/icons-react";
import { useEnvironments, useProjects, useProviders } from "../api/hooks";
import { useUi } from "../store/ui";
import { ArtifactToggle } from "../artifacts/blocks";
import { TtsToggle } from "../tts/components";

export function Header() {
  const projectId = useUi((s) => s.currentProjectId);
  const setProject = useUi((s) => s.setProject);
  const toggle = useUi((s) => s.toggleSidebar);
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const { data: projects = [] } = useProjects();
  const { data: environments = [] } = useEnvironments(projectId ?? undefined);
  const { data: providers = [] } = useProviders();

  const project = projects.find((p) => p.id === projectId);
  const activeEnv = environments.find((e) => e.id === project?.activeEnvironmentId) || environments[0];
  const activeProvider = providers.find((p) => p.hasKey && p.providerType !== "mock") || providers[0];

  return (
    <header className="epmw-header">
      <button className="conv-item" style={{ width: "auto", padding: 6 }} onClick={toggle} aria-label="Toggle sidebar">
        {collapsed ? <SidePanelOpen size={18} /> : <SidePanelClose size={18} />}
      </button>
      <div className="epmw-wordmark">
        <WatsonHealthAiResults size={20} className="spark" />
        EPM&nbsp;Wizard
      </div>
      <div className="meta">
        <Application size={14} />
        <select
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
      </div>
      <span className="spacer" />
      <div className="meta">
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
      <TtsToggle />
      <ArtifactToggle />
    </header>
  );
}
