import { Button, FileUploaderButton } from "@carbon/react";
import {
  useBackups,
  useCreateBackup,
  useDiskUsage,
  useImportProject,
  useProjects,
} from "../api/hooks";
import { downloadProjectExport } from "../api/data";
import { formatBytes } from "../utils/format";
import { useUi } from "../store/ui";

/** Local data management: export/import, backups, and disk usage. */
export function DataPage() {
  const pid = useUi((s) => s.currentProjectId) ?? undefined;
  const { data: projects = [] } = useProjects();
  const project = projects.find((p) => p.id === pid);
  const { data: backups = [] } = useBackups();
  const createBackup = useCreateBackup();
  const { data: disk } = useDiskUsage();
  const importProject = useImportProject();

  return (
    <div className="page">
      <h2>Data</h2>
      <div className="page-sub">Everything is stored locally on this computer. Export, import, and back up your data here.</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 760 }}>
        <div className="stat-tile">
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Export &amp; import</div>
          <div style={{ fontSize: 12, color: "var(--cds-text-secondary,#8d8d8d)", marginBottom: 10 }}>
            Export the current project{project ? ` (${project.name})` : ""} as a zip archive, or import a previously
            exported project.
          </div>
          <div className="action-row">
            <Button size="sm" kind="primary" disabled={!pid} onClick={() => pid && downloadProjectExport(pid)}>
              Export project
            </Button>
            <FileUploaderButton
              size="sm"
              buttonKind="tertiary"
              labelText={importProject.isPending ? "Importing…" : "Import project"}
              accept={[".zip"]}
              disableLabelChanges
              disabled={importProject.isPending}
              onChange={(e) => {
                const input = e.target as HTMLInputElement;
                const file = input.files?.[0];
                if (file) importProject.mutate(file);
                input.value = "";
              }}
            />
          </div>
        </div>
        <div className="stat-tile">
          <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
            <span style={{ fontWeight: 600 }}>Backups</span>
            <span style={{ flex: 1 }} />
            <Button size="sm" kind="tertiary" disabled={createBackup.isPending} onClick={() => createBackup.mutate()}>
              {createBackup.isPending ? "Backing up…" : "Back up now"}
            </Button>
          </div>
          <table className="data-table">
            <thead>
              <tr><th>Filename</th><th>Size</th><th>Created</th></tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <tr key={b.filename}>
                  <td className="mono" style={{ fontSize: 12 }}>{b.filename}</td>
                  <td>{formatBytes(b.sizeBytes)}</td>
                  <td style={{ fontSize: 12, color: "#8d8d8d" }}>{new Date(b.createdAt).toLocaleString()}</td>
                </tr>
              ))}
              {backups.length === 0 && <tr><td colSpan={3} style={{ color: "#8d8d8d" }}>No backups yet.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="stat-tile">
          <div style={{ fontWeight: 600, marginBottom: 10 }}>Disk usage</div>
          <div style={{ display: "flex", gap: 32, marginBottom: 14 }}>
            <div>
              <div className="n">{disk ? formatBytes(disk.dbBytes) : "—"}</div>
              <div className="l">Database</div>
            </div>
            <div>
              <div className="n">{disk ? formatBytes(disk.backupsBytes) : "—"}</div>
              <div className="l">Backups</div>
            </div>
          </div>
          <table className="data-table">
            <thead>
              <tr><th>Project</th><th>Artifacts</th><th>Artifact size</th></tr>
            </thead>
            <tbody>
              {(disk?.projects ?? []).map((p) => (
                <tr key={p.projectId}>
                  <td>{p.name}</td>
                  <td>{p.artifactCount}</td>
                  <td>{formatBytes(p.artifactBytes)}</td>
                </tr>
              ))}
              {(disk?.projects ?? []).length === 0 && (
                <tr><td colSpan={3} style={{ color: "#8d8d8d" }}>No projects.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
