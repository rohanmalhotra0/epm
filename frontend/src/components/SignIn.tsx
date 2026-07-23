import { useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { WatsonHealthAiResults, Upload } from "@carbon/icons-react";
import {
  Button,
  ComposedModal,
  ModalBody,
  ModalFooter,
  ModalHeader,
} from "@carbon/react";
import {
  useConnectEnvironment,
  useCreateEnvironment,
  useEnvironments,
} from "../api/hooks";
import { useInertAppBackground } from "../hooks/useInertAppBackground";
import { useUi } from "../store/ui";
import type { EnvironmentOut } from "../schemas/types";

const CLASSIFICATIONS = ["development", "test", "production"];
const OAUTH_METHOD = "oauthClientCredentials";

/**
 * Keeps the workspace mounted while prompting for the first Oracle EPM
 * connection. The user lands directly in chat, with this modal owning focus
 * until they connect or deliberately continue without an instance.
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
  const focusChat = () => {
    const focus = () =>
      document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Message EPM Wizard"]')?.focus();
    window.setTimeout(focus, 0);
  };
  const connectLater = () => {
    skipGate();
    focusChat();
  };

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
      } else {
        focusChat();
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
      onClose={() => {
        connectLater();
        return true;
      }}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
      <ModalHeader
        label={(
          <span className="signin-brand">
            <WatsonHealthAiResults size={20} className="spark" aria-hidden="true" />
            EPM Wizard setup
          </span>
        )}
        title={<span id="signin-title" className="text-balance">Connect your Oracle EPM instance</span>}
        closeModal={connectLater}
        iconDescription="Connect later"
      />
      <ModalBody hasScrollingContent aria-label="Oracle EPM connection settings">
        <p className="signin-sub text-pretty">
          Your chat is ready behind this window. Connect a Planning instance now, or continue and
          add one later from Settings.
        </p>

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
            setError("");
            setAuthMode(e.target.value as "password" | "oauth");
          }}
        >
          <option value="password" style={{ color: "#000" }}>
            Username &amp; password
          </option>
          <option value="oauth" style={{ color: "#000" }}>
            OAuth 2.0 client credentials
          </option>
        </select>

        {oauth && (
          <>
            <label className="signin-label" htmlFor="signin-token-url">Token URL</label>
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

        <label className="signin-label" htmlFor="signin-user-id">{oauth ? "Client ID" : "Username"}</label>
        <input
          id="signin-user-id"
          className="signin-input"
          placeholder={oauth ? "Confidential application client ID" : "you@example.com"}
          value={oauth ? form.clientId : form.username}
          onChange={(e) => set(oauth ? "clientId" : "username", e.target.value)}
          aria-describedby={errorId}
        />

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

        <details className="signin-advanced">
          <summary>Advanced connection options</summary>
          <div className="signin-advanced-body">
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
            >
              Load credentials file
            </Button>

            <div className="signin-row">
              <div>
                <label className="signin-label" htmlFor="signin-application">Application</label>
                <input
                  id="signin-application"
                  className="signin-input"
                  placeholder="Auto-detect"
                  value={form.application}
                  onChange={(e) => set("application", e.target.value)}
                />
              </div>
              <div>
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
                <label className="signin-label" htmlFor="signin-scope">Scope</label>
                <input
                  id="signin-scope"
                  className="signin-input"
                  placeholder="Optional OCI IAM scope"
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
              Remember {oauth ? "client secret" : "password"} in the encrypted local store
            </label>
          </div>
        </details>

        {error && <div id="signin-error" className="signin-error" role="alert">{error}</div>}
        <p className="signin-security text-pretty">
          Credentials are kept out of chat messages, model prompts, and application logs.
        </p>
      </ModalBody>
      <ModalFooter
        primaryButtonText={busy ? "Connecting…" : "Connect instance"}
        primaryButtonDisabled={busy}
        secondaryButtonText="Not now"
        onRequestSubmit={signIn}
        onRequestClose={connectLater}
      >
        {null}
      </ModalFooter>
    </ComposedModal>
  );
}
