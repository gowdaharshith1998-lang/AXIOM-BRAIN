export type LabelBox = {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  dx?: number;
  dy?: number;
};

function intersects(a: LabelBox, b: LabelBox): boolean {
  return Math.abs(a.x - b.x) * 2 < a.width + b.width && Math.abs(a.y - b.y) * 2 < a.height + b.height;
}

export function resolveLabelCollisions(labels: LabelBox[], passes = 4, maxPushPx = 12): LabelBox[] {
  const out = labels.map((label) => ({ ...label, dx: label.dx ?? 0, dy: label.dy ?? 0 }));
  for (let pass = 0; pass < passes; pass++) {
    for (let i = 0; i < out.length; i++) {
      for (let j = i + 1; j < out.length; j++) {
        const a = out[i];
        const b = out[j];
        if (!intersects(a, b)) continue;
        let x = a.x - b.x;
        let y = a.y - b.y;
        const len = Math.hypot(x, y) || 1;
        x /= len;
        y /= len;
        a.dx = (a.dx ?? 0) + x * maxPushPx;
        a.dy = (a.dy ?? 0) + y * maxPushPx;
        b.dx = (b.dx ?? 0) - x * maxPushPx;
        b.dy = (b.dy ?? 0) - y * maxPushPx;
        a.x += x * maxPushPx;
        a.y += y * maxPushPx;
        b.x -= x * maxPushPx;
        b.y -= y * maxPushPx;
      }
    }
  }
  return out;
}
