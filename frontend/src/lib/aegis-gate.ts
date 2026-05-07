import * as THREE from "three";

import { CLUSTER_COLORS, type ClusterId } from "@/lib/cluster-layout";

export type AegisGateState = "idle" | "evaluating" | "allow" | "deny";

const STATE_COLORS: Record<AegisGateState, string> = {
  idle: "#ffffff",
  evaluating: "#ffffff",
  allow: "#22c55e",
  deny: "#ef4444",
};

export class AegisGate {
  readonly ring: THREE.Mesh<THREE.TorusGeometry, THREE.MeshBasicMaterial>;
  private state: AegisGateState = "idle";
  private stateUntil = 0;

  constructor(
    readonly cluster: ClusterId,
    ring: THREE.Mesh<THREE.TorusGeometry, THREE.MeshBasicMaterial>,
    private readonly defaultColor = CLUSTER_COLORS[cluster],
  ) {
    this.ring = ring;
    this.setState("idle", 0);
  }

  setState(state: AegisGateState, nowMs = performance.now()): void {
    this.state = state;
    this.stateUntil = state === "evaluating" ? nowMs + 220 : state === "idle" ? 0 : nowMs + 600;
    this.applyState();
  }

  update(nowMs: number): void {
    if (this.state !== "idle" && nowMs >= this.stateUntil) this.setState("idle", nowMs);
    const pulse = this.state === "idle" ? 0.04 * Math.sin(nowMs / 600) : 0;
    this.ring.material.opacity = this.opacityForState() + pulse;
  }

  currentState(): AegisGateState {
    return this.state;
  }

  private applyState(): void {
    this.ring.material.color.set(this.state === "idle" ? this.defaultColor : STATE_COLORS[this.state]);
    this.ring.material.opacity = this.opacityForState();
  }

  private opacityForState(): number {
    if (this.state === "idle") return 0.35;
    if (this.state === "evaluating") return 0.65;
    return 0.9;
  }
}

export function createAegisRing(cluster: ClusterId): THREE.Mesh<THREE.TorusGeometry, THREE.MeshBasicMaterial> {
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(14, 0.4, 8, 64),
    new THREE.MeshBasicMaterial({
      color: CLUSTER_COLORS[cluster],
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  ring.userData = { cluster, kind: "aegis-gate" };
  return ring;
}
