import * as THREE from "three";

export type NodeLodMode = "sprite" | "sphere";

export const NODE_SPRITE_DISTANCE = 280;
export const EDGE_SKIP_DISTANCE = 320;
export const BLOOM_REDUCE_DISTANCE = 280;
export const BLOOM_FULL_STRENGTH = 0.25;
export const BLOOM_OVERVIEW_STRENGTH = 0.12;

export function nodeLodMode(cameraDistance: number): NodeLodMode {
  return cameraDistance > NODE_SPRITE_DISTANCE ? "sprite" : "sphere";
}

export function shouldRenderEdge(edgeIndex: number, cameraDistance: number): boolean {
  return cameraDistance <= EDGE_SKIP_DISTANCE || edgeIndex % 3 === 0;
}

export function bloomStrengthForDistance(cameraDistance: number): number {
  return cameraDistance > BLOOM_REDUCE_DISTANCE ? BLOOM_OVERVIEW_STRENGTH : BLOOM_FULL_STRENGTH;
}

export function disposeMaterial(material: THREE.Material | THREE.Material[]): void {
  if (Array.isArray(material)) {
    material.forEach((m) => m.dispose());
    return;
  }
  material.dispose();
}

export function swapMeshGeometry(mesh: THREE.Mesh, nextGeometry: THREE.BufferGeometry): void {
  const previous = mesh.geometry;
  if (previous !== nextGeometry) previous.dispose();
  mesh.geometry = nextGeometry;
}

let sharedSpriteTexture: THREE.CanvasTexture | null = null;

export function createNodeSpriteMaterial(color: THREE.ColorRepresentation): THREE.SpriteMaterial {
  if (!sharedSpriteTexture) {
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      const gradient = ctx.createRadialGradient(32, 32, 1, 32, 32, 32);
      gradient.addColorStop(0, "rgba(255,255,255,0.85)");
      gradient.addColorStop(0.35, "rgba(255,255,255,0.55)");
      gradient.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, 64, 64);
    }
    sharedSpriteTexture = new THREE.CanvasTexture(canvas);
  }
  return new THREE.SpriteMaterial({
    map: sharedSpriteTexture,
    color,
    transparent: true,
    opacity: 0.6,
    depthWrite: false,
    blending: THREE.NormalBlending,
  });
}
