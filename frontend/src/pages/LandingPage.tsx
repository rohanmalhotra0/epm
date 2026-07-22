import "../styles/landing.css";

/**
 * Public marketing / landing page — the ONLY page served without the Google
 * auth gate. It lives at "/" (see main.tsx, which renders this instead of the
 * app when the path is not under /app). The single call-to-action links to
 * "/app", which oauth2-proxy (the epmw-auth front door) intercepts: an
 * unauthenticated visitor is bounced to Google and returned to /app once
 * signed in. In local dev (no gate) the link simply loads the app.
 */

// Where the "Sign in" CTA sends the visitor. oauth2-proxy protects everything
// under /app and redirects to Google, coming back here afterwards.
const APP_ENTRY = "/app";

const FEATURES = [
  {
    title: "AI copilot for EPM",
    body: "Ask questions, draft artifacts and reason over your Planning application in plain language — grounded in your own metadata.",
  },
  {
    title: "Live Oracle EPM connection",
    body: "Connect a Planning tenant with a password or OAuth 2.0 client credentials. Secrets stay in process memory — never written to chat or logs.",
  },
  {
    title: "Spreadsheets, forms & reports",
    body: "Generate and edit data forms, rule specs and snapshot summaries as first-class artifacts alongside the conversation.",
  },
];

function GoogleGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

export function LandingPage() {
  return (
    <div className="landing">
      <header className="landing-nav">
        <a className="landing-brand" href="/">
          <img src="/favicon.svg" alt="" width={28} height={28} />
          <span>EPM&nbsp;Wizard</span>
        </a>
        <a className="landing-nav-cta" href={APP_ENTRY}>
          Sign in
        </a>
      </header>

      <main className="landing-hero">
        <p className="landing-eyebrow">Local-first · Oracle EPM</p>
        <h1 className="landing-title">
          The AI workspace for
          <br />
          Oracle EPM implementation
        </h1>
        <p className="landing-sub">
          Plan, build and reason over your Planning application with an AI copilot that
          connects to your live tenant — and keeps your data on your terms.
        </p>
        <div className="landing-actions">
          <a className="landing-btn-primary" href={APP_ENTRY}>
            <GoogleGlyph />
            <span>Sign in with Google</span>
          </a>
          <a className="landing-btn-ghost" href="#features">
            See what it does
          </a>
        </div>
        <p className="landing-fineprint">
          Access is restricted to approved accounts. You'll be returned here if you're not on
          the list.
        </p>
      </main>

      <section id="features" className="landing-features">
        {FEATURES.map((f) => (
          <div className="landing-feature" key={f.title}>
            <h3>{f.title}</h3>
            <p>{f.body}</p>
          </div>
        ))}
      </section>

      <footer className="landing-footer">
        <span>EPM Wizard</span>
        <span className="landing-footer-sep">·</span>
        <a href={APP_ENTRY}>Sign in</a>
      </footer>
    </div>
  );
}
