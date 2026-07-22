/**
 * Inline-SVG diagrams shared by the public landing (/) and docs (/docs) pages.
 * Hand-built SVG (same precedent as the Guide's diagrams and the cube map): no
 * image assets, no libraries, nothing fetched. Fixed dark palette because the
 * container is always dark.
 *
 * Self-drawing: stroked connectors carry `pathLength="1"` and the class
 * `md-draw`, so the page CSS can animate `stroke-dashoffset` from 1 → 0 the
 * first time the figure scrolls into view (`.in-view`). At rest — and under
 * `prefers-reduced-motion` — the strokes render fully drawn. The boxes and
 * labels are always present, so the diagram is complete and legible with no
 * motion at all.
 */

// Palette mirrors the Guide diagrams (blocks/, GuidePage) so the whole product
// reads as one system.
const C = {
  code: "#4589ff", // deterministic application code
  llm: "#be95ff", // language model — proposes only
  human: "#42be65", // you
  store: "#f1c21b", // encrypted local secret store
  warn: "#fa4d56", // a denied / never-crossed path
  muted: "#8d8d8d",
  line: "#6f6f6f",
  panel: "#262626",
  stroke: "#393939", // hairline borders on the enclosure / boundary
  text: "#f4f4f4",
  sub: "#9a9a9a",
} as const;

function Box({
  x,
  y,
  w,
  h = 56,
  label,
  sub,
  stroke,
}: {
  x: number;
  y: number;
  w: number;
  h?: number;
  label: string;
  sub?: string;
  stroke: string;
}) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={2} fill={C.panel} stroke={stroke} strokeWidth={1.5} />
      <text x={x + w / 2} y={sub ? y + h / 2 - 3 : y + h / 2 + 4} textAnchor="middle" fill={C.text} fontSize={12.5} fontWeight={600}>
        {label}
      </text>
      {sub && (
        <text x={x + w / 2} y={y + h / 2 + 14} textAnchor="middle" fill={C.sub} fontSize={10}>
          {sub}
        </text>
      )}
    </g>
  );
}

/**
 * Trust-boundary / architecture diagram: everything that touches secrets stays
 * on your machine; only deterministic code crosses the connector boundary to
 * the Oracle tenant, carrying metadata and artifacts — never credentials, and
 * never the model itself.
 */
export function TrustBoundaryDiagram() {
  const seg = (i: number): React.CSSProperties => ({ "--seg": i }) as unknown as React.CSSProperties;
  return (
    <svg
      className="md-svg"
      viewBox="0 0 840 372"
      role="img"
      aria-label="Trust boundary diagram. On your machine: you approve every change; a deterministic code layer validates and ships; a language model proposes only; and an encrypted secret store holds credentials that never leave. Only the deterministic code crosses the connector boundary to the Oracle EPM tenant, carrying metadata, rules, and artifacts — never secrets, and never the model."
    >
      <defs>
        <marker id="md-arrow" viewBox="0 0 10 10" refX={9} refY={5} markerWidth={7} markerHeight={7} orient="auto-start-reverse">
          <path d="M 0 1 L 9 5 L 0 9 z" fill={C.line} />
        </marker>
      </defs>

      {/* your-machine enclosure */}
      <rect x={16} y={40} width={476} height={312} rx={3} fill="none" stroke={C.stroke} strokeWidth={1} strokeDasharray="2 4" />
      <text x={28} y={30} fill={C.muted} fontSize={11} letterSpacing="0.12em" fontFamily="'IBM Plex Mono', monospace">
        YOUR MACHINE
      </text>

      {/* nodes inside the machine */}
      <Box x={40} y={64} w={196} label="You" sub="approve every change" stroke={C.human} />
      <Box x={40} y={158} w={196} label="Encrypted secret store" sub="sealed · secrets never leave" stroke={C.store} />
      <Box x={40} y={264} w={196} label="Language model" sub="proposes only" stroke={C.llm} />
      <Box x={276} y={158} w={196} label="Deterministic code" sub="validates & ships" stroke={C.code} />

      {/* internal connectors (self-drawing) */}
      {/* secret store -> code : unlocks the tenant connection */}
      <line className="md-draw" style={seg(0)} pathLength={1} x1={236} y1={186} x2={276} y2={186} stroke={C.line} strokeWidth={1.5} markerEnd="url(#md-arrow)" />
      {/* you -> code : approve */}
      <path className="md-draw" style={seg(1)} pathLength={1} d="M 236 92 L 374 92 L 374 158" fill="none" stroke={C.line} strokeWidth={1.5} markerEnd="url(#md-arrow)" />
      {/* llm -> code : proposes a spec */}
      <path className="md-draw" style={seg(2)} pathLength={1} d="M 236 292 L 374 292 L 374 214" fill="none" stroke={C.line} strokeWidth={1.5} markerEnd="url(#md-arrow)" />

      {/* secret store -> language model : DENIED. Static dashed line (not
          routed through the md-draw reveal, whose stroke-dasharray:1 would
          override "4 3" and render it solid), so the "blocked" dashes show in
          every state. */}
      <line className="md-draw-deny" x1={138} y1={214} x2={138} y2={264} stroke={C.warn} strokeWidth={1.5} strokeDasharray="4 3" />
      <g>
        <circle cx={138} cy={239} r={9} fill={C.panel} stroke={C.warn} strokeWidth={1.5} />
        <line x1={132} y1={245} x2={144} y2={233} stroke={C.warn} strokeWidth={1.5} />
      </g>
      <text x={156} y={243} fill={C.warn} fontSize={10} fontFamily="'IBM Plex Mono', monospace">
        never sent to the model
      </text>

      {/* connector boundary */}
      <line x1={556} y1={40} x2={556} y2={352} stroke={C.muted} strokeWidth={1} strokeDasharray="3 4" />
      <text x={556} y={30} textAnchor="middle" fill={C.muted} fontSize={11} letterSpacing="0.1em" fontFamily="'IBM Plex Mono', monospace">
        CONNECTOR BOUNDARY
      </text>
      <text x={556} y={344} textAnchor="middle" fill={C.muted} fontSize={9.5} fontFamily="'IBM Plex Mono', monospace">
        the model can&rsquo;t cross
      </text>

      {/* the only crossing: deterministic code -> tenant */}
      <path
        className="md-draw"
        style={seg(3)}
        pathLength={1}
        d="M 472 186 L 636 186"
        fill="none"
        stroke={C.code}
        strokeWidth={1.75}
        markerEnd="url(#md-arrow)"
      />
      <text x={554} y={176} textAnchor="middle" fill={C.sub} fontSize={10} fontFamily="'IBM Plex Mono', monospace">
        metadata · rules · artifacts
      </text>

      {/* the tenant, outside the machine */}
      <Box x={636} y={150} w={188} h={72} label="Oracle EPM tenant" sub="Planning · documented REST" stroke={C.muted} />
    </svg>
  );
}
