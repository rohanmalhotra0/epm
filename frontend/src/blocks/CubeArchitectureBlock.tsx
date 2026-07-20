import { useState, useRef, useEffect } from "react";
import { Types, ZoomIn, ZoomOut, Search } from "@carbon/icons-react";
import type { CubeArchitecture, DimensionNode } from "../schemas/types";

const STATUS_COLOR: Record<string, string> = {
  selected: "#4589ff",
  missing: "#ff832b",
  defaulted: "#8d8d8d",
  available: "#525252",
  duplicate: "#be95ff",
  invalid: "#da1e28",
};

const NODE_W = 180;
const NODE_H = 130;

function zones(model: CubeArchitecture): Record<string, DimensionNode[]> {
  const z: Record<string, DimensionNode[]> = { top: [], left: [], right: [], bottom: [] };
  const hasForm = !!model.formCoverage;
  for (const d of model.dimensions) {
    if (hasForm) {
      if (d.usedOnAxis === "pov") z.top.push(d);
      else if (d.usedOnAxis === "pages") z.left.push(d);
      else if (d.usedOnAxis === "columns") z.right.push(d);
      else if (d.usedOnAxis === "rows") z.bottom.push(d);
      else z.bottom.push(d);
    } else {
      if (d.group === "context" || d.group === "time") z.top.push(d);
      else if (d.group === "organization") z.left.push(d);
      else if (d.group === "financial") z.right.push(d);
      else z.bottom.push(d);
    }
  }
  return z;
}

function CubeCard({
  d,
  x,
  y,
  onClick,
  isHovered,
  onHover,
  isExpanded,
  isHighlighted
}: {
  d: DimensionNode;
  x: number;
  y: number;
  onClick: () => void;
  isHovered: boolean;
  onHover: (hovered: boolean) => void;
  isExpanded: boolean;
  isHighlighted: boolean;
}) {
  const color = STATUS_COLOR[d.status ?? "available"] || "#525252";
  const scale = isExpanded ? 1.15 : (isHovered ? 1.05 : 1);
  const opacity = isHighlighted ? 1 : (isHovered ? 1 : 0.85);

  // Calculate dimensions list
  const dimensions = [];
  if (d.type) dimensions.push({ label: "Type", value: d.type });
  if (d.memberCount != null) dimensions.push({ label: "Members", value: d.memberCount.toString() });
  if (d.usedOnAxis) dimensions.push({ label: "Axis", value: d.usedOnAxis });
  if (d.group) dimensions.push({ label: "Group", value: d.group });

  return (
    <g
      transform={`translate(${x},${y})`}
      style={{
        cursor: "pointer",
        transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        transformOrigin: "center"
      }}
      onClick={onClick}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      <g
        transform={`scale(${scale})`}
        style={{
          transformOrigin: `${NODE_W/2}px ${NODE_H/2}px`,
          transition: "transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
        }}
      >
        {/* Outer glow for expanded state */}
        {isExpanded && (
          <rect
            width={NODE_W + 16}
            height={NODE_H + 16}
            x={-8}
            y={-8}
            rx={6}
            fill={color}
            opacity={0.2}
          />
        )}

        {/* Hover glow effect */}
        {isHovered && !isExpanded && (
          <rect
            width={NODE_W + 8}
            height={NODE_H + 8}
            x={-4}
            y={-4}
            rx={5}
            fill={color}
            opacity={0.12}
          />
        )}

        {/* Main card */}
        <rect
          width={NODE_W}
          height={NODE_H}
          rx={4}
          fill={isExpanded ? "#2a2a2a" : (isHovered ? "#262626" : "#1f1f1f")}
          stroke={color}
          strokeWidth={isExpanded ? 2.5 : (isHovered ? 2 : 1.5)}
          opacity={opacity}
        />

        {/* Top accent bar */}
        <rect
          width={NODE_W}
          height={6}
          rx={4}
          fill={color}
          opacity={isExpanded ? 0.9 : 0.7}
        />

        {/* Title */}
        <text
          x={NODE_W / 2}
          y={28}
          fill="#f4f4f4"
          fontSize={isExpanded ? 16 : 14}
          fontWeight={isExpanded ? 700 : 600}
          textAnchor="middle"
        >
          {d.name.length > (isExpanded ? 20 : 16)
            ? d.name.slice(0, isExpanded ? 19 : 15) + "…"
            : d.name}
        </text>

        {/* Subtitle */}
        <text
          x={NODE_W / 2}
          y={46}
          fill="#8d8d8d"
          fontSize={11}
          textAnchor="middle"
        >
          {d.type || "Custom"}
        </text>

        {/* Member count badge */}
        {d.memberCount != null && (
          <>
            <rect
              x={NODE_W / 2 - 30}
              y={56}
              width={60}
              height={22}
              rx={3}
              fill={isExpanded ? color : "#161616"}
              opacity={isExpanded ? 0.2 : 0.8}
            />
            <text
              x={NODE_W / 2}
              y={71}
              fill={isExpanded ? color : "#a8a8a8"}
              fontSize={isExpanded ? 15 : 13}
              fontWeight={isExpanded ? 700 : 600}
              textAnchor="middle"
            >
              {d.memberCount}
            </text>
          </>
        )}

        {/* Expanded details */}
        {isExpanded && (
          <>
            <line
              x1={12}
              y1={86}
              x2={NODE_W - 12}
              y2={86}
              stroke="#393939"
              strokeWidth={1}
            />

            {dimensions.slice(0, 3).map((dim, i) => (
              <g key={i}>
                <text
                  x={16}
                  y={102 + i * 14}
                  fill="#8d8d8d"
                  fontSize={9}
                  textAnchor="start"
                >
                  {dim.label}
                </text>
                <text
                  x={NODE_W - 16}
                  y={102 + i * 14}
                  fill="#f4f4f4"
                  fontSize={9}
                  fontWeight={600}
                  textAnchor="end"
                >
                  {dim.value}
                </text>
              </g>
            ))}
          </>
        )}

        {/* Expand indicator */}
        <g transform={`translate(${NODE_W/2}, ${NODE_H - 8})`}>
          <circle r={6} fill={isExpanded ? color : "#393939"} opacity={0.6} />
          <g transform={`rotate(${isExpanded ? 180 : 0})`}>
            <line x1={-3} y1={-1} x2={0} y2={2} stroke="#f4f4f4" strokeWidth={1.5} strokeLinecap="round" />
            <line x1={0} y1={2} x2={3} y2={-1} stroke="#f4f4f4" strokeWidth={1.5} strokeLinecap="round" />
          </g>
        </g>
      </g>
    </g>
  );
}

export function CubeArchitectureBlock({ data }: { data: CubeArchitecture; onAction: (v: string) => void }) {
  const [showTable, setShowTable] = useState(true);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [expandedNode, setExpandedNode] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement>(null);

  const z = zones(data);
  const spacing = 40;
  const colH = Math.max(z.left.length, z.right.length, 1) * (NODE_H + spacing);
  const midWidth = Math.max(z.top.length, z.bottom.length, 2) * (NODE_W + spacing);
  const width = Math.max(midWidth + 2 * (NODE_W + 80), 900);
  const height = colH + 2 * (NODE_H + 80) + 80;
  const cx = width / 2;
  const cy = height / 2;
  const cubeW = 200;
  const cubeH = 90;

  // Filter dimensions based on search query
  const filteredDimensions = data.dimensions.filter(d =>
    d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (d.type ?? "").toLowerCase().includes(searchQuery.toLowerCase())
  );

  const isHighlighted = (dimName: string) => {
    if (!searchQuery) return true;
    return filteredDimensions.some(d => d.name === dimName);
  };

  // Handle mouse events for pan
  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button !== 0) return; // Only left click
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const panStep = 20;
      const zoomStep = 0.2;

      switch (e.key) {
        case "ArrowUp":
          e.preventDefault();
          setPan(prev => ({ ...prev, y: prev.y + panStep }));
          break;
        case "ArrowDown":
          e.preventDefault();
          setPan(prev => ({ ...prev, y: prev.y - panStep }));
          break;
        case "ArrowLeft":
          e.preventDefault();
          setPan(prev => ({ ...prev, x: prev.x + panStep }));
          break;
        case "ArrowRight":
          e.preventDefault();
          setPan(prev => ({ ...prev, x: prev.x - panStep }));
          break;
        case "+":
        case "=":
          e.preventDefault();
          setZoom(prev => Math.min(3, prev + zoomStep));
          break;
        case "-":
        case "_":
          e.preventDefault();
          setZoom(prev => Math.max(0.5, prev - zoomStep));
          break;
        case "0":
          e.preventDefault();
          setZoom(1);
          setPan({ x: 0, y: 0 });
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const place = (arr: DimensionNode[], zone: string) =>
    arr.map((d, i) => {
      let x = 0;
      let y = 0;
      if (zone === "top") {
        x = cx - ((arr.length * (NODE_W + spacing)) / 2) + i * (NODE_W + spacing);
        y = 40;
      } else if (zone === "bottom") {
        x = cx - ((arr.length * (NODE_W + spacing)) / 2) + i * (NODE_W + spacing);
        y = height - NODE_H - 40;
      } else if (zone === "left") {
        x = 40;
        y = cy - ((arr.length * (NODE_H + spacing)) / 2) + i * (NODE_H + spacing);
      } else {
        x = width - NODE_W - 40;
        y = cy - ((arr.length * (NODE_H + spacing)) / 2) + i * (NODE_H + spacing);
      }
      return { d, x, y };
    });

  const all = [...place(z.top, "top"), ...place(z.bottom, "bottom"), ...place(z.left, "left"), ...place(z.right, "right")];

  return (
    <div className="block-card">
      <div className="block-head">
        <Types size={16} />
        <span>Cube architecture — {data.cube}</span>
        <span className="grow" />
        <span className="tag-inline">{data.dimensionCount} dimensions</span>
      </div>
      <div className="block-body">
        {/* Controls row */}
        <div style={{
          display: "flex",
          gap: 12,
          marginBottom: 12,
          padding: "8px 12px",
          background: "#262626",
          borderRadius: 4,
          alignItems: "center"
        }}>
          <div style={{ position: "relative", flex: 1, maxWidth: 300 }}>
            <Search size={16} style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: "#8d8d8d" }} />
            <input
              type="text"
              placeholder="Search dimensions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: "100%",
                padding: "6px 8px 6px 32px",
                background: "#1f1f1f",
                border: "1px solid #393939",
                borderRadius: 3,
                color: "#f4f4f4",
                fontSize: 13
              }}
            />
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              onClick={() => setZoom(Math.max(0.5, zoom - 0.2))}
              style={{
                padding: 6,
                background: "#1f1f1f",
                border: "1px solid #393939",
                borderRadius: 3,
                cursor: "pointer",
                display: "flex",
                alignItems: "center"
              }}
              title="Zoom out"
            >
              <ZoomOut size={16} color="#f4f4f4" />
            </button>
            <span style={{ fontSize: 12, color: "#a8a8a8", minWidth: 45, textAlign: "center" }}>
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => setZoom(Math.min(3, zoom + 0.2))}
              style={{
                padding: 6,
                background: "#1f1f1f",
                border: "1px solid #393939",
                borderRadius: 3,
                cursor: "pointer",
                display: "flex",
                alignItems: "center"
              }}
              title="Zoom in"
            >
              <ZoomIn size={16} color="#f4f4f4" />
            </button>
            <button
              onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}
              style={{
                padding: "6px 12px",
                background: "#1f1f1f",
                border: "1px solid #393939",
                borderRadius: 3,
                cursor: "pointer",
                fontSize: 12,
                color: "#f4f4f4"
              }}
            >
              Reset
            </button>
          </div>
          <div style={{ fontSize: 11, color: "#8d8d8d", marginLeft: "auto" }}>
            Arrow keys: pan • +/−: zoom • 0: reset
          </div>
        </div>

        <div className="cube-map-wrap" style={{ position: "relative", overflow: "hidden", background: "#0f0f0f", borderRadius: 4 }}>
          <svg
            ref={svgRef}
            className="cube-map"
            viewBox={`0 0 ${width} ${height}`}
            width="100%"
            style={{
              minHeight: 600,
              cursor: isDragging ? "grabbing" : "grab",
              transition: isDragging ? "none" : "transform 0.1s ease-out"
            }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
          >
            <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
              {/* Connection lines with animations */}
              {all.map(({ d, x, y }, i) => {
                const highlighted = isHighlighted(d.name);
                const isActive = hoveredNode === d.name || expandedNode === d.name;
                const lineColor = isActive ? STATUS_COLOR[d.status ?? "available"] : "#393939";
                const lineOpacity = highlighted
                  ? (isActive ? 0.7 : (expandedNode ? 0.15 : 0.25))
                  : 0.08;
                return (
                  <line
                    key={`l${i}`}
                    x1={cx}
                    y1={cy}
                    x2={x + NODE_W / 2}
                    y2={y + NODE_H / 2}
                    stroke={lineColor}
                    strokeWidth={isActive ? 2.5 : 1}
                    opacity={lineOpacity}
                    strokeDasharray={expandedNode && expandedNode !== d.name ? "4 4" : "none"}
                    style={{ transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)" }}
                  />
                );
              })}

              {/* Central cube with enhanced design */}
              <g>
                {/* Outer glow */}
                {hoveredNode && (
                  <rect
                    x={cx - cubeW / 2 - 8}
                    y={cy - cubeH / 2 - 8}
                    width={cubeW + 16}
                    height={cubeH + 16}
                    rx={8}
                    fill="#4589ff"
                    opacity={0.15}
                  />
                )}

                {/* Main cube */}
                <rect
                  x={cx - cubeW / 2}
                  y={cy - cubeH / 2}
                  width={cubeW}
                  height={cubeH}
                  rx={5}
                  fill="#1a1a1a"
                  stroke="#4589ff"
                  strokeWidth={2.5}
                  style={{
                    filter: hoveredNode ? "drop-shadow(0 0 12px rgba(69, 137, 255, 0.5))" : "drop-shadow(0 2px 8px rgba(0, 0, 0, 0.3))",
                    transition: "filter 0.3s ease-out"
                  }}
                />

                {/* Top accent */}
                <rect
                  x={cx - cubeW / 2}
                  y={cy - cubeH / 2}
                  width={cubeW}
                  height={8}
                  rx={5}
                  fill="#4589ff"
                  opacity={0.6}
                />

                {/* Cube name */}
                <text x={cx} y={cy + 2} fill="#f4f4f4" fontSize={18} fontWeight={700} textAnchor="middle">
                  {data.cube}
                </text>

                {/* Application */}
                <text x={cx} y={cy + 22} fill="#8d8d8d" fontSize={12} textAnchor="middle">
                  {data.application}
                </text>

                {/* Dimension count badge */}
                <rect
                  x={cx - 40}
                  y={cy + 32}
                  width={80}
                  height={20}
                  rx={3}
                  fill="#4589ff"
                  opacity={0.2}
                />
                <text x={cx} y={cy + 46} fill="#4589ff" fontSize={11} fontWeight={600} textAnchor="middle">
                  {data.dimensionCount} dimensions
                </text>
              </g>

              {/* Dimension nodes */}
              {all.map(({ d, x, y }, i) => (
                <CubeCard
                  key={i}
                  d={d}
                  x={x}
                  y={y}
                  onClick={() => {
                    setExpandedNode(expandedNode === d.name ? null : d.name);
                  }}
                  isHovered={hoveredNode === d.name}
                  onHover={(hovered) => setHoveredNode(hovered ? d.name : null)}
                  isExpanded={expandedNode === d.name}
                  isHighlighted={isHighlighted(d.name)}
                />
              ))}
            </g>
          </svg>

          {/* Tooltip */}
          {hoveredNode && (
            <div style={{
              position: "absolute",
              bottom: 12,
              left: 12,
              background: "rgba(26, 26, 26, 0.95)",
              border: "1px solid #393939",
              borderRadius: 4,
              padding: "8px 12px",
              fontSize: 12,
              color: "#f4f4f4",
              backdropFilter: "blur(8px)",
              boxShadow: "0 4px 12px rgba(0, 0, 0, 0.3)",
              maxWidth: 280
            }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{hoveredNode}</div>
              {(() => {
                const node = data.dimensions.find(d => d.name === hoveredNode);
                if (!node) return null;
                return (
                  <>
                    <div style={{ color: "#a8a8a8", fontSize: 11 }}>
                      Type: {node.type}
                      {node.memberCount != null && ` · ${node.memberCount} members`}
                    </div>
                    {node.usedOnAxis && (
                      <div style={{ color: "#a8a8a8", fontSize: 11 }}>
                        Axis: {node.usedOnAxis.toUpperCase()}
                      </div>
                    )}
                    {node.status && (
                      <div style={{
                        marginTop: 4,
                        padding: "2px 6px",
                        background: STATUS_COLOR[node.status],
                        borderRadius: 2,
                        fontSize: 10,
                        display: "inline-block"
                      }}>
                        {node.status}
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}
        </div>
        <div className="cube-legend">
          {["selected", "missing", "defaulted", "available"].map((s) => (
            <span key={s}>
              <span className="sw" style={{ background: STATUS_COLOR[s] }} />
              {s}
            </span>
          ))}
          <span style={{ marginLeft: "auto", cursor: "pointer" }} onClick={() => setShowTable((v) => !v)}>
            {showTable ? "Hide table" : "Show table"}
          </span>
        </div>
        {showTable && (
          <div className="grid-preview" style={{ marginTop: 12 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Dimension</th>
                  <th>Type</th>
                  <th style={{ textAlign: "right" }}>Members</th>
                  <th>Placement</th>
                  <th>Selection</th>
                </tr>
              </thead>
              <tbody>
                {data.dimensions.map((d) => (
                  <tr key={d.name}>
                    <td>{d.name}</td>
                    <td>{d.type === "custom" ? <em>Custom dimension</em> : d.type}</td>
                    <td style={{ textAlign: "right" }}>{d.memberCount ?? "—"}</td>
                    <td>{d.usedOnAxis ? d.usedOnAxis.toUpperCase() : data.formCoverage ? "Not assigned" : "—"}</td>
                    <td>{d.selectionSummary || d.selectedMember || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
