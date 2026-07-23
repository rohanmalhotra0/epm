import {
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import {
  Button,
  Search as SearchInput,
} from "@carbon/react";
import {
  ListBoxes,
  Reset,
  Types,
  ZoomIn,
  ZoomOut,
} from "@carbon/icons-react";
import type { CubeArchitecture, DimensionNode } from "../schemas/types";
import "./CubeArchitectureBlock.css";

const NODE_W = 188;
const NODE_H = 108;
const MIN_ZOOM = 0.65;
const MAX_ZOOM = 1.85;
const ZOOM_STEP = 0.15;

type ZoneName = "top" | "left" | "right" | "bottom";

interface PlacedDimension {
  d: DimensionNode;
  x: number;
  y: number;
  zone: ZoneName;
}

const STATUS_LABELS: Record<string, string> = {
  selected: "Selected",
  missing: "Missing",
  defaulted: "Defaulted",
  available: "Available",
  duplicate: "Duplicate",
  invalid: "Invalid",
};

function statusKey(status?: string): string {
  return STATUS_LABELS[status ?? "available"] ? (status ?? "available") : "available";
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function displayValue(value?: string | null): string {
  if (!value) return "Not set";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function zones(model: CubeArchitecture): Record<ZoneName, DimensionNode[]> {
  const result: Record<ZoneName, DimensionNode[]> = {
    top: [],
    left: [],
    right: [],
    bottom: [],
  };
  const hasForm = Boolean(model.formCoverage);

  for (const dimension of model.dimensions) {
    if (hasForm) {
      if (dimension.usedOnAxis === "pov") result.top.push(dimension);
      else if (dimension.usedOnAxis === "pages") result.left.push(dimension);
      else if (dimension.usedOnAxis === "columns") result.right.push(dimension);
      else result.bottom.push(dimension);
    } else {
      if (dimension.group === "context" || dimension.group === "time") result.top.push(dimension);
      else if (dimension.group === "organization") result.left.push(dimension);
      else if (dimension.group === "financial") result.right.push(dimension);
      else result.bottom.push(dimension);
    }
  }

  return result;
}

function DimensionCard({
  dimension,
  x,
  y,
  index,
  selected,
  active,
  muted,
  onSelect,
  onHover,
}: {
  dimension: DimensionNode;
  x: number;
  y: number;
  index: number;
  selected: boolean;
  active: boolean;
  muted: boolean;
  onSelect: () => void;
  onHover: (hovered: boolean) => void;
}) {
  const status = statusKey(dimension.status);
  const secondary = dimension.usedOnAxis || dimension.group || dimension.type || "custom";

  return (
    <foreignObject
      x={x}
      y={y}
      width={NODE_W}
      height={NODE_H}
      className="architecture-node-enter"
      style={{ animationDelay: `${Math.min(index * 18, 144)}ms` }}
    >
      <button
        type="button"
        className="architecture-node"
        data-status={status}
        data-active={active || undefined}
        data-muted={muted || undefined}
        aria-pressed={selected}
        aria-label={`${dimension.name}, ${displayValue(dimension.type)}, ${
          dimension.memberCount == null ? "member count unavailable" : `${formatNumber(dimension.memberCount)} members`
        }`}
        onClick={onSelect}
        onFocus={() => onHover(true)}
        onBlur={() => onHover(false)}
        onPointerEnter={() => onHover(true)}
        onPointerLeave={() => onHover(false)}
      >
        <span className="architecture-node-topline">
          <span className="architecture-status-dot" aria-hidden="true" />
          <span className="architecture-node-status">{STATUS_LABELS[status]}</span>
        </span>
        <strong title={dimension.name}>{dimension.name}</strong>
        <span className="architecture-node-meta">
          <span>{displayValue(secondary)}</span>
          <span className="architecture-node-members tabular-nums">
            {dimension.memberCount == null ? "—" : formatNumber(dimension.memberCount)}
            <small> members</small>
          </span>
        </span>
      </button>
    </foreignObject>
  );
}

function DimensionInspector({
  dimension,
  searchHasNoMatches,
}: {
  dimension: DimensionNode | null;
  searchHasNoMatches: boolean;
}) {
  if (!dimension) {
    return (
      <aside className="dimension-inspector" aria-live="polite">
        <div className="dimension-inspector-empty">
          <Types size={20} aria-hidden="true" />
          <strong>{searchHasNoMatches ? "No dimensions found" : "Select a dimension"}</strong>
          <p className="text-pretty">
            {searchHasNoMatches
              ? "Try a different name or dimension type."
              : "Choose a node to inspect its type, placement, members, and selection."}
          </p>
        </div>
      </aside>
    );
  }

  const status = statusKey(dimension.status);

  return (
    <aside className="dimension-inspector" aria-live="polite" aria-label={`${dimension.name} details`}>
      <div className="dimension-inspector-heading">
        <span className="architecture-status-dot" data-status={status} aria-hidden="true" />
        <div>
          <span>{STATUS_LABELS[status]}</span>
          <h4 className="text-balance">{dimension.name}</h4>
        </div>
      </div>
      {dimension.alias && dimension.alias !== dimension.name && (
        <p className="dimension-alias text-pretty">{dimension.alias}</p>
      )}
      <dl className="dimension-facts">
        <div>
          <dt>Type</dt>
          <dd>{displayValue(dimension.type)}</dd>
        </div>
        <div>
          <dt>Group</dt>
          <dd>{displayValue(dimension.group)}</dd>
        </div>
        <div>
          <dt>Members</dt>
          <dd className="tabular-nums">
            {dimension.memberCount == null ? "Unavailable" : formatNumber(dimension.memberCount)}
          </dd>
        </div>
        <div>
          <dt>Placement</dt>
          <dd>{dimension.usedOnAxis ? dimension.usedOnAxis.toUpperCase() : "Not assigned"}</dd>
        </div>
      </dl>
      {(dimension.selectionSummary || dimension.selectedMember) && (
        <div className="dimension-selection">
          <span>Selection</span>
          <strong>{dimension.selectionSummary || dimension.selectedMember}</strong>
        </div>
      )}
      {dimension.rootMembers.length > 0 && (
        <div className="dimension-roots">
          <span>Root members</span>
          <ul>
            {dimension.rootMembers.slice(0, 4).map((member) => <li key={member}>{member}</li>)}
          </ul>
          {dimension.rootMembers.length > 4 && (
            <small className="tabular-nums">+{dimension.rootMembers.length - 4} more</small>
          )}
        </div>
      )}
    </aside>
  );
}

export function CubeArchitectureBlock({
  data,
  onAction: _onAction,
  showHeader = true,
}: {
  data: CubeArchitecture;
  onAction: (value: string) => void;
  showHeader?: boolean;
}) {
  const [showTable, setShowTable] = useState(false);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [drag, setDrag] = useState<{
    pointerId: number;
    x: number;
    y: number;
    panX: number;
    panY: number;
  } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const grouped = useMemo(() => zones(data), [data]);
  const spacing = 34;
  const columnHeight = Math.max(grouped.left.length, grouped.right.length, 1) * (NODE_H + spacing);
  const middleWidth = Math.max(grouped.top.length, grouped.bottom.length, 2) * (NODE_W + spacing);
  const width = Math.max(middleWidth + 2 * (NODE_W + 88), 980);
  const height = Math.max(columnHeight + 2 * (NODE_H + 84) + 72, 650);
  const centerX = width / 2;
  const centerY = height / 2;
  const cubeWidth = 220;
  const cubeHeight = 128;

  const query = searchQuery.trim().toLowerCase();
  const matchingDimensions = useMemo(
    () => data.dimensions.filter((dimension) =>
      [dimension.name, dimension.alias, dimension.type, dimension.group, dimension.usedOnAxis]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))),
    [data.dimensions, query],
  );
  const matchNames = useMemo(
    () => new Set(matchingDimensions.map((dimension) => dimension.name)),
    [matchingDimensions],
  );
  const selectedDimension =
    data.dimensions.find((dimension) => dimension.name === selectedNode) ?? null;
  const knownMembers = data.dimensions.reduce(
    (sum, dimension) => sum + (dimension.memberCount ?? 0),
    0,
  );
  const assignedDimensions = data.dimensions.filter((dimension) => dimension.usedOnAxis).length;
  const dimensionCount = data.dimensionCount ?? data.dimensions.length;

  const place = (dimensions: DimensionNode[], zone: ZoneName): PlacedDimension[] =>
    dimensions.map((dimension, index) => {
      const rowSpan = dimensions.length * (NODE_W + spacing) - spacing;
      const columnSpan = dimensions.length * (NODE_H + spacing) - spacing;
      let x = 0;
      let y = 0;

      if (zone === "top") {
        x = centerX - rowSpan / 2 + index * (NODE_W + spacing);
        y = 38;
      } else if (zone === "bottom") {
        x = centerX - rowSpan / 2 + index * (NODE_W + spacing);
        y = height - NODE_H - 38;
      } else if (zone === "left") {
        x = 38;
        y = centerY - columnSpan / 2 + index * (NODE_H + spacing);
      } else {
        x = width - NODE_W - 38;
        y = centerY - columnSpan / 2 + index * (NODE_H + spacing);
      }

      return { d: dimension, x, y, zone };
    });

  const placedDimensions = [
    ...place(grouped.top, "top"),
    ...place(grouped.left, "left"),
    ...place(grouped.right, "right"),
    ...place(grouped.bottom, "bottom"),
  ];

  const screenToUser = () => {
    const rectangle = svgRef.current?.getBoundingClientRect();
    if (!rectangle || rectangle.width === 0 || rectangle.height === 0) return 1;
    return 1 / Math.min(rectangle.width / width, rectangle.height / height);
  };

  const zoomBy = (delta: number) => {
    setZoom((current) => Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, current + delta)));
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || (event.target as Element).closest("button, input")) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      panX: pan.x,
      panY: pan.y,
    });
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const scale = screenToUser();
    setPan({
      x: drag.panX + (event.clientX - drag.x) * scale,
      y: drag.panY + (event.clientY - drag.y) * scale,
    });
  };

  const handlePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDrag(null);
  };

  const handleCanvasKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    const panStep = 24;
    if (event.key === "ArrowUp") setPan((current) => ({ ...current, y: current.y + panStep }));
    else if (event.key === "ArrowDown") setPan((current) => ({ ...current, y: current.y - panStep }));
    else if (event.key === "ArrowLeft") setPan((current) => ({ ...current, x: current.x + panStep }));
    else if (event.key === "ArrowRight") setPan((current) => ({ ...current, x: current.x - panStep }));
    else if (event.key === "+" || event.key === "=") zoomBy(ZOOM_STEP);
    else if (event.key === "-" || event.key === "_") zoomBy(-ZOOM_STEP);
    else if (event.key === "0") resetView();
    else return;
    event.preventDefault();
  };

  const content = (
    <>
      <div className="architecture-summary" aria-label="Cube summary">
        <div>
          <span>Dimensions</span>
          <strong className="tabular-nums">{formatNumber(dimensionCount)}</strong>
        </div>
        <div>
          <span>Known members</span>
          <strong className="tabular-nums">{formatNumber(knownMembers)}</strong>
        </div>
        <div>
          <span>{data.formCoverage ? "Assigned to axes" : "Application"}</span>
          <strong className={data.formCoverage ? "tabular-nums" : undefined}>
            {data.formCoverage ? `${assignedDimensions}/${dimensionCount}` : data.application}
          </strong>
        </div>
      </div>

      <div className="architecture-toolbar">
        <SearchInput
          size="sm"
          labelText="Search dimensions"
          placeholder="Find a dimension"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
        />
        <span className="architecture-match-count tabular-nums" role="status" aria-live="polite">
          {query ? `${matchingDimensions.length} of ${dimensionCount}` : `${dimensionCount} total`}
        </span>
        <div className="architecture-zoom-controls" aria-label="Diagram zoom controls">
          <Button
            type="button"
            size="sm"
            kind="ghost"
            hasIconOnly
            renderIcon={ZoomOut}
            iconDescription="Zoom out"
            aria-label="Zoom out"
            disabled={zoom <= MIN_ZOOM}
            onClick={() => zoomBy(-ZOOM_STEP)}
          />
          <output className="architecture-zoom-value tabular-nums" aria-live="polite">
            {Math.round(zoom * 100)}%
          </output>
          <Button
            type="button"
            size="sm"
            kind="ghost"
            hasIconOnly
            renderIcon={ZoomIn}
            iconDescription="Zoom in"
            aria-label="Zoom in"
            disabled={zoom >= MAX_ZOOM}
            onClick={() => zoomBy(ZOOM_STEP)}
          />
          <Button
            type="button"
            size="sm"
            kind="ghost"
            renderIcon={Reset}
            onClick={resetView}
          >
            Reset view
          </Button>
        </div>
      </div>

      <div className="architecture-workspace">
        <div
          className={`architecture-viewport${drag ? " is-dragging" : ""}`}
          role="group"
          aria-label={`Interactive architecture for ${data.cube}. Drag to pan. When this canvas is focused, use arrow keys to pan, plus and minus to zoom, or zero to reset.`}
          tabIndex={0}
          onKeyDown={handleCanvasKeyDown}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          <svg
            ref={svgRef}
            className="architecture-canvas"
            viewBox={`0 0 ${width} ${height}`}
            width="100%"
            role="img"
            aria-label={`${data.cube} connected to ${dimensionCount} dimensions`}
          >
            <g
              className={`architecture-pan-zoom${drag ? " is-dragging" : ""}`}
              style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
            >
              {placedDimensions.map(({ d, x, y }) => {
                const active = hoveredNode === d.name || selectedDimension?.name === d.name;
                const muted = Boolean(query) && !matchNames.has(d.name);
                return (
                  <line
                    key={`connection-${d.name}`}
                    className="architecture-connection"
                    data-status={statusKey(d.status)}
                    data-active={active || undefined}
                    data-muted={muted || undefined}
                    x1={centerX}
                    y1={centerY}
                    x2={x + NODE_W / 2}
                    y2={y + NODE_H / 2}
                  />
                );
              })}

              <g className="architecture-cube" transform={`translate(${centerX - cubeWidth / 2} ${centerY - cubeHeight / 2})`}>
                <rect width={cubeWidth} height={cubeHeight} rx={4} />
                <path d={`M 0 8 H ${cubeWidth}`} />
                <text x={cubeWidth / 2} y={42} textAnchor="middle">{data.cube}</text>
                <text x={cubeWidth / 2} y={66} textAnchor="middle">{data.application}</text>
                <text x={cubeWidth / 2} y={96} textAnchor="middle">
                  {dimensionCount} dimensions
                </text>
              </g>

              {placedDimensions.map(({ d, x, y }, index) => {
                const selected = selectedDimension?.name === d.name;
                return (
                  <DimensionCard
                    key={d.name}
                    dimension={d}
                    x={x}
                    y={y}
                    index={index}
                    selected={selected}
                    active={selected || hoveredNode === d.name}
                    muted={Boolean(query) && !matchNames.has(d.name)}
                    onSelect={() => setSelectedNode(selected ? null : d.name)}
                    onHover={(hovered) => setHoveredNode(hovered ? d.name : null)}
                  />
                );
              })}
            </g>
          </svg>
          <div className="architecture-canvas-hint" aria-hidden="true">
            Drag to pan · select a dimension for details
          </div>
        </div>

        <DimensionInspector
          dimension={selectedDimension}
          searchHasNoMatches={Boolean(query) && matchingDimensions.length === 0}
        />
      </div>

      <div className="architecture-footer">
        <div className="architecture-legend" aria-label="Dimension status legend">
          {Object.entries(STATUS_LABELS)
            .filter(([status]) => data.dimensions.some((dimension) => statusKey(dimension.status) === status))
            .map(([status, label]) => (
              <span key={status}>
                <span className="architecture-status-dot" data-status={status} aria-hidden="true" />
                {label}
              </span>
            ))}
        </div>
        <Button
          type="button"
          size="sm"
          kind="ghost"
          renderIcon={ListBoxes}
          aria-expanded={showTable}
          onClick={() => setShowTable((current) => !current)}
        >
          {showTable ? "Hide dimension table" : "Show dimension table"}
        </Button>
      </div>

      {showTable && (
        <div className="architecture-table-wrap" role="region" aria-label="Dimension table" tabIndex={0}>
          <table className="data-table architecture-table">
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Type</th>
                <th>Members</th>
                <th>Placement</th>
                <th>Selection</th>
              </tr>
            </thead>
            <tbody>
              {matchingDimensions.map((dimension) => (
                <tr key={dimension.name} data-selected={selectedDimension?.name === dimension.name || undefined}>
                  <td>
                    <button type="button" onClick={() => setSelectedNode(dimension.name)}>
                      {dimension.name}
                    </button>
                  </td>
                  <td>{dimension.type === "custom" ? "Custom dimension" : displayValue(dimension.type)}</td>
                  <td className="tabular-nums">{dimension.memberCount == null ? "—" : formatNumber(dimension.memberCount)}</td>
                  <td>{dimension.usedOnAxis ? dimension.usedOnAxis.toUpperCase() : "Not assigned"}</td>
                  <td>{dimension.selectionSummary || dimension.selectedMember || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );

  if (!showHeader) {
    return <section className="architecture-standalone" aria-label={`${data.cube} architecture`}>{content}</section>;
  }

  return (
    <section className="block-card architecture-block" aria-label={`${data.cube} architecture`}>
      <div className="block-head">
        <Types size={16} aria-hidden="true" />
        <span>Cube architecture — {data.cube}</span>
        <span className="grow" />
        <span className="tag-inline tabular-nums">{dimensionCount} dimensions</span>
      </div>
      <div className="block-body">{content}</div>
    </section>
  );
}
