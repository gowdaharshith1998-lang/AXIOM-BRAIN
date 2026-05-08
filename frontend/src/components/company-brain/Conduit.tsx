export type ConduitPoint = { x: number; y: number };

export type ConduitProps = {
  clusterId: string;
  sourceColor: string;
  hubColor: string;
  sourceCentroid: ConduitPoint;
  hubCentroid: ConduitPoint;
  isFocusedMode: boolean;
  isThisClusterFocused: boolean;
  particleCount?: 2 | 3;
};

function hash(text: string): number {
  let out = 0;
  for (let i = 0; i < text.length; i++) out = (out * 31 + text.charCodeAt(i)) >>> 0;
  return out;
}

function quadControlPoint(from: ConduitPoint, to: ConduitPoint, seed: number): ConduitPoint {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.hypot(dx, dy) || 1;
  const px = -dy / len;
  const py = dx / len;
  const magnitude = 60 + (seed % 61); // 60–120
  return { x: (from.x + to.x) / 2 + px * magnitude, y: (from.y + to.y) / 2 + py * magnitude };
}

function quadPath(from: ConduitPoint, ctrl: ConduitPoint, to: ConduitPoint): string {
  return `M ${from.x} ${from.y} Q ${ctrl.x} ${ctrl.y} ${to.x} ${to.y}`;
}

export function Conduit({
  clusterId,
  sourceColor,
  hubColor,
  sourceCentroid,
  hubCentroid,
  isFocusedMode,
  isThisClusterFocused,
  particleCount = 2,
}: ConduitProps) {
  const focused = !isFocusedMode || isThisClusterFocused;
  const dimmed = isFocusedMode && !isThisClusterFocused;
  const opacity = dimmed ? 0.15 : 0.5;
  const seed = hash(clusterId);
  const ctrl = quadControlPoint(sourceCentroid, hubCentroid, seed);
  const path = quadPath(sourceCentroid, ctrl, hubCentroid);
  const durBase = 3 + (seed % 4); // 3–6

  return (
    <g data-role="conduit" data-cluster-id={clusterId} data-focused={String(focused)}>
      <defs>
        <linearGradient id={`grad-${clusterId}`} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor={sourceColor} stopOpacity={0.9} />
          <stop offset="100%" stopColor={hubColor} stopOpacity={0.9} />
        </linearGradient>
      </defs>

      <path
        data-role="conduit-path"
        data-dimmed={dimmed ? "true" : "false"}
        d={path}
        stroke={`url(#grad-${clusterId})`}
        strokeWidth={1.4}
        opacity={opacity}
        fill="none"
      />

      {Array.from({ length: particleCount }, (_, index) => {
        const dur = `${durBase + (index % 2)}s`;
        const begin = `${(index * 0.9 + (seed % 10) * 0.05).toFixed(2)}s`;
        return (
          <circle key={`p-${index}`} data-role="conduit-particle" r={2.4} fill={sourceColor} filter="url(#particle-glow)">
            <animateMotion dur={dur} repeatCount="indefinite" path={path} begin={begin} />
          </circle>
        );
      })}
    </g>
  );
}

