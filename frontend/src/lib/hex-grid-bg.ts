import * as THREE from "three";

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

export function createHexGridPlane(): THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial> {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 1024;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "rgba(55, 102, 146, 0.2)";
    ctx.lineWidth = 1.25;
    const size = 40;
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
  texture.repeat.set(2.25, 1.65);

  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(620, 360),
    new THREE.MeshBasicMaterial({
      map: texture,
      color: "#DCEEFF",
      transparent: true,
      opacity: 0.13,
      depthWrite: false,
      blending: THREE.NormalBlending,
    }),
  );
  mesh.position.z = -120;
  return mesh;
}

export type StarField = {
  points: THREE.Points<THREE.BufferGeometry, THREE.PointsMaterial>;
  update: (nowMs: number) => void;
  dispose: () => void;
};

export function createStarField(count = 58): StarField {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const radius = 80 + Math.random() * 140;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3] = Math.sin(phi) * Math.cos(theta) * radius;
    positions[i * 3 + 1] = Math.sin(phi) * Math.sin(theta) * radius * 0.58;
    positions[i * 3 + 2] = -40 + Math.cos(phi) * radius * 0.35;
    const alpha = 0.18 + Math.random() * 0.34;
    colors[i * 3] = alpha;
    colors[i * 3 + 1] = alpha;
    colors[i * 3 + 2] = alpha * 1.15;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const material = new THREE.PointsMaterial({
    size: 0.55,
    vertexColors: true,
    transparent: true,
    opacity: 0.48,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const points = new THREE.Points(geometry, material);
  return {
    points,
    update: (nowMs: number) => {
      points.rotation.z = Math.sin(nowMs * 0.00005) * 0.015;
      points.rotation.y += 0.000035;
    },
    dispose: () => {
      geometry.dispose();
      material.dispose();
    },
  };
}
