import { useMemo, useState } from "react";

import { SourceIcon } from "@/components/graph/SourceIcons";
import {
  SOURCE_VENDOR_COLOURS,
  SOURCE_VENDOR_LABELS,
  SOURCE_VENDOR_ORDER,
  vendorFromSourceId,
  type SourceVendorId,
} from "@/lib/source-vendor";
import { useBrainStore, type Edge, type Entity } from "@/state/brain.store";

const INITIAL_NODE_CAP = 50;
const LABELLED_NODE_COUNT = 30;
const GROUP_WIDTH = 220;
const GROUP_GAP = 48;
const GROUP_PADDING = 28;
const NODE_GAP = 54;

type PlacedNode = {
  entity: Entity;
  vendor: SourceVendorId;
  x: number;
  y: number;
  radius: number;
  connectionCount: number;
};

type SourceGroup = {
  vendor: SourceVendorId;
  nodes: PlacedNode[];
  x: number;
  height: number;
};

function titleForEntity(entity: Entity): string {
  for (const key of ["title", "name", "subject", "label", "file_path"]) {
    const value = entity.data?.[key];
    if (typeof value === "string" && value.trim()) {
      return key === "file_path" ? (value.split("/").pop() ?? value) : value;
    }
  }
  return entity.id;
}

function connectionCounts(edges: Map<string, Edge>): Map<string, number> {
  const counts = new Map<string, number>();
  for (const edge of edges.values()) {
    counts.set(edge.source_id, (counts.get(edge.source_id) ?? 0) + 1);
    counts.set(edge.target_id, (counts.get(edge.target_id) ?? 0) + 1);
  }
  return counts;
}

function nodeRadius(connectionCount: number, maxCount: number): number {
  const minR = 8;
  const maxR = 22;
  if (maxCount <= 0) return minR;
  const ratio = Math.sqrt(connectionCount / maxCount);
  return minR + ratio * (maxR - minR);
}

function buildLayout(
  entities: Map<string, Entity>,
  edges: Map<string, Edge>,
  visibleLimit: number,
): { groups: SourceGroup[]; width: number; height: number; labelledIds: Set<string> } {
  const counts = connectionCounts(edges);
  const ranked = Array.from(entities.values())
    .map((entity) => ({
      entity,
      vendor: vendorFromSourceId(entity.source_id),
      connectionCount: counts.get(entity.id) ?? 0,
    }))
    .filter((row): row is { entity: Entity; vendor: SourceVendorId; connectionCount: number } => row.vendor !== null)
    .sort((a, b) => b.connectionCount - a.connectionCount || titleForEntity(a.entity).localeCompare(titleForEntity(b.entity)));

  const visible = ranked.slice(0, visibleLimit);
  const labelledIds = new Set(visible.slice(0, LABELLED_NODE_COUNT).map((row) => row.entity.id));
  const maxCount = Math.max(1, ...visible.map((row) => row.connectionCount));

  const byVendor = new Map<SourceVendorId, typeof visible>();
  for (const vendor of SOURCE_VENDOR_ORDER) byVendor.set(vendor, []);
  for (const row of visible) byVendor.get(row.vendor)?.push(row);

  const groups: SourceGroup[] = [];
  let offsetX = GROUP_PADDING;

  for (const vendor of SOURCE_VENDOR_ORDER) {
    const rows = byVendor.get(vendor) ?? [];
    if (rows.length === 0) continue;

    const nodes: PlacedNode[] = rows.map((row, index) => ({
      entity: row.entity,
      vendor,
      x: offsetX + GROUP_WIDTH / 2,
      y: GROUP_PADDING + 56 + index * NODE_GAP,
      radius: nodeRadius(row.connectionCount, maxCount),
      connectionCount: row.connectionCount,
    }));

    const height = GROUP_PADDING + 56 + rows.length * NODE_GAP + GROUP_PADDING;
    groups.push({ vendor, nodes, x: offsetX, height });
    offsetX += GROUP_WIDTH + GROUP_GAP;
  }

  const width = Math.max(640, offsetX + GROUP_PADDING);
  const height = Math.max(420, ...groups.map((group) => group.height), 420);

  return { groups, width, height, labelledIds };
}

export function GraphCanvas() {
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);
  const selectedId = useBrainStore((s) => s.selectedId);
  const select = useBrainStore((s) => s.select);
  const [visibleLimit, setVisibleLimit] = useState(INITIAL_NODE_CAP);

  const layout = useMemo(
    () => buildLayout(entities, edges, visibleLimit),
    [entities, edges, visibleLimit],
  );

  const { groups, width, height, labelledIds } = layout;

  const visibleIds = useMemo(() => {
    const counts = connectionCounts(edges);
    return new Set(
      Array.from(entities.values())
        .map((entity) => ({
          entity,
          vendor: vendorFromSourceId(entity.source_id),
          connectionCount: counts.get(entity.id) ?? 0,
        }))
        .filter((row): row is { entity: Entity; vendor: SourceVendorId; connectionCount: number } => row.vendor !== null)
        .sort((a, b) => b.connectionCount - a.connectionCount || titleForEntity(a.entity).localeCompare(titleForEntity(b.entity)))
        .slice(0, visibleLimit)
        .map((row) => row.entity.id),
    );
  }, [entities, edges, visibleLimit]);

  const positionedById = useMemo(() => {
    const map = new Map<string, PlacedNode>();
    for (const group of groups) {
      for (const node of group.nodes) map.set(node.entity.id, node);
    }
    return map;
  }, [groups]);

  const edgeLines = useMemo(() => {
    const lines: Array<{ key: string; x1: number; y1: number; x2: number; y2: number }> = [];
    for (const edge of edges.values()) {
      if (!visibleIds.has(edge.source_id) || !visibleIds.has(edge.target_id)) continue;
      const source = positionedById.get(edge.source_id);
      const target = positionedById.get(edge.target_id);
      if (!source || !target) continue;
      lines.push({
        key: edge.id,
        x1: source.x,
        y1: source.y,
        x2: target.x,
        y2: target.y,
      });
    }
    return lines;
  }, [edges, positionedById, visibleIds]);

  const totalMapped = useMemo(() => {
    let count = 0;
    for (const entity of entities.values()) {
      if (vendorFromSourceId(entity.source_id)) count++;
    }
    return count;
  }, [entities]);

  const canShowMore = visibleLimit < totalMapped;

  return (
    <div className="relative h-full w-full overflow-auto bg-[#05050A]">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="min-h-full min-w-full"
        role="img"
        aria-label="Entity graph grouped by source"
      >
        <defs>
          <pattern id="graph-grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#0F1A2A" strokeWidth="0.6" opacity="0.35" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill="url(#graph-grid)" />

        {edgeLines.map((line) => (
          <line
            key={line.key}
            x1={line.x1}
            y1={line.y1}
            x2={line.x2}
            y2={line.y2}
            stroke="#2B7FFF"
            strokeOpacity={0.18}
            strokeWidth={1}
          />
        ))}

        {groups.map((group) => (
          <g key={group.vendor}>
            <rect
              x={group.x}
              y={GROUP_PADDING / 2}
              width={GROUP_WIDTH}
              height={group.height - GROUP_PADDING / 2}
              rx={16}
              fill="#07111d"
              stroke="#1a2f4a"
              strokeWidth={1}
            />
            <foreignObject x={group.x + 16} y={GROUP_PADDING + 4} width={GROUP_WIDTH - 32} height={40}>
              <div className="flex items-center gap-2 text-[#E8F0FF]">
                <span style={{ color: SOURCE_VENDOR_COLOURS[group.vendor] }}>
                  <SourceIcon vendor={group.vendor} className="h-4 w-4" />
                </span>
                <span className="text-[12px] font-semibold uppercase tracking-[0.12em]">
                  {SOURCE_VENDOR_LABELS[group.vendor]}
                </span>
                <span className="text-[11px] text-[#8ba8cb]">{group.nodes.length}</span>
              </div>
            </foreignObject>

            {group.nodes.map((node) => {
              const selected = node.entity.id === selectedId;
              const labelled = labelledIds.has(node.entity.id);
              const colour = SOURCE_VENDOR_COLOURS[node.vendor];
              return (
                <g key={node.entity.id}>
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.radius + (selected ? 4 : 0)}
                    fill={selected ? `${colour}33` : "transparent"}
                    stroke={selected ? colour : "transparent"}
                    strokeWidth={1.5}
                  />
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.radius}
                    fill={`${colour}22`}
                    stroke={colour}
                    strokeWidth={selected ? 2 : 1.2}
                    className="cursor-pointer"
                    onClick={() => select(node.entity.id)}
                  />
                  <foreignObject
                    x={node.x - node.radius}
                    y={node.y - node.radius}
                    width={node.radius * 2}
                    height={node.radius * 2}
                    className="pointer-events-none"
                  >
                    <div className="flex h-full w-full items-center justify-center">
                      <span style={{ color: colour }}>
                        <SourceIcon vendor={node.vendor} className="h-3.5 w-3.5" />
                      </span>
                    </div>
                  </foreignObject>
                  {labelled ? (
                    <text
                      x={node.x}
                      y={node.y + node.radius + 14}
                      textAnchor="middle"
                      fill="rgba(232,240,255,0.88)"
                      fontSize="10"
                      fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
                    >
                      {titleForEntity(node.entity).slice(0, 28)}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </g>
        ))}
      </svg>

      {canShowMore ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-24 flex justify-center">
          <button
            type="button"
            className="pointer-events-auto rounded-lg border border-[#1d3452] bg-[#071328]/95 px-4 py-2 text-[12px] font-medium text-[#9bc9ff] transition hover:border-[#2f8cff] hover:text-[#eef5ff]"
            onClick={() => setVisibleLimit((limit) => limit + INITIAL_NODE_CAP)}
          >
            Show more ({Math.min(INITIAL_NODE_CAP, totalMapped - visibleLimit)} more entities)
          </button>
        </div>
      ) : null}

      {groups.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center px-8 text-center text-sm text-[#8ba8cb]">
          No source-mapped entities yet. Connect GitHub, Notion, Linear, Slack, or Gmail to populate the graph.
        </div>
      ) : null}
    </div>
  );
}
