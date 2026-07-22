// "How to use" — a task-oriented guide for EPM consultants. Pure static
// content: no backend calls, no hooks, renders offline.

import "../styles/doc-pages.css";

/** An example message you can type in the chat, styled like a chat chip. */
function Chat({ children }: { children: React.ReactNode }) {
  return (
    <div className="chat-example">
      <span className="who">You</span>
      <span>{children}</span>
    </div>
  );
}

function Section({ no, title, children }: { no: number; title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3>
        <span className="doc-no" aria-hidden="true">{no}</span>
        {title}
      </h3>
      {children}
    </section>
  );
}

export function HowToPage() {
  return (
    <div className="page">
      <h2>How to use EPM Wizard</h2>
      <div className="page-sub">
        A practical walkthrough, in the order you would use it on a real engagement. Everything happens in the chat —
        these are the messages to type.
      </div>
      <div className="doc-page">
        <Section no={1} title="Getting started">
          <p>You can try everything before configuring anything.</p>
          <ol className="doc-steps">
            <li>
              <b>Demo Mode works instantly.</b> EPM Wizard starts with a deterministic local AI provider and a fixture
              Planning application, so the whole product is usable with no API key and no Oracle tenant. Nothing external
              is contacted.
            </li>
            <li>
              To use a real AI model, open <b>Settings → AI Providers</b> and add Anthropic, an
              OpenAI-compatible endpoint (OpenAI, OpenRouter, Together AI, Ollama), or Gemini.
            </li>
            <li>
              To connect a real Oracle environment, open <b>Settings → Oracle Environments</b> and click <b>Connect</b> —
              a harmless read-only call verifies your credentials.
            </li>
            <li>Not sure what to ask? Type:</li>
          </ol>
          <Chat><code>/help</code></Chat>
        </Section>

        <Section no={2} title="Build a context">
          <p>
            A <b>context</b> is EPM Wizard&rsquo;s local knowledge of your application: cubes, dimensions, members, forms,
            and rules. It is stored on your machine and reused automatically.
          </p>
          <ol className="doc-steps">
            <li>Ask for a context in the chat (or use the <b>Contexts</b> tab → <b>Build context</b>):</li>
          </ol>
          <Chat><code>/context</code></Chat>
          <Chat>What cubes and dimensions exist?</Chat>
          <ul>
            <li>
              A <b>quick</b> context captures the application inventory through the connector — cubes, dimension outlines,
              members, forms, and the business-rule list.
            </li>
            <li>
              Each section is honestly marked <code>complete</code>, <code>partial</code>, <code>derived</code>,{" "}
              <code>unavailable</code>, or <code>notRequested</code> — the assistant never pretends to know more than it
              fetched.
            </li>
          </ul>
        </Section>

        <Section no={3} title="Upload an Application Snapshot">
          <p>
            The REST interfaces cannot supply everything. An <b>LCM Artifact Snapshot</b> zip fills the gaps — it is the
            file produced by <code>epmautomate exportSnapshot</code> followed by{" "}
            <code>downloadFile &quot;Artifact Snapshot&quot;</code>.
          </p>
          <ol className="doc-steps">
            <li>
              Attach the zip with the <b>paperclip in the chat</b>, or go to the <b>Contexts</b> tab and click{" "}
              <b>Upload snapshot</b>.
            </li>
            <li>
              Choose how to apply it: <b>merge</b> it onto the active context (recommended — you keep the live inventory
              and gain the snapshot detail), or import it as a <b>standalone</b> context.
            </li>
          </ol>
          <Chat><code>/context merge snapshot</code></Chat>
          <p>What a snapshot unlocks:</p>
          <ul>
            <li>Calculation Manager <b>rule bodies</b> and runtime prompts — not just rule names</li>
            <li><b>Full member hierarchies</b> with member formulas</li>
            <li>Substitution and user <b>variables</b></li>
            <li>Complete <b>form definitions</b> and references, plus FDMEE inventory</li>
          </ul>
          <p>
            The zip is parsed deterministically and fully in-memory; the application, cubes, and dimensions come from the
            zip&rsquo;s own manifest, so any Planning application works.
          </p>
        </Section>

        <Section no={4} title="Create a form">
          <p>Describe the form in plain language; refine it conversationally; deploy only when you approve.</p>
          <ol className="doc-steps">
            <li>Ask for the form:</li>
          </ol>
          <Chat>Create an Actuals form with level-zero descendants of Total Payroll in rows</Chat>
          <ol className="doc-steps" start={2}>
            <li>Review the <b>preview grid</b> rendered in the chat — it looks like the EPM form it will become.</li>
            <li>Refine with short edits; the preview updates each time:</li>
          </ol>
          <Chat>move Entity to POV</Chat>
          <Chat>hide March</Chat>
          <Chat>use aliases</Chat>
          <ol className="doc-steps" start={4}>
            <li>
              Say <b>validate</b> — the spec is checked against real tenant metadata (member existence, axis rules,
              sizing, security).
            </li>
            <li>
              Say <b>deploy</b> and click the approval card. After deployment, the form is read back and marked{" "}
              <b>verified</b> only when it is confirmed to exist.
            </li>
            <li>Every deployment is recorded on the <b>Deployments</b> tab with its verification result.</li>
          </ol>
        </Section>

        <Section no={5} title="Create a business rule">
          <p>Rule drafting is grounded on the real rules in your context — and is never deployed automatically.</p>
          <ol className="doc-steps">
            <li>Ask for the rule:</li>
          </ol>
          <Chat>Create a business rule that copies Working to Final</Chat>
          <ol className="doc-steps" start={2}>
            <li>
              A visible <b>&ldquo;Grounded on&rdquo;</b> block appears first, listing the real rule scripts, templates,
              and variables from your context that the draft is based on.
            </li>
            <li>The draft script streams into the chat, always labelled a <b>proposal</b>.</li>
            <li>Click <b>Save as artifact</b> to keep it.</li>
            <li>
              Saving also produces a downloadable, deterministic <b>Calc Manager import package</b> — you review it and
              import it through Migration yourself. Rule drafts are <b>never auto-deployed</b>.
            </li>
          </ol>
        </Section>

        <Section no={6} title="Run rules and runtime prompts">
          <ol className="doc-steps">
            <li>Ask in plain language, or use the slash command:</li>
          </ol>
          <Chat>Run the IR rule</Chat>
          <Chat><code>/run-rule CopyWorkingToFinal</code></Chat>
          <ol className="doc-steps" start={2}>
            <li>
              If the rule has <b>runtime prompts</b>, they render as a small form in the chat — fill them in and submit.
            </li>
            <li>Execution status streams back, and every run is recorded in the local audit history.</li>
          </ol>
        </Section>

        <Section no={7} title="Work from spreadsheets">
          <p>
            Drop an <code>.xlsx</code> or <code>.csv</code> onto the chat (or attach it with the paperclip). The sheet is
            analyzed and classified — nothing in it is ever executed.
          </p>
          <ul>
            <li>
              <b>Chart of accounts</b> (Member/Parent or Level 1..N columns) — merge the hierarchy into your context and
              render a metadata CSV.
            </li>
            <li><b>Form layout</b> (period column headers like Jan, Feb, Q1 over a label column) — turn it into a form:</li>
          </ul>
          <Chat>Create a form from my spreadsheet layout</Chat>
          <ul>
            <li><b>Data tables</b> — plan the data load (a load-file plan you can review), and reconcile against the tenant.</li>
          </ul>
        </Section>

        <Section no={8} title="Visualize cube architecture">
          <ol className="doc-steps">
            <li>Ask for any cube in the active context:</li>
          </ol>
          <Chat>Visualize OEP_DCSH</Chat>
          <ol className="doc-steps" start={2}>
            <li>
              An interactive cube map renders inline — dimensions, coverage, and sizing. The same visualizer lives at the
              bottom of the <b>Contexts</b> tab, with an all-cubes overview.
            </li>
          </ol>
        </Section>

        <Section no={9} title="Export and share">
          <ul>
            <li>
              <b>Context reports</b> — on the <b>Contexts</b> tab, export any version as <b>Word</b>, <b>PDF</b>, or{" "}
              <b>Markdown</b>, ready to hand to a client.
            </li>
            <li>
              <b>Portable context packages</b> — <code>/context export</code> produces a <code>.epwcontext</code> zip
              (manifest + checksums, no secrets) that a teammate can import.
            </li>
            <li>
              <b>Whole project</b> — the <b>Data</b> tab exports the current project as a zip archive and imports it back,
              for backup or moving machines.
            </li>
          </ul>
        </Section>

        <section className="doc-callout" aria-label="Safety promises">
          <h3>Safety promises</h3>
          <ul>
            <li>
              <b>Nothing deploys without your explicit approval.</b> Every modifying operation stops at an approval card;
              rule drafts are proposals and are never executed or auto-deployed.
            </li>
            <li>
              <b>Production is guarded.</b> PROD environments carry a persistent badge and require typing an explicit
              confirmation phrase (for example <code>confirm deploy FormName</code>) plus passing validation.
            </li>
            <li>
              <b>Secrets never reach the model.</b> API keys and passwords live in a local encrypted store; a centralized
              redactor scrubs logs, tool results, and errors, and pasted credentials are redacted before storage.
            </li>
            <li>
              <b>Everything stays local.</b> Projects, conversations, contexts, artifacts, and deployment history are
              stored on your machine.
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
