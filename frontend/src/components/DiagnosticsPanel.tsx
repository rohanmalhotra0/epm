import { Button } from "@carbon/react";
import { useDiagnostics } from "../api/hooks";

const DOT: Record<string, string> = { ok: "#42be65", warn: "#f1c21b", unavailable: "#6f6f6f", error: "#fa4d56" };

/** Compact system-health strip. Small enough to live inside Settings. */
export function DiagnosticsPanel() {
  const { data, isError } = useDiagnostics();

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
    </div>
  );
}
