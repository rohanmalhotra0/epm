import { useState } from "react";
import { Button, ContentSwitcher, Switch } from "@carbon/react";
import { useDiagnostics, useDiagnosticsLogs, type LogEntryOut } from "../api/hooks";

const DOT: Record<string, string> = { ok: "#42be65", warn: "#f1c21b", unavailable: "#6f6f6f", error: "#fa4d56" };

const LEVEL_COLOR: Record<string, string> = {
  error: "#fa4d56",
  critical: "#fa4d56",
  warn: "#f1c21b",
  warning: "#f1c21b",
  info: "#4589ff",
  debug: "#6f6f6f",
};

type LevelFilter = "all" | "warn" | "error";
const FILTERS: LevelFilter[] = ["all", "warn", "error"];

function matchesFilter(entry: LogEntryOut, filter: LevelFilter): boolean {
  const level = (entry.level || "").toLowerCase();
  if (filter === "error") return level === "error" || level === "critical";
  if (filter === "warn") return ["warn", "warning", "error", "critical"].includes(level);
  return true;
}

function LogRow({ entry }: { entry: LogEntryOut }) {
  const level = (entry.level || "info").toLowerCase();
  const color = LEVEL_COLOR[level] || "#8d8d8d";
  const highlighted = ["warn", "warning", "error", "critical"].includes(level);
  const extra = entry.data && Object.keys(entry.data).length > 0 ? JSON.stringify(entry.data) : "";
  return (
    <div style={{ display: "flex", gap: 8, padding: "2px 0", alignItems: "baseline" }}>
      <span
        style={{
          color: highlighted ? "#161616" : color,
          background: highlighted ? color : "transparent",
          border: `1px solid ${color}`,
          borderRadius: 2,
          padding: "0 4px",
          fontSize: 9,
          fontWeight: 600,
          textTransform: "uppercase",
          flexShrink: 0,
          minWidth: 38,
          textAlign: "center",
        }}
      >
        {level}
      </span>
      <span style={{ color: "#8d8d8d", flexShrink: 0 }}>{entry.ts}</span>
      <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {entry.event}
        {entry.logger ? <span style={{ color: "#8d8d8d" }}> · {entry.logger}</span> : null}
        {extra ? <span style={{ color: "#8d8d8d" }}> {extra}</span> : null}
      </span>
    </div>
  );
}

/** Compact system-health strip. Small enough to live inside Settings. */
export function DiagnosticsPanel() {
  const { data, isError } = useDiagnostics();
  const [levelFilter, setLevelFilter] = useState<LevelFilter>("all");
  const logsQuery = useDiagnosticsLogs(200);
  const logs = (logsQuery.data?.logs ?? []).filter((l) => matchesFilter(l, levelFilter));

  return (
    <div className="stat-tile" style={{ maxWidth: 640 }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontWeight: 600 }}>System health</span>
        <span style={{ flex: 1 }} />
        <Button size="sm" kind="ghost" onClick={() => window.open("/api/diagnostics/bundle", "_blank")}>
          Download bundle
        </Button>
      </div>
      {isError && <div style={{ color: "#fa4d56", fontSize: 12 }}>Backend unreachable.</div>}
      {data && (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px" }}>
            {data.subsystems.map((s) => (
              <span key={s.name} title={s.detail ?? ""} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: DOT[s.status] || "#6f6f6f" }} />
                {s.name}
              </span>
            ))}
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: "var(--cds-text-secondary,#8d8d8d)" }}>
            v{data.appVersion} · {data.activeProvider} / {data.activeModel} · redaction{" "}
            {data.redactionHealthy ? "healthy" : "FAILED"}
          </div>
        </>
      )}
      <div style={{ marginTop: 16, borderTop: "1px solid var(--cds-border-subtle,#393939)", paddingTop: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>Logs</span>
          <span style={{ flex: 1 }} />
          <ContentSwitcher
            size="sm"
            selectedIndex={FILTERS.indexOf(levelFilter)}
            onChange={({ index }) => setLevelFilter(FILTERS[index ?? 0])}
          >
            <Switch name="all" text="All" />
            <Switch name="warn" text="Warn+" />
            <Switch name="error" text="Error" />
          </ContentSwitcher>
          <Button size="sm" kind="ghost" disabled={logsQuery.isFetching} onClick={() => logsQuery.refetch()}>
            Refresh
          </Button>
        </div>
        <div
          style={{
            maxHeight: 240,
            overflowY: "auto",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: 11,
            background: "var(--cds-field,#161616)",
            border: "1px solid var(--cds-border-subtle,#393939)",
            padding: 8,
          }}
        >
          {logs.map((l, i) => (
            <LogRow key={`${l.ts}-${i}`} entry={l} />
          ))}
          {logs.length === 0 && <div style={{ color: "#8d8d8d" }}>No log entries.</div>}
        </div>
      </div>
    </div>
  );
}
