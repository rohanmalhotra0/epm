import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { WatsonHealthAiResults } from "@carbon/icons-react";
import { Button } from "@carbon/react";
import {
  useConnectEnvironment,
  useCreateEnvironment,
  useEnvironments,
} from "../api/hooks";
import { useUi } from "../store/ui";
import type { EnvironmentOut } from "../schemas/types";

const CLASSIFICATIONS = ["development", "test", "production"];

/**
 * Blocks the app behind an Oracle EPM sign-in until a live environment is
 * connected. Demo mode is only offered when enabled in Settings. Settings stays
 * reachable while gated so the user can turn demo on.
 */
export function SignInGate({ children }: { children: React.ReactNode }) {
  const projectId = useUi((s) => s.currentProjectId) ?? undefined;
  const { pathname } = useLocation();
  const { data: environments = [], isLoading } = useEnvironments(projectId);

  const connected = environments.some((e) => e.connected);
  // Let the user reach Settings even when not signed in (to enable demo mode).
  const allowThrough = connected || pathname === "/settings";

  if (!projectId || isLoading) {
    return <>{children}</>;
  }

  return (
    <>
      {children}
      {!allowThrough && <SignInScreen projectId={projectId} environments={environments} />}
    </>
  );
}

function SignInScreen({
  projectId,
  environments,
}: {
  projectId: string;
  environments: EnvironmentOut[];
}) {
  const nav = useNavigate();
  const createEnv = useCreateEnvironment(projectId);
  const connect = useConnectEnvironment(projectId);

  const [form, setForm] = useState({
    baseUrl: "",
    username: "",
    password: "",
    application: "",
    classification: "development",
    remember: false,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k: keyof typeof form, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  const signIn = async () => {
    setError("");
    if (!form.baseUrl || !form.username || !form.password) {
      setError("Instance URL, username and password are required.");
      return;
    }
    setBusy(true);
    try {
      const base = form.baseUrl.trim().replace(/\/+$/, "");
      let env = environments.find((e) => !e.demo && (e.baseUrl || "") === base);
      if (!env) {
        env = await createEnv.mutateAsync({
          name: `Oracle EPM (${form.username})`,
          baseUrl: base,
          username: form.username.trim(),
          authMethod: form.remember ? "passwordStored" : "passwordInMemory",
          classification: form.classification,
          preferredApplication: form.application.trim() || undefined,
          demo: false,
        });
      }
      const result: any = await connect.mutateAsync({
        id: env.id,
        password: form.password,
        remember: form.remember,
      });
      if (result && result.connected === false) {
        setError(result.detail || result.message || "Could not connect. Check your credentials.");
      }
    } catch (e: any) {
      setError(e?.message || "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="signin-overlay">
      <div className="signin-card">
        <div className="signin-brand">
          <WatsonHealthAiResults size={26} className="spark" />
          <span>EPM&nbsp;Wizard</span>
        </div>
        <h1 className="signin-title">Sign in to Oracle EPM</h1>
        <p className="signin-sub">
          Connect to your Planning tenant to begin. Your password is held in process memory only
          and never written to chat or logs.
        </p>

        <label className="signin-label">Instance URL</label>
        <input
          className="signin-input"
          placeholder="https://planning-test-yourpod.epm.us.oraclecloud.com"
          value={form.baseUrl}
          onChange={(e) => set("baseUrl", e.target.value)}
          autoFocus
        />

        <div className="signin-row">
          <div style={{ flex: 1 }}>
            <label className="signin-label">Username</label>
            <input
              className="signin-input"
              placeholder="you@example.com"
              value={form.username}
              onChange={(e) => set("username", e.target.value)}
            />
          </div>
          <div style={{ width: 150 }}>
            <label className="signin-label">Application</label>
            <input
              className="signin-input"
              placeholder="auto-detect"
              value={form.application}
              onChange={(e) => set("application", e.target.value)}
            />
          </div>
        </div>

        <div className="signin-row">
          <div style={{ flex: 1 }}>
            <label className="signin-label">Password</label>
            <input
              className="signin-input"
              type="password"
              value={form.password}
              onChange={(e) => set("password", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !busy && signIn()}
            />
          </div>
          <div style={{ width: 150 }}>
            <label className="signin-label">Classification</label>
            <select
              className="signin-input"
              value={form.classification}
              onChange={(e) => set("classification", e.target.value)}
            >
              {CLASSIFICATIONS.map((c) => (
                <option key={c} value={c} style={{ color: "#000" }}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </div>

        <label className="signin-check">
          <input
            type="checkbox"
            checked={form.remember}
            onChange={(e) => set("remember", e.target.checked)}
          />
          Remember password on this machine (encrypted local store)
        </label>

        {error && <div className="signin-error">{error}</div>}

        <Button kind="primary" disabled={busy} onClick={signIn} style={{ width: "100%", maxWidth: "none", marginTop: 8 }}>
          {busy ? "Connecting…" : "Connect"}
        </Button>

        <div className="signin-footer">
          <span className="signin-muted">
            Need to configure an AI model first?{" "}
            <button className="signin-link" onClick={() => nav("/settings")}>
              Open Settings
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}
