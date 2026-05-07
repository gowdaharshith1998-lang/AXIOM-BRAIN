import * as THREE from "three";

export function createHexGridPlane(): THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial> {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 1024;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#1a1f2e";
    ctx.lineWidth = 1;
    const size = 32;
    const h = Math.sqrt(3) * size;
    for (let y = -h; y < canvas.height + h; y += h * 0.75) {
      const row = Math.round(y / (h * 0.75));
      for (let x = -size * 2; x < canvas.width + size * 2; x += size * 1.5) {
        drawHex(ctx, x + (row % 2) * size * 0.75, y, size);
      }
    }
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(3, 3);
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(1000, 1000),
    new THREE.MeshBasicMaterial({
      map: texture,
      transparent: true,
      opacity: 0.18,
      depthWrite: false,
    }),
  );
  mesh.position.z = -50;
  return mesh;
}

function drawHex(ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number): void {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i;
    const x = cx + Math.cos(angle) * size;
    const y = cy + Math.sin(angle) * size;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.stroke();
}

export function HexGridBackground() {
  return null;
}
