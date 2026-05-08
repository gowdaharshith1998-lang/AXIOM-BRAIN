import type React from "react";

export type HexPoint = { x: number; y: number };

export type HexConstellationProps = {
  clusterId: string;
  label: string;
  count?: number;
  color: string;
  centroid: HexPoint;
  satelliteCount: number; // expected 5–7
  outerDotCount: number; // expected 4–8
  ariaLabel?: string | null;
  ariaHidden?: boolean;
};

const CENTRAL_RADIUS = 16; // 32px across
const SAT_RADIUS = 6; // 12px across

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

function hexPoints(radius: number): string {
  const pts: string[] = [];
  // flat-top hex
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i;
    pts.push(`${Math.cos(a) * radius},${Math.sin(a) * radius}`);
  }
  return pts.join(" ");
}

function hashSeed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function rand01(seed: number): () => number {
  let s = seed || 1;
  return () => {
    // xorshift32
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) & 0xffffffff) / 0xffffffff;
  };
}

function satellitePositions(count: number, seed: number): HexPoint[] {
  const r = rand01(seed);
  const base = 56;
  const jitter = 10;
  const pts: HexPoint[] = [];
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2 + (r() - 0.5) * 0.6;
    const radius = base + (r() - 0.5) * jitter;
    pts.push({ x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
  }
  return pts;
}

function outerDots(count: number, seed: number): HexPoint[] {
  const r = rand01(seed ^ 0x9e3779b9);
  const minR = 90;
  const maxR = 140;
  const pts: HexPoint[] = [];
  for (let i = 0; i < count; i++) {
    const angle = r() * Math.PI * 2;
    const radius = minR + r() * (maxR - minR);
    pts.push({ x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
  }
  return pts;
}

function spiderPath(to: HexPoint): string {
  // Slight outward bow: perpendicular control point
  const dx = to.x;
  const dy = to.y;
  const len = Math.hypot(dx, dy) || 1;
  const px = -dy / len;
  const py = dx / len;
  const offset = 10;
  const cx = dx * 0.5 + px * offset;
  const cy = dy * 0.5 + py * offset;
  return `M 0 0 Q ${cx.toFixed(2)} ${cy.toFixed(2)} ${to.x.toFixed(2)} ${to.y.toFixed(2)}`;
}

export function HexConstellation({
  clusterId,
  label,
  count = 0,
  color,
  centroid,
  satelliteCount,
  outerDotCount,
  ariaLabel,
  ariaHidden,
}: HexConstellationProps) {
  const reduced = prefersReducedMotion();
  const seed = hashSeed(clusterId);
  const sats = satellitePositions(Math.max(5, Math.min(7, satelliteCount)), seed);
  const dots = outerDots(Math.max(4, Math.min(8, outerDotCount)), seed);

  const centralClass = reduced ? "central" : "central breathe";
  const centralAnimProps: Record<string, string> = reduced ? {} : { "data-anim": "breathe" };

  return (
    <g
      data-role="cluster"
      data-cluster-id={clusterId}
      className="cluster"
      transform={`translate(${centroid.x} ${centroid.y})`}
      aria-label={ariaLabel === null ? undefined : (ariaLabel ?? `${label} cluster, ${count} entities`)}
      aria-hidden={ariaHidden ? "true" : undefined}
    >
      <circle data-role="aura" cx={0} cy={0} r={80} fill={color} opacity={0.08} />

      {!reduced && (
        <>
          {dots.map((p, i) => (
            <circle key={`dot-${i}`} data-role="outer-dot" cx={p.x} cy={p.y} r={2} fill={color} opacity={0.32} />
          ))}
        </>
      )}

      {!reduced && (
        <>
          {sats.map((p, i) => (
            <path key={`spider-${i}`} data-role="spider-line" d={spiderPath(p)} fill="none" stroke={color} opacity={0.5} strokeWidth={0.6} />
          ))}
          {sats.length >= 2 && (
            <line
              data-role="satellite-link"
              x1={sats[0].x}
              y1={sats[0].y}
              x2={sats[1].x}
              y2={sats[1].y}
              stroke={color}
              opacity={0.22}
              strokeWidth={0.6}
            />
          )}
          {sats.map((p, i) => (
            <polygon
              key={`sat-${i}`}
              data-role="satellite-hex"
              points={hexPoints(SAT_RADIUS)}
              transform={`translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`}
              fill="rgba(6, 18, 36, 0.96)"
              stroke={color}
              strokeWidth={0.6}
              opacity={0.95}
            />
          ))}
        </>
      )}

      <polygon
        data-role="central-hex"
        className={centralClass}
        points={hexPoints(CENTRAL_RADIUS)}
        fill="rgba(9, 23, 47, 0.98)"
        stroke={color}
        strokeWidth={1.2}
        {...(centralAnimProps as unknown as React.SVGProps<SVGPolygonElement>)}
      />
    </g>
  );
}

