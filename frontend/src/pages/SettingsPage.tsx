import { useState } from "react";
import {
  Button,
  Checkbox,
  PasswordInput,
  Select,
  SelectItem,
  TextInput,
} from "@carbon/react";
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
import "../styles/feature-pages.css";

const PROVIDER_TYPES = ["mock", "together", "anthropic", "openai", "openrouter", "gemini", "ollama", "generic"];

const EMPTY_PROVIDER = {
  name: "", providerType: "anthropic", baseUrl: "", apiKey: "", defaultModel: "",
  chatModel: "", fastModel: "", structuredModel: "", codeModel: "", embeddingModel: "", visionModel: "",
};

const EMPTY_ENVIRONMENT = {
  name: "", baseUrl: "", username: "", classification: "development", demo: false,
};

export function SettingsPage() {
  const pid = useUi((s) => s.currentProjectId) ?? undefined;
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const { data: providers = [] } = useProviders();
  const { data: environments = [] } = useEnvironments(pid);
  const createProvider = useCreateProvider();
  const createEnv = useCreateEnvironment(pid);
  const connect = useConnectEnvironment(pid);

  const [np, setNp] = useState(EMPTY_PROVIDER);
  const [ne, setNe] = useState(EMPTY_ENVIRONMENT);
  const [pw, setPw] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string>("");
  const [discovered, setDiscovered] = useState<string[]>([]);
  const [detecting, setDetecting] = useState(false);
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null);

  const applyOllamaPreset = () => {
    setNp({ ...EMPTY_PROVIDER, name: "Local Ollama", providerType: "ollama", baseUrl: "http://localhost:11434/v1" });
    setDiscovered([]);
    toast.info("Local model preset applied", "Ollama needs no API key. Click Detect models to list what's installed.");
  };

  const applyTogetherPreset = () => {
    setNp({ ...EMPTY_PROVIDER, name: "Together AI", providerType: "together", baseUrl: "https://api.together.xyz/v1" });
    setDiscovered([]);
    toast.info("Together AI preset applied", "Paste your Together API key, then Detect models. Set a Vision role model (e.g. a Qwen-VL) for screenshots.");
  };

  const detectModels = async () => {
    setDetecting(true);
    try {
      const r = await api<{ models: string[] }>("/api/providers/models/discover", {
        method: "POST",
        body: JSON.stringify({
          providerType: np.providerType,
          baseUrl: np.baseUrl || undefined,
          apiKey: np.apiKey || undefined,
        }),
      });
      setDiscovered(r.models);
      if (r.models.length === 0) {
        toast.warning("No models found", "The provider answered but reported an empty model list.");
      } else {
        toast.success(`${r.models.length} model${r.models.length === 1 ? "" : "s"} detected`);
        if (!np.defaultModel) setNp((cur) => ({ ...cur, defaultModel: r.models[0] }));
      }
    } catch (e) {
      const hint = np.providerType === "ollama"
        ? "Is Ollama running? Start it with `ollama serve` and try again."
        : (e as Error).message;
      toast.error("Could not detect models", hint);
    } finally {
      setDetecting(false);
    }
  };

  const testProvider = async (id: string, name: string) => {
    setTestingProviderId(id);
    setMsg("");
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
      setMsg(`Provider error: ${e?.message || "Connection test failed"}`);
      toast.error(`${name} failed`, e?.message);
    } finally {
      setTestingProviderId(null);
    }
  };

  const addProvider = () => {
    const { chatModel, fastModel, structuredModel, codeModel, embeddingModel, visionModel, ...body } = np;
    const roleModels: Record<string, string> = {
      ...(chatModel.trim() ? { chat: chatModel.trim() } : {}),
      ...(fastModel.trim() ? { fast: fastModel.trim() } : {}),
      ...(structuredModel.trim() ? { structured: structuredModel.trim() } : {}),
      ...(codeModel.trim() ? { code: codeModel.trim() } : {}),
      ...(embeddingModel.trim() ? { embedding: embeddingModel.trim() } : {}),
      ...(visionModel.trim() ? { vision: visionModel.trim() } : {}),
    };
    createProvider.mutate({
      ...body,
      ...(Object.keys(roleModels).length ? { roleModels } : {}),
    });
    setNp(EMPTY_PROVIDER);
    setDiscovered([]);
  };

  const addEnvironment = () => {
    createEnv.mutate(ne as any);
    setNe(EMPTY_ENVIRONMENT);
  };

  const pendingStatus = detecting
    ? "Detecting provider models…"
    : createProvider.isPending
      ? "Adding provider…"
      : createEnv.isPending
        ? "Adding environment…"
        : connect.isPending
          ? "Connecting to environment…"
          : testingProviderId
            ? "Testing provider connection…"
            : "";

  return (
    <div className="page settings-page">
      <h2>Settings</h2>
      <div className="page-sub">Configure AI providers and Oracle environments. Secrets are stored in the local encrypted store, never in chat or logs.</div>
      <div className="settings-status" role="status" aria-live="polite">
        {pendingStatus}
      </div>

      <h3 id="providers-heading" className="settings-section-heading">AI Providers</h3>
      <div
        className="settings-table-scroll"
        role="region"
        aria-labelledby="providers-heading"
        tabIndex={0}
      >
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th><th>Type</th><th>Model</th><th>Key</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {providers.length === 0 && (
              <tr><td colSpan={5} className="settings-empty-cell">No providers yet. Add one below.</td></tr>
            )}
            {providers.map((p) => {
              const isTesting = testingProviderId === p.id;
              return (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td><span className="tag-inline">{p.providerType}</span></td>
                  <td>{p.defaultModel ?? "—"}</td>
                  <td><span aria-label={p.hasKey ? "API key saved" : "No API key saved"}>{p.hasKey ? "✓" : "—"}</span></td>
                  <td>
                    <Button
                      size="sm"
                      kind="ghost"
                      disabled={testingProviderId !== null}
                      aria-busy={isTesting}
                      onClick={() => testProvider(p.id, p.name)}
                    >
                      {isTesting ? "Testing…" : "Test"}
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <section className="stat-tile settings-form-card" aria-labelledby="add-provider-heading">
        <h4 id="add-provider-heading" className="settings-form-heading">Add provider</h4>
        <div className="action-row settings-preset-row">
          <Button size="sm" kind={np.providerType === "together" ? "primary" : "tertiary"} onClick={applyTogetherPreset}>
            Together AI
          </Button>
          <Button size="sm" kind={np.providerType === "ollama" ? "primary" : "tertiary"} onClick={applyOllamaPreset}>
            Local model (Ollama)
          </Button>
          <span className="settings-preset-help">
            Together = cheap hosted open models. Ollama = fully local, nothing leaves your computer.
          </span>
        </div>
        <div className="settings-form-grid">
          <TextInput
            id="provider-name"
            labelText="Provider name"
            placeholder="Name"
            value={np.name}
            size="sm"
            onChange={(e) => setNp({ ...np, name: e.target.value })}
          />
          <Select
            id="provider-type"
            labelText="Provider type"
            value={np.providerType}
            size="sm"
            onChange={(e) => {
              setNp({ ...np, providerType: e.target.value });
              setDiscovered([]);
            }}
          >
            {PROVIDER_TYPES.map((t) => <SelectItem key={t} value={t} text={t} />)}
          </Select>
          <TextInput
            id="provider-base-url"
            labelText="Base URL (optional)"
            placeholder="Base URL (optional)"
            value={np.baseUrl}
            size="sm"
            onChange={(e) => setNp({ ...np, baseUrl: e.target.value })}
          />
          {discovered.length > 0 ? (
            <Select
              id="provider-default-model"
              labelText="Default model"
              value={np.defaultModel}
              size="sm"
              onChange={(e) => setNp({ ...np, defaultModel: e.target.value })}
            >
              {!discovered.includes(np.defaultModel) && (
                <SelectItem value={np.defaultModel} text={np.defaultModel || "Pick a model"} />
              )}
              {discovered.map((m) => <SelectItem key={m} value={m} text={m} />)}
            </Select>
          ) : (
            <TextInput
              id="provider-default-model"
              labelText="Default model"
              placeholder="Default model"
              value={np.defaultModel}
              size="sm"
              onChange={(e) => setNp({ ...np, defaultModel: e.target.value })}
            />
          )}
          <div className="settings-span-full">
            <PasswordInput
              id="provider-api-key"
              labelText="API key"
              helperText={np.providerType === "ollama" ? "Not needed for a local Ollama provider." : "Stored in the local encrypted store."}
              placeholder={np.providerType === "ollama" ? "API key (not needed for Ollama)" : "API key"}
              value={np.apiKey}
              size="sm"
              autoComplete="new-password"
              onChange={(e) => setNp({ ...np, apiKey: e.target.value })}
            />
          </div>
          <div className="settings-span-full settings-role-heading">
            Role models (optional) — override the default model per task
          </div>
          <TextInput
            id="provider-chat-model"
            labelText="Chat model"
            placeholder="Chat model"
            value={np.chatModel}
            size="sm"
            onChange={(e) => setNp({ ...np, chatModel: e.target.value })}
          />
          <TextInput
            id="provider-fast-model"
            labelText="Fast model"
            placeholder="Fast model"
            value={np.fastModel}
            size="sm"
            onChange={(e) => setNp({ ...np, fastModel: e.target.value })}
          />
          <TextInput
            id="provider-structured-model"
            labelText="Structured model"
            placeholder="Structured model"
            value={np.structuredModel}
            size="sm"
            onChange={(e) => setNp({ ...np, structuredModel: e.target.value })}
          />
          <TextInput
            id="provider-code-model"
            labelText="Code model"
            placeholder="Code model"
            value={np.codeModel}
            size="sm"
            onChange={(e) => setNp({ ...np, codeModel: e.target.value })}
          />
          <TextInput
            id="provider-vision-model"
            labelText="Vision model"
            placeholder="Vision model (screenshots)"
            helperText="Used when a message carries screenshots."
            value={np.visionModel}
            size="sm"
            onChange={(e) => setNp({ ...np, visionModel: e.target.value })}
          />
          <div className="settings-span-full">
            <TextInput
              id="provider-embedding-model"
              labelText="Embedding model (RAG)"
              placeholder="Embedding model (RAG)"
              helperText="Used for hybrid RAG scoring; leave empty for the provider default."
              value={np.embeddingModel}
              size="sm"
              onChange={(e) => setNp({ ...np, embeddingModel: e.target.value })}
            />
          </div>
        </div>
        <div className="action-row">
          <Button
            size="sm"
            kind="primary"
            disabled={!np.name.trim() || createProvider.isPending}
            aria-busy={createProvider.isPending}
            onClick={addProvider}
          >
            {createProvider.isPending ? "Adding provider…" : "Add provider"}
          </Button>
          <Button
            size="sm"
            kind="tertiary"
            disabled={detecting || createProvider.isPending}
            aria-busy={detecting}
            onClick={detectModels}
          >
            {detecting ? "Detecting…" : "Detect models"}
          </Button>
        </div>
      </section>

      <h3 id="environments-heading" className="settings-section-heading">Oracle Environments</h3>
      <div
        className="settings-table-scroll settings-environments-table"
        role="region"
        aria-labelledby="environments-heading"
        tabIndex={0}
      >
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th><th>Classification</th><th>URL</th><th>Connected</th>
              <th aria-label="Connection" />
            </tr>
          </thead>
          <tbody>
            {environments.length === 0 && (
              <tr><td colSpan={5} className="settings-empty-cell">No environments yet. Add one below.</td></tr>
            )}
            {environments.map((e) => {
              const isConnecting = connect.isPending && connect.variables?.id === e.id;
              return (
                <tr key={e.id}>
                  <td>{e.name}</td>
                  <td><span className={`env-badge ${e.classification}`}>{e.classification}</span></td>
                  <td className="mono settings-url-cell">{e.baseUrl || "demo"}</td>
                  <td><span aria-label={e.connected ? "Connected" : "Not connected"}>{e.connected ? "✓" : "—"}</span></td>
                  <td>
                    <div className="settings-connect-row">
                      {!e.demo && (
                        <PasswordInput
                          id={`environment-password-${e.id}`}
                          labelText={`Password for ${e.name}`}
                          hideLabel
                          placeholder={`${e.name} password`}
                          value={pw[e.id] || ""}
                          size="sm"
                          autoComplete="current-password"
                          disabled={isConnecting}
                          onChange={(event) => setPw({ ...pw, [e.id]: event.target.value })}
                        />
                      )}
                      <Button
                        size="sm"
                        kind="tertiary"
                        disabled={connect.isPending}
                        aria-busy={isConnecting}
                        onClick={() => connect.mutate({ id: e.id, password: pw[e.id] })}
                      >
                        {isConnecting ? "Connecting…" : "Connect"}
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <section className="stat-tile settings-form-card" aria-labelledby="add-environment-heading">
        <h4 id="add-environment-heading" className="settings-form-heading">Add environment</h4>
        <div className="settings-form-grid">
          <TextInput
            id="environment-name"
            labelText="Environment name"
            placeholder="Name"
            value={ne.name}
            size="sm"
            onChange={(e) => setNe({ ...ne, name: e.target.value })}
          />
          <Select
            id="environment-classification"
            labelText="Classification"
            value={ne.classification}
            size="sm"
            onChange={(e) => setNe({ ...ne, classification: e.target.value })}
          >
            {["development", "test", "production"].map((c) => <SelectItem key={c} value={c} text={c} />)}
          </Select>
          <TextInput
            id="environment-base-url"
            labelText="Base URL"
            placeholder="Base URL"
            value={ne.baseUrl}
            size="sm"
            onChange={(e) => setNe({ ...ne, baseUrl: e.target.value })}
          />
          <TextInput
            id="environment-username"
            labelText="Username"
            placeholder="Username"
            value={ne.username}
            size="sm"
            onChange={(e) => setNe({ ...ne, username: e.target.value })}
          />
          <div className="settings-span-full">
            <Checkbox
              id="environment-demo"
              labelText="Demo environment (no Oracle tenant)"
              checked={ne.demo}
              onChange={(_event, { checked }) => setNe({ ...ne, demo: checked })}
            />
          </div>
        </div>
        <div className="action-row">
          <Button
            size="sm"
            kind="primary"
            disabled={!ne.name.trim() || createEnv.isPending}
            aria-busy={createEnv.isPending}
            onClick={addEnvironment}
          >
            {createEnv.isPending ? "Adding environment…" : "Add environment"}
          </Button>
        </div>
      </section>

      <h3 className="settings-section-heading">Diagnostics</h3>
      <DiagnosticsPanel />

      <h3 className="settings-section-heading">Appearance</h3>
      <div className="action-row">
        <Button size="sm" kind={theme === "g100" ? "primary" : "tertiary"} onClick={() => setTheme("g100")}>Dark (Gray 100)</Button>
        <Button size="sm" kind={theme === "white" ? "primary" : "tertiary"} onClick={() => setTheme("white")}>Light</Button>
      </div>

      {msg && <div className="settings-test-result" role="status">{msg}</div>}
    </div>
  );
}
