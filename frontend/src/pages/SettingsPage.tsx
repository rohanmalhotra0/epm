import { useState } from "react";
import { Button } from "@carbon/react";
import { api } from "../api/client";
import {
  useConnectEnvironment,
  useCreateEnvironment,
  useCreateProvider,
  useEnvironments,
  useProviders,
} from "../api/hooks";
import { useUi } from "../store/ui";
import { DiagnosticsPanel } from "../components/DiagnosticsPanel";
import { toast } from "../store/toast";

const PROVIDER_TYPES = ["mock", "watsonx", "anthropic", "openai", "openrouter", "gemini", "ollama", "generic"];

export function SettingsPage() {
  const pid = useUi((s) => s.currentProjectId) ?? undefined;
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const { data: providers = [] } = useProviders();
  const { data: environments = [] } = useEnvironments(pid);
  const createProvider = useCreateProvider();
  const createEnv = useCreateEnvironment(pid);
  const connect = useConnectEnvironment(pid);

  const [np, setNp] = useState({ name: "", providerType: "anthropic", baseUrl: "", apiKey: "", defaultModel: "" });
  const [ne, setNe] = useState({ name: "", baseUrl: "", username: "", classification: "development", demo: false });
  const [pw, setPw] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string>("");

  const testProvider = async (id: string, name: string) => {
    try {
      const r = await api<any>(`/api/providers/${id}/test`, { method: "POST" });
      if (r.ok) {
        setMsg(`Provider OK — ${(r.models || []).length} models`);
        toast.success(`${name} is reachable`, `${(r.models || []).length} models available`);
      } else {
        setMsg(`Provider error: ${r.error}`);
        toast.error(`${name} failed`, r.error);
      }
    } catch (e: any) {
      toast.error(`${name} failed`, e?.message);
    }
  };

  return (
    <div className="page">
      <h2>Settings</h2>
      <div className="page-sub">Configure AI providers and Oracle environments. Secrets are stored in the local encrypted store, never in chat or logs.</div>

      <h3 style={{ margin: "16px 0 8px" }}>AI Providers</h3>
      <table className="data-table">
        <thead><tr><th>Name</th><th>Type</th><th>Model</th><th>Key</th><th></th></tr></thead>
        <tbody>
          {providers.map((p) => (
            <tr key={p.id}>
              <td>{p.name}</td>
              <td><span className="tag-inline">{p.providerType}</span></td>
              <td>{p.defaultModel ?? "—"}</td>
              <td>{p.hasKey ? "✓" : "—"}</td>
              <td><Button size="sm" kind="ghost" onClick={() => testProvider(p.id, p.name)}>Test</Button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="stat-tile" style={{ marginTop: 12, maxWidth: 640 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Add provider</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <input placeholder="Name" value={np.name} onChange={(e) => setNp({ ...np, name: e.target.value })} style={inp} />
          <select value={np.providerType} onChange={(e) => setNp({ ...np, providerType: e.target.value })} style={inp}>
            {PROVIDER_TYPES.map((t) => <option key={t} value={t} style={{ color: "#000" }}>{t}</option>)}
          </select>
          <input placeholder="Base URL (optional)" value={np.baseUrl} onChange={(e) => setNp({ ...np, baseUrl: e.target.value })} style={inp} />
          <input placeholder="Default model" value={np.defaultModel} onChange={(e) => setNp({ ...np, defaultModel: e.target.value })} style={inp} />
          <input placeholder="API key" type="password" value={np.apiKey} onChange={(e) => setNp({ ...np, apiKey: e.target.value })} style={{ ...inp, gridColumn: "1 / 3" }} />
        </div>
        <div className="action-row">
          <Button size="sm" kind="primary" disabled={!np.name} onClick={() => { createProvider.mutate(np as any); setNp({ name: "", providerType: "anthropic", baseUrl: "", apiKey: "", defaultModel: "" }); }}>Add provider</Button>
        </div>
      </div>

      <h3 style={{ margin: "24px 0 8px" }}>Oracle Environments</h3>
      <table className="data-table">
        <thead><tr><th>Name</th><th>Classification</th><th>URL</th><th>Connected</th><th></th></tr></thead>
        <tbody>
          {environments.map((e) => (
            <tr key={e.id}>
              <td>{e.name}</td>
              <td><span className={`env-badge ${e.classification}`}>{e.classification}</span></td>
              <td className="mono" style={{ fontSize: 11 }}>{e.baseUrl || "demo"}</td>
              <td>{e.connected ? "✓" : "—"}</td>
              <td style={{ display: "flex", gap: 6 }}>
                {!e.demo && (
                  <input placeholder="password" type="password" value={pw[e.id] || ""} onChange={(ev) => setPw({ ...pw, [e.id]: ev.target.value })} style={{ ...inp, width: 120 }} />
                )}
                <Button size="sm" kind="tertiary" onClick={() => connect.mutate({ id: e.id, password: pw[e.id] })}>Connect</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="stat-tile" style={{ marginTop: 12, maxWidth: 640 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Add environment</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <input placeholder="Name" value={ne.name} onChange={(e) => setNe({ ...ne, name: e.target.value })} style={inp} />
          <select value={ne.classification} onChange={(e) => setNe({ ...ne, classification: e.target.value })} style={inp}>
            {["development", "test", "production"].map((c) => <option key={c} value={c} style={{ color: "#000" }}>{c}</option>)}
          </select>
          <input placeholder="Base URL" value={ne.baseUrl} onChange={(e) => setNe({ ...ne, baseUrl: e.target.value })} style={inp} />
          <input placeholder="Username" value={ne.username} onChange={(e) => setNe({ ...ne, username: e.target.value })} style={inp} />
          <label style={{ fontSize: 12, gridColumn: "1/3", display: "flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={ne.demo} onChange={(e) => setNe({ ...ne, demo: e.target.checked })} /> Demo environment (no Oracle tenant)
          </label>
        </div>
        <div className="action-row">
          <Button size="sm" kind="primary" disabled={!ne.name} onClick={() => { createEnv.mutate(ne as any); setNe({ name: "", baseUrl: "", username: "", classification: "development", demo: false }); }}>Add environment</Button>
        </div>
      </div>

      <h3 style={{ margin: "24px 0 8px" }}>Diagnostics</h3>
      <DiagnosticsPanel />

      <h3 style={{ margin: "24px 0 8px" }}>Appearance</h3>
      <div className="action-row">
        <Button size="sm" kind={theme === "g100" ? "primary" : "tertiary"} onClick={() => setTheme("g100")}>Dark (Gray 100)</Button>
        <Button size="sm" kind={theme === "white" ? "primary" : "tertiary"} onClick={() => setTheme("white")}>Light</Button>
      </div>

      {msg && <div style={{ marginTop: 16, fontSize: 12, color: "#78a9ff" }}>{msg}</div>}
    </div>
  );
}

const inp: React.CSSProperties = {
  padding: "6px 10px",
  background: "var(--cds-field,#262626)",
  color: "inherit",
  border: "1px solid var(--cds-border-subtle,#393939)",
  fontFamily: "inherit",
  fontSize: 12.5,
};
