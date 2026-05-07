import * as THREE from "three";

import { type ClusterId } from "@/lib/cluster-layout";

const ICONS: Record<ClusterId, string> = {
  billing_payments: "$",
  incidents_ops: "!",
  engineering_code: "{}",
  people_teams: "::",
  decisions_policy: "OK",
  customer_support: "?",
  growth_product: "UP",
};

export function iconTextForCluster(cluster: ClusterId): string {
  return ICONS[cluster];
}

export function createClusterHubIconSprite(cluster: ClusterId): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  let ctx: CanvasRenderingContext2D | null = null;
  if (typeof navigator === "undefined" || !navigator.userAgent.includes("jsdom")) {
    try {
      ctx = canvas.getContext("2d");
    } catch {
      ctx = null;
    }
  }
  if (ctx) {
    ctx.clearRect(0, 0, 128, 128);
    ctx.fillStyle = "rgba(255,255,255,0.95)";
    ctx.font = cluster === "engineering_code" ? "700 42px ui-monospace" : "700 58px ui-monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(iconTextForCluster(cluster), 64, 66);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    opacity: 0.95,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(4, 4, 1);
  sprite.userData = { cluster, kind: "cluster-hub-icon" };
  return sprite;
}
