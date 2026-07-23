import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import "../styles/docs.css";
import { useScrollReveal } from "../hooks/useScrollReveal";
import { TrustBoundaryDiagram } from "./marketingDiagrams";

/**
 * Public product documentation, served at /docs WITHOUT the Google auth gate
 * (see main.tsx's public router and deploy/fly/auth.fly.toml). It shares the
 * landing page's Carbon shell so the two read as one product: same dark
 * surfaces, hairline borders, IBM Plex, sharp corners. Static content, no
 * backend calls. Motion is functional only (a gentle scroll-reveal and the
 * self-drawing trust-boundary diagram) and fully reduced-motion compliant.
 *
 * "Sign in with Google" is a real navigation to /app so it passes through the
 * gate; in-product links (home, docs) use the public router.
 */

const APP_ENTRY = "/app";

const NAV = [
  { id: "overview", label: "Overview" },
  { id: "quickstart", label: "Quickstart" },
  { id: "chat", label: "Talking to the chat" },
  { id: "blocks", label: "Reading the results" },
  { id: "approvals", label: "Approvals & safety" },
  { id: "agent", label: "The Narrated Browser Agent" },
  { id: "connect", label: "Connect your tenant & model" },
  { id: "security", label: "Security" },
  { id: "model", label: "The model" },
  { id: "next", label: "Next steps" },
] as const;

function GoogleGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

function ExtensionDownload({ children = "Download extension" }: { children?: string }) {
  return (
    <a
      className="docs-download"
      href={__EXTENSION_ZIP_URL__}
      download={__EXTENSION_ZIP_NAME__}
    >
      <span aria-hidden="true">↓</span>
      {children}
    </a>
  );
}

/** A code / example block; keys are lightly accented via the `.k` class. */
function Code({ children }: { children: React.ReactNode }) {
  return (
    <pre className="docs-code">
      <code>{children}</code>
    </pre>
  );
}

export function DocsPage() {
  const rootRef = useScrollReveal<HTMLDivElement>();
  const [active, setActive] = useState<string>(NAV[0].id);

  // Scrollspy for the sticky table of contents. Independent of motion
  // preferences because it is a navigation aid, not an animation.
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: "-28% 0px -62% 0px", threshold: 0 },
    );
    for (const n of NAV) {
      const el = document.getElementById(n.id);
      if (el) io.observe(el);
    }
    return () => io.disconnect();
  }, []);

  return (
    <div className="docs" ref={rootRef}>
      <header className="docs-nav">
        <div className="docs-nav-inner">
          <Link className="docs-brand" to="/">
            <img src="/favicon.svg" alt="" width={24} height={24} />
            <span>EPM&nbsp;Wizard</span>
            <span className="docs-brand-sep">/</span>
            <span className="docs-brand-docs">Documentation</span>
          </Link>
          <div className="docs-nav-right">
            <Link className="docs-nav-link" to="/">
              ← Back to site
            </Link>
            <ExtensionDownload />
            <a className="docs-signin" href={APP_ENTRY}>
              <GoogleGlyph />
              <span>Sign in with Google</span>
            </a>
          </div>
        </div>
      </header>

      <div className="docs-shell">
        {/* -------- sticky table of contents -------- */}
        <aside className="docs-toc">
          <p className="docs-toc-title">On this page</p>
          <nav>
            <ul>
              {NAV.map((n) => (
                <li key={n.id}>
                  <a href={`#${n.id}`} className={active === n.id ? "active" : ""}>
                    <span className="docs-toc-tick" />
                    {n.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <a className="docs-signin block" href={APP_ENTRY}>
            <GoogleGlyph />
            <span>Open the app</span>
          </a>
        </aside>

        {/* -------- prose column -------- */}
        <main className="docs-main">
          <div className="docs-lead">
            <p className="docs-eyebrow" data-reveal>
              DOCUMENTATION
            </p>
            <h1 data-reveal>The AI workspace for Oracle EPM implementation</h1>
            <p className="docs-lede" data-reveal>
              EPM Wizard is a ChatGPT-style chat app for Oracle EPM (Hyperion Planning) work. You describe what you want,
              and results come back as live, interactive blocks instead of walls of text. Alongside it, an optional Chrome
              extension, the Narrated Browser Agent, can drive Oracle EPM Cloud's own web UI while narrating each step and
              hold recognized risky actions for your approval when its default safety gate is enabled. This page covers
              what the product is, how to get started, and where its honest limits are.
            </p>
          </div>

          {/* ---- overview ---- */}
          <section id="overview" className="docs-section">
            <h2 data-reveal>Overview</h2>
            <p data-reveal>
              EPM Wizard has two surfaces. Most work happens in the <em>chat web app</em>: it is the primary interface, and
              what it returns is structured and interactive: a form preview you can read like a grid, a cube map, a
              validation report, or a deployment plan. You do not have to decode paragraphs. When a task means clicking through
              Oracle's own screens, the <em>Narrated Browser Agent</em> extension can take the wheel in your browser and
              talk you through every move.
            </p>
            <div className="docs-cards" data-reveal>
              <div className="docs-card">
                <b>Chat web app</b>
                <span>
                  A conversational workspace for Planning: build and inspect forms, rules, and cube architecture, grounded
                  in your own application metadata. Results render inline as typed, interactive blocks.
                </span>
              </div>
              <div className="docs-card">
                <b>Narrated Browser Agent</b>
                <span>
                  A Chrome extension that drives Oracle EPM Cloud's real web UI on the tab you point it at, narrating each
                  step in a side panel and, with the default gate enabled, holding recognized destructive or production
                  actions for your approval.
                </span>
              </div>
              <div className="docs-card">
                <b>Use either, or both</b>
                <span>
                  The two surfaces are independent. The chat app works on its own with no extension; the browser agent
                  runs against Oracle's UI whether or not you are mid-conversation in the app.
                </span>
              </div>
            </div>
          </section>

          {/* ---- quickstart ---- */}
          <section id="quickstart" className="docs-section">
            <h2 data-reveal>Quickstart</h2>
            <ol className="docs-steps">
              <li data-reveal>
                <div className="docs-step-header">
                  <b>Install the Chrome extension</b>
                  <span>Chrome 116+</span>
                </div>
                <p>
                  Download and unzip the extension. Open <code>chrome://extensions</code>, enable Developer mode, then
                  choose <b>Load unpacked</b>. Select the unzipped folder.
                </p>
                <div className="docs-step-actions">
                  <ExtensionDownload children="Download extension ZIP" />
                  <small>Manifest V3 · Chrome Web Store release coming later</small>
                </div>
              </li>
              <li data-reveal>
                <div className="docs-step-header"><b>Open the web workspace</b><span>Website</span></div>
                <p>
                  On the hosted deployment, continuing to <code>/app</code> starts Google sign-in. A local or self-hosted
                  deployment may open the app directly.
                </p>
              </li>
              <li data-reveal>
                <div className="docs-step-header"><b>Connect Oracle EPM</b><span>Environment</span></div>
                <p>
                  Add a non-demo environment with a username and password or OCI IAM OAuth client credentials. A valid
                  website session and connected live environment enable <b>Start</b>.
                </p>
              </li>
              <li data-reveal>
                <div className="docs-step-header"><b>Explore Demo Mode</b><span>No tenant required</span></div>
                <p>
                  The included <code>MCWPCF</code> Planning fixture and deterministic provider let you explore the web
                  workspace without an AI key or Oracle tenant. Demo Mode does not unlock a browser-agent run.
                </p>
              </li>
              <li data-reveal>
                <div className="docs-step-header"><b>Try an example request</b><span>Chat</span></div>
                <p>Type a request in plain language and review the interactive result:</p>
                <Code>Create an Actuals form with level-zero descendants of Total Payroll in rows</Code>
                <p>
                  Refine it conversationally with <em>move Entity to POV</em>, <em>hide March</em>, or <em>use aliases</em>.
                  Ask <code>/help</code> to see what else the assistant can do.
                </p>
              </li>
            </ol>
          </section>

          {/* ---- talking to the chat ---- */}
          <section id="chat" className="docs-section">
            <h2 data-reveal>Talking to the chat</h2>
            <p data-reveal>
              The composer is the one place you type. Press <b>Enter</b> to send, <b>Shift+Enter</b> for a newline. Start a
              message with <code>/</code> to open the slash-command menu with autocomplete, or press <b>Ctrl / Cmd + K</b>{" "}
              for the command palette to jump across conversations and artifacts.
            </p>
            <div className="docs-ref" data-reveal>
              <div className="docs-ref-row">
                <code>/forms</code>
                <span>Build, preview, edit, and deploy a data form.</span>
              </div>
              <div className="docs-ref-row">
                <code>/architecture</code>
                <span>Visualize a cube's dimensions as a map.</span>
              </div>
              <div className="docs-ref-row">
                <code>/rules</code>
                <span>Search, explain, and run business rules.</span>
              </div>
              <div className="docs-ref-row">
                <code>/run-rule</code>
                <span>Run a business rule; runtime prompts render as a form.</span>
              </div>
              <div className="docs-ref-row">
                <code>/context</code>
                <span>Learn or refresh the local knowledge of your application.</span>
              </div>
              <div className="docs-ref-row">
                <code>/help</code>
                <span>See what EPM Wizard can do and how to ask for it.</span>
              </div>
            </div>
            <p data-reveal>
              You can attach files with the paperclip: an LCM Artifact Snapshot <code>.zip</code> to teach it full rule
              bodies, hierarchies, and variables, or an <code>.xlsx</code> / <code>.csv</code> spreadsheet to work from
              existing layouts. And where your browser supports the Web Speech API, you can dictate a message by voice and
              have narration read back to you. This is browser-dependent and may be unavailable.
            </p>
          </section>

          {/* ---- reading the results ---- */}
          <section id="blocks" className="docs-section">
            <h2 data-reveal>Reading the results</h2>
            <p data-reveal>
              Answers render <em>inline</em> as typed, interactive blocks: the thing itself, not a description of it. Each
              block knows its own shape, so a form preview reads like an EPM grid and a cube map draws as a diagram.
            </p>
            <div className="docs-cards" data-reveal>
              <div className="docs-card">
                <b>Form preview grid</b>
                <span>An EPM-style grid with a POV / Pages bar, rows, and columns. Read the form before it exists.</span>
              </div>
              <div className="docs-card">
                <b>Cube map</b>
                <span>An SVG dimensionality visualizer for a cube's dimensions and how they intersect.</span>
              </div>
              <div className="docs-card">
                <b>Validation report</b>
                <span>What passed, what failed, and why, checked against tenant metadata before anything ships.</span>
              </div>
              <div className="docs-card">
                <b>Deployment plan · progress · result</b>
                <span>The plan proposed, live progress while it runs, and the confirmed result read back at the end.</span>
              </div>
              <div className="docs-card">
                <b>Diff</b>
                <span>A precise before / after between two versions of a spec or context.</span>
              </div>
              <div className="docs-card">
                <b>Grounded on</b>
                <span>The real rules, templates, and naming a draft was built from, with retrieval made visible.</span>
              </div>
              <div className="docs-card">
                <b>Runtime-prompt form</b>
                <span>A business rule's runtime prompts, rendered as a form you fill in before it runs.</span>
              </div>
              <div className="docs-card">
                <b>Member search</b>
                <span>Exact, identifier-first matches for members, forms, rules, and variables.</span>
              </div>
              <div className="docs-card">
                <b>Snapshot summary</b>
                <span>What an uploaded LCM snapshot added to your context, with provenance.</span>
              </div>
            </div>
            <p data-reveal>
              For forms and reports there is also an opt-in <em>Artifacts side panel</em>. It opens on request and shows a
              structural preview of the artifact, and lets you edit it with natural-language prompts for the whole
              artifact, a table, or a single cell. It is a preview-and-prompt surface, not a full spreadsheet editor.
            </p>
          </section>

          {/* ---- approvals & safety ---- */}
          <section id="approvals" className="docs-section">
            <h2 data-reveal>Approvals &amp; safety</h2>
            <p data-reveal>
              Every change moves through the same five stages. The language model only reaches the first; everything after
              is deterministic code, and stage three is a hard stop that waits for you.
            </p>
            <ol className="docs-loop" data-reveal>
              <li>
                <span>01</span>
                <b>Propose</b>
                <em>in chat, as a typed spec</em>
              </li>
              <li>
                <span>02</span>
                <b>Validate</b>
                <em>against tenant metadata</em>
              </li>
              <li className="gate">
                <span>03</span>
                <b>Approve</b>
                <em>you, explicitly; it stops here</em>
              </li>
              <li>
                <span>04</span>
                <b>Deploy</b>
                <em>typed connector · never shell</em>
              </li>
              <li>
                <span>05</span>
                <b>Verify</b>
                <em>read back · marked verified</em>
              </li>
            </ol>
            <p data-reveal>
              Operations are classified <code>readOnly</code>, <code>execution</code>, <code>modifying</code>, and{" "}
              <code>destructive</code>. Read-only work runs freely; anything that modifies or destroys stops at an approval
              card and is refused at the connector boundary unless you approved it upstream. Production environments are
              deliberately slower: they carry a persistent PROD badge, and deploying there additionally requires typing a
              confirmation phrase such as <code>confirm deploy FormName</code>, plus passing validation.
            </p>
          </section>

          {/* ---- the narrated browser agent ---- */}
          <section id="agent" className="docs-section">
            <h2 data-reveal>The Narrated Browser Agent</h2>
            <p data-reveal>
              The Narrated Browser Agent is a Manifest V3 Chrome extension that drives Oracle EPM Cloud's real web UI on the
              tab you point it at, and narrates every step in a side panel so you can watch exactly what it does. It acts
              only on the tab you choose, and you can <b>Start</b>, <b>Pause</b>, <b>Resume</b>, or <b>Stop</b> it at any
              time. Optional spoken narration is available where your browser supports the Web Speech API.
            </p>
            <ol className="docs-steps">
              <li data-reveal>
                <div className="docs-step-header">
                  <b>Install the extension</b>
                  <span>Unpacked</span>
                </div>
                <p>
                  Download and unzip the public build. Open <code>chrome://extensions</code>, turn on Developer mode,
                  choose <b>Load unpacked</b>, and select the extension folder.
                </p>
                <div className="docs-step-actions">
                  <ExtensionDownload children="Download extension ZIP" />
                  <small>You can also use the repository's <code>extension/</code> folder.</small>
                </div>
              </li>
              <li data-reveal>
                <div className="docs-step-header"><b>Connect and launch</b><span>Browser Agent</span></div>
                <p>
                  Sign in, connect a non-demo Oracle environment, then open <code>/app/agent</code>. The app detects the
                  extension and hands off the backend URL, project, and optional goal. Open your Oracle EPM tab, then
                  press <b>Start</b>.
                </p>
              </li>
              <li data-reveal>
                <div className="docs-step-header"><b>Watch the run</b><span>Live narration</span></div>
                <p>
                  The side panel narrates each step, shows the current action, and counts progress while the browser agent
                  works on the selected tab.
                </p>
              </li>
            </ol>
            <h3 data-reveal>How it grounds itself</h3>
            <p data-reveal>
              The agent targets elements semantically, not by pixel coordinates. It reads the page's <em>accessibility
              tree</em>, including roles, names, and values, and assigns each interactive element a stable reference id, so it acts
              on <code>ref=42</code> rather than a location on screen. When a view carries no accessibility information,
              as can happen with canvas and JET data grids, it falls back to a screenshot plus a vision model to decide
              where to act.
            </p>
            <h3 data-reveal>The production-safety gate</h3>
            <p data-reveal>
              When enabled, the gate is enforced in extension code rather than left to a model prompt: before an action
              runs, the extension consults it and <b>holds</b> the action for your explicit approval when it fires.
            </p>
            <ul className="docs-list">
              <li data-reveal>
                <b>A destructive target.</b> The element about to be clicked or typed has an accessible name matching a
                destructive verb such as deploy, delete, clear, run-rule, refresh database, promote, or publish. Held everywhere.
              </li>
              <li data-reveal>
                <b>Any write on a production tab.</b> When the tab looks like a production tenant, every write is held,
                including blind coordinate clicks whose target cannot be read.
              </li>
              <li data-reveal>
                <b>A coordinate-only write.</b> A click or type whose target cannot be identified is held even outside a
                detected production environment.
              </li>
              <li data-reveal>
                <b>Cross-origin navigation.</b> Leaving the current origin is held so a run cannot silently jump to a
                different site.
              </li>
            </ul>
            <p data-reveal>
              Scroll, wait, screenshot, and same-origin navigation can run without a prompt. The gate is on by default and
              can be toggled in the panel's settings. It is a heuristic based on accessible-name and URL matching, not a proof
              of safety.
            </p>
            <blockquote className="docs-quote" data-reveal>
              Keep the gate on and supervise. It holds risky actions for you; it does not guarantee an action is safe.
            </blockquote>
            <p data-reveal>
              Honest limits, stated plainly: the browser agent has <b>not</b> been validated against a live Oracle tenant.
              The Oracle-specific UI hardening for nested iframes, canvas / JET grids, selector heuristics, and SSO is in
              progress. Screenshots use Chrome&apos;s visible-tab capture first. Chrome requires the <code>debugger</code>
              permission at install time, while trusted canvas control stays off in EPM Wizard until you enable it. CDP can
              then provide fallback capture and coordinate actions, and Chrome shows its &quot;… is debugging this
              browser&quot; banner only while attached. Validate against a real Planning UI before trusting any driving
              behaviour.
            </p>
          </section>

          {/* ---- connect your tenant & model ---- */}
          <section id="connect" className="docs-section">
            <h2 data-reveal>Connect your tenant &amp; model</h2>
            <p data-reveal>
              Demo Mode needs nothing external. To use a real model or a real environment, open <em>Settings</em>. No file
              editing required.
            </p>
            <ul className="docs-list">
              <li data-reveal>
                <b>Settings → AI Providers.</b> Connect Anthropic, any OpenAI-compatible endpoint, Gemini, or a local
                model. A deterministic <em>Mock</em> provider is the default, so the app works with no key at all; keys you
                add are held in an encrypted local store.
              </li>
              <li data-reveal>
                <b>Settings → Oracle Environments.</b> Add an environment by URL and authenticate with a username and
                password or OAuth 2.0 client credentials, classifying it DEV, TEST, or PROD. A harmless read-only call
                verifies the connection.
              </li>
            </ul>
            <p data-reveal>
              What the connection is used for, stated plainly: read-only metadata and rule execution use the documented
              Oracle Planning REST API. Automated form <em>deployment</em> to a live tenant is <b>not</b> claimed until the
              documented migration workflow is validated against a development tenant. EPM Automate is installed locally, on
              your own machine. It is not redistributed with EPM Wizard.
            </p>
          </section>

          {/* ---- security ---- */}
          <section id="security" className="docs-section">
            <h2 data-reveal>Security</h2>
            <p data-reveal>
              EPM Wizard is local-first and self-hostable. In a local deployment, projects and secrets stay in your own
              environment. In a hosted deployment, the configured server stores application data and sends model inputs to
              the AI provider you select; its hosting and provider policies apply. In both modes, secrets are kept out of
              model prompts and scrubbed from logs and diagnostics.
            </p>
            <figure className="docs-fig" data-reveal tabIndex={0}>
              <TrustBoundaryDiagram />
              <figcaption>
                The trust boundary. Configured credentials stay out of model prompts; typed connector code reaches Oracle.
              </figcaption>
            </figure>
            <ul className="docs-list">
              <li data-reveal>
                <b>Configured credentials stay out of model prompts.</b> Stored API keys and Oracle credentials live in a
                Fernet-encrypted secret store and are scrubbed from logs, tool results, errors, and diagnostics. Page
                observations and screenshots are model context, so do not expose unrelated secrets in a driven tab.
              </li>
              <li data-reveal>
                <b>No shell, ever.</b> Executable actions are typed, allowlisted functions. External commands run as
                argument arrays with strict validation, no path traversal or shell metacharacters, plus timeouts.
              </li>
              <li data-reveal>
                <b>Local mode stays local.</b> When you self-host on your machine, projects, conversations, contexts,
                artifacts, and deployment history live in your local data directory. Hosted deployments use their
                configured server-side storage.
              </li>
            </ul>
          </section>

          {/* ---- the model ---- */}
          <section id="model" className="docs-section">
            <h2 data-reveal>The model</h2>
            <p data-reveal>
              EPM Wizard runs on any provider you configure (Anthropic, any OpenAI-compatible endpoint, or Gemini), and it
              also ships its own fine-tuned <em>coder</em>, a LoRA fine-tune of Qwen2.5-32B-Instruct specialized for one
              job: turning a plain-English request into a schema-valid <code>FormSpecification</code>, and applying
              natural-language edits to an existing spec.
            </p>
            <div className="docs-cards" data-reveal>
              <div className="docs-card">
                <b>Base &amp; method</b>
                <span>Qwen2.5-32B-Instruct base · LoRA (rank 16), supervised fine-tuning</span>
              </div>
              <div className="docs-card">
                <b>Training set</b>
                <span>1,810 examples, each checked schema-valid · 3 epochs</span>
              </div>
              <div className="docs-card">
                <b>Result</b>
                <span>Converged cleanly: eval loss 0.011 → 0.0038</span>
              </div>
            </div>
            <p data-reveal>
              Every training label was produced against the demo application's synthetic fixture metadata and kept only
              when the deterministic validator reported no blocking errors, so the labels are schema-valid for that fixture.
            </p>
            <blockquote className="docs-quote" data-reveal>
              v1 is a pipeline-validation checkpoint. It was trained on a synthetic, template-derived corpus from a single
              demo application, so the low loss reflects the regularity of that data, not a measure of real-world quality,
              which has not yet been evaluated.
            </blockquote>
            <p data-reveal>
              Until v1 is measured against real specs and shown to beat a stock model with retrieval grounding, EPM Wizard
              defaults to a stock model grounded in your own metadata. The full training run, hyperparameters, and
              limitations live in <code>docs/MODEL_CARD.md</code>.
            </p>
          </section>

          {/* ---- next steps ---- */}
          <section id="next" className="docs-section">
            <h2 data-reveal>Next steps</h2>
            <div className="docs-next" data-reveal>
              <div className="docs-next-intro">
                <p className="docs-next-kicker">Choose a starting point</p>
                <h3>Start in the workspace, or add the browser agent.</h3>
                <p>Both paths work independently, so you can begin with the one you need today.</p>
              </div>
              <div className="docs-next-grid">
                <a className="docs-next-option" href={APP_ENTRY}>
                  <span className="docs-next-option-top">
                    <span className="docs-next-option-number">01</span>
                    <span className="docs-next-option-meta">Web workspace</span>
                  </span>
                  <strong>Open EPM Wizard</strong>
                  <small>Continue with Google, then use Demo Mode or connect your Oracle environment.</small>
                  <span className="docs-next-option-arrow" aria-hidden="true">→</span>
                </a>
                <a
                  className="docs-next-option"
                  href={__EXTENSION_ZIP_URL__}
                  download={__EXTENSION_ZIP_NAME__}
                >
                  <span className="docs-next-option-top">
                    <span className="docs-next-option-number">02</span>
                    <span className="docs-next-option-meta">Chrome extension</span>
                  </span>
                  <strong>Download the browser agent</strong>
                  <small>Unzip the Manifest V3 build and load its folder from Chrome extensions.</small>
                  <span className="docs-next-option-arrow" aria-hidden="true">↓</span>
                </a>
              </div>
              <p className="docs-next-back">
                Need the overview first? <Link to="/">Return to the landing page</Link>.
              </p>
            </div>
          </section>
        </main>
      </div>

      <footer className="docs-footer">
        <p className="docs-disclaimer">
          EPM Wizard is an independent implementation tool. IBM, Oracle, and their respective product names are
          trademarks of their respective owners. EPM Wizard is not made, endorsed, or sponsored by IBM or Oracle.
        </p>
      </footer>
    </div>
  );
}
