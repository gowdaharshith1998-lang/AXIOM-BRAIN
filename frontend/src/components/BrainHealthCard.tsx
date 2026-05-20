import { useEffect, useState } from "react";

import type { Entity } from "@/state/brain.store";
import { useBrainStore } from "@/state/brain.store";

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function compositeImportanceValue(entity: Entity): number | null {
  const direct = entity.composite_importance;
  const nested = entity.data?.composite_importance;
  return typeof direct === "number" ? direct : typeof nested === "number" ? nested : null;
}

type BrainHealthMetricPoint = {
  date?: string;
  value?: unknown;
  brain_health_score?: unknown;
};

type BrainHealthMetricResponse = {
  timeseries?: BrainHealthMetricPoint[];
  snapshots?: BrainHealthMetricPoint[];
};

function normalizeHealthValue(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const normalized = value > 1 ? value / 100 : value;
  return Math.max(0, Math.min(1, normalized));
}

function historyFromPayload(payload: BrainHealthMetricResponse): number[] {
  const points = Array.isArray(payload.timeseries) ? payload.timeseries : payload.snapshots;
  if (!points) return [];
  return points
    .map((point) => normalizeHealthValue(point.value ?? point.brain_health_score))
    .filter((value): value is number => value !== null)
    .slice(-36);
}

function CompactStatusPill({
  label,
  tone,
  pulse = false,
}: {
  label: string;
  tone: "live" | "syncing" | "offline" | "neutral";
  pulse?: boolean;
}) {
  const dotClass =
    tone === "live"
      ? "bg-[#45f0a1] shadow-[0_0_6px_#45f0a1]"
      : tone === "syncing"
        ? "bg-amber-400"
        : tone === "offline"
          ? "bg-rose-400"
          : "bg-[#6b7280]";
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 rounded border border-white/10 bg-white/[0.04] px-2 py-0.5 text-xs text-[#E8F0FF]/75">
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass} ${pulse ? "animate-pulse" : ""}`} aria-hidden />
      {label}
    </span>
  );
}

export function BrainHealthCard() {
  const entityCount = useBrainStore((s) => s.entities.size);
  const edgeCount = useBrainStore((s) => s.edges.size);
  const entities = useBrainStore((s) => s.entities);
  const clusterHealth = useBrainStore((s) => s.clusterHealth);
  const fps = useBrainStore((s) => s.fps);
  const connectionStatus = useBrainStore((s) => s.connectionStatus);

  const [eventTimes, setEventTimes] = useState<number[]>([]);

  let classifiedCount = 0;
  for (const entity of entities.values()) {
    const v = compositeImportanceValue(entity);
    if (v !== null && v > 0) classifiedCount++;
  }
  const classifiedPct =
    entityCount === 0 ? null : (classifiedCount / entityCount) * 100;

  let healthy = 0;
  let degraded = 0;
  let critical = 0;
  for (const snapshot of Object.values(clusterHealth)) {
    if (snapshot.status === "healthy") healthy++;
    else if (snapshot.status === "degraded") degraded++;
    else if (snapshot.status === "critical") critical++;
  }
  const totalClusters = healthy + degraded + critical;
  const clustersPresent = Object.values(clusterHealth).filter((snapshot) => snapshot.total_entities > 0).length;
  const eventsPerMin = eventTimes.length;

  // Health score in [0, 1]:
  // 0.40*classified + 0.35*event-flow + 0.15*fps + 0.10*cluster-coverage; minus 0.15 when event-flow is zero.
  const healthScore = (() => {
    if (totalClusters === 0 || classifiedPct === null) return null;
    const classifiedRatio = Math.max(0, Math.min(1, classifiedPct / 100));
    const eventsComponent = eventsPerMin > 0 ? 1 : 0;
    const fpsComponent = Math.max(0, Math.min(1, fps / 50));
    const coverage = Math.max(0, Math.min(1, clustersPresent / Math.max(1, totalClusters)));
    let score = 0.4 * classifiedRatio + 0.35 * eventsComponent + 0.15 * fpsComponent + 0.1 * coverage;
    if (eventsPerMin <= 0) score -= 0.15;
    return Math.max(0, Math.min(1, score));
  })();

  type PillKind = "initializing" | "healthy" | "degraded" | "critical";
  let pillKind: PillKind;
  if (totalClusters === 0) pillKind = "initializing";
  else if ((healthScore ?? 0) >= 0.85) pillKind = "healthy";
  else if ((healthScore ?? 0) >= 0.6) pillKind = "degraded";
  else pillKind = "critical";

  const [history, setHistory] = useState<number[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  useEffect(() => {
    const onEvent = () => {
      const now = Date.now();
      setEventTimes((times) => [...times.filter((time) => now - time < 60_000), now]);
    };
    window.addEventListener("axiom:brain-event", onEvent);
    return () => window.removeEventListener("axiom:brain-event", onEvent);
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadHistory() {
      try {
        const response = await fetch(
          "/api/internal/metrics-snapshots?days=2&metric=brain_health",
          { signal: controller.signal },
        );
        if (!response.ok) throw new Error(`history fetch failed: ${response.status}`);
        const payload = (await response.json()) as BrainHealthMetricResponse;
        setHistory(historyFromPayload(payload));
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setHistory([]);
      } finally {
        if (!controller.signal.aborted) setHistoryLoaded(true);
      }
    }

    void loadHistory();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setEventTimes((times) => times.filter((time) => Date.now() - time < 60_000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const points = history
    .map((value, index) => {
      const x = (index / Math.max(1, history.length - 1)) * 186;
      const y = 32 - value * 30;
      return `${x.toFixed(1)},${Math.max(2, Math.min(29, y)).toFixed(1)}`;
    })
    .join(" ");

  const healthDisplay = healthScore === null ? "—" : `${(healthScore * 100).toFixed(1)}%`;
  const classifiedDisplay = classifiedPct === null ? "—" : `${classifiedPct.toFixed(1)}%`;

  const healthValueClass =
    healthScore === null
      ? "text-[#E8F0FF]/55"
      : pillKind === "healthy"
        ? "font-semibold text-[#45f0a1]"
        : pillKind === "degraded"
          ? "font-semibold text-amber-400"
          : "font-semibold text-rose-400";

  const liveTone =
    connectionStatus === "live" ? "live" : connectionStatus === "syncing" ? "syncing" : "offline";
  const liveLabel = connectionStatus === "live" ? "LIVE" : connectionStatus === "syncing" ? "SYNCING" : "OFFLINE";
  const healthStatusLabel =
    pillKind === "initializing"
      ? "Initializing"
      : pillKind === "healthy"
        ? "Healthy"
        : pillKind === "degraded"
          ? "Degraded"
          : "Critical";
  const healthTone =
    pillKind === "healthy" ? "live" : pillKind === "degraded" ? "syncing" : pillKind === "critical" ? "offline" : "neutral";

  return (
    <section className="fixed right-6 top-[48px] z-30 mt-2 w-[248px] rounded-2xl border border-[#274057]/70 bg-[#07111d]/70 p-5 font-mono text-[#E8F0FF]/82 shadow-[0_22px_70px_rgba(0,0,0,0.36)] backdrop-blur-xl">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <CompactStatusPill label={String(eventsPerMin)} tone="neutral" />
        <CompactStatusPill label={liveLabel} tone={liveTone} pulse={connectionStatus === "live"} />
      </div>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="text-xs uppercase tracking-[0.18em] text-[#E8F0FF]/72">Brain Health</div>
        <CompactStatusPill label={healthStatusLabel} tone={healthTone} pulse={pillKind === "healthy"} />
      </div>
      <div className="space-y-4 text-sm">
        <Row label="Entities" value={formatCount(entityCount)} />
        <Row label="Relationships" value={formatCount(edgeCount)} />
        <Row label="Events / min" value={eventsPerMin.toLocaleString()} />
        <Row label="Classified" value={classifiedDisplay} />
        <div className="border-t border-white/10 pt-4">
          <Row label="Health" value={healthDisplay} valueClassName={healthValueClass} />
          {historyLoaded && history.length === 0 ? (
            <div className="mt-3 text-xs text-[#E8F0FF]/50">Collecting health history...</div>
          ) : (
            <svg className="mt-3 h-8 w-full overflow-visible" viewBox="0 0 186 32" aria-hidden="true">
              <polyline points={points} fill="none" stroke="#31f4a3" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </div>
      </div>
    </section>
  );
}

function Row({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-[#E8F0FF]/66">{label}</span>
      <span className={valueClassName ?? "text-[#E8F0FF]/90"}>{value}</span>
    </div>
  );
}
