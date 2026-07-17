import { useState } from "react";
import { Types } from "@carbon/icons-react";
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

function Node({ d, x, y, onClick }: { d: DimensionNode; x: number; y: number; onClick: () => void }) {
  const color = STATUS_COLOR[d.status ?? "available"] || "#525252";
  return (
    <g transform={`translate(${x},${y})`} style={{ cursor: "pointer" }} onClick={onClick}>
      <rect width={NODE_W} height={NODE_H} rx={2} fill="#1f1f1f" stroke={color} strokeWidth={1.5} />
      <rect width={4} height={NODE_H} fill={color} />
      <text x={12} y={16} fill="#f4f4f4" fontSize={12} fontWeight={600}>
        {d.name.length > 16 ? d.name.slice(0, 15) + "…" : d.name}
      </text>
      <text x={12} y={31} fill="#a8a8a8" fontSize={10}>
        {d.type}
        {d.memberCount != null ? ` · ${d.memberCount}` : ""}
        {d.usedOnAxis ? ` · ${d.usedOnAxis}` : ""}
      </text>
    </g>
  );
}

export function CubeArchitectureBlock({ data, onAction }: { data: CubeArchitecture; onAction: (v: string) => void }) {
  const [showTable, setShowTable] = useState(true);
  const z = zones(data);
  const colH = Math.max(z.left.length, z.right.length, 1) * (NODE_H + 14);
  const midWidth = Math.max(z.top.length, z.bottom.length, 2) * (NODE_W + 16);
  const width = Math.max(midWidth + 2 * (NODE_W + 40), 640);
  const height = colH + 2 * (NODE_H + 60) + 40;
  const cx = width / 2;
  const cy = height / 2;
  const cubeW = 170;
  const cubeH = 74;

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
        <div className="cube-map-wrap">
          <svg className="cube-map" viewBox={`0 0 ${width} ${height}`} width="100%" style={{ maxHeight: 460 }}>
            {all.map(({ x, y }, i) => (
              <line
                key={`l${i}`}
                x1={cx}
                y1={cy}
                x2={x + NODE_W / 2}
                y2={y + NODE_H / 2}
                stroke="#393939"
                strokeWidth={1}
              />
            ))}
            <rect x={cx - cubeW / 2} y={cy - cubeH / 2} width={cubeW} height={cubeH} rx={3} fill="#262626" stroke="#4589ff" strokeWidth={2} />
            <text x={cx} y={cy - 4} fill="#f4f4f4" fontSize={16} fontWeight={600} textAnchor="middle">
              {data.cube}
            </text>
            <text x={cx} y={cy + 16} fill="#a8a8a8" fontSize={11} textAnchor="middle">
              {data.application}
            </text>
            {all.map(({ d, x, y }, i) => (
              <Node key={i} d={d} x={x} y={y} onClick={() => onAction(`inspect ${d.name} hierarchy`)} />
            ))}
          </svg>
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
