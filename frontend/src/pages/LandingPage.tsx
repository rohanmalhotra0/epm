import { Link } from "react-router-dom";
import "../styles/landing.css";

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
  ["Manifest V3", "A real, loadable Chrome extension — not a video mockup."],
  ["Local-first", "Projects, context, artifacts, and history stay in your environment."],
  ["Human-gated", "With the default safety gate on, recognized risky actions stop for approval."],
  ["Demo-ready", "Explore the web workspace with no tenant and no model API key."],
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

function BrowserProductPreview() {
  const rows = ["Salaries", "Overtime", "Benefits", "Bonus"];
  return (
    <div className="lp-preview" aria-label="Illustration of EPM Wizard driving an Oracle EPM page">
      <div className="lp-preview-chrome">
        <span className="lp-window-dots" aria-hidden="true"><i /><i /><i /></span>
        <span className="lp-address">planning.oraclecloud.com / Forms / Actuals</span>
        <span className="lp-secure">ACTIVE TAB</span>
      </div>

      <div className="lp-preview-body">
        <div className="lp-oracle-ui">
          <div className="lp-oracle-nav">
            <span className="lp-oracle-logo">ORACLE EPM</span>
            <span>Home</span>
            <span>Forms</span>
            <span>Rules</span>
          </div>
          <div className="lp-form-head">
            <div>
              <span className="lp-form-kicker">PLANNING / FORMS</span>
              <b>Actuals — Payroll Review</b>
            </div>
            <span className="lp-env-badge">TEST</span>
          </div>
          <div className="lp-grid">
            <div className="lp-grid-row lp-grid-header">
              <span>Account</span><span>Jan</span><span>Feb</span><span>Mar</span>
            </div>
            {rows.map((row, index) => (
              <div className={`lp-grid-row${index === 1 ? " selected" : ""}`} key={row}>
                <span>{row}</span><span>{index === 1 ? "142" : "—"}</span><span>—</span><span>—</span>
              </div>
            ))}
          </div>
        </div>

        <aside className="lp-agent-panel">
          <div className="lp-agent-head">
            <div>
              <span className="lp-live-dot" aria-hidden="true" />
              <b>Browser Agent</b>
            </div>
            <span className="lp-connected">CONNECTED</span>
          </div>
          <div className="lp-goal">
            <span>GOAL</span>
            <p>Open Actuals and set Scenario to Forecast</p>
          </div>
          <ol className="lp-run-log">
            <li className="done"><span>01</span><p>Opened the Forms library</p><b>DONE</b></li>
            <li className="done"><span>02</span><p>Selected “Actuals”</p><b>DONE</b></li>
            <li className="current"><span>03</span><p>Set Scenario to Forecast</p><b>NOW</b></li>
          </ol>
          <div className="lp-approval">
            <div>
              <span>APPROVAL REQUIRED</span>
              <b>Production write detected</b>
            </div>
            <p>The agent is paused. Review the target before it continues.</p>
            <div className="lp-approval-actions">
              <span>Approve once</span>
              <span>Skip</span>
            </div>
          </div>
        </aside>
      </div>
      <div className="lp-preview-caption">
        <span>Accessibility-tree grounding</span>
        <span>Step-by-step narration</span>
        <span>Approval before risk</span>
      </div>
    </div>
  );
}

function ResultStack() {
  return (
    <div className="lp-result-stack" aria-label="Examples of structured EPM Wizard results">
      <div className="lp-result-card form-card">
        <div className="lp-result-top">
          <span>FORM PREVIEW</span>
          <b>VALID</b>
        </div>
        <h3>25-01 Actuals</h3>
        <div className="lp-axis">
          <span>Rows</span><b>Account · Lvl-0 Total Payroll</b>
          <span>Columns</span><b>Period · Jan–Dec</b>
          <span>POV</span><b>Entity · Total Entity</b>
        </div>
      </div>
      <div className="lp-result-card approval-card">
        <div className="lp-result-top">
          <span>DEPLOYMENT</span>
          <b>WAITING FOR YOU</b>
        </div>
        <h3>Deploy to Vision / TEST?</h3>
        <p>4 validation checks passed. Nothing changes until you approve.</p>
        <div className="lp-inline-actions"><span>Approve &amp; deploy</span><span>Preview package</span></div>
      </div>
      <div className="lp-result-card ground-card">
        <div className="lp-result-top">
          <span>GROUNDED ON</span>
          <b>3 SOURCES</b>
        </div>
        <div className="lp-source"><span>BR_PAYROLL_COPY</span><b>Calculation Manager rule</b></div>
        <div className="lp-source"><span>OEP_FS</span><b>Live cube outline</b></div>
      </div>
    </div>
  );
}

export function LandingPage() {
  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="lp-nav-inner">
          <Link className="lp-brand" to="/" aria-label="EPM Wizard home">
            <img src="/favicon.svg" alt="" width={28} height={28} />
            <span>EPM Wizard</span>
            <small>FOR ORACLE EPM</small>
          </Link>
          <nav className="lp-nav-links" aria-label="Primary navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#safety">Safety</a>
            <Link to="/docs">Docs</Link>
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
            <h1>EPM work,<br />without the click maze.</h1>
            <p className="lp-hero-lede">
              Install the browser agent, sign in, and tell it what needs to happen in Oracle EPM.
              It works alongside a structured AI workspace, narrates every browser step, and — with
              the default safety gate on — pauses before recognized risky changes.
            </p>
            <div className="lp-hero-actions">
              <ExtensionDownload />
              <GoogleSignIn />
            </div>
            <div className="lp-install-meta">
              <span>v{extensionVersion}</span>
              <span>Chrome 116+</span>
              <span>Manifest V3</span>
              <span>ZIP · load unpacked</span>
            </div>
            <p className="lp-hero-note">
              The web workspace has a tenant-free Demo Mode. Starting an extension run requires a
              website session and a connected Oracle EPM environment.
            </p>
            <p className="lp-beta-note">
              Supervised early access · Oracle-specific UI hardening is in progress · not yet validated on a live tenant
            </p>
          </div>
          <div className="lp-hero-visual">
            <BrowserProductPreview />
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

        <section className="lp-section lp-start" id="how-it-works">
          <div className="lp-section-heading" data-reveal>
            <p className="lp-kicker">START HERE</p>
            <h2>Four steps from download to first run.</h2>
            <p>The hosted extension and web workspace are designed as one handoff, with no IDs or server URLs to copy.</p>
          </div>
          <ol className="lp-start-grid">
            <li data-reveal>
              <span className="lp-step-number">01</span>
              <div className="lp-step-art">
                <span className="lp-zip">ZIP</span>
                <i>epm-wizard-extension-{extensionVersion}.zip</i>
              </div>
              <h3>Download and load in Chrome</h3>
              <p>Unzip the download, open <code>chrome://extensions</code>, enable Developer mode, then choose Load unpacked.</p>
            </li>
            <li data-reveal>
              <span className="lp-step-number">02</span>
              <div className="lp-step-art google-art"><GoogleGlyph /><i>Continue with Google</i></div>
              <h3>Use one website session</h3>
              <p>Google sign-in unlocks the hosted workspace and lets the extension verify the same website session.</p>
            </li>
            <li data-reveal>
              <span className="lp-step-number">03</span>
              <div className="lp-step-art connect-art"><span>●</span><i>Oracle environment connected</i></div>
              <h3>Connect Oracle EPM</h3>
              <p>Add a non-demo environment with a password or OCI IAM OAuth client credentials. The extension will not start without it.</p>
            </li>
            <li data-reveal>
              <span className="lp-step-number">04</span>
              <div className="lp-step-art launch-art"><span>↗</span><i>Launch on current tab</i></div>
              <h3>Launch from Browser Agent</h3>
              <p>Open the Agent page, enter a goal, and launch. The project and backend connection are handed off automatically.</p>
            </li>
          </ol>
          <div className="lp-start-actions" data-reveal>
            <ExtensionDownload />
            <Link className="lp-text-link" to="/docs#agent">Read the installation guide <ArrowIcon /></Link>
          </div>
        </section>

        <section className="lp-section lp-workflows">
          <div className="lp-section-heading" data-reveal>
            <p className="lp-kicker">ONE WORKSPACE, THREE MODES</p>
            <h2>Build it. Understand it. Operate it.</h2>
            <p>EPM Wizard keeps the request, the real application context, and the browser execution in one reviewable flow.</p>
          </div>
          <div className="lp-workflow-grid">
            {WORKFLOWS.map((workflow) => (
              <article className="lp-workflow" key={workflow.number} data-reveal>
                <div className="lp-workflow-meta"><span>{workflow.number}</span><b>{workflow.label}</b></div>
                <h3>{workflow.title}</h3>
                <p>{workflow.body}</p>
                <code>{workflow.example}</code>
              </article>
            ))}
          </div>
        </section>

        <section className="lp-section lp-results">
          <div className="lp-results-copy" data-reveal>
            <p className="lp-kicker">RESULTS YOU CAN REVIEW</p>
            <h2>It answers in interfaces, not walls of text.</h2>
            <p>
              Requests come back as form previews, cube maps, validation reports, diffs,
              runtime prompts, and deployment plans. The model proposes; deterministic code
              validates and packages the work.
            </p>
            <ul>
              <li><span>01</span>Inspect exact rows, columns, POV, and member resolution.</li>
              <li><span>02</span>See which real rules and artifacts grounded a draft.</li>
              <li><span>03</span>Approve a reviewed plan before anything is deployed.</li>
            </ul>
            <Link className="lp-text-link" to="/docs#blocks">Explore every result type <ArrowIcon /></Link>
          </div>
          <div data-reveal><ResultStack /></div>
        </section>

        <section className="lp-section lp-safety" id="safety">
          <div className="lp-safety-copy" data-reveal>
            <p className="lp-kicker">BUILT TO PAUSE</p>
            <h2>The most important agent action is stop.</h2>
            <p>
              With the safety gate enabled by default, recognized destructive targets and writes on
              production-looking tabs are held before execution.
              You see the target, environment, and reason for the hold, then approve once or skip.
            </p>
            <p className="lp-honesty">
              The gate uses accessible names and URL heuristics; it is a meaningful guardrail, not a
              proof of safety. Keep it enabled and supervise real runs.
            </p>
          </div>
          <div className="lp-safety-console" data-reveal>
            <div className="lp-console-head"><span>RUN 0042</span><b>PAUSED</b></div>
            <div className="lp-console-line ok"><span>00:01</span><b>READ</b><p>Opened Forms library</p></div>
            <div className="lp-console-line ok"><span>00:03</span><b>SELECT</b><p>Located “Actuals”</p></div>
            <div className="lp-console-line held"><span>00:05</span><b>HELD</b><p>Write target on production tab</p></div>
            <div className="lp-console-review">
              <span>REVIEW REQUIRED</span>
              <h3>Set Scenario to Forecast?</h3>
              <p>planning-prod.example.com · target ref=42</p>
              <div><span>Approve once</span><span>Skip action</span></div>
            </div>
          </div>
        </section>

        <section className="lp-section lp-final">
          <div className="lp-final-card" data-reveal>
            <p className="lp-kicker">READY WHEN YOU ARE</p>
            <h2>Put EPM Wizard one click away.</h2>
            <p>Download the Chrome extension, then open the workspace with Google. Demo Mode is waiting on the other side.</p>
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
          <Link className="lp-brand" to="/">
            <img src="/favicon.svg" alt="" width={24} height={24} />
            <span>EPM Wizard</span>
          </Link>
          <p>
            Independent implementation tooling. Not made, endorsed, or sponsored by IBM or Oracle.
          </p>
          <div><a href="#how-it-works">Get started</a><Link to="/docs">Docs</Link></div>
        </div>
      </footer>
    </div>
  );
}
