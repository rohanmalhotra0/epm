import { Fragment, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import "../styles/landing.css";
import { useScrollReveal, usePrefersReducedMotion } from "../hooks/useScrollReveal";
import { TrustBoundaryDiagram, BrowserAgentDiagram } from "./marketingDiagrams";

/**
 * Public marketing / landing page — served without the Google auth gate at "/"
 * (see main.tsx). The primary CTA links to "/app", which oauth2-proxy intercepts
 * and sends through Google, returning to /app once signed in.
 *
 * The product has TWO surfaces and the page leads with both:
 *   1. A ChatGPT-style chat workspace for Oracle EPM — you ask in plain language
 *      and get back live, typed result blocks (form-preview grids, cube maps,
 *      validation, deployment plans), not walls of text.
 *   2. A Chrome extension — the Narrated Browser Agent — that drives Oracle EPM
 *      Cloud's real web UI for you, narrating each step, with an enforced gate
 *      that HOLDS destructive and production actions for your approval.
 *
 * Aesthetic: dark IBM Carbon industrial (flat surfaces, hairline borders, sharp
 * corners, IBM Plex, accent #4589ff sparingly, Carbon green #24a148 for
 * live/verified, red #fa4d56 for a held/denied action). All motion is plain CSS
 * + one IntersectionObserver hook; every mockup is legible at rest, so
 * prefers-reduced-motion loses choreography, never content. Faux UI is
 * illustrative and aria-hidden.
 */

const APP_ENTRY = "/app";

const v = (o: Record<string, string | number>): React.CSSProperties => o as unknown as React.CSSProperties;

/* ------------------------------------------------------------------ content */

// Section 01 — what a request renders back as.
const ANATOMY = [
  {
    asked: "“Create an Actuals form with level-zero descendants of Total Payroll in rows.”",
    rendered: "A form-preview grid you can read — accounts in rows, months in columns, validated against your outline before anything ships.",
  },
  {
    asked: "“Visualize OEP_DCSH”",
    rendered: "An interactive cube map — every dimension, its coverage and sizing — rendered inline in the conversation.",
  },
  {
    asked: "“Draft a rule that copies Working to Final”",
    rendered: "A script grounded on your real rules, with a visible “Grounded on” block — a proposal, never auto-run.",
  },
  {
    asked: "“Deploy it to TEST”",
    rendered: "An approval card. The model proposes; nothing changes on your tenant until you approve.",
  },
];

// Section 02 — the typed result blocks the chat renders.
const BLOCKS = [
  { no: "01", name: "Form preview", body: "A live EPM-style grid — POV, rows, columns, and a validation status you can read at a glance." },
  { no: "02", name: "Cube map", body: "An interactive view of a cube — its dimensions, coverage, and sizing — drawn inline." },
  { no: "03", name: "Validation report", body: "Member existence, axis rules, sizing, and security, checked against your real outline." },
  { no: "04", name: "Deployment plan", body: "The plan, its progress, and the result — marked verified only once confirmed." },
  { no: "05", name: "Grounded-on", body: "The real rule scripts and templates a draft was generated from — no hidden context." },
  { no: "06", name: "Diff", body: "Exactly what a refresh or snapshot merge changed, member by member." },
  { no: "07", name: "Runtime-prompt form", body: "A rule's runtime prompts, rendered as a small form to fill in and submit." },
  { no: "08", name: "Member search", body: "Resolve members exactly — identifier-first, with no fuzzy substitution." },
];

// Section 03 — the working loop, chat-native.
const LOOP = [
  { no: "01", name: "Propose", sub: "you ask in plain language" },
  { no: "02", name: "Validate", sub: "checked against your tenant" },
  { no: "03", name: "Approve", sub: "you, explicitly — it stops here", gate: true },
  { no: "04", name: "Deploy", sub: "the reviewed artifact ships" },
  { no: "05", name: "Verify", sub: "read back · marked verified" },
];

// Section 04 — browser-agent capabilities + narration.
const AGENT_CAPS: Array<[string, string]> = [
  ["Grounds on the page", "Accessibility-tree first — it targets real elements by ref id, not blind pixel coordinates."],
  ["Falls back to vision", "For canvas / JET data grids with no accessibility info: a screenshot and a vision model."],
  ["Narrates every step", "Numbered click / type / scroll / navigate actions stream into a side panel, with optional spoken narration."],
  ["Enforced safety gate", "Destructive targets and any write on a production tab are held for your approval. On by default."],
];

const NARRATION: Array<{ t: string; state: "ok" | "run"; text: string; ref?: string }> = [
  { t: "00:00:01", state: "ok", text: "Opened Forms library", ref: "ref=12" },
  { t: "00:00:03", state: "ok", text: "Selected “Actuals”", ref: "ref=42" },
  { t: "00:00:05", state: "run", text: "Typing period range Jan–Dec…" },
];

// Section 07 — honest, on-message telemetry.
const STATS = [
  { to: 0, suffix: "", label: "secrets sent to the model" },
  { to: 0, suffix: "", label: "destructive actions run without your approval" },
  { to: 8, suffix: "", label: "typed result blocks rendered in chat" },
  { to: 100, suffix: "%", label: "of actions are typed, allowlisted functions" },
];

// Section 08 — the model layer.
const MODEL_SPEC: Array<[string, string]> = [
  ["Providers", "Anthropic · any OpenAI-compatible endpoint · Gemini · local"],
  ["EPM Coder v1", "A LoRA fine-tune on a Qwen2.5-32B-Instruct base"],
  ["Specialized for", "Plain-English request → validated FormSpecification"],
  ["Training set", "1,810 examples, each checked schema-valid · 3 epochs"],
  ["Result", "Converged cleanly · eval loss 0.011 → 0.0038"],
];

type Tag = "policy" | "deny" | "local" | "verify";
const LEDGER: Array<{ t: string; tag: Tag; claim: string; how: string; gate?: boolean }> = [
  {
    t: "00:00:01",
    tag: "policy",
    gate: true,
    claim: "Nothing deploys without your explicit approval.",
    how: "Every modifying operation stops at an approval card in the chat. The model proposes; you approve.",
  },
  {
    t: "00:00:02",
    tag: "deny",
    claim: "The browser agent holds destructive & production actions.",
    how: "Deploy, delete, clear, run-rule, and any write on a production tab are held for approval in the side panel — read-only actions never pause.",
  },
  {
    t: "00:00:03",
    tag: "deny",
    claim: "Secrets never reach the model.",
    how: "Credentials live in an encrypted local store and are scrubbed from logs, tool results, and errors.",
  },
  {
    t: "00:00:04",
    tag: "deny",
    claim: "No shell, ever.",
    how: "Executable actions are typed, allowlisted functions — argument arrays with strict validation, never a shell string.",
  },
  {
    t: "00:00:05",
    tag: "local",
    claim: "Your data stays on your machine.",
    how: "Projects, contexts, artifacts, and history live in one local data directory — not a hosted service.",
  },
];

/* --------------------------------------------------------------- primitives */

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

function SignInButton({ variant }: { variant: "primary" | "nav" }) {
  return (
    <a className={variant === "primary" ? "lp-btn lp-btn-primary" : "lp-btn lp-btn-nav"} href={APP_ENTRY}>
      <GoogleGlyph />
      <span>Sign in with Google</span>
    </a>
  );
}

/** Count-up telemetry tile. Ramps 0 → `to` on first view; renders the final
 *  value immediately under reduced motion. */
function Stat({ to, suffix, label, reduce }: { to: number; suffix: string; label: string; reduce: boolean }) {
  const numRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = numRef.current;
    if (!el) return;
    const final = `${to}${suffix}`;
    if (reduce || typeof IntersectionObserver === "undefined" || typeof requestAnimationFrame === "undefined") {
      el.textContent = final;
      return;
    }
    el.textContent = `0${suffix}`;
    let raf = 0;
    const io = new IntersectionObserver(
      (entries, obs) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          obs.disconnect();
          const start = performance.now();
          const dur = 850;
          const step = (now: number) => {
            const p = Math.min(1, (now - start) / dur);
            const eased = 1 - Math.pow(1 - p, 3);
            el.textContent = `${Math.round(to * eased)}${suffix}`;
            raf = p < 1 ? requestAnimationFrame(step) : 0;
          };
          raf = requestAnimationFrame(step);
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [to, suffix, reduce]);

  return (
    <div className="lp-stat" data-reveal>
      <span className="lp-stat-num" ref={numRef}>
        {to}
        {suffix}
      </span>
      <span className="lp-stat-label">{label}</span>
    </div>
  );
}

/* --------------------------------------------------------------- hero chat */

/** A ChatGPT-style conversation that streams a real EPM request end-to-end and
 *  rests on an in-chat approval card — the product's core guarantee, shown as
 *  motion. Decorative → aria-hidden; a readable summary sits in .lp-sr-only, and
 *  the value proposition lives in the hero copy beside it. Streaming is a single
 *  CSS timeline keyed off `.running`; at rest the whole exchange is printed and
 *  resting on the approval card. */
function HeroChat({ replayKey, running }: { replayKey: number; running: boolean }) {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "…"];
  const accounts = ["Salaries", "Overtime", "Benefits", "Bonus"];
  return (
    <div className={`lp-term lp-chat${running ? " running" : ""}`} key={replayKey} aria-hidden="true">
      <div className="lp-chat-head">
        <span className="lp-chat-avatar">EW</span>
        <span className="lp-chat-name">EPM Wizard</span>
        <span className="lp-chat-status lp-term-status">
          <b data-st="local">THINKING</b>
          <b data-st="work">RENDERING</b>
          <b data-st="ok">AWAITING YOU</b>
        </span>
      </div>

      <div className="lp-chat-body">
        <div className="lp-msg user" data-anim style={v({ "--d": "0.2s" })}>
          <div className="lp-bubble">
            Create an Actuals form with level-zero descendants of Total Payroll in rows, Jan–Dec in columns.
          </div>
        </div>

        <div className="lp-msg bot">
          <span className="lp-chat-avatar sm">EW</span>
          <div className="lp-msg-col">
            <div className="lp-typing">
              <i />
              <i />
              <i />
            </div>
            <div className="lp-steps">
              <div className="lp-step" data-anim style={v({ "--d": "1.7s" })}>
                <span className="lp-tick">✓</span> Recognizing intent
              </div>
              <div className="lp-step" data-anim style={v({ "--d": "2.0s" })}>
                <span className="lp-tick">✓</span> Retrieving context
              </div>
              <div className="lp-step" data-anim style={v({ "--d": "2.3s" })}>
                <span className="lp-tick">✓</span> Validating against tenant
              </div>
            </div>
            <div className="lp-say" data-anim style={v({ "--d": "2.8s" })}>
              Here&rsquo;s the form — 24 accounts × 12 months.
              <span className="lp-cursor" />
            </div>

            {/* inline form-preview block */}
            <div className="lp-fp" data-anim style={v({ "--d": "3.3s" })}>
              <div className="lp-fp-head">
                <span className="lp-fp-title">Form preview — 25-01 Actuals</span>
                <span className="lp-fp-valid">● valid</span>
                <span className="lp-fp-cube">OEP_FS</span>
              </div>
              <div className="lp-fp-sub">Vision · Forms / Payroll</div>
              <div className="lp-fp-chips">
                <span>Rows · Account: Lvl-0 of Total Payroll (24)</span>
                <span>Columns · Period: Jan–Dec</span>
                <span>POV · Entity: Total Entity</span>
              </div>
              <div className="lp-fp-grid" style={v({ "--cols": months.length })}>
                <span className="lp-fp-cell hdr rowh" />
                {months.map((m) => (
                  <span className="lp-fp-cell hdr" key={m}>
                    {m}
                  </span>
                ))}
                {accounts.map((a) => (
                  <Fragment key={a}>
                    <span className="lp-fp-cell rowh">{a}</span>
                    {months.map((m) => (
                      <span className="lp-fp-cell" key={`${a}-${m}`}>
                        —
                      </span>
                    ))}
                  </Fragment>
                ))}
              </div>
              <div className="lp-fp-foot">~288 cells · 24 rows × 12 months</div>
            </div>

            {/* inline approval block */}
            <div className="lp-gate" data-anim style={v({ "--d": "4.3s" })}>
              <div className="lp-gate-head">
                <span className="lp-gate-badge">APPROVAL REQUIRED</span>
                <span className="lp-gate-meta">deploy · TEST</span>
              </div>
              <div className="lp-gate-q">Deploy 25-01 Actuals to Vision (TEST)?</div>
              <div className="lp-gate-actions">
                <span className="lp-gate-btn primary">Approve &amp; deploy</span>
                <span className="lp-gate-btn">Preview package</span>
                <span className="lp-cursor" />
              </div>
              <div className="lp-gate-foot">nothing deploys until you say so</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------- browser-agent side panel */

function AgentPanel() {
  return (
    <div className="lp-panel" aria-hidden="true">
      <div className="lp-panel-head">
        <span className="lp-panel-dot" />
        <span className="lp-panel-name">Narrated Browser Agent</span>
        <span className="lp-panel-ctrls">
          <i>▶</i>
          <i>❚❚</i>
          <i>■</i>
        </span>
      </div>
      <div className="lp-panel-goal">Goal · Open the Actuals form and set Scenario to Forecast</div>
      <div className="lp-panel-feed">
        {NARRATION.map((n) => (
          <div className={`lp-narr${n.state === "run" ? " run" : ""}`} key={n.t}>
            <span className="lp-narr-t">{n.t}</span>
            <span className="lp-narr-mark">{n.state === "run" ? "●" : "✓"}</span>
            <span className="lp-narr-text">
              {n.text}
              {n.ref ? <span className="lp-narr-ref"> {n.ref}</span> : null}
            </span>
          </div>
        ))}
        <div className="lp-held">
          <div className="lp-held-head">
            <span className="lp-held-badge">HELD FOR APPROVAL</span>
            <span className="lp-held-env">PROD</span>
          </div>
          <div className="lp-held-detail">target: “Deploy” · context: production tenant (planning-prod…)</div>
          <div className="lp-held-actions">
            <span className="lp-gate-btn warn">Approve action</span>
            <span className="lp-gate-btn">Skip</span>
          </div>
        </div>
      </div>
      <div className="lp-panel-foot">accessibility-tree grounding · screenshot fallback · 3 steps</div>
    </div>
  );
}

/* -------------------------------------------------------------------- page */

export function LandingPage() {
  const rootRef = useScrollReveal<HTMLDivElement>();
  const reduce = usePrefersReducedMotion();
  const [replayKey, setReplayKey] = useState(0);

  // Left scroll-progress rail (wide screens, motion only).
  useEffect(() => {
    if (reduce) return;
    const root = rootRef.current;
    if (!root || typeof requestAnimationFrame === "undefined") return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const p = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
      root.style.setProperty("--sp", p.toFixed(4));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [reduce, rootRef]);

  return (
    <div className="lp" ref={rootRef}>
      <div className="lp-rail" aria-hidden="true">
        <span className="lp-rail-fill" />
      </div>

      {/* ---------------------------------------------------------- top nav */}
      <header className="lp-nav">
        <div className="lp-nav-inner">
          <Link className="lp-brand" to="/">
            <img src="/favicon.svg" alt="" width={26} height={26} />
            <span>EPM&nbsp;Wizard</span>
          </Link>
          <nav className="lp-nav-links">
            <a href="#chat">Chat</a>
            <a href="#agent">Browser Agent</a>
            <a href="#security">Security</a>
            <Link to="/docs">Docs</Link>
          </nav>
          <SignInButton variant="nav" />
        </div>
      </header>

      <main>
        {/* -------------------------------------------------------- hero */}
        <section className="lp-hero" id="chat">
          <div className="lp-hero-inner">
            <div className="lp-hero-copy">
              <p className="lp-eyebrow">
                <span className="lp-eyebrow-tick" />
                CHAT · BROWSER AGENT · ORACLE EPM
              </p>
              <h1 className="lp-title">
                Chat with your EPM app.
                <br />
                Or let it drive the screen.
                <br />
                You approve everything.
              </h1>
              <p className="lp-sub">
                A ChatGPT-style workspace for Oracle EPM (Hyperion Planning). Ask in plain language and get back live,
                typed result blocks — form-preview grids, cube maps, validation, deployment plans — not walls of text. A
                companion Chrome extension drives Oracle EPM Cloud&rsquo;s real UI for you and narrates each step, with an
                enforced gate that holds destructive and production actions for your approval.
              </p>
              <div className="lp-actions">
                <SignInButton variant="primary" />
                <Link className="lp-btn lp-btn-ghost" to="/docs">
                  Read the docs
                  <span className="lp-arrow" aria-hidden="true">
                    →
                  </span>
                </Link>
              </div>
              <p className="lp-fineprint">Try it in Demo Mode — no Oracle tenant, no API key.</p>
            </div>

            <div className="lp-hero-term-wrap">
              <HeroChat replayKey={replayKey} running={!reduce} />
              <p className="lp-sr-only">
                Example conversation: a user asks EPM Wizard to create an Actuals form with level-zero descendants of
                Total Payroll in rows and January to December in columns. The assistant recognizes the intent, retrieves
                context, validates against the tenant, and renders a form-preview grid, then presents an approval card to
                deploy to the test environment — nothing is deployed until the user approves.
              </p>
              {!reduce && (
                <button type="button" className="lp-replay" onClick={() => setReplayKey((k) => k + 1)}>
                  ↺ replay
                </button>
              )}
            </div>
          </div>
          <div className="lp-ruler" aria-hidden="true" />
        </section>

        {/* --------------------------------- what the chat renders (anatomy) */}
        <section className="lp-section lp-anatomy">
          <p className="lp-kicker" data-reveal>
            01 / the chat, and what it renders
          </p>
          <h2 className="lp-h2" data-reveal>
            You ask in plain language. It answers in interfaces.
          </h2>
          <div className="lp-anatomy-grid">
            {ANATOMY.map((row, i) => (
              <div className="lp-anatomy-row" data-reveal style={v({ "--i": i })} key={row.asked}>
                <div className="lp-anatomy-said">
                  <span className="lp-anatomy-label">you asked</span>
                  <code>{row.asked}</code>
                </div>
                <div className="lp-anatomy-ran">
                  <span className="lp-anatomy-label">the chat rendered</span>
                  <p>{row.rendered}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ------------------------------------------ inline blocks gallery */}
        <section className="lp-section lp-blocks-section">
          <p className="lp-kicker" data-reveal>
            02 / inline result blocks
          </p>
          <h2 className="lp-h2" data-reveal>
            Typed, interactive results — not walls of text
          </h2>
          <div className="lp-blocks">
            {BLOCKS.map((b, i) => (
              <div className="lp-block" data-reveal style={v({ "--i": i % 4 })} key={b.no}>
                <span className="lp-block-no">{b.no}</span>
                <h3>{b.name}</h3>
                <p>{b.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ------------------------------------------ the loop, 5 stages */}
        <section className="lp-section lp-loop">
          <p className="lp-kicker" data-reveal>
            03 / the working loop
          </p>
          <h2 className="lp-h2" data-reveal>
            From a sentence to a verified change
          </h2>
          <ol className="lp-loop-row" data-reveal>
            {LOOP.map((s, i) => (
              <li className={`lp-stage${s.gate ? " gate" : ""}`} style={v({ "--i": i })} key={s.no}>
                <span className="lp-stage-no">{s.no}</span>
                <span className="lp-stage-name">{s.name}</span>
                <span className="lp-stage-sub">{s.sub}</span>
              </li>
            ))}
          </ol>
          <p className="lp-loop-note" data-reveal>
            The model proposes; deterministic, tested code disposes. Stage three is a hard stop that waits for you — in
            the chat, and again in the browser agent.
          </p>
        </section>

        {/* ------------------------------------------ narrated browser agent */}
        <section className="lp-section lp-agent" id="agent">
          <p className="lp-kicker" data-reveal>
            04 / the narrated browser agent
          </p>
          <h2 className="lp-h2" data-reveal>
            It can take the wheel — and narrate every move.
          </h2>
          <div className="lp-agent-grid">
            <div className="lp-agent-copy">
              <p className="lp-lede" data-reveal>
                Install the Chrome extension and EPM Wizard drives Oracle EPM Cloud&rsquo;s actual web UI for you. It reads
                the page&rsquo;s accessibility tree to target real elements, narrates each step in a side panel, and stops
                at an enforced safety gate before anything destructive or production-facing runs.
              </p>
              <dl className="lp-spec-sheet" data-reveal>
                {AGENT_CAPS.map(([k, val], i) => (
                  <div className="lp-spec-row" style={v({ "--i": i })} key={k}>
                    <dt>{k}</dt>
                    <dd>{val}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="lp-agent-panel-wrap" data-reveal>
              <AgentPanel />
              <p className="lp-sr-only">
                Illustrative side panel: the agent opens the Forms library, selects Actuals, begins typing a period range,
                then holds a “Deploy” action on a production tenant for your approval before it runs.
              </p>
            </div>
          </div>
          <figure className="lp-arch-fig" data-reveal>
            <BrowserAgentDiagram />
          </figure>
          <p className="lp-fineprint lp-agent-honest" data-reveal>
            The browser agent is a real, loadable extension. Oracle-specific UI hardening is still in progress and it has
            not been validated against a live tenant — keep the safety gate on and supervise it.
          </p>
        </section>

        {/* ------------------------------------ architecture / trust boundary */}
        <section id="security" className="lp-section lp-arch">
          <p className="lp-kicker" data-reveal>
            05 / security
          </p>
          <h2 className="lp-h2" data-reveal>
            Where does my password go? It stops here.
          </h2>
          <p className="lp-lede" data-reveal>
            Local-first by design: your projects and history stay on your machine, and everything that touches a secret
            stays there too. Only deterministic code crosses the connector boundary to your tenant — carrying metadata
            and artifacts, never credentials, and never the model. The browser agent runs in your browser, under your own
            signed-in session.
          </p>
          <figure className="lp-arch-fig" data-reveal>
            <TrustBoundaryDiagram />
          </figure>
        </section>

        {/* --------------------------------------- guardrails audit ledger */}
        <section className="lp-section lp-ledger-section">
          <p className="lp-kicker" data-reveal>
            06 / guardrails
          </p>
          <h2 className="lp-h2" data-reveal>
            What is guaranteed, and by what
          </h2>
          <div className="lp-ledger">
            {LEDGER.map((r, i) => (
              <div className={`lp-log${r.gate ? " gate" : ""}`} data-reveal style={v({ "--i": i })} key={r.claim}>
                <span className="lp-log-t">{r.t}</span>
                <span className={`lp-log-tag tag-${r.tag}`}>{r.tag.toUpperCase()}</span>
                <div className="lp-log-text">
                  <b>{r.claim}</b>
                  <span>{r.how}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* --------------------------------------------- telemetry band */}
        <section className="lp-section lp-stats-section">
          <p className="lp-kicker" data-reveal>
            07 / telemetry
          </p>
          <h2 className="lp-sr-only">Telemetry</h2>
          <div className="lp-stats">
            {STATS.map((s) => (
              <Stat key={s.label} to={s.to} suffix={s.suffix} label={s.label} reduce={reduce} />
            ))}
          </div>
        </section>

        {/* ------------------------------------------------ the model */}
        <section className="lp-section lp-model-section">
          <p className="lp-kicker" data-reveal>
            08 / the model layer
          </p>
          <h2 className="lp-h2" data-reveal>
            Bring your own model — or run ours
          </h2>
          <p className="lp-lede" data-reveal>
            EPM Wizard is model-agnostic: connect Anthropic, any OpenAI-compatible endpoint, or Gemini, and the assistant
            reasons over your own metadata. It also ships a specialist fine-tune — EPM Coder — trained to turn
            plain-English requests into validated form specifications.
          </p>
          <dl className="lp-spec-sheet">
            {MODEL_SPEC.map(([k, val], i) => (
              <div className="lp-spec-row" data-reveal style={v({ "--i": i })} key={k}>
                <dt>{k}</dt>
                <dd>{val}</dd>
              </div>
            ))}
          </dl>
          <p className="lp-model-note" data-reveal>
            EPM Coder v1 is a pipeline-validation checkpoint trained on a synthetic corpus — proof the training loop works
            end-to-end, not a production-quality benchmark. Until it&rsquo;s measured on real tenants, the assistant
            defaults to a stock model grounded in your own metadata.
          </p>
        </section>

        {/* ------------------------------------------------ get started */}
        <section className="lp-section lp-cta">
          <div className="lp-cta-card" data-reveal>
            <h2>Start in Demo Mode — no key, no tenant.</h2>
            <p>
              Sign in and EPM Wizard opens on a fixture Planning application with a deterministic local provider — nothing
              external is contacted. Bring your own model and tenant when you&rsquo;re ready.
            </p>
            <div className="lp-actions">
              <SignInButton variant="primary" />
              <Link className="lp-btn lp-btn-ghost" to="/docs">
                Read the docs
                <span className="lp-arrow" aria-hidden="true">
                  →
                </span>
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* ----------------------------------------------------------- footer */}
      <footer className="lp-footer">
        <div className="lp-ruler" aria-hidden="true" />
        <div className="lp-footer-inner">
          <Link className="lp-brand" to="/">
            <img src="/favicon.svg" alt="" width={22} height={22} />
            <span>EPM&nbsp;Wizard</span>
          </Link>
          <p className="lp-disclaimer">
            EPM Wizard is an independent implementation tool. IBM, Oracle, and their respective product names are
            trademarks of their respective owners. EPM Wizard is not made, endorsed, or sponsored by IBM or Oracle.
          </p>
        </div>
      </footer>
    </div>
  );
}
