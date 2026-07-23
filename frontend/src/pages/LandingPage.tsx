import { useState } from "react";
import { Link } from "react-router-dom";
import "../styles/landing.css";
import { usePrefersReducedMotion, useScrollReveal } from "../hooks/useScrollReveal";

const APP_ENTRY = "/app";

const extensionVersion =
  __EXTENSION_ZIP_NAME__.match(/extension-(\d+\.\d+\.\d+)\.zip$/)?.[1] ?? "latest";

const WORKFLOWS = [
  {
    number: "01",
    label: "BUILD",
    title: "Turn a sentence into a real EPM artifact.",
    body: "Ask for a form, rule, or cube view in plain language. EPM Wizard returns a structured preview you can inspect and refine.",
    example: "Create an Actuals form for Total Payroll",
  },
  {
    number: "02",
    label: "UNDERSTAND",
    title: "Bring the context your application is missing.",
    body: "Layer an LCM snapshot or workbook over live metadata, then ground drafts in your own hierarchies, rules, formulas, and conventions.",
    example: "Explain why this forecast workbook behaves this way",
  },
  {
    number: "03",
    label: "OPERATE",
    title: "Let the extension handle the click path.",
    body: "Give the browser agent a goal. It targets the active tab, narrates each step, and pauses before destructive or production-facing actions.",
    example: "Open Actuals and set Scenario to Forecast",
  },
];

const PROOF_POINTS = [
  ["Manifest V3", "A real, loadable Chrome extension, not a video mockup."],
  ["Local-first", "Projects, context, artifacts, and history stay in your environment."],
  ["Human-gated", "With the default safety gate on, recognized risky actions stop for approval."],
  ["Auditable", "Every proposal, validation, approval, and deployment stays reviewable."],
];

const USE_CASES = [
  ["Forms & reports", "Build structured Planning artifacts from plain-language requirements."],
  ["Business rules", "Explain, draft, compare, and run rules with visible grounding."],
  ["Snapshot grounding", "Layer LCM exports and workbooks over live tenant metadata."],
  ["Cube architecture", "Map dimensions, intersections, hierarchy depth, and sizing."],
  ["Controlled deployment", "Validate, approve, package, deploy, and verify every change."],
  ["Browser operations", "Navigate Oracle EPM with narrated, human-gated browser control."],
];

function GoogleGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path d="M9 2v9m0 0 3.5-3.5M9 11 5.5 7.5M3 15h12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" aria-hidden="true">
      <path d="M3 8.5h10m-3.5-3.5 3.5 3.5L9.5 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ExtensionDownload({ compact = false }: { compact?: boolean }) {
  return (
    <a
      className={`lp-button lp-button-download${compact ? " compact" : ""}`}
      href={__EXTENSION_ZIP_URL__}
      download={__EXTENSION_ZIP_NAME__}
    >
      <DownloadIcon />
      <span>{compact ? "Download extension" : "Download Chrome extension"}</span>
    </a>
  );
}

function GoogleSignIn({ compact = false }: { compact?: boolean }) {
  return (
    <a
      className={`lp-button lp-button-google${compact ? " compact" : ""}`}
      href={APP_ENTRY}
      aria-label={compact ? "Sign in" : undefined}
    >
      <GoogleGlyph />
      <span>{compact ? "Sign in" : "Continue with Google"}</span>
    </a>
  );
}

type RunView = "tab" | "target" | "action" | "result" | "evidence";

const RUN_STAGES: Array<{
  id: Extract<RunView, "tab" | "target" | "action">;
  number: string;
  icon: string;
  title: string;
  detail: string;
}> = [
  { id: "tab", number: "01", icon: "TAB", title: "Active Oracle tab", detail: "planning.oraclecloud.com" },
  { id: "target", number: "02", icon: "REF 42", title: "Actuals / Scenario", detail: "accessibility tree match" },
  { id: "action", number: "03", icon: "SET", title: "Forecast", detail: "write prepared, not sent" },
];

const RUN_DETAILS: Record<
  RunView,
  { eyebrow: string; title: string; body: string; status: string; tone: string; icon: string }
> = {
  tab: {
    eyebrow: "01 / ACTIVE TAB",
    title: "Connected to the Oracle Planning page",
    body: "The extension scopes the run to the selected tab and verifies the website session.",
    status: "CONNECTED",
    tone: "info",
    icon: "01",
  },
  target: {
    eyebrow: "02 / ACCESSIBILITY MATCH",
    title: "Found the Scenario selector",
    body: "The agent resolved a stable accessibility reference before preparing any interaction.",
    status: "FOUND",
    tone: "info",
    icon: "42",
  },
  action: {
    eyebrow: "03 / STAGED ACTION",
    title: "Forecast is ready to apply",
    body: "The value is prepared locally. It has not been written to the Oracle EPM page.",
    status: "STAGED",
    tone: "info",
    icon: "03",
  },
  result: {
    eyebrow: "OUTPUT READY / VERIFIED",
    title: "Scenario is now set to Forecast",
    body: "EPM Wizard applied the value on the Actuals form, read the page back, and verified the final state.",
    status: "VERIFIED",
    tone: "success",
    icon: "✓",
  },
  evidence: {
    eyebrow: "VERIFICATION EVIDENCE",
    title: "Four checks confirm the output",
    body: "Target, selected value, page state, and environment all match the requested Forecast change.",
    status: "4 CHECKS",
    tone: "info",
    icon: "04",
  },
};

function AnimatedAgentRun({ running }: { running: boolean }) {
  const [view, setView] = useState<RunView>("result");
  const [hasInteracted, setHasInteracted] = useState(false);
  const detail = RUN_DETAILS[view];
  const inspect = (nextView: RunView) => {
    setHasInteracted(true);
    setView(nextView);
  };

  return (
    <section
      className={`lp-agent-run${running ? " is-running" : ""}`}
      aria-label="Interactive EPM Wizard run. The browser agent receives a goal, finds the Actuals form, sets Scenario to Forecast, and verifies the output."
    >
      <div className="lp-run-topbar">
        <span className="lp-run-mark" aria-hidden="true"><i /><i /><i /></span>
        <span className="lp-run-title">browser-agent / run-0042</span>
        <span className="lp-run-status" aria-live="polite">
          {!hasInteracted ? (
            <>
              <b className="lp-run-working">WORKING</b>
              <b className="lp-run-complete">VERIFIED</b>
            </>
          ) : (
            <b className={`lp-run-state tone-${detail.tone}`}>{detail.status}</b>
          )}
        </span>
      </div>

      <div className="lp-run-body">
        <div className="lp-run-command">
          <span>GOAL</span>
          <p>Open Actuals and set Scenario to Forecast</p>
          <i aria-hidden="true" />
        </div>

        <div className="lp-run-flow">
          {RUN_STAGES.map((stage, index) => (
            <div className="lp-run-stage-wrap" key={stage.id}>
              <button
                type="button"
                className={`lp-run-stage lp-run-stage-${stage.id}${view === stage.id ? " selected" : ""}`}
                aria-pressed={view === stage.id}
                onClick={() => inspect(stage.id)}
              >
                <span>{stage.number}</span>
                <i className="lp-stage-icon">{stage.icon}</i>
                <b>{stage.title}</b>
                <small>{stage.detail}</small>
              </button>
              {index < RUN_STAGES.length - 1 && (
                <span
                  className={`lp-run-connector connector-${index === 0 ? "one" : "two"}`}
                  aria-hidden="true"
                />
              )}
            </div>
          ))}
        </div>

        <div
          className={`lp-run-inspector tone-${detail.tone}${hasInteracted ? " is-user-change" : " is-initial"}`}
          key={view}
          aria-live="polite"
        >
          <div className="lp-run-gate-head">
            <span className="lp-run-shield" aria-hidden="true">{detail.icon}</span>
            <div>
              <span>{detail.eyebrow}</span>
              <b>{detail.title}</b>
            </div>
            <small>{detail.status}</small>
          </div>
          <p>{detail.body}</p>
          <div className="lp-run-gate-actions">
            {view === "result" ? (
              <>
                <button type="button" onClick={() => inspect("action")}>View exact change</button>
                <button type="button" onClick={() => inspect("evidence")}>View evidence</button>
              </>
            ) : (
              <button type="button" onClick={() => inspect("result")}>View verified output</button>
            )}
          </div>
        </div>
      </div>

      <div className="lp-run-footer">
        <span><i /> Accessibility-tree grounded</span>
        <span>Every step narrated</span>
        <span>Human approval enforced</span>
      </div>
    </section>
  );
}

function WorkflowVisual({ mode }: { mode: string }) {
  if (mode === "BUILD") {
    return (
      <div
        className="lp-product-frame"
        role="img"
        aria-label="EPM Wizard chat turning a request into a validated Actuals form preview."
      >
        <div className="lp-product-bar">
          <span>EPM Wizard</span><b>MCWPCF</b><small>TEST</small>
        </div>
        <div className="lp-product-shell">
          <div className="lp-product-rail" aria-hidden="true">
            <span className="active">Chat</span><span>Artifacts</span><span>Deployments</span>
          </div>
          <div className="lp-product-main">
            <div className="lp-chat-request">Create an Actuals form for Total Payroll.</div>
            <div className="lp-chat-response">
              <span>FORM SPECIFICATION</span><b>Validated against MCWPCF</b>
            </div>
            <div className="lp-form-spec">
              <div className="lp-form-spec-head"><b>25-01 Actuals</b><span>VALID</span></div>
              <div className="lp-form-spec-pov">Scenario: Actual · Entity: Total Entity · Version: Working</div>
              <div className="lp-form-spec-grid">
                <b>Account</b><b>Jan</b><b>Feb</b><b>Mar</b>
                <span>Salaries</span><span>1,284</span><span>1,301</span><span>1,296</span>
                <span>Benefits</span><span>412</span><span>419</span><span>417</span>
                <span>Overtime</span><span>142</span><span>128</span><span>136</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (mode === "UNDERSTAND") {
    return (
      <div
        className="lp-product-frame"
        role="img"
        aria-label="EPM Wizard metadata explorer showing a member hierarchy and the sources grounding a business rule."
      >
        <div className="lp-product-bar">
          <span>Metadata explorer</span><b>Context v12</b><small>ACTIVE</small>
        </div>
        <div className="lp-context-shell">
          <div className="lp-context-tree">
            <div><b>▾ Account</b><small>246 members</small></div>
            <span>├─ Total Payroll</span>
            <span className="selected">│&nbsp;&nbsp;├─ Salaries</span>
            <span>│&nbsp;&nbsp;├─ Benefits</span>
            <span>│&nbsp;&nbsp;└─ Overtime</span>
            <span>└─ Operating Expense</span>
          </div>
          <div className="lp-context-detail">
            <span>SELECTED MEMBER</span>
            <h3>Salaries</h3>
            <dl>
              <div><dt>Dimension</dt><dd>Account</dd></div>
              <div><dt>Parent</dt><dd>Total Payroll</dd></div>
              <div><dt>Cube</dt><dd>OEP_FS</dd></div>
            </dl>
            <div className="lp-grounding-list">
              <b>Grounded on 3 sources</b>
              <span>BR_PAYROLL_COPY <small>Calculation Manager</small></span>
              <span>Account.csv <small>LCM snapshot</small></span>
              <span>OEP_FS <small>Live outline</small></span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="lp-product-frame"
      role="img"
      aria-label="EPM Wizard deployment review showing validation, approval, deployment, and verification stages."
    >
      <div className="lp-product-bar">
        <span>Deployment review</span><b>Vision / TEST</b><small>AWAITING APPROVAL</small>
      </div>
      <div className="lp-deploy-shell">
        <div className="lp-deploy-summary">
          <span>CHANGE SET</span>
          <h3>25-01 Actuals</h3>
          <p>Create form · OEP_FS · 1 artifact</p>
        </div>
        <ol className="lp-deploy-steps">
          <li className="done"><span>01</span><div><b>Specification validated</b><small>4 deterministic checks passed</small></div><strong>DONE</strong></li>
          <li className="current"><span>02</span><div><b>Human approval</b><small>Review exact target and package</small></div><strong>NOW</strong></li>
          <li><span>03</span><div><b>Deploy through connector</b><small>Typed operation · no shell</small></div><strong>WAIT</strong></li>
          <li><span>04</span><div><b>Verify in tenant</b><small>Read back and confirm</small></div><strong>WAIT</strong></li>
        </ol>
        <div className="lp-deploy-actions"><span>Approve &amp; deploy</span><span>Inspect package</span></div>
      </div>
    </div>
  );
}

export function LandingPage() {
  const rootRef = useScrollReveal<HTMLDivElement>();
  const reduceMotion = usePrefersReducedMotion();
  const [runKey, setRunKey] = useState(0);

  return (
    <div className="lp" ref={rootRef}>
      <header className="lp-nav">
        <div className="lp-nav-inner">
          <Link className="lp-brand" to="/" aria-label="EPM Wizard home">
            <img src="/favicon.svg" alt="" width={28} height={28} />
            <span>EPM Wizard</span>
            <small>FOR ORACLE EPM</small>
          </Link>
          <nav className="lp-nav-links" aria-label="Primary navigation">
            <Link to="/docs">Documentation</Link>
          </nav>
          <div className="lp-nav-actions">
            <ExtensionDownload compact />
            <GoogleSignIn compact />
          </div>
        </div>
      </header>

      <main>
        <section className="lp-hero">
          <div className="lp-hero-copy">
            <p className="lp-eyebrow">
              <span>NEW</span>
              CHROME EXTENSION + AI WORKSPACE
            </p>
            <h1>
              <span>EPM work,</span>
              <small>without the click maze.</small>
            </h1>
            <p className="lp-hero-lede">
              Turn Oracle EPM requests into structured, reviewable work, then carry them into the
              product with a narrated browser agent that pauses before risk.
            </p>
            <div className="lp-hero-actions">
              <ExtensionDownload />
              <GoogleSignIn />
            </div>
            <div className="lp-install-meta">
              <span>v{extensionVersion}</span>
              <span>Chrome 116+</span>
              <span>Manifest V3</span>
              <span>Local-first workspace</span>
            </div>
            <p className="lp-hero-note">
              Structured specifications · deterministic validation · explicit human approval
            </p>
          </div>
          <div className="lp-hero-visual">
            <AnimatedAgentRun key={runKey} running={!reduceMotion} />
            {!reduceMotion && (
              <button
                className="lp-run-replay"
                type="button"
                onClick={() => setRunKey((key) => key + 1)}
              >
                <span aria-hidden="true">↺</span>
                Replay run
              </button>
            )}
          </div>
        </section>

        <section className="lp-proof" aria-label="Product highlights">
          {PROOF_POINTS.map(([title, body]) => (
            <div className="lp-proof-item" key={title}>
              <b>{title}</b>
              <span>{body}</span>
            </div>
          ))}
        </section>

        <section className="lp-section lp-workflows" id="product">
          <div className="lp-section-heading" data-reveal>
            <p className="lp-kicker">ONE CONTROLLED WORKSPACE</p>
            <h2>Build it. Understand it. Operate it.</h2>
            <p>
              Keep the request, real application context, artifact specification, and browser
              execution together in one professional review surface.
            </p>
          </div>
          <div className="lp-workflow-grid">
            {WORKFLOWS.map((workflow) => (
              <article className="lp-workflow" key={workflow.number} data-reveal>
                <div className="lp-workflow-copy">
                  <div className="lp-workflow-meta"><span>{workflow.number}</span><b>{workflow.label}</b></div>
                  <h3 className="text-balance">{workflow.title}</h3>
                  <p>{workflow.body}</p>
                  <code>{workflow.example}</code>
                </div>
                <WorkflowVisual mode={workflow.label} />
              </article>
            ))}
          </div>
        </section>

        <section className="lp-section lp-use-cases">
          <div className="lp-section-heading" data-reveal>
            <p className="lp-kicker">BUILT FOR REAL EPM WORK</p>
            <h2>One workspace across the implementation lifecycle.</h2>
            <p>
              From discovery and design through controlled execution, every surface is tailored
              to the objects and safeguards Oracle EPM teams already understand.
            </p>
          </div>
          <div className="lp-use-case-grid">
            {USE_CASES.map(([title, body], index) => (
              <article key={title} data-reveal>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h3>{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="lp-section lp-final">
          <div className="lp-final-card" data-reveal>
            <p className="lp-kicker">BRING STRUCTURE TO EVERY CHANGE</p>
            <h2>Make Oracle EPM work reviewable from request to result.</h2>
            <p>Open the workspace, connect your instance, and keep every proposal, approval, and execution in one place.</p>
            <div className="lp-hero-actions">
              <ExtensionDownload />
              <GoogleSignIn />
            </div>
            <Link className="lp-text-link" to="/docs">Or read the full product docs <ArrowIcon /></Link>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-footer-inner">
          <div className="lp-footer-brand">
            <Link className="lp-brand" to="/">
              <img src="/favicon.svg" alt="" width={24} height={24} />
              <span>EPM Wizard</span>
            </Link>
            <p>Structured AI and supervised browser control for Oracle EPM implementation teams.</p>
          </div>
          <div className="lp-footer-links">
            <div><b>Resources</b><Link to="/docs">Documentation</Link><Link to="/docs#agent">Extension guide</Link><Link to="/docs#security">Security</Link></div>
            <div><b>Workspace</b><a href={APP_ENTRY}>Sign in</a><a href={__EXTENSION_ZIP_URL__} download={__EXTENSION_ZIP_NAME__}>Download extension</a></div>
          </div>
          <p className="lp-footer-legal">
            Independent implementation tooling. Not made, endorsed, or sponsored by IBM or Oracle.
          </p>
        </div>
      </footer>
    </div>
  );
}
