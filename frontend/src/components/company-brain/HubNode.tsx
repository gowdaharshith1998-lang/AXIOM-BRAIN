export type HubNodeProps = {
  hubX: number;
  hubY: number;
  hubColor: string;
  glowId?: string;
};

function hexPoints(size: number): string {
  const r = size / 2;
  const points: Array<[number, number]> = [];
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i - Math.PI / 2;
    points.push([Math.cos(a) * r, Math.sin(a) * r]);
  }
  return points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  const mm = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  return Boolean(mm?.matches);
}

export function HubNode({ hubX, hubY, hubColor, glowId = "hub-glow" }: HubNodeProps) {
  const reduced = prefersReducedMotion();

  return (
    <g data-role="hub" transform={`translate(${hubX} ${hubY})`}>
      <circle
        data-role="hub-ring-pulse"
        r="44"
        className={reduced ? undefined : "hub-ring-pulse"}
        fill="none"
        stroke={hubColor}
        strokeOpacity="0.55"
        strokeWidth="1.25"
      />

      <polygon
        data-role="hub-glyph"
        points={hexPoints(80)}
        fill={`url(#${glowId})`}
        stroke={hubColor}
        strokeWidth="1.6"
      />

      <text
        data-role="hub-wordmark"
        x="0"
        y="72"
        textAnchor="middle"
        style={{ fontSize: 22, letterSpacing: "0.18em" }}
      >
        AXIOM
      </text>
      <text data-role="hub-subtitle" x="0" y="90" textAnchor="middle" style={{ fontSize: 11 }}>
        COMPANY BRAIN
      </text>
      <text
        data-role="hub-tagline"
        x="0"
        y="104"
        textAnchor="middle"
        fontStyle="italic"
        style={{ fontSize: 11 }}
      >
        Knowledge. Connected. Executable.
      </text>
    </g>
  );
}

