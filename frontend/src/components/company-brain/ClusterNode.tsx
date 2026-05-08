import type React from "react";

import { HexConstellation } from "@/components/company-brain/HexConstellation";
import type { CompanyBrainCluster } from "@/components/company-brain/companyBrainTypes";
import { useBrainFocus } from "@/hooks/useBrainFocus";

export type ClusterNodeProps = {
  cluster: CompanyBrainCluster;
  selectedId: string;
  onSelect: (cluster: CompanyBrainCluster) => void;
  onLegacyHover?: (id: string | null) => void;
};

export function ClusterNode({ cluster, selectedId, onSelect, onLegacyHover }: ClusterNodeProps) {
  const { focus, setHoveredCluster } = useBrainFocus();

  const isHovered = focus.hoveredClusterId === cluster.id;
  const isDimmed = Boolean(focus.hoveredClusterId && focus.hoveredClusterId !== cluster.id) ||
    (focus.mode === "FOCUS_CLUSTER" && focus.clusterId !== cluster.id);

  return (
    <g
      data-role="cluster-hit"
      data-cluster-id={cluster.id}
      tabIndex={0}
      aria-label={`${cluster.label} cluster, ${cluster.count} entities`}
      className={[
        "cb-cluster-node",
        isHovered ? "cb-hovered" : "",
        isDimmed ? "cb-dimmed" : "",
        selectedId === cluster.id ? "is-active" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ cursor: "pointer" } as React.CSSProperties}
      onClick={() => onSelect(cluster)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(cluster);
        }
      }}
      onMouseEnter={() => {
        setHoveredCluster(cluster.id);
        onLegacyHover?.(cluster.id);
      }}
      onMouseLeave={() => {
        setHoveredCluster(null);
        onLegacyHover?.(null);
      }}
    >
      <HexConstellation
        clusterId={cluster.id}
        label={cluster.label}
        count={cluster.count}
        color={cluster.color}
        centroid={{ x: cluster.x, y: cluster.y }}
        satelliteCount={cluster.satellites}
        outerDotCount={6}
        ariaLabel={null}
        ariaHidden
      />

      <text
        x={cluster.x + (cluster.x < 850 ? 110 : -110)}
        y={cluster.y - 16}
        className="cb-cluster-label"
        textAnchor={cluster.x < 850 ? "start" : "end"}
      >
        {cluster.label}
      </text>
      <text
        x={cluster.x + (cluster.x < 850 ? 110 : -110)}
        y={cluster.y + 18}
        className="cb-cluster-count"
        textAnchor={cluster.x < 850 ? "start" : "end"}
      >
        {cluster.countLabel ?? cluster.count.toLocaleString()}
      </text>
    </g>
  );
}

