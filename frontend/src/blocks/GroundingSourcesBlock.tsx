// Renders the assistant's `groundingSources` block: which context artifacts a
// generated form or rule draft was grounded on (RAG retrieval). The shape is
// server-driven and still evolving — every field is accessed defensively so
// missing/extra fields never crash the transcript.

import { Search } from "@carbon/icons-react";

const SNIPPET_LIMIT = 300;

function ChunkRow({ chunk, first }: { chunk: any; first: boolean }) {
  const c = chunk || {};
  const kind = typeof c.kind === "string" && c.kind ? c.kind : "artifact";
  const name = typeof c.name === "string" && c.name ? c.name : "(unnamed)";
  const scope = c.cube || c.dimension;
  const method = typeof c.method === "string" && c.method ? c.method : null;
  const score = typeof c.score === "number" && Number.isFinite(c.score) ? c.score.toFixed(2) : null;
  const badge = [method, score].filter(Boolean).join(" · ");
  const raw = typeof c.snippet === "string" ? c.snippet : "";
  const snippet = raw.length > SNIPPET_LIMIT ? `${raw.slice(0, SNIPPET_LIMIT)}…` : raw;
  return (
    <div style={{ marginTop: first ? 0 : 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <span className="tag-inline">{kind}</span>
        <b style={{ fontSize: 12.5 }}>{name}</b>
        {scope && (
          <span style={{ fontSize: 12, color: "var(--cds-text-secondary)" }}>({String(scope)})</span>
        )}
        <span className="grow" />
        {badge && <span className="tag-inline">{badge}</span>}
      </div>
      {snippet && (
        <code
          style={{
            display: "block",
            marginTop: 4,
            padding: "6px 8px",
            fontSize: 11.5,
            lineHeight: 1.45,
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            background: "var(--cds-layer-01, rgba(125,125,125,.08))",
            borderRadius: 4,
          }}
        >
          {snippet}
        </code>
      )}
    </div>
  );
}

export function GroundingSourcesBlock({ data }: { data: any }) {
  const d = data || {};
  const chunks: any[] = Array.isArray(d.chunks) ? d.chunks : [];
  const purpose = typeof d.purpose === "string" && d.purpose ? d.purpose : null;
  const query = typeof d.query === "string" && d.query ? d.query : null;
  return (
    <div className="block-card">
      <div className="block-head">
        <Search size={16} />{" "}
        <span>
          {chunks.length > 0
            ? `Grounded on ${chunks.length} artifact${chunks.length === 1 ? "" : "s"}`
            : "Grounding"}
        </span>
        <span className="grow" />
        {purpose && <span className="tag-inline">{purpose}</span>}
      </div>
      <div className="block-body">
        {chunks.length === 0 ? (
          <div style={{ fontSize: 12, color: "var(--cds-text-secondary)" }}>No grounding sources.</div>
        ) : (
          <>
            {query && (
              <div style={{ fontSize: 12, color: "var(--cds-text-secondary)", marginBottom: 8 }}>
                Query: <span className="mono">{query}</span>
              </div>
            )}
            {chunks.map((c, i) => (
              <ChunkRow chunk={c} first={i === 0} key={i} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
