// "How it works" — architecture and feature internals, with hand-built inline
// SVG diagrams (same precedent as the SVG cube map in src/blocks/). Pure
// static content: no backend calls, no hooks.

import "../styles/doc-pages.css";

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
    <div className="doc-legend">
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
      <Node x={COL3[2]} y={ROW2[0]} w={W3} label="BM25 index" sub="+ optional embeddings (watsonx / OpenAI)" />
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

export function HowItWorksPage() {
  return (
    <div className="page">
      <h2>How EPM Wizard works</h2>
      <div className="page-sub">
        The architecture behind the chat: what the language model does, what deterministic code does, and where your data
        lives.
      </div>
      <div className="doc-page">
        <section>
          <h3>The LLM never owns the artifact</h3>
          <p>The one principle everything else follows from.</p>
          <p>
            The language model interprets intent, asks questions, and <b>proposes</b> structured specifications
            (<code>FormSpecification</code>, <code>RuleSpecification</code>). Deterministic application code does
            everything that must be correct and reproducible: validating specs against canonical Pydantic schemas and
            real tenant metadata, resolving exact members (no fuzzy substitution), rendering safe XML via ElementTree,
            building byte-reproducible packages with SHA-256 checksums, deploying, and verifying. There is no{" "}
            <code>subprocess.run(model_output, shell=True)</code> anywhere — every executable action maps to a typed,
            allowlisted backend function.
          </p>
          <div className="doc-diagram">
            <PipelineDiagram />
          </div>
          <p className="doc-diagram-caption">
            Diagram 1 — the deterministic pipeline. A request only reaches an Oracle environment after validation,
            preview, and your explicit approval; the result is verified and recorded locally.
          </p>
          <Legend tones={["human", "llm", "code", "store"]} />
        </section>

        <section>
          <h3>The connector boundary</h3>
          <p>One authoritative gateway to EPM — and the model is not allowed through it.</p>
          <p>
            All Oracle traffic goes through a single connector boundary with three implementations: a <b>Demo</b>{" "}
            connector (local fixtures and simulated jobs, the default), an <b>Oracle REST</b> connector (documented
            Planning REST API for read-only metadata and rule execution), and a restricted <b>EPM Automate runner</b>{" "}
            with a strict command allowlist, subprocess argument arrays (never a shell), timeouts, and output redaction.
            Operations are classified <code>readOnly | execution | modifying | destructive</code>; modifying and
            destructive operations require explicit approval upstream. There is no generic command endpoint.
          </p>
        </section>

        <section>
          <h3>RAG grounding</h3>
          <p>Generation is grounded on your application, not on generic training data.</p>
          <p>
            When you ask for a new form or business rule, the agent retrieves the most relevant records from the{" "}
            <b>active context version</b> — real rule scripts, templates, forms, variables, and naming digests, including
            everything a snapshot contributed. Retrieval is deterministic pure-Python <b>BM25</b>, fully offline (it
            works in Demo Mode), and upgrades to hybrid lexical + embedding scoring when the configured provider supports
            embeddings (watsonx.ai or OpenAI-compatible). The retrieved excerpts are shown to you in a visible{" "}
            <b>&ldquo;Grounded on&rdquo;</b> block and passed to the model as fenced excerpts in the prompt. The
            per-version index is cached on disk; embedding failures fall back silently to lexical scoring, so grounding
            never blocks creation.
          </p>
          <div className="doc-diagram">
            <RagDiagram />
          </div>
          <p className="doc-diagram-caption">
            Diagram 2 — the RAG grounding flow. The same excerpts you see in the &ldquo;Grounded on&rdquo; block are what
            the model receives.
          </p>
          <Legend tones={["store", "code", "llm"]} />
        </section>

        <section>
          <h3>Snapshot upload</h3>
          <p>How an LCM zip becomes context the agent can ground on.</p>
          <p>
            An Artifact Snapshot zip is parsed <b>deterministically and entirely in memory</b> — with zip-slip and
            zip-bomb guards — and the application, cubes, and dimensions are discovered from the zip&rsquo;s own{" "}
            <code>Export.xml</code> and folder manifest, never assumed. The extracted records (rule bodies, full
            hierarchies, variables, form definitions) are layered <b>on top of</b> the connector-built context as a new
            version (<code>mode: hybrid</code>, or <code>snapshot</code> when imported standalone). Every
            snapshot-derived record carries <code>source: &quot;snapshot&quot;</code>, and prior context versions are
            immutable — you can always see where a fact came from and diff versions against each other.
          </p>
          <div className="doc-diagram">
            <SnapshotDiagram />
          </div>
          <p className="doc-diagram-caption">
            Diagram 3 — the snapshot upload flow. The zip itself is not stored inside the context; its parsed records
            are, each with provenance.
          </p>
          <Legend tones={["human", "code", "store"]} />
        </section>

        <section>
          <h3>Context versions and provenance</h3>
          <p>
            Contexts are <b>versioned and append-only</b>: building, refreshing, or merging a snapshot creates a new
            version rather than editing the old one. Each manifest section is honestly marked{" "}
            <code>complete | partial | derived | unavailable | notRequested</code>, and every record carries provenance
            (connector call or snapshot file). Retrieval over the context is <b>identifier-first</b> — exact match, then
            case-insensitive, alias, prefix, substring — so the agent never silently substitutes a look-alike member.
          </p>
        </section>

        <section>
          <h3>Security and redaction</h3>
          <p>
            Secrets are never sent to the model, logged, or written into chat history, context packages, or generated
            artifacts. A centralized redactor scrubs every log line, tool result, error, and diagnostics bundle. API keys
            and remembered passwords live in a local <b>encrypted secret store</b> (Fernet), not SQLite; messages that
            look like pasted credentials are redacted before storage. Command arguments are strictly validated — no path
            traversal, no shell metacharacters — and production deployments require a persistent PROD badge, an explicit
            confirmation phrase, passing validation, a matching context, and an audit record.
          </p>
        </section>

        <section>
          <h3>Local-first data</h3>
          <p>
            Everything lives in one local data directory: the SQLite database (Alembic-migrated), the encrypted secret
            store, generated artifact packages, <code>.epwcontext</code> packages, uploaded snapshots, and the
            per-version RAG index cache. Data survives browser refresh and container restarts; schemas are owned by
            Pydantic on the backend and code-generated into the TypeScript and Zod types this UI uses, with a drift test
            keeping them in lockstep.
          </p>
        </section>

        <section>
          <h3>Hosted on IBM Cloud (optional)</h3>
          <p>
            The same application can run as a login-gated website entirely on IBM Cloud: Code Engine hosts it (scaling to
            zero when idle) behind an App ID (OAuth/OIDC) front door, and watsonx.ai provides token-billed inference and
            RAG embeddings. See <code>docs/IBM_CLOUD.md</code> in the repository for the architecture and runbook.
          </p>
        </section>
      </div>
    </div>
  );
}
