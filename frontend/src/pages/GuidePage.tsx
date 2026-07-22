// The in-app guide — one page that covers both how to use EPM Wizard and how
// it works underneath, organized around the actual working loop. Each stage
// pairs "do this" (example chat messages) with "under the hood" (internals).
// Pure static content: no backend calls, no hooks. The three SVG diagrams are
// hand-built inline SVG, same precedent as the cube map in src/blocks/.

import { Link } from "react-router-dom";
import "../styles/guide-page.css";

/* ---------- small content primitives -------------------------------------- */

/** An example message you can type in the chat, styled like a chat chip. */
function Chat({ children }: { children: React.ReactNode }) {
  return (
    <div className="chat-example">
      <span className="who">You</span>
      <span>{children}</span>
    </div>
  );
}

/** Mono uppercase micro-label used as a column kicker inside stages. */
function Micro({ children }: { children: React.ReactNode }) {
  return <div className="guide-micro">{children}</div>;
}

/** A numbered stage of the working loop, with an oversized ghost number. */
function Stage({ no, title, children }: { no: string; title: string; children: React.ReactNode }) {
  return (
    <section className="guide-stage">
      <div className="stage-no" aria-hidden="true">
        {no}
      </div>
      <div className="stage-body">
        <h3>{title}</h3>
        {children}
      </div>
    </section>
  );
}

/* ---------- shared diagram primitives ------------------------------------- */

// Fixed dark palette (the diagram container is always dark, like the cube map).
const TONES = {
  code: "#4589ff", // deterministic application code
  llm: "#be95ff", // language model
  human: "#42be65", // the user
  store: "#f1c21b", // stored locally
} as const;

type Tone = keyof typeof TONES;

function Node({
  x,
  y,
  w = 168,
  h = 56,
  label,
  sub,
  tone = "code",
}: {
  x: number;
  y: number;
  w?: number;
  h?: number;
  label: string;
  sub?: string;
  tone?: Tone;
}) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={3} fill="#262626" stroke={TONES[tone]} strokeWidth={1.5} />
      <text
        x={x + w / 2}
        y={sub ? y + h / 2 - 4 : y + h / 2 + 4}
        textAnchor="middle"
        fill="#f4f4f4"
        fontSize={12}
        fontWeight={600}
      >
        {label}
      </text>
      {sub && (
        <text x={x + w / 2} y={y + h / 2 + 14} textAnchor="middle" fill="#8d8d8d" fontSize={10}>
          {sub}
        </text>
      )}
    </g>
  );
}

function Arrow({ x1, y1, x2, y2, marker }: { x1: number; y1: number; x2: number; y2: number; marker: string }) {
  return <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#6f6f6f" strokeWidth={1.5} markerEnd={`url(#${marker})`} />;
}

function ArrowDefs({ id }: { id: string }) {
  return (
    <defs>
      <marker id={id} viewBox="0 0 10 10" refX={9} refY={5} markerWidth={7} markerHeight={7} orient="auto-start-reverse">
        <path d="M 0 1 L 9 5 L 0 9 z" fill="#6f6f6f" />
      </marker>
    </defs>
  );
}

function Legend({ tones }: { tones: Tone[] }) {
  const labels: Record<Tone, string> = {
    code: "deterministic application code",
    llm: "language model (proposes only)",
    human: "you",
    store: "stored locally",
  };
  return (
    <div className="guide-legend">
      {tones.map((t) => (
        <span key={t}>
          <span className="sw" style={{ border: `1.5px solid ${TONES[t]}` }} />
          {labels[t]}
        </span>
      ))}
    </div>
  );
}

/* ---------- diagram 1: the deterministic pipeline -------------------------- */

// 4-column snake layout. Columns at x = 25/219/413/607 (w=168, gap=26).
const COL4 = [25, 219, 413, 607];
const ROW3 = [28, 165, 302];
const W = 168;
const H = 56;

function PipelineDiagram() {
  const m = "arrow-pipeline";
  const rows: Array<Array<{ label: string; sub?: string; tone?: Tone }>> = [
    [
      { label: "User request", sub: "chat message", tone: "human" },
      { label: "Intent router", sub: "slash commands + NL" },
      { label: "Context retrieval", sub: "identifier-first, local" },
      { label: "Proposed spec", sub: "FormSpec / RuleSpec", tone: "llm" },
    ],
    // rendered right-to-left (snake)
    [
      { label: "Pydantic validation", sub: "canonical schemas" },
      { label: "Tenant validation", sub: "members, axes, sizing" },
      { label: "Interactive preview", sub: "rendered in chat" },
      { label: "Approval", sub: "PROD: confirmation phrase", tone: "human" },
    ],
    [
      { label: "Deterministic artifact", sub: "safe XML, reproducible zip" },
      { label: "Deploy", sub: "connector boundary" },
      { label: "Verify", sub: "read back from tenant" },
      { label: "Local history", sub: "deployments + audit", tone: "store" },
    ],
  ];
  return (
    <svg
      viewBox="0 0 800 386"
      role="img"
      aria-label="Deterministic deployment pipeline diagram: user request through intent routing, context retrieval, proposed specification, validation, preview, approval, deterministic generation, deployment, verification, and local history"
    >
      <title>The deterministic pipeline — the language model proposes, deterministic code validates and deploys</title>
      <ArrowDefs id={m} />
      {/* row 1, left to right */}
      {rows[0].map((n, i) => (
        <Node key={n.label} x={COL4[i]} y={ROW3[0]} label={n.label} sub={n.sub} tone={n.tone} />
      ))}
      {[0, 1, 2].map((i) => (
        <Arrow key={i} x1={COL4[i] + W} y1={ROW3[0] + H / 2} x2={COL4[i + 1]} y2={ROW3[0] + H / 2} marker={m} />
      ))}
      {/* snake down on the right */}
      <Arrow x1={COL4[3] + W / 2} y1={ROW3[0] + H} x2={COL4[3] + W / 2} y2={ROW3[1]} marker={m} />
      {/* row 2, right to left */}
      {rows[1].map((n, i) => (
        <Node key={n.label} x={COL4[3 - i]} y={ROW3[1]} label={n.label} sub={n.sub} tone={n.tone} />
      ))}
      {[3, 2, 1].map((i) => (
        <Arrow key={i} x1={COL4[i]} y1={ROW3[1] + H / 2} x2={COL4[i - 1] + W} y2={ROW3[1] + H / 2} marker={m} />
      ))}
      {/* snake down on the left */}
      <Arrow x1={COL4[0] + W / 2} y1={ROW3[1] + H} x2={COL4[0] + W / 2} y2={ROW3[2]} marker={m} />
      {/* row 3, left to right */}
      {rows[2].map((n, i) => (
        <Node key={n.label} x={COL4[i]} y={ROW3[2]} label={n.label} sub={n.sub} tone={n.tone} />
      ))}
      {[0, 1, 2].map((i) => (
        <Arrow key={i} x1={COL4[i] + W} y1={ROW3[2] + H / 2} x2={COL4[i + 1]} y2={ROW3[2] + H / 2} marker={m} />
      ))}
    </svg>
  );
}

/* ---------- diagram 2: RAG grounding flow ---------------------------------- */

// 3-column snake layout. Columns at x = 45/295/545 (w=210, gap=40).
const COL3 = [45, 295, 545];
const ROW2 = [28, 158];
const W3 = 210;

function RagDiagram() {
  const m = "arrow-rag";
  return (
    <svg
      viewBox="0 0 800 242"
      role="img"
      aria-label="RAG grounding flow diagram: active context version through chunker, BM25 index with optional embeddings, top-k retrieval, the Grounded on block, and generation"
    >
      <title>RAG grounding — retrieval is deterministic and offline; embeddings are an optional upgrade</title>
      <ArrowDefs id={m} />
      <Node x={COL3[0]} y={ROW2[0]} w={W3} label="Active context version" sub="live records + snapshot records" tone="store" />
      <Node x={COL3[1]} y={ROW2[0]} w={W3} label="Chunker" sub="records → indexed chunks" />
      <Node x={COL3[2]} y={ROW2[0]} w={W3} label="BM25 index" sub="+ optional embeddings (OpenAI-compatible)" />
      <Arrow x1={COL3[0] + W3} y1={ROW2[0] + H / 2} x2={COL3[1]} y2={ROW2[0] + H / 2} marker={m} />
      <Arrow x1={COL3[1] + W3} y1={ROW2[0] + H / 2} x2={COL3[2]} y2={ROW2[0] + H / 2} marker={m} />
      <Arrow x1={COL3[2] + W3 / 2} y1={ROW2[0] + H} x2={COL3[2] + W3 / 2} y2={ROW2[1]} marker={m} />
      <Node x={COL3[2]} y={ROW2[1]} w={W3} label="Top-k grounding" sub="most relevant rule bodies, templates…" />
      <Node x={COL3[1]} y={ROW2[1]} w={W3} label="“Grounded on” block" sub="shown in chat; fenced excerpts in prompt" />
      <Node x={COL3[0]} y={ROW2[1]} w={W3} label="Generation" sub="draft is a proposal only" tone="llm" />
      <Arrow x1={COL3[2]} y1={ROW2[1] + H / 2} x2={COL3[1] + W3} y2={ROW2[1] + H / 2} marker={m} />
      <Arrow x1={COL3[1]} y1={ROW2[1] + H / 2} x2={COL3[0] + W3} y2={ROW2[1] + H / 2} marker={m} />
    </svg>
  );
}

/* ---------- diagram 3: snapshot upload flow -------------------------------- */

function SnapshotDiagram() {
  const m = "arrow-snapshot";
  return (
    <svg
      viewBox="0 0 800 242"
      role="img"
      aria-label="Snapshot upload and merge flow diagram: LCM snapshot zip through the safe in-memory parser, snapshot-tagged records, merge onto the live context, and a new hybrid context version"
    >
      <title>Snapshot upload — parsed in memory, layered onto the live context as a new immutable version</title>
      <ArrowDefs id={m} />
      <Node x={COL3[0]} y={ROW2[0]} w={W3} label="LCM snapshot zip" sub="exportSnapshot + downloadFile" tone="human" />
      <Node x={COL3[1]} y={ROW2[0]} w={W3} label="Safe in-memory parser" sub="zip-slip/bomb guards; manifest-driven" />
      <Node x={COL3[2]} y={ROW2[0]} w={W3} label="Snapshot records" sub='each tagged source: "snapshot"' />
      <Arrow x1={COL3[0] + W3} y1={ROW2[0] + H / 2} x2={COL3[1]} y2={ROW2[0] + H / 2} marker={m} />
      <Arrow x1={COL3[1] + W3} y1={ROW2[0] + H / 2} x2={COL3[2]} y2={ROW2[0] + H / 2} marker={m} />
      <Arrow x1={COL3[2] + W3 / 2} y1={ROW2[0] + H} x2={COL3[2] + W3 / 2} y2={ROW2[1]} marker={m} />
      <Node x={COL3[2]} y={ROW2[1]} w={W3} label="Merge onto live context" sub="or standalone import" />
      <Node x={COL3[1]} y={ROW2[1]} w={W3} label="New context version" sub="mode: hybrid — full provenance" tone="store" />
      <Arrow x1={COL3[2]} y1={ROW2[1] + H / 2} x2={COL3[1] + W3} y2={ROW2[1] + H / 2} marker={m} />
      <text x={COL3[0] + W3 / 2} y={ROW2[1] + H / 2 + 4} textAnchor="middle" fill="#8d8d8d" fontSize={11}>
        Prior versions are never mutated.
      </text>
    </svg>
  );
}

/* ---------- the page -------------------------------------------------------- */

export function GuidePage() {
  return (
    <div className="page guide-page">
      {/* ---- hero ---- */}
      <header className="guide-hero">
        <div className="guide-hero-inner">
          <div className="guide-kicker">EPM Wizard / from prompt to verified deployment</div>
          <h1>
            You describe the change.
            <br />
            Deterministic code ships it.
          </h1>
          <p className="guide-hero-sub">
            The language model proposes structured specifications. Typed code validates them against your real tenant,
            builds byte-reproducible artifacts, deploys, and reads the result back. Everything stays on your machine.
          </p>
          <div className="guide-cta-row">
            <Link className="guide-cta primary" to="/">
              Open the chat
            </Link>
            <Link className="guide-cta tertiary" to="/settings">
              Connect your tenant
            </Link>
          </div>
          <div className="guide-term" aria-hidden="true">
            <div className="term-line">
              <span className="term-who you">you</span>
              <span>Create a revenue form for FY26 with products in rows</span>
            </div>
            <div className="term-line">
              <span className="term-who">epmw</span>
              <span>preview rendered — 14 rows × 13 columns · POV: Scenario, Version</span>
            </div>
            <div className="term-line">
              <span className="term-who you">you</span>
              <span>validate</span>
            </div>
            <div className="term-line">
              <span className="term-who">epmw</span>
              <span>0 errors — every member resolved against tenant metadata</span>
            </div>
            <div className="term-line">
              <span className="term-who you">you</span>
              <span>deploy</span>
            </div>
            <div className="term-line">
              <span className="term-who">epmw</span>
              <span>approved → deployed → read back → verified</span>
            </div>
          </div>
        </div>
      </header>

      {/* ---- the one rule ---- */}
      <section className="guide-section">
        <div className="guide-kicker">the principle</div>
        <h2>The one rule</h2>
        <p className="guide-lede">The LLM never owns the artifact. Everything else follows from that.</p>
        <p>
          The model interprets intent, asks questions, and proposes structured specifications —{" "}
          <code>FormSpecification</code>, <code>RuleSpecification</code>. Deterministic code does everything that has to
          be correct and reproducible: validation against canonical Pydantic schemas and real tenant metadata, exact
          member resolution with no fuzzy substitution, safe XML via ElementTree, byte-reproducible zips with SHA-256
          checksums, deployment, verification. There is no <code>subprocess.run(model_output, shell=True)</code>{" "}
          anywhere in the codebase — every executable action maps to a typed, allowlisted backend function.
        </p>
        <div className="guide-diagram">
          <PipelineDiagram />
        </div>
        <p className="guide-diagram-caption">
          The deterministic pipeline. A request only reaches an Oracle environment after validation, preview, and your
          explicit approval — and the result is verified and recorded locally.
        </p>
        <Legend tones={["human", "llm", "code", "store"]} />
      </section>

      {/* ---- the working loop ---- */}
      <section className="guide-section">
        <div className="guide-kicker">the working loop</div>
        <h2>Five stages, start to verified</h2>
        <p className="guide-lede">
          Each stage pairs the messages you type with what actually runs underneath.
        </p>

        <Stage no="01" title="Start">
          <div className="stage-cols">
            <div>
              <Micro>Do this</Micro>
              <p>
                Demo Mode works the moment the app opens: a deterministic local provider plus a fixture Planning
                application. No API key, no tenant, nothing external contacted.
              </p>
              <p>
                For real models, open <b>Settings → AI Providers</b> — Anthropic, any OpenAI-compatible endpoint
                (OpenAI, OpenRouter, Together AI, Ollama), or Gemini. For a real tenant, open{" "}
                <b>Settings → Oracle Environments</b> and click <b>Connect</b>; a harmless read-only call checks the
                credentials. Lost? Ask the chat:
              </p>
              <Chat>
                <code>/help</code>
              </Chat>
            </div>
            <div>
              <Micro>Under the hood</Micro>
              <p>
                All EPM traffic crosses one connector boundary with three implementations: a <b>Demo</b> connector
                (local fixtures, simulated jobs), an <b>Oracle REST</b> connector (documented Planning REST API, used
                for read-only metadata and rule execution), and a
                restricted <b>EPM Automate runner</b> — strict command allowlist, subprocess argument arrays (never a
                shell), timeouts, output redaction. Operations are classified{" "}
                <code>readOnly | execution | modifying | destructive</code>, and there is no generic command endpoint.
                The model is not allowed through this boundary at all.
              </p>
            </div>
          </div>
        </Stage>

        <Stage no="02" title="Teach it your application">
          <div className="stage-cols">
            <div>
              <Micro>Do this</Micro>
              <p>
                A <b>context</b> is the local knowledge of your application — cubes, dimensions, members, forms, rules.
                It is stored on your machine and reused automatically. Build one from the chat or the Contexts tab:
              </p>
              <Chat>
                <code>/context</code>
              </Chat>
              <Chat>What cubes and dimensions exist?</Chat>
              <p>
                A quick context captures the application inventory through the connector — cubes, dimension outlines,
                members, forms, and the business-rule list. Each section is honestly
                marked <code>complete | partial | derived | unavailable | notRequested</code> — the assistant never
                pretends to know more than it fetched.
              </p>
              <p>
                REST cannot supply everything, so feed it an <b>LCM Artifact Snapshot</b> zip — the file{" "}
                <code>epmautomate exportSnapshot</code> then <code>downloadFile &quot;Artifact Snapshot&quot;</code>{" "}
                produces. Attach it with the paperclip or upload it on the Contexts tab, then merge it onto the live
                context — recommended, since you keep the live inventory and gain the snapshot detail — or import it as
                a standalone context:
              </p>
              <Chat>
                <code>/context merge snapshot</code>
              </Chat>
              <p>
                A snapshot unlocks Calc Manager rule bodies and runtime prompts, full member hierarchies with formulas,
                substitution and user variables, complete form definitions and references, and the FDMEE inventory.
              </p>
            </div>
            <div>
              <Micro>Under the hood</Micro>
              <p>
                The zip is parsed deterministically and entirely in memory, with zip-slip and zip-bomb guards. The
                application, cubes, and dimensions come from the zip&rsquo;s own <code>Export.xml</code> and folder
                manifest — never assumed — so any Planning application works. Every extracted record is tagged{" "}
                <code>source: &quot;snapshot&quot;</code>. A merge produces a new version with{" "}
                <code>mode: hybrid</code>; a standalone import produces <code>mode: snapshot</code>.
              </p>
              <p>
                Contexts are versioned and append-only: building, refreshing, or merging creates a new version; prior
                versions are immutable and every record carries provenance. Lookups are identifier-first — exact, then
                case-insensitive, alias, prefix, substring — so the agent never silently substitutes a look-alike
                member.
              </p>
            </div>
          </div>
          <div className="guide-diagram">
            <SnapshotDiagram />
          </div>
          <p className="guide-diagram-caption">
            The snapshot flow. The zip itself is not stored inside the context; its parsed records are, each with
            provenance.
          </p>
          <Legend tones={["human", "code", "store"]} />
        </Stage>

        <Stage no="03" title="Ask for the thing">
          <div className="stage-cols">
            <div>
              <Micro>Do this</Micro>
              <p>
                Forms are conversational. Describe one and a preview grid renders in the chat — it looks like the EPM
                form it will become. Refine it in short edits; the preview updates each time:
              </p>
              <Chat>Create an Actuals form with level-zero descendants of Total Payroll in rows</Chat>
              <Chat>move Entity to POV</Chat>
              <Chat>hide March</Chat>
              <Chat>use aliases</Chat>
              <p>Business rules start the same way:</p>
              <Chat>Create a business rule that copies Working to Final</Chat>
              <p>
                A visible <b>&ldquo;Grounded on&rdquo;</b> block lists the real rule scripts, templates, forms, and
                variables the draft is based on, then the script streams in — always labelled a proposal.{" "}
                <b>Save as artifact</b> keeps it and produces a downloadable, deterministic Calc Manager import package
                that you review and import through Migration yourself.
              </p>
            </div>
            <div>
              <Micro>Under the hood</Micro>
              <p>
                Retrieval runs over the active context version — rule scripts, templates, forms, variables, and naming
                digests, including everything a snapshot contributed. It is deterministic pure-Python <b>BM25</b>, fully
                offline — it works in Demo Mode — and upgrades to hybrid lexical + embedding scoring when the configured
                provider exposes embeddings (any OpenAI-compatible endpoint). The per-version index is cached on disk,
                and an embedding failure falls back silently to lexical scoring, so grounding never blocks creation.
              </p>
              <p>
                The excerpts you see in the &ldquo;Grounded on&rdquo; block are exactly what the model receives, as
                fenced excerpts in the prompt. No hidden context.
              </p>
            </div>
          </div>
          <div className="guide-diagram">
            <RagDiagram />
          </div>
          <p className="guide-diagram-caption">
            The RAG grounding flow. Generation is grounded on your application, not on generic training data.
          </p>
          <Legend tones={["store", "code", "llm"]} />
        </Stage>

        <Stage no="04" title="Approve and deploy">
          <div className="stage-cols">
            <div>
              <Micro>Do this</Micro>
              <p>
                Say <b>validate</b> — the spec is checked against real tenant metadata: member existence, axis rules,
                sizing, security. Say <b>deploy</b> and click the approval card. On PROD, the environment carries a
                persistent badge and deployment additionally requires typing a confirmation phrase such as{" "}
                <code>confirm deploy FormName</code>, plus passing validation.
              </p>
              <p>Running existing rules works in plain language or by slash command:</p>
              <Chat>Run the IR rule</Chat>
              <Chat>
                <code>/run-rule CopyWorkingToFinal</code>
              </Chat>
              <p>
                If a rule has runtime prompts, they render as a small form in the chat — fill it in and submit.
                Execution status streams back.
              </p>
            </div>
            <div>
              <Micro>Under the hood</Micro>
              <p>
                The approval card is not decoration — modifying and destructive operations are refused at the connector
                boundary unless approval happened upstream. The artifact that ships is the deterministic package built
                from the validated spec, byte-for-byte reproducible with SHA-256 checksums, not whatever the model last
                said.
              </p>
            </div>
          </div>
        </Stage>

        <Stage no="05" title="Verify and keep">
          <div className="stage-cols">
            <div>
              <Micro>Do this</Micro>
              <p>
                After deployment the form is read back from the tenant and marked <b>verified</b> only when it is
                confirmed to exist. Every run and deployment lands on the <b>Deployments</b> tab with its verification
                result, and in the local audit history.
              </p>
            </div>
            <div>
              <Micro>Take it with you</Micro>
              <p>
                Context reports export any version as Word, PDF, or Markdown from the Contexts tab, ready to hand to a
                client.{" "}
                <code>/context export</code> produces a portable <code>.epwcontext</code> zip — manifest, checksums, no
                secrets — that a teammate can import. The Data tab exports and imports the whole project as a zip, for
                backup or moving machines.
              </p>
              <Chat>
                <code>/context export</code>
              </Chat>
            </div>
          </div>
        </Stage>
      </section>

      {/* ---- also in the box ---- */}
      <section className="guide-section">
        <div className="guide-kicker">also in the box</div>
        <h2>Smaller tools that earn their keep</h2>
        <div className="guide-grid">
          <div className="guide-cell">
            <h3>Spreadsheets</h3>
            <p>
              Drop an <code>.xlsx</code> or <code>.csv</code> onto the chat. The sheet is analyzed and classified — a
              chart of accounts (Member/Parent or Level 1..N columns; merge the hierarchy, render a metadata CSV), a
              form layout (period column headers like Jan, Feb, Q1 over a label column), or a data table (a load-file
              plan you can review, reconciled against the tenant). Nothing in the file is ever executed.
            </p>
            <Chat>Create a form from my spreadsheet layout</Chat>
          </div>
          <div className="guide-cell">
            <h3>Cube visualizer</h3>
            <p>
              An interactive cube map — dimensions, coverage, sizing — renders inline in the chat and lives at the
              bottom of the Contexts tab with an all-cubes overview.
            </p>
            <Chat>Visualize OEP_DCSH</Chat>
          </div>
          <div className="guide-cell">
            <h3>Slash commands</h3>
            <p>
              <code>/help</code>, <code>/context</code>, <code>/run-rule</code> and friends autocomplete in the
              composer, and <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>K</kbd> opens a palette that searches conversations,
              messages, and artifacts across the project.
            </p>
          </div>
          <div className="guide-cell">
            <h3>Context diffing</h3>
            <p>
              Because context versions are immutable, any two can be diffed — see exactly what a refresh or a snapshot
              merge changed, member by member, before you trust it.
            </p>
          </div>
        </div>
      </section>

      {/* ---- guardrails ---- */}
      <section className="guide-section">
        <div className="guide-kicker">guardrails</div>
        <h2>What is guaranteed, and by what</h2>
        <div className="guide-ledger">
          <div className="ledger-row">
            <div className="ledger-claim">Nothing deploys without your explicit approval.</div>
            <div className="ledger-how">
              Every modifying operation stops at an approval card. Rule drafts are proposals and are{" "}
              <b>never auto-deployed</b> or executed — you import the generated Calc Manager package through Migration
              yourself.
            </div>
          </div>
          <div className="ledger-row">
            <div className="ledger-claim">Production is deliberately slow.</div>
            <div className="ledger-how">
              PROD environments carry a persistent badge; deploying there requires a typed confirmation phrase (
              <code>confirm deploy FormName</code>), passing validation, a matching context, and an audit record.
            </div>
          </div>
          <div className="ledger-row">
            <div className="ledger-claim">Secrets never reach the model.</div>
            <div className="ledger-how">
              Secrets are never sent to the model, logged, or written into chat history, context packages, or generated
              artifacts. API keys and passwords live in a Fernet-encrypted local secret store, not SQLite. A centralized
              redactor scrubs every log line, tool result, error, and diagnostics bundle; messages that look like pasted
              credentials are redacted before storage.
            </div>
          </div>
          <div className="ledger-row">
            <div className="ledger-claim">No shell, ever.</div>
            <div className="ledger-how">
              Executable actions are typed, allowlisted functions. External commands run as argument arrays with strict
              validation — no path traversal, no shell metacharacters — plus timeouts and output redaction.
            </div>
          </div>
          <div className="ledger-row">
            <div className="ledger-claim">Everything stays local.</div>
            <div className="ledger-how">
              Projects, conversations, contexts, artifacts, and deployment history live in one data directory: the
              SQLite database (Alembic-migrated), the encrypted secret store, artifact packages,{" "}
              <code>.epwcontext</code> exports, uploaded snapshots, and the per-version RAG index cache. Data survives
              browser refresh and container restarts. Schemas are owned by Pydantic and code-generated into the
              TypeScript and Zod types this UI uses, with a drift test keeping them in lockstep.
            </div>
          </div>
        </div>
      </section>

      {/* ---- closing ---- */}
      <section className="guide-section guide-close">
        <p>
          That is the whole loop. Type <code>/help</code> in the chat whenever you lose the thread.
        </p>
        <Link className="guide-cta primary" to="/">
          Open the chat
        </Link>
      </section>
    </div>
  );
}
