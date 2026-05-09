import * as THREE from "three";

import { CLUSTER_COLORS, CLUSTER_LABELS, type ClusterId } from "@/lib/cluster-layout";
export type ClusterLabelMeta = {
  entities: number;
  relationships: number;
};

export function clusterLabelText(cluster: ClusterId): string {
  return CLUSTER_LABELS[cluster].toUpperCase();
}

export function clusterLabelAnchor(hub: THREE.Vector3, offset = 12): THREE.Vector3 {
  const dir = new THREE.Vector2(hub.x, hub.y);
  if (dir.lengthSq() < 0.001) dir.set(0, 1);
  dir.normalize().multiplyScalar(offset);
  return new THREE.Vector3(hub.x + dir.x, hub.y + dir.y, hub.z + 3);
}

export function bracketLinePoints(hub: THREE.Vector3, anchor: THREE.Vector3): [THREE.Vector3, THREE.Vector3, THREE.Vector3] {
  const elbow = new THREE.Vector3(anchor.x + (hub.x - anchor.x) * 0.35, anchor.y, anchor.z);
  return [anchor.clone(), elbow, hub.clone()];
}

function metaText(meta: ClusterLabelMeta): string {
  return `${meta.entities.toLocaleString()} entities · ${compactNumber(meta.relationships)} relationships`;
}

function compactNumber(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k`;
  return value.toLocaleString();
}

export function createClusterBracketElement(
  cluster: ClusterId,
  count: number,
  meta: Partial<ClusterLabelMeta> = {},
): HTMLDivElement {
  const resolved = {
    entities: meta.entities ?? count,
    relationships: meta.relationships ?? 0,
  } satisfies ClusterLabelMeta;
  const div = document.createElement("div");
  div.className = "axiom-cluster-bracket-label";
  div.dataset.cluster = cluster;
  div.style.color = CLUSTER_COLORS[cluster];
  div.style.fontFamily = "JetBrains Mono, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
  div.style.fontSize = "14px";
  div.style.fontWeight = "600";
  div.style.letterSpacing = "0.18em";
  div.style.textTransform = "uppercase";
  div.style.opacity = "0.85";
  div.style.pointerEvents = "none";
  div.style.userSelect = "none";
  div.style.whiteSpace = "nowrap";
  div.style.textShadow = "0 0 8px rgba(0,0,0,0.95), 0 1px 2px rgba(0,0,0,0.85)";
  div.innerHTML = `<div class="cluster-name">${clusterLabelText(cluster)}</div><div class="cluster-meta">${metaText(resolved)}</div>`;
  return div;
}

export function updateClusterBracketElement(
  div: HTMLDivElement,
  cluster: ClusterId,
  count: number,
  meta: Partial<ClusterLabelMeta> = {},
): void {
  const resolved = {
    entities: meta.entities ?? count,
    relationships: meta.relationships ?? 0,
  } satisfies ClusterLabelMeta;
  div.innerHTML = `<div class="cluster-name">${clusterLabelText(cluster)}</div><div class="cluster-meta">${metaText(resolved)}</div>`;
}

export function ClusterBracketLabel({ cluster, count }: { cluster: ClusterId; count: number }) {
  return (
    <div
      data-cluster={cluster}
      className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em]"
      style={{ color: CLUSTER_COLORS[cluster], opacity: 0.85 }}
    >
      <div className="cluster-name">{clusterLabelText(cluster)}</div>
      <div className="cluster-meta">{count.toLocaleString()} entities · 0 relationships</div>
    </div>
  );
}
