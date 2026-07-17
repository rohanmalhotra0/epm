import { Rocket, CheckmarkFilled, WarningFilled, ErrorFilled } from "@carbon/icons-react";
import type { DeploymentPlan, DeploymentReport } from "../schemas/types";

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div style={{ display: "flex", fontSize: 12.5, padding: "3px 0" }}>
      <span style={{ width: 150, color: "var(--cds-text-secondary)" }}>{k}</span>
      <span>{v}</span>
    </div>
  );
}

export function DeploymentPlanBlock({ data }: { data: DeploymentPlan }) {
  return (
    <div className="block-card">
      <div className="block-head">
        <Rocket size={16} />
        <span>Deployment plan — {data.artifactName}</span>
        <span className="grow" />
        <span className={`env-badge ${data.environmentClassification}`}>{data.environmentClassification}</span>
      </div>
      <div className="block-body">
        <Row k="Environment" v={data.environmentName} />
        <Row k="Application" v={`${data.application}${data.cube ? " · " + data.cube : ""}`} />
        <Row k="Folder" v={data.folder} />
        <Row k="Action" v={data.operation} />
        <Row k="Overwrites existing" v={data.overwritesExisting ? "Yes — backup will be captured" : "No"} />
        <Row k="Validation" v={data.validationPassed ? "Passed" : "Has errors"} />
        <Row k="Mode" v={data.demoMode ? "Demo (no Oracle tenant is changed)" : "Live"} />
        {data.warnings?.length > 0 && (
          <div style={{ marginTop: 6, fontSize: 12, color: "#f1c21b" }}>
            {data.warnings.map((w, i) => (
              <div key={i}>⚠ {w}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function DeploymentProgressBlock({ data }: { data: DeploymentPlan }) {
  return (
    <div className="block-card">
      <div className="block-head">
        <div className="spinner" />
        <span>Deploying — {data.artifactName}</span>
      </div>
      <div className="block-body">
        {data.steps.map((s) => (
          <div className="dep-step" key={s.key}>
            <span className={`st ${s.status}`}>{s.status}</span>
            <span>{s.label}</span>
            {s.detail && <span style={{ color: "var(--cds-text-secondary)", fontSize: 11 }}>· {s.detail}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function DeploymentResultBlock({ data }: { data: DeploymentReport }) {
  const ok = data.verified;
  const partial = data.success && !data.verified;
  const Icon = ok ? CheckmarkFilled : partial ? WarningFilled : ErrorFilled;
  const color = ok ? "#42be65" : partial ? "#f1c21b" : "#ff8389";
  return (
    <div className="block-card">
      <div className="block-head" style={{ color }}>
        <Icon size={16} />
        <span>{ok ? "Deployed & verified" : partial ? "Imported — verification incomplete" : "Deployment failed"}</span>
        <span className="grow" />
        {data.rollbackAvailable && <span className="tag-inline">rollback available</span>}
      </div>
      <div className="block-body">
        <Row k="Artifact" v={data.plan.artifactName} />
        <Row k="Environment" v={`${data.plan.environmentName} (${data.plan.environmentClassification})`} />
        {data.packageChecksum && <Row k="Package checksum" v={<span className="mono">{data.packageChecksum.slice(0, 20)}</span>} />}
        {data.jobId && <Row k="Oracle job" v={data.jobId} />}
        {data.durationMs != null && <Row k="Duration" v={`${data.durationMs} ms`} />}
        {data.verificationNotes?.length > 0 && (
          <div style={{ marginTop: 8 }}>
            {data.verificationNotes.map((n, i) => (
              <div key={i} style={{ fontSize: 12.5 }}>
                {n}
              </div>
            ))}
          </div>
        )}
        {data.errors?.length > 0 && (
          <div style={{ marginTop: 8, color: "#ff8389", fontSize: 12.5 }}>
            {data.errors.map((e, i) => (
              <div key={i}>{e}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
