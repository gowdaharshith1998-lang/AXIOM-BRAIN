import type { CompanyBrainCluster } from "@/components/company-brain/companyBrainTypes";
import type React from "react";

import { ClusterNode } from "@/components/company-brain/ClusterNode";

type CompanyBrainGraphProps = {
  clusters: CompanyBrainCluster[];
  hiddenFilters: Set<string>;
  selectedId: string;
  hoveredId: string | null;
  onSelect: (cluster: CompanyBrainCluster) => void;
  onHover: (id: string | null) => void;
};

const CROSS_LINKS = [
  ["people", "teams"],
  ["leadership", "decisions"],
  ["meetings", "documents"],
  ["decisions", "policies"],
  ["code", "systems"],
  ["projects", "tickets"],
  ["tickets", "incidents"],
  ["vendors", "systems"],
  ["customers", "tickets"],
] as const;

function satellitePoints(cluster: CompanyBrainCluster): { x: number; y: number; r: number }[] {
  return Array.from({ length: cluster.satellites }, (_, index) => {
    const angle = (Math.PI * 2 * index) / cluster.satellites + (cluster.x + cluster.y) * 0.017;
    const orbit = 4.4 + (index % 3) * 0.45;
    return {
      x: cluster.x + Math.cos(angle) * orbit,
      y: cluster.y + Math.sin(angle) * orbit,
      r: index % 4 === 0 ? 0.75 : 0.58,
    };
  });
}

function curvedPath(from: CompanyBrainCluster, toX = 50, toY = 50): string {
  const dx = toX - from.x;
  const dy = toY - from.y;
  const sweep = from.y < 50 ? -8 : 8;
  const c1x = from.x + dx * 0.36;
  const c1y = from.y + dy * 0.2 + sweep;
  const c2x = from.x + dx * 0.72;
  const c2y = from.y + dy * 0.82 - sweep;
  return `M ${from.x} ${from.y} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${toX} ${toY}`;
}

function crossPath(from: CompanyBrainCluster, to: CompanyBrainCluster): string {
  const cx = (from.x + to.x) / 2;
  const cy = (from.y + to.y) / 2 - 7;
  return `M ${from.x} ${from.y} Q ${cx} ${cy} ${to.x} ${to.y}`;
}

export function CompanyBrainGraph({
  clusters,
  hiddenFilters,
  selectedId,
  hoveredId,
  onSelect,
  onHover,
}: CompanyBrainGraphProps) {
  const visibleClusters = clusters.filter((cluster) => !hiddenFilters.has(cluster.filter));
  const byId = new Map(visibleClusters.map((cluster) => [cluster.id, cluster]));

  return (
    <section className="cb-graph-panel" aria-label="Company Brain knowledge graph">
      <div className="cb-graph-status">
        <span className="cb-live-dot" />
        LIVE
        <span>Graph updates in real time</span>
      </div>

      <svg className="cb-graph-svg" viewBox="14 9 72 72" role="img" aria-label="AXIOM Company Brain clusters">
        <defs>
          <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.96" />
            <stop offset="36%" stopColor="#2f8dff" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#06152f" stopOpacity="0" />
          </radialGradient>
          <filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g className="cb-core-links">
          {visibleClusters.map((cluster) => (
            <path
              key={`${cluster.id}-core`}
              className={`cb-core-link ${hoveredId === cluster.id || selectedId === cluster.id ? "is-hot" : ""}`}
              d={curvedPath(cluster)}
              stroke={cluster.color}
            />
          ))}
        </g>

        <g className="cb-cross-links">
          {CROSS_LINKS.map(([fromId, toId]) => {
            const from = byId.get(fromId);
            const to = byId.get(toId);
            if (!from || !to) return null;
            return <path key={`${fromId}-${toId}`} className="cb-cross-link" d={crossPath(from, to)} stroke={from.color} />;
          })}
        </g>

        <g className="cb-core" filter="url(#softGlow)">
          <circle cx="50" cy="50" r="7.2" fill="url(#coreGlow)" />
          <circle cx="50" cy="50" r="4.2" fill="#082c68" stroke="#53a6ff" strokeWidth="0.4" />
          <path d="M50 45.6 54 47.9v4.6L50 54.8l-4-2.3v-4.6z" fill="none" stroke="#e8f4ff" strokeWidth="0.48" />
          <path d="M50 45.6v4.6m4-2.3-4 2.3m-4-2.3 4 2.3m0 4.6v-4.6" stroke="#8ed5ff" strokeWidth="0.32" />
          <text x="50" y="59.4" className="cb-core-title" textAnchor="middle">
            AXIOM
          </text>
          <text x="50" y="63.2" className="cb-core-subtitle" textAnchor="middle">
            COMPANY BRAIN
          </text>
          <text x="50" y="67.4" className="cb-core-caption" textAnchor="middle">
            Knowledge. Connected. Executable.
          </text>
        </g>

        {visibleClusters.map((cluster) => {
          return (
            <g
              key={cluster.id}
              className={`cb-cluster ${selectedId === cluster.id || hoveredId === cluster.id ? "is-active" : ""}`}
              style={{ "--cluster-color": cluster.color } as React.CSSProperties}
            >
              {satellitePoints(cluster).map((point, index) => (
                <g key={`${cluster.id}-sat-${index}`}>
                  <line x1={cluster.x} y1={cluster.y} x2={point.x} y2={point.y} stroke={cluster.color} className="cb-satellite-line" />
                  <circle cx={point.x} cy={point.y} r={point.r} className="cb-satellite" />
                </g>
              ))}
              <ClusterNode cluster={cluster} selectedId={selectedId} onSelect={onSelect} onLegacyHover={onHover} />
            </g>
          );
        })}
      </svg>

      <div className="cb-graph-controls" aria-label="Graph controls">
        <button type="button" title="Fit graph">⛶</button>
        <button type="button" title="Zoom in">+</button>
        <button type="button" title="Zoom out">−</button>
        <button type="button" title="Center graph">⌖</button>
      </div>
    </section>
  );
}
