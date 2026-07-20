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

const NODE_W = 150;
const NODE_H = 40;

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

function Node({
  d,
  x,
  y,
  onClick,
  isHovered,
  onHover,
  isHighlighted
}: {
  d: DimensionNode;
  x: number;
  y: number;
  onClick: () => void;
  isHovered: boolean;
  onHover: (hovered: boolean) => void;
  isHighlighted: boolean;
}) {
  const color = STATUS_COLOR[d.status ?? "available"] || "#525252";
  const scale = isHovered ? 1.05 : 1;
  const opacity = isHighlighted ? 1 : (isHovered ? 1 : 0.9);

  return (
    <g
      transform={`translate(${x},${y})`}
      style={{
        cursor: "pointer",
        transition: "all 0.2s ease-out"
      }}
      onClick={onClick}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      <g transform={`scale(${scale})`} style={{ transformOrigin: `${NODE_W/2}px ${NODE_H/2}px` }}>
        {/* Hover glow effect */}
        {isHovered && (
          <rect
            width={NODE_W + 8}
            height={NODE_H + 8}
            x={-4}
            y={-4}
            rx={4}
            fill={color}
            opacity={0.15}
          />
        )}
        <rect
          width={NODE_W}
          height={NODE_H}
          rx={2}
          fill={isHovered ? "#262626" : "#1f1f1f"}
          stroke={color}
          strokeWidth={isHovered ? 2 : 1.5}
          opacity={opacity}
        />
        <rect width={4} height={NODE_H} fill={color} opacity={opacity} />
        <text x={12} y={16} fill="#f4f4f4" fontSize={12} fontWeight={isHovered ? 700 : 600}>
          {d.name.length > 16 ? d.name.slice(0, 15) + "…" : d.name}
        </text>
        <text x={12} y={31} fill="#a8a8a8" fontSize={10}>
          {d.type}
          {d.memberCount != null ? ` · ${d.memberCount}` : ""}
          {d.usedOnAxis ? ` · ${d.usedOnAxis}` : ""}
        </text>
      </g>
    </g>
  );
}

export function CubeArchitectureBlock({ data, onAction }: { data: CubeArchitecture; onAction: (v: string) => void }) {
  const [showTable, setShowTable] = useState(true);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement>(null);

  const z = zones(data);
  const colH = Math.max(z.left.length, z.right.length, 1) * (NODE_H + 14);
  const midWidth = Math.max(z.top.length, z.bottom.length, 2) * (NODE_W + 16);
  const width = Math.max(midWidth + 2 * (NODE_W + 40), 640);
  const height = colH + 2 * (NODE_H + 60) + 40;
  const cx = width / 2;
  const cy = height / 2;
  const cubeW = 170;
  const cubeH = 74;

  // Filter dimensions based on search query
  const filteredDimensions = data.dimensions.filter(d =>
    d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.type.toLowerCase().includes(searchQuery.toLowerCase())
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

  const handleWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const delta = e.deltaY * -0.001;
    const newZoom = Math.min(Math.max(0.5, zoom + delta), 3);
    setZoom(newZoom);
  };

  const place = (arr: DimensionNode[], zone: string) =>
    arr.map((d, i) => {
      let x = 0;
      let y = 0;
      if (zone === "top") {
        x = cx - ((arr.length * (NODE_W + 16)) / 2) + i * (NODE_W + 16) + 8;
        y = 20;
      } else if (zone === "bottom") {
        x = cx - ((arr.length * (NODE_W + 16)) / 2) + i * (NODE_W + 16) + 8;
        y = height - NODE_H - 20;
      } else if (zone === "left") {
        x = 20;
        y = cy - ((arr.length * (NODE_H + 14)) / 2) + i * (NODE_H + 14);
      } else {
        x = width - NODE_W - 20;
        y = cy - ((arr.length * (NODE_H + 14)) / 2) + i * (NODE_H + 14);
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
        </div>

        <div className="cube-map-wrap" style={{ position: "relative", overflow: "hidden", background: "#0f0f0f", borderRadius: 4 }}>
          <svg
            ref={svgRef}
            className="cube-map"
            viewBox={`0 0 ${width} ${height}`}
            width="100%"
            style={{
              maxHeight: 520,
              cursor: isDragging ? "grabbing" : "grab",
              transition: isDragging ? "none" : "transform 0.1s ease-out"
            }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onWheel={handleWheel}
          >
            <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
              {/* Connection lines with animations */}
              {all.map(({ d, x, y }, i) => {
                const highlighted = isHighlighted(d.name);
                const lineColor = hoveredNode === d.name ? STATUS_COLOR[d.status ?? "available"] : "#393939";
                return (
                  <line
                    key={`l${i}`}
                    x1={cx}
                    y1={cy}
                    x2={x + NODE_W / 2}
                    y2={y + NODE_H / 2}
                    stroke={lineColor}
                    strokeWidth={hoveredNode === d.name ? 2 : 1}
                    opacity={highlighted ? (hoveredNode === d.name ? 0.8 : 0.3) : 0.1}
                    style={{ transition: "all 0.2s ease-out" }}
                  />
                );
              })}

              {/* Central cube with pulse animation */}
              <g>
                <rect
                  x={cx - cubeW / 2}
                  y={cy - cubeH / 2}
                  width={cubeW}
                  height={cubeH}
                  rx={3}
                  fill="#262626"
                  stroke="#4589ff"
                  strokeWidth={2}
                  style={{
                    filter: hoveredNode ? "drop-shadow(0 0 8px rgba(69, 137, 255, 0.4))" : "none",
                    transition: "filter 0.3s ease-out"
                  }}
                />
                <text x={cx} y={cy - 4} fill="#f4f4f4" fontSize={16} fontWeight={600} textAnchor="middle">
                  {data.cube}
                </text>
                <text x={cx} y={cy + 16} fill="#a8a8a8" fontSize={11} textAnchor="middle">
                  {data.application}
                </text>
              </g>

              {/* Dimension nodes */}
              {all.map(({ d, x, y }, i) => (
                <Node
                  key={i}
                  d={d}
                  x={x}
                  y={y}
                  onClick={() => onAction(`inspect ${d.name} hierarchy`)}
                  isHovered={hoveredNode === d.name}
                  onHover={(hovered) => setHoveredNode(hovered ? d.name : null)}
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
