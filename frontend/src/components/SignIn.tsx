import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { WatsonHealthAiResults, Upload } from "@carbon/icons-react";
import { Button, ComposedModal } from "@carbon/react";
import {
  useConnectEnvironment,
  useCreateEnvironment,
  useEnvironments,
} from "../api/hooks";
import { useUi } from "../store/ui";
import type { EnvironmentOut } from "../schemas/types";

const CLASSIFICATIONS = ["development", "test", "production"];
const OAUTH_METHOD = "oauthClientCredentials";

/**
 * Blocks the app behind an Oracle EPM sign-in until a live environment is
 * connected. Demo mode is only offered when enabled in Settings. Settings stays
 * reachable while gated so the user can turn demo on.
 */
export function SignInGate({ children }: { children: React.ReactNode }) {
  const projectId = useUi((s) => s.currentProjectId) ?? undefined;
  const gateSkipped = useUi((s) => s.oracleGateSkipped);
  const { pathname } = useLocation();
  const { data: environments = [], isLoading } = useEnvironments(projectId);

  const connected = environments.some((e) => e.connected);
  // Let the user reach Settings even when not signed in (to enable demo mode).
  // Oracle is optional — once skipped, go straight to the app (AI chat works
  // without a tenant; connect later from this screen via Settings → Sign in).
  const allowThrough = connected || gateSkipped || pathname === "/settings";

  if (!projectId || isLoading) {
    return <>{children}</>;
  }

  return allowThrough ? <>{children}</> : <SignInScreen projectId={projectId} environments={environments} />;
}

function useInertAppBackground(modalRef: React.RefObject<HTMLDivElement>) {
  useEffect(() => {
    const modal = modalRef.current;
    const appShell = modal?.closest<HTMLElement>(".app-shell");
    if (!modal || !appShell) return;

    const background: HTMLElement[] = [];
    let branch: HTMLElement = modal;

    while (branch !== appShell && branch.parentElement) {
      const parent = branch.parentElement;
      for (const sibling of Array.from(parent.children)) {
        if (sibling !== branch && sibling instanceof HTMLElement) {
          background.push(sibling);
        }
      }
      branch = parent;
    }

    const previous = background.map((element) => ({
      element,
      ariaHidden: element.getAttribute("aria-hidden"),
      inert: element.inert,
      hadInertAttribute: element.hasAttribute("inert"),
    }));

    for (const element of background) {
      element.inert = true;
      element.setAttribute("inert", "");
      element.setAttribute("aria-hidden", "true");
    }

    return () => {
      for (const state of previous) {
        state.element.inert = state.inert;
        if (!state.hadInertAttribute) {
          state.element.removeAttribute("inert");
        }
        if (state.ariaHidden === null) {
          state.element.removeAttribute("aria-hidden");
        } else {
          state.element.setAttribute("aria-hidden", state.ariaHidden);
        }
      }
    };
  }, [modalRef]);
}

function SignInScreen({
  projectId,
  environments,
}: {
  projectId: string;
  environments: EnvironmentOut[];
}) {
  const nav = useNavigate();
  const skipGate = useUi((s) => s.skipOracleGate);
  const createEnv = useCreateEnvironment(projectId);
  const connect = useConnectEnvironment(projectId);

  const [authMode, setAuthMode] = useState<"password" | "oauth">("password");
  const [form, setForm] = useState({
    baseUrl: "",
    username: "",
    password: "",
    tokenUrl: "",
    clientId: "",
    clientSecret: "",
    scope: "",
    application: "",
    classification: "development",
    remember: false,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  useInertAppBackground(modalRef);

  const set = (k: keyof typeof form, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  const parseCredentialsFile = (text: string) => {
    const lines = text.split("\n").map((l) => l.trim());
    const data: Record<string, string> = {};
    for (const line of lines) {
      const match = line.match(/^([A-Z_]+)=(.+)$/);
      if (match) {
        data[match[1]] = match[2];
      }
    }
    if (data.USERNAME) set("username", data.USERNAME);
    if (data.PASSWORD) set("password", data.PASSWORD);
    if (data.INSTANCE) set("baseUrl", data.INSTANCE);
    if (data.TOKEN_URL) set("tokenUrl", data.TOKEN_URL);
    if (data.CLIENT_ID) set("clientId", data.CLIENT_ID);
    if (data.CLIENT_SECRET) set("clientSecret", data.CLIENT_SECRET);
    if (data.SCOPE) set("scope", data.SCOPE);
    if (data.TOKEN_URL || data.CLIENT_ID) setAuthMode("oauth");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.name.endsWith(".txt")) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        const text = ev.target?.result as string;
        parseCredentialsFile(text);
      };
      reader.readAsText(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.name.endsWith(".txt")) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        const text = ev.target?.result as string;
        parseCredentialsFile(text);
      };
      reader.readAsText(file);
    }
    // Reset input so the same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const oauth = authMode === "oauth";
  const errorId = error ? "signin-error" : undefined;

  const signIn = async () => {
    setError("");
    if (oauth) {
      if (!form.baseUrl || !form.tokenUrl || !form.clientId || !form.clientSecret) {
        setError("Instance URL, token URL, client ID and client secret are required.");
        return;
      }
    } else if (!form.baseUrl || !form.username || !form.password) {
      setError("Instance URL, username and password are required.");
      return;
    }
    setBusy(true);
    try {
      const base = form.baseUrl.trim().replace(/\/+$/, "");
      let env = environments.find(
        (e) => !e.demo && (e.baseUrl || "") === base && (e.authMethod === OAUTH_METHOD) === oauth,
      );
      if (!env) {
        env = await createEnv.mutateAsync({
          name: `Oracle EPM (${oauth ? form.clientId.trim() : form.username})`,
          baseUrl: base,
          username: oauth ? undefined : form.username.trim(),
          authMethod: oauth ? OAUTH_METHOD : form.remember ? "passwordStored" : "passwordInMemory",
          oauthTokenUrl: oauth ? form.tokenUrl.trim() : undefined,
          oauthClientId: oauth ? form.clientId.trim() : undefined,
          oauthScope: oauth ? form.scope.trim() || undefined : undefined,
          classification: form.classification,
          preferredApplication: form.application.trim() || undefined,
          demo: false,
        });
      }
      const result: any = await connect.mutateAsync({
        id: env.id,
        password: oauth ? form.clientSecret : form.password,
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
    <ComposedModal
      ref={modalRef}
      open
      size="sm"
      className="signin-overlay"
      containerClassName={`signin-card ${dragActive ? "drag-active" : ""}`}
      aria-labelledby="signin-title"
      selectorPrimaryFocus="#signin-base-url"
      preventCloseOnClickOutside
      onClose={() => false}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
        <div className="signin-brand">
          <WatsonHealthAiResults size={26} className="spark" />
          <span>EPM&nbsp;Wizard</span>
        </div>
        <h1 id="signin-title" className="signin-title text-balance">Sign in to Oracle EPM</h1>
        <p className="signin-sub text-pretty">
          Connect to your Planning tenant to begin — with your Oracle password or an OAuth 2.0
          client credential. The secret is held in process memory only and never written to chat
          or logs.
        </p>

        <input
          ref={fileInputRef}
          type="file"
          accept=".txt"
          onChange={handleFileSelect}
          aria-label="Credentials file"
          style={{ display: "none" }}
        />

        <Button
          kind="tertiary"
          size="sm"
          renderIcon={Upload}
          onClick={() => fileInputRef.current?.click()}
          style={{ marginBottom: 16, alignSelf: "flex-start" }}
        >
          Load credentials from file
        </Button>

        {dragActive && (
          <div className="drop-overlay">
            <div className="drop-message">Drop credentials file to auto-fill</div>
          </div>
        )}

        <label className="signin-label" htmlFor="signin-base-url">Instance URL</label>
        <input
          id="signin-base-url"
          className="signin-input"
          placeholder="https://planning-test-yourpod.epm.us.oraclecloud.com"
          value={form.baseUrl}
          onChange={(e) => set("baseUrl", e.target.value)}
          aria-describedby={errorId}
          autoFocus
        />

        <label className="signin-label" htmlFor="signin-auth-mode">Authentication</label>
        <select
          id="signin-auth-mode"
          className="signin-input"
          value={authMode}
          onChange={(e) => {
            // Clear any stale field-validation error: switching modes changes
            // which fields are required, so a prior "…required" message no
            // longer applies until the next submit.
            setError("");
            setAuthMode(e.target.value as "password" | "oauth");
          }}
        >
          <option value="password" style={{ color: "#000" }}>
            Username &amp; password
          </option>
          <option value="oauth" style={{ color: "#000" }}>
            OAuth 2.0 client credentials (OCI IAM)
          </option>
        </select>

        {oauth && (
          <>
            <label className="signin-label" htmlFor="signin-token-url">Token URL (identity domain)</label>
            <input
              id="signin-token-url"
              className="signin-input"
              placeholder="https://idcs-….identity.oraclecloud.com/oauth2/v1/token"
              value={form.tokenUrl}
              onChange={(e) => set("tokenUrl", e.target.value)}
              aria-describedby={errorId}
            />
          </>
        )}

        <div className="signin-row">
          <div style={{ flex: 1 }}>
            <label className="signin-label" htmlFor="signin-user-id">{oauth ? "Client ID" : "Username"}</label>
            <input
              id="signin-user-id"
              className="signin-input"
              placeholder={oauth ? "confidential application client ID" : "you@example.com"}
              value={oauth ? form.clientId : form.username}
              onChange={(e) => set(oauth ? "clientId" : "username", e.target.value)}
              aria-describedby={errorId}
            />
          </div>
          <div style={{ width: 150 }}>
            <label className="signin-label" htmlFor="signin-application">Application</label>
            <input
              id="signin-application"
              className="signin-input"
              placeholder="auto-detect"
              value={form.application}
              onChange={(e) => set("application", e.target.value)}
            />
          </div>
        </div>

        <div className="signin-row">
          <div style={{ flex: 1 }}>
            <label className="signin-label" htmlFor="signin-secret">{oauth ? "Client secret" : "Password"}</label>
            <input
              id="signin-secret"
              className="signin-input"
              type="password"
              value={oauth ? form.clientSecret : form.password}
              onChange={(e) => set(oauth ? "clientSecret" : "password", e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !busy && signIn()}
              aria-describedby={errorId}
            />
          </div>
          <div style={{ width: 150 }}>
            <label className="signin-label" htmlFor="signin-classification">Classification</label>
            <select
              id="signin-classification"
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

        {oauth && (
          <>
            <label className="signin-label" htmlFor="signin-scope">Scope (optional)</label>
            <input
              id="signin-scope"
              className="signin-input"
              placeholder="urn:opc:serviceInstanceID=…urn:opc:resource:consumer::all"
              value={form.scope}
              onChange={(e) => set("scope", e.target.value)}
            />
          </>
        )}

        <label className="signin-check">
          <input
            type="checkbox"
            checked={form.remember}
            onChange={(e) => set("remember", e.target.checked)}
          />
          Remember {oauth ? "client secret" : "password"} on this machine (encrypted local store)
        </label>

        {error && <div id="signin-error" className="signin-error" role="alert">{error}</div>}

        <Button kind="primary" disabled={busy} onClick={signIn} style={{ width: "100%", maxWidth: "none", marginTop: 8 }}>
          {busy ? "Connecting…" : "Connect"}
        </Button>

        <Button
          kind="ghost"
          onClick={skipGate}
          style={{ width: "100%", maxWidth: "none", marginTop: 8 }}
        >
          Continue without Oracle →
        </Button>

        <div className="signin-footer">
          <span className="signin-muted">
            Oracle is optional — chat and AI features work without a tenant.{" "}
            <button className="signin-link" onClick={() => nav("/settings")}>
              Open Settings
            </button>
          </span>
        </div>
    </ComposedModal>
  );
}
