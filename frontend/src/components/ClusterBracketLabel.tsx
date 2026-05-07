import * as THREE from "three";

import { CLUSTER_COLORS, CLUSTER_LABELS, type ClusterId } from "@/lib/cluster-layout";
import type { ClusterHealthStatus } from "@/state/brain.store";

export type ClusterLabelMeta = {
  entities: number;
  loc: string;
  health: ClusterHealthStatus;
};

export function clusterLabelText(cluster: ClusterId): string {
  return CLUSTER_LABELS[cluster].toUpperCase();
}

export function clusterLabelAnchor(hub: THREE.Vector3, offset = 68): THREE.Vector3 {
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
  return `${meta.entities} entities · ${meta.loc} LOC`;
}

function pillClass(status: ClusterHealthStatus): string {
  return `health-pill health-${status}`;
}

export function createClusterBracketElement(
  cluster: ClusterId,
  count: number,
  meta: Partial<ClusterLabelMeta> = {},
): HTMLDivElement {
  const resolved = {
    entities: meta.entities ?? count,
    loc: meta.loc ?? "0.0K",
    health: meta.health ?? "healthy",
  } satisfies ClusterLabelMeta;
  const div = document.createElement("div");
  div.className = "axiom-cluster-bracket-label";
  div.dataset.cluster = cluster;
  div.style.color = CLUSTER_COLORS[cluster];
  div.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
  div.style.fontSize = "11px";
  div.style.fontWeight = "600";
  div.style.letterSpacing = "0.18em";
  div.style.textTransform = "uppercase";
  div.style.opacity = "0.85";
  div.style.pointerEvents = "none";
  div.style.userSelect = "none";
  div.style.whiteSpace = "nowrap";
  div.style.textShadow = "0 0 8px rgba(0,0,0,0.95), 0 1px 2px rgba(0,0,0,0.85)";
  div.innerHTML = `<div class="cluster-name">${clusterLabelText(cluster)}</div><div class="cluster-meta">${metaText(resolved)}</div><span class="${pillClass(resolved.health)}">${resolved.health}</span>`;
  return div;
}

export function updateClusterBracketElement(
  div: HTMLDivElement,
  cluster: ClusterId,
  count: number,
  meta: Partial<ClusterLabelMeta> = {},
): void {
  const previous = div.querySelector(".health-pill")?.textContent;
  const resolved = {
    entities: meta.entities ?? count,
    loc: meta.loc ?? "0.0K",
    health: meta.health ?? "healthy",
  } satisfies ClusterLabelMeta;
  div.innerHTML = `<div class="cluster-name">${clusterLabelText(cluster)}</div><div class="cluster-meta">${metaText(resolved)}</div><span class="${pillClass(resolved.health)}">${resolved.health}</span>`;
  if (previous && previous !== resolved.health) div.classList.add("health-flash");
  window.setTimeout(() => div.classList.remove("health-flash"), 650);
}

export function ClusterBracketLabel({ cluster, count }: { cluster: ClusterId; count: number }) {
  return (
    <div
      data-cluster={cluster}
      className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em]"
      style={{ color: CLUSTER_COLORS[cluster], opacity: 0.85 }}
    >
      <div className="cluster-name">{clusterLabelText(cluster)}</div>
      <div className="cluster-meta">{count} entities · 0.0K LOC</div>
      <span className="health-pill health-healthy">healthy</span>
    </div>
  );
}
