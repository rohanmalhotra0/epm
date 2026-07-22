import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import "../styles/landing.css";
import { useScrollReveal, usePrefersReducedMotion } from "../hooks/useScrollReveal";
import { TrustBoundaryDiagram } from "./marketingDiagrams";

/**
 * Public marketing / landing page — the ONLY page (besides /docs) served
 * without the Google auth gate. main.tsx renders it at "/" when the path is not
 * under /app. The primary CTA links to "/app", which oauth2-proxy (the
 * epmw-auth front door) intercepts: an unauthenticated visitor is bounced to
 * Google and returned to /app once signed in. In local dev (no gate) the link
 * simply loads the app.
 *
 * Design language — "a running instrument, not a stack of marketing blocks":
 * dark IBM Carbon industrial (flat #161616/#1c1c1c surfaces, hairline borders,
 * sharp corners, IBM Plex Sans + Mono, accent #4589ff used at most once per
 * viewport, Carbon green #24a148 reserved for live/verified). The hero streams
 * one real EPM change end-to-end and deliberately STOPS at the approval gate —
 * the product's core guarantee ("nothing deploys without you") shown as motion.
 *
 * All motion is plain CSS (transform/opacity/stroke only) plus one tiny
 * IntersectionObserver hook. Everything is fully legible at rest, so
 * prefers-reduced-motion (see landing.css) loses choreography, never content.
 */

// Where the "Sign in with Google" CTA sends the visitor. oauth2-proxy protects
// everything under /app and redirects to Google, returning here afterwards. It
// must be a real navigation (plain <a>), not an in-app <Link>, so it hits the
// gate rather than the public router.
const APP_ENTRY = "/app";

// Cast helper for inline CSS custom properties (--d, --i, --w …), which
// React.CSSProperties does not type.
const v = (o: Record<string, string | number>): React.CSSProperties => o as unknown as React.CSSProperties;

/* ------------------------------------------------------------------ content */

const FEATURES = [
  {
    no: "01",
    title: "An AI copilot for EPM",
    body: "Ask questions, draft forms and rules, and reason over your Planning application in plain language — grounded in your own metadata, not generic training data.",
  },
  {
    no: "02",
    title: "A live Oracle EPM connection",
    body: "Connect a Planning tenant with a password or OAuth 2.0 client credentials. Every call crosses one audited connector boundary; secrets stay in an encrypted local store.",
  },
  {
    no: "03",
    title: "Forms, rules & reports as artifacts",
    body: "Generate and edit data forms, rule specifications, and snapshot summaries as first-class, byte-reproducible artifacts alongside the conversation.",
  },
];

const LOOP = [
  { no: "01", name: "Propose", sub: "plain language → typed spec" },
  { no: "02", name: "Validate", sub: "against live tenant metadata" },
  { no: "03", name: "Approve", sub: "you, explicitly — it stops here", gate: true },
  { no: "04", name: "Deploy", sub: "byte-reproducible artifact" },
  { no: "05", name: "Verify", sub: "read back · marked verified" },
];

const STATS = [
  { to: 0, suffix: "", label: "secrets ever sent to the model" },
  { to: 0, suffix: "", label: "deploys without your approval" },
  { to: 100, suffix: "%", label: "byte-reproducible artifacts" },
  { to: 5, suffix: "", label: "validation gates per change" },
];

// The model story (see docs/MODEL_CARD.md). EPM Wizard is model-agnostic AND
// ships a specialist fine-tune, so lead with providers and present the fine-tune
// as one option. Deliberately NOT a quality benchmark — the corpus is synthetic
// and template-derived, so we state run facts ("converged"), never accuracy, and
// carry the honest caveat below. No training cost/runtime on a public page.
const MODEL_SPEC: Array<[string, string]> = [
  ["Providers", "Anthropic · any OpenAI-compatible endpoint · Gemini"],
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
    how: "Every modifying operation stops at an approval card. The model proposes; you approve.",
  },
  {
    t: "00:00:02",
    tag: "deny",
    claim: "Secrets never reach the model.",
    how: "Credentials live in a Fernet-encrypted local store and are scrubbed from logs, tool results, and errors.",
  },
  {
    t: "00:00:03",
    tag: "deny",
    claim: "No shell, ever.",
    how: "Executable actions are typed, allowlisted functions — argument arrays with strict validation, never a shell string.",
  },
  {
    t: "00:00:04",
    tag: "local",
    claim: "Your data stays on your machine.",
    how: "Projects, contexts, artifacts, and history live in one local data directory — not a hosted service.",
  },
  {
    t: "00:00:05",
    tag: "verify",
    claim: "Production is deliberately slow.",
    how: "PROD environments carry a badge; deploying requires a typed confirmation phrase plus passing validation.",
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

/** A single count-up telemetry tile. Ramps 0 → `to` (easeOutCubic) the first
 *  time it scrolls into view; renders the final value immediately when motion
 *  is reduced or IntersectionObserver is missing. Tabular figures + a reserved
 *  width keep it from reflowing as digits change. */
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

/* ------------------------------------------------------------- hero terminal */

/** The scripted, self-running session. Delays (in seconds) form a single CSS
 *  timeline keyed off the `.running` class; at rest every line is printed and
 *  the sequence rests on the approval gate. Decorative → aria-hidden; the real
 *  value proposition lives in the readable hero copy beside it. */
function HeroTerminal({ replayKey, running }: { replayKey: number; running: boolean }) {
  const spec: Array<[string, string]> = [
    ["form", "Revenue"],
    ["driver", "Working_Days"],
    ["cube", "OEP_FS"],
    ["scope", "FY26 · Forecast"],
  ];
  const checks = [
    'dimension "Account" exists',
    "member path resolved · no fuzzy match",
    "no direct write · artifact only",
    "reproducible · sha256:9f2a…d1",
  ];
  return (
    <div className={`lp-term${running ? " running" : ""}`} key={replayKey} aria-hidden="true">
      <div className="lp-term-bar">
        <span className="lp-term-dots">
          <i />
          <i />
          <i />
        </span>
        <span className="lp-term-tab">session · epm-wizard</span>
        <span className="lp-term-status">
          <b data-st="local">LOCAL</b>
          <b data-st="work">WORKING</b>
          <b data-st="ok">AWAITING&nbsp;YOU</b>
        </span>
      </div>
      <div className="lp-term-body">
        <div className="lp-tline lp-cmd" style={v({ "--d": "0.15s" })}>
          <span className="lp-prompt">$</span>
          <span className="lp-type" style={v({ "--w": "46ch" })}>
            add a Working Days driver to the Revenue form
          </span>
        </div>

        <div className="lp-tline lp-note" style={v({ "--d": "1.45s" })}>
          <span className="lp-c">//</span> proposing spec
        </div>
        {spec.map(([k, val], i) => (
          <div className="lp-tline lp-spec" key={k} style={v({ "--d": `${1.7 + i * 0.12}s` })}>
            <span className="lp-k">{k}</span>
            <span className="lp-v">{val}</span>
          </div>
        ))}

        <div className="lp-tline lp-note" style={v({ "--d": "2.5s" })}>
          <span className="lp-c">//</span> validating against tenant
        </div>
        <div className="lp-tline" style={v({ "--d": "2.7s" })}>
          <span className="lp-scan" />
        </div>
        {checks.map((c, i) => (
          <div className="lp-tline lp-check" key={c} style={v({ "--d": `${3.7 + i * 0.2}s` })}>
            <span className="lp-tick">✓</span>
            <span>{c}</span>
          </div>
        ))}

        <div className="lp-tline lp-gate" style={v({ "--d": "4.7s" })}>
          <div className="lp-gate-head">
            <span className="lp-gate-badge">APPROVAL REQUIRED</span>
            <span className="lp-gate-meta">1 modifying op</span>
          </div>
          <div className="lp-gate-actions">
            <span className="lp-gate-btn primary">Approve</span>
            <span className="lp-gate-btn">Diff</span>
            <span className="lp-cursor" />
          </div>
          <div className="lp-gate-foot">nothing deploys until you say so</div>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- page */

export function LandingPage() {
  const rootRef = useScrollReveal<HTMLDivElement>();
  const reduce = usePrefersReducedMotion();
  const [replayKey, setReplayKey] = useState(0);

  // Left scroll-progress rail (wide screens only). Only wired when motion is
  // welcome; otherwise the rail is hidden (see landing.css) and we never touch
  // scroll. rAF-throttled, writes a single 0..1 custom property.
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
            <a href="#product">Product</a>
            <a href="#security">Security</a>
            <Link to="/docs">Docs</Link>
          </nav>
          <SignInButton variant="nav" />
        </div>
      </header>

      <main>
        {/* -------------------------------------------------------- hero */}
        <section className="lp-hero">
          <div className="lp-hero-inner">
            <div className="lp-hero-copy">
              <p className="lp-eyebrow">
                <span className="lp-eyebrow-tick" />
                LOCAL-FIRST · ORACLE EPM · §000
              </p>
              <h1 className="lp-title">
                Describe the change.
                <br />
                Watch it validate.
                <br />
                Ship the artifact.
              </h1>
              <p className="lp-sub">
                An AI workspace for Oracle EPM implementation. Plain-language intent becomes a structured spec, checked by
                deterministic code against your live tenant — local-first, secrets never leave your machine, and nothing
                deploys without your approval.
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
              <p className="lp-fineprint">Secrets never reach the model. Your data never leaves your machine.</p>
            </div>

            <div className="lp-hero-term-wrap">
              <HeroTerminal replayKey={replayKey} running={!reduce} />
              {!reduce && (
                <button type="button" className="lp-replay" onClick={() => setReplayKey((k) => k + 1)}>
                  ↺ replay
                </button>
              )}
            </div>
          </div>
          <div className="lp-ruler" aria-hidden="true" />
        </section>

        {/* ---------------------------------------- anatomy of a change */}
        <section id="product" className="lp-section lp-anatomy">
          <p className="lp-kicker" data-reveal>
            01 / anatomy of a change
          </p>
          <h2 className="lp-h2" data-reveal>
            What you just watched, mapped to what actually ran
          </h2>
          <div className="lp-anatomy-grid">
            {[
              {
                said: "“add a Working Days driver to the Revenue form”",
                ran: "The model interprets intent and proposes a typed FormSpecification — it never writes the artifact itself.",
              },
              {
                said: "validating against tenant",
                ran: "Deterministic code resolves every member exactly against your live metadata. No fuzzy substitution, no guesses.",
              },
              {
                said: "APPROVAL REQUIRED",
                ran: "Modifying operations are refused at the connector boundary unless you approve upstream. The pause is the point.",
              },
              {
                said: "sha256:9f2a…d1",
                ran: "The package that ships is byte-for-byte reproducible with a SHA-256 checksum — not whatever the model last said.",
              },
            ].map((row, i) => (
              <div className="lp-anatomy-row" data-reveal style={v({ "--i": i })} key={row.said}>
                <div className="lp-anatomy-said">
                  <span className="lp-anatomy-label">on screen</span>
                  <code>{row.said}</code>
                </div>
                <div className="lp-anatomy-ran">
                  <span className="lp-anatomy-label">under the hood</span>
                  <p>{row.ran}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ------------------------------------------ the loop, 5 stages */}
        <section className="lp-section lp-loop">
          <p className="lp-kicker" data-reveal>
            02 / the working loop
          </p>
          <h2 className="lp-h2" data-reveal>
            Five stages, from a sentence to a verified deployment
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
            The language model only reaches stage one. Everything that has to be correct and reproducible is deterministic
            code — and stage three is a hard stop that waits for you.
          </p>
        </section>

        {/* --------------------------------------------- telemetry band */}
        <section className="lp-section lp-stats-section">
          <p className="lp-kicker" data-reveal>
            03 / telemetry
          </p>
          <h2 className="lp-sr-only">Telemetry</h2>
          <div className="lp-stats">
            {STATS.map((s) => (
              <Stat key={s.label} to={s.to} suffix={s.suffix} label={s.label} reduce={reduce} />
            ))}
          </div>
        </section>

        {/* ---------------------------------------------- what it does */}
        <section className="lp-section lp-features-section">
          <p className="lp-kicker" data-reveal>
            04 / what it does
          </p>
          <h2 className="lp-sr-only">What it does</h2>
          <div className="lp-features">
            {FEATURES.map((f, i) => (
              <div className="lp-feature" data-reveal style={v({ "--i": i })} key={f.no}>
                <span className="lp-feature-no">{f.no}</span>
                <h3>{f.title}</h3>
                <p>{f.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ------------------------------------ architecture / trust boundary */}
        <section id="security" className="lp-section lp-arch">
          <p className="lp-kicker" data-reveal>
            05 / architecture
          </p>
          <h2 className="lp-h2" data-reveal>
            Where does my password go? It stops here.
          </h2>
          <p className="lp-lede" data-reveal>
            Everything that touches a secret stays on your machine. Only deterministic code crosses the connector boundary
            to your tenant — carrying metadata and artifacts, never credentials, and never the model.
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

        {/* ---------------------------------------- reproducibility strip */}
        <section className="lp-section lp-repro-section">
          <p className="lp-kicker" data-reveal>
            07 / reproducibility
          </p>
          <h2 className="lp-sr-only">Reproducibility</h2>
          <div className="lp-repro" data-reveal>
            <div className="lp-repro-log">
              <div className="lp-repro-line">
                <span className="lp-prompt">$</span> epmw build --artifact RevenueForm
              </div>
              <div className="lp-repro-line dim">packaging FormSpecification … ok</div>
              <div className="lp-repro-line dim">normalizing member order … ok</div>
              <div className="lp-repro-line dim">writing form.xml (deterministic) … ok</div>
              <div className="lp-repro-line">
                <span className="lp-repro-key">sha256</span> 9f2a4c7e…d1 RevenueForm.zip
              </div>
              <div className="lp-repro-line ok">✓ identical across 3 runs · byte-for-byte reproducible</div>
            </div>
            <p className="lp-repro-note">
              The same spec always produces the same bytes. No testimonials — just a checksum you can reproduce.
            </p>
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
            EPM Wizard is model-agnostic: connect Anthropic, any OpenAI-compatible endpoint, or Gemini, and the
            assistant reasons over your own metadata. It also ships a specialist fine-tune — EPM Coder — trained
            to turn plain-English requests into validated form specifications.
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
            EPM Coder v1 is a pipeline-validation checkpoint trained on a synthetic corpus — proof the training
            loop works end-to-end, not a production-quality benchmark. Until it&rsquo;s measured on real tenants,
            the assistant defaults to a stock model grounded in your own metadata.
          </p>
        </section>

        {/* ------------------------------------------------ get started */}
        <section className="lp-section lp-cta">
          <div className="lp-cta-card" data-reveal>
            <h2>Start with a demo application — no key, no tenant.</h2>
            <p>
              Demo Mode works the moment you sign in: a deterministic local provider and a fixture Planning application,
              nothing external contacted. Bring your own model and tenant when you&rsquo;re ready.
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
