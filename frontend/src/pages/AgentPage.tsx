import { useEffect, useState } from "react";
import { Button, InlineNotification, TextArea } from "@carbon/react";
import { Bot, CheckmarkFilled, Download, Launch } from "@carbon/icons-react";
import { useUi } from "../store/ui";
import { toast } from "../store/toast";
import { detectExtension, launchAgent, type ExtensionInfo } from "../agent/extensionBridge";
import "../styles/feature-pages.css";

// Set VITE_EXTENSION_STORE_URL at build time once the extension is published;
// until then the page shows the "load unpacked" developer path only.
const STORE_URL = (import.meta.env.VITE_EXTENSION_STORE_URL as string | undefined) || "";

export function AgentPage() {
  const projectId = useUi((s) => s.currentProjectId);
  const [ext, setExt] = useState<ExtensionInfo | null>(null);
  const [goal, setGoal] = useState("");
  const [checking, setChecking] = useState(true);

  const check = async () => {
    setChecking(true);
    setExt(await detectExtension());
    setChecking(false);
  };
  useEffect(() => { check(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const onLaunch = () => {
    launchAgent({
      backendUrl: window.location.origin,
      projectId: projectId ?? "",
      goal: goal.trim() || undefined,
    });
    toast.success(
      "Agent panel launching",
      "If it doesn't open, click the EPM Wizard icon in your Chrome toolbar — it's already configured.",
    );
  };

  const installed = !!ext?.installed;

  return (
    <div className="page">
      <h2 style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Bot size={20} /> Browser Agent
      </h2>
      <div className="page-sub">
        A Chrome extension that drives Oracle EPM Cloud's web UI for you, narrating each
        step in a side panel. It reads the page's accessibility tree (falling back to
        screenshots) and only ever acts on the tab you point it at.
      </div>

      <div style={{ maxWidth: 720, marginTop: 20, display: "grid", gap: 20 }}>
        {/* status */}
        <div className="action-row" style={{ alignItems: "center", gap: 10 }}>
          {checking ? (
            <span style={{ color: "var(--cds-text-secondary,#8d8d8d)" }}>Checking for the extension…</span>
          ) : installed ? (
            <span style={{ display: "flex", alignItems: "center", gap: 6, color: "#42be65" }}>
              <CheckmarkFilled size={16} /> Extension detected{ext?.version ? ` (v${ext.version})` : ""}
            </span>
          ) : (
            <span style={{ color: "var(--cds-text-secondary,#8d8d8d)" }}>Extension not detected in this browser.</span>
          )}
          <Button size="sm" kind="ghost" onClick={check} disabled={checking}>Re-check</Button>
        </div>

        {installed ? (
          <section style={{ display: "grid", gap: 12 }}>
            <TextArea
              id="agent-goal"
              labelText="Goal (optional — handed to the panel)"
              placeholder="e.g. Open the Actuals data form and set Scenario to Forecast"
              rows={2}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
            <div className="action-row">
              <Button size="md" renderIcon={Launch} onClick={onLaunch}>
                Launch agent on the current tab
              </Button>
            </div>
            <div style={{ fontSize: 12.5, color: "var(--cds-text-secondary,#8d8d8d)", lineHeight: 1.6 }}>
              This hands the agent your backend URL (<code>{window.location.origin}</code>) and current
              project automatically — no manual setup. Open your Oracle EPM tab, then press{" "}
              <b>Start</b> in the panel. You're signed in here, so the agent authenticates with the
              same session.
            </div>
          </section>
        ) : (
          <InstallInstructions />
        )}

        {/* safety */}
        <InlineNotification
          kind="info"
          lowContrast
          hideCloseButton
          title="Production-safety gate is enforced"
          subtitle="Destructive actions (deploy, delete, clear, run rule…) and any write on a production tenant are held for your explicit approval in the panel before they run — not left to the model's judgement."
        />
      </div>
    </div>
  );
}

function InstallInstructions() {
  return (
    <section style={{ display: "grid", gap: 12 }}>
      {STORE_URL ? (
        <div className="action-row">
          <Button size="md" renderIcon={Launch} href={STORE_URL} target="_blank">
            Install from the Chrome Web Store
          </Button>
        </div>
      ) : (
        <InlineNotification
          kind="warning"
          lowContrast
          hideCloseButton
          title="Not yet on the Chrome Web Store"
          subtitle="Load it unpacked from the repo for now (developer mode)."
        />
      )}
      <div className="action-row">
        <Button
          size="md"
          kind="tertiary"
          renderIcon={Download}
          href={__EXTENSION_ZIP_URL__}
          // Hint the browser to save (with a versioned name) rather than navigate.
          {...{ download: __EXTENSION_ZIP_NAME__ }}
        >
          Download extension (.zip)
        </Button>
      </div>
      <div style={{ fontSize: 13, lineHeight: 1.7 }}>
        <b>Load unpacked (developer)</b>
        <ol style={{ margin: "6px 0 0 18px", padding: 0 }}>
          <li>
            <b>Download extension (.zip)</b> above and unzip it somewhere permanent
            (Chrome reads the unpacked folder each time it starts, so don't delete it).
            Already have the repo? Point at its <code>extension/</code> folder instead.
          </li>
          <li>Open <ChromeExtensionsLink /> and turn on <b>Developer mode</b>.</li>
          <li>Click <b>Load unpacked</b> and select the unzipped folder.</li>
          <li>Come back here and press <b>Re-check</b>.</li>
        </ol>
      </div>
    </section>
  );
}

// A clickable `chrome://extensions` "link". Chrome blocks web pages from
// navigating to chrome:// URLs, so a real <a href> would render but do nothing
// on click — instead we copy the address and tell the user to paste it, which
// is the only thing that actually works from a web page.
function ChromeExtensionsLink() {
  const ADDR = "chrome://extensions";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(ADDR);
      toast.success(
        "Address copied",
        "Paste it into a new Chrome tab — Chrome blocks opening chrome:// links from web pages.",
      );
    } catch {
      toast.info("Copy this address", `${ADDR} — paste it into a new Chrome tab.`);
    }
  };
  return (
    <code
      role="button"
      tabIndex={0}
      onClick={copy}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          copy();
        }
      }}
      title="Click to copy — Chrome blocks opening chrome:// links from web pages"
      style={{
        cursor: "pointer",
        textDecoration: "underline",
        textUnderlineOffset: 2,
        color: "var(--cds-link-primary,#78a9ff)",
      }}
    >
      {ADDR}
    </code>
  );
}
