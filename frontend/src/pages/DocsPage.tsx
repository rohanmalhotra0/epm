import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import "../styles/docs.css";
import { useScrollReveal } from "../hooks/useScrollReveal";
import { TrustBoundaryDiagram } from "./marketingDiagrams";

/**
 * Public product documentation — served at /docs WITHOUT the Google auth gate
 * (see main.tsx's public router and deploy/fly/auth.fly.toml). It shares the
 * landing page's Carbon shell so the two read as one product: same dark
 * surfaces, hairline borders, IBM Plex, sharp corners. Static content — no
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
  { id: "approval", label: "The approval model" },
  { id: "security", label: "Security & trust" },
  { id: "artifacts", label: "Artifacts & reproducibility" },
  { id: "reference", label: "Reference" },
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

/** A code / command block; keys are lightly accented via the `.k` class. */
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
  // preferences — it is a navigation aid, not an animation.
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
            <span className="docs-brand-docs">Docs</span>
          </Link>
          <div className="docs-nav-right">
            <Link className="docs-nav-link" to="/">
              ← Back to site
            </Link>
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
              EPM Wizard turns plain-language intent into structured specifications, validates them with deterministic
              code against your live Oracle Planning tenant, and ships byte-reproducible artifacts — while your data and
              credentials stay on your machine. This page covers what it is, how to get started, and the guarantees it
              makes.
            </p>
          </div>

          {/* ---- overview ---- */}
          <section id="overview" className="docs-section">
            <h2 data-reveal>Overview</h2>
            <p data-reveal>
              EPM Wizard is a local-first copilot for Enterprise Performance Management (Oracle Hyperion Planning)
              implementation work. You describe a change in the chat; a language model interprets your intent and
              proposes a typed specification; and deterministic, typed code does everything that has to be correct and
              reproducible — validation, exact member resolution, safe artifact generation, deployment, and verification.
            </p>
            <p data-reveal>The design rests on one rule:</p>
            <blockquote className="docs-quote" data-reveal>
              The language model never owns the artifact. It proposes; deterministic code validates and ships.
            </blockquote>
            <div className="docs-cards" data-reveal>
              <div className="docs-card">
                <b>Local-first</b>
                <span>Projects, contexts, artifacts, and history live in one data directory on your machine.</span>
              </div>
              <div className="docs-card">
                <b>Grounded</b>
                <span>Answers and drafts are grounded in your own application metadata, not generic training data.</span>
              </div>
              <div className="docs-card">
                <b>Approval-gated</b>
                <span>Every modifying operation stops at an approval card. Nothing deploys on its own.</span>
              </div>
            </div>
          </section>

          {/* ---- quickstart ---- */}
          <section id="quickstart" className="docs-section">
            <h2 data-reveal>Quickstart</h2>
            <ol className="docs-steps">
              <li data-reveal>
                <b>Sign in.</b> Access is gated by Google sign-in. Approved accounts land directly in the app; others are
                returned to the landing page.
              </li>
              <li data-reveal>
                <b>Try Demo Mode.</b> The app is usable the moment it opens: a deterministic local provider plus a fixture
                Planning application. No API key, no tenant, nothing external contacted. Ask the chat for orientation:
                <Code>
                  <span className="k">/help</span>
                </Code>
              </li>
              <li data-reveal>
                <b>Add an AI provider.</b> Open <em>Settings → AI Providers</em> to connect Anthropic, any
                OpenAI-compatible endpoint (OpenAI, OpenRouter, Together AI, Ollama), or Gemini. Keys are held in an
                encrypted local store.
              </li>
              <li data-reveal>
                <b>Connect a tenant.</b> Open <em>Settings → Oracle Environments</em> and click <em>Connect</em>. Authenticate
                with a password or OAuth 2.0 client credentials; a harmless read-only call verifies the connection.
              </li>
              <li data-reveal>
                <b>Teach it your application.</b> Build a context — the local knowledge of your cubes, dimensions, members,
                forms, and rules — from the chat or the Contexts tab, and optionally merge an LCM Artifact Snapshot for
                full rule bodies and hierarchies:
                <Code>
                  <span className="k">/context</span>
                  {"\n"}
                  <span className="k">/context merge snapshot</span>
                </Code>
              </li>
            </ol>
          </section>

          {/* ---- approval model ---- */}
          <section id="approval" className="docs-section">
            <h2 data-reveal>The approval model</h2>
            <p data-reveal>
              Every change moves through the same five stages. The language model only reaches the first; everything after
              is deterministic code, and stage three is a hard stop that waits for you.
            </p>
            <ol className="docs-loop" data-reveal>
              <li>
                <span>01</span>
                <b>Propose</b>
                <em>plain language → typed spec</em>
              </li>
              <li>
                <span>02</span>
                <b>Validate</b>
                <em>against live tenant metadata</em>
              </li>
              <li className="gate">
                <span>03</span>
                <b>Approve</b>
                <em>you, explicitly — it stops here</em>
              </li>
              <li>
                <span>04</span>
                <b>Deploy</b>
                <em>byte-reproducible artifact</em>
              </li>
              <li>
                <span>05</span>
                <b>Verify</b>
                <em>read back · marked verified</em>
              </li>
            </ol>
            <p data-reveal>
              Operations are classified <code>readOnly</code>, <code>execution</code>, <code>modifying</code>, and{" "}
              <code>destructive</code>. Modifying and destructive operations are refused at the connector boundary unless
              approval happened upstream. Production environments are deliberately slower: they carry a persistent badge,
              and deploying there additionally requires typing a confirmation phrase such as{" "}
              <code>confirm deploy FormName</code>, plus passing validation.
            </p>
          </section>

          {/* ---- security ---- */}
          <section id="security" className="docs-section">
            <h2 data-reveal>Security &amp; trust boundaries</h2>
            <p data-reveal>
              Everything that touches a secret stays on your machine. Only deterministic code crosses the connector
              boundary to your tenant — carrying metadata and artifacts, never credentials, and never the model itself.
            </p>
            <figure className="docs-fig" data-reveal>
              <TrustBoundaryDiagram />
              <figcaption>
                The trust boundary. The model proposes inside your machine; only typed, allowlisted code reaches Oracle.
              </figcaption>
            </figure>
            <ul className="docs-list">
              <li data-reveal>
                <b>Secrets never reach the model.</b> API keys and passwords live in a Fernet-encrypted local secret store
                and are scrubbed from logs, tool results, errors, and diagnostics by a centralized redactor.
              </li>
              <li data-reveal>
                <b>No shell, ever.</b> Executable actions are typed, allowlisted functions. External commands run as
                argument arrays with strict validation — no path traversal, no shell metacharacters — plus timeouts.
              </li>
              <li data-reveal>
                <b>Your data stays local.</b> Projects, conversations, contexts, artifacts, and deployment history live in
                one local data directory (SQLite + the encrypted secret store), not a hosted service.
              </li>
            </ul>
          </section>

          {/* ---- artifacts ---- */}
          <section id="artifacts" className="docs-section">
            <h2 data-reveal>Artifacts &amp; reproducibility</h2>
            <p data-reveal>
              Forms, rules, and reports are generated as first-class artifacts from a validated specification. The package
              that ships is deterministic and byte-for-byte reproducible, with a SHA-256 checksum — not whatever the model
              last said. The same spec always produces the same bytes.
            </p>
            <Code>
              <span className="dim">$</span> epmw build --artifact RevenueForm{"\n"}
              <span className="dim"> packaging FormSpecification … ok</span>
              {"\n"}
              <span className="dim"> normalizing member order … ok</span>
              {"\n"}
              <span className="dim"> writing form.xml (deterministic) … ok</span>
              {"\n"}
              <span className="k">sha256</span> 9f2a4c7e…d1 RevenueForm.zip{"\n"}
              <span className="ok">✓ identical across 3 runs · byte-for-byte reproducible</span>
            </Code>
            <p data-reveal>
              Context versions are immutable and append-only, so any two can be diffed. Reports export any version as Word,
              PDF, or Markdown; <code>/context export</code> produces a portable <code>.epwcontext</code> zip — manifest,
              checksums, no secrets — that a teammate can import, and the Data tab exports the whole project as a zip for
              backup or moving machines.
            </p>
          </section>

          {/* ---- reference ---- */}
          <section id="reference" className="docs-section">
            <h2 data-reveal>Reference</h2>
            <p data-reveal>Common slash commands autocomplete in the composer:</p>
            <div className="docs-ref" data-reveal>
              <div className="docs-ref-row">
                <code>/help</code>
                <span>Show what the assistant can do and how to ask for it.</span>
              </div>
              <div className="docs-ref-row">
                <code>/context</code>
                <span>Build or refresh the local knowledge of your application.</span>
              </div>
              <div className="docs-ref-row">
                <code>/context merge snapshot</code>
                <span>Layer an LCM Artifact Snapshot onto the live context.</span>
              </div>
              <div className="docs-ref-row">
                <code>/context export</code>
                <span>Produce a portable <code>.epwcontext</code> package (no secrets).</span>
              </div>
              <div className="docs-ref-row">
                <code>/run-rule NAME</code>
                <span>Run an existing business rule; runtime prompts render as a form.</span>
              </div>
              <div className="docs-ref-row">
                <code>Ctrl / Cmd + K</code>
                <span>Open the command palette to search conversations and artifacts.</span>
              </div>
            </div>
            <div className="docs-next" data-reveal>
              <h3>Ready to try it?</h3>
              <p>Sign in to open the app in Demo Mode — no key or tenant required to start.</p>
              <a className="docs-signin" href={APP_ENTRY}>
                <GoogleGlyph />
                <span>Sign in with Google</span>
              </a>
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
