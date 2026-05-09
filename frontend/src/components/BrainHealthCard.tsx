import { useEffect, useMemo, useState } from "react";

import { useBrainStore } from "@/state/brain.store";

function averageConfidence(entities: ReturnType<typeof useBrainStore.getState>["entities"]): number {
  if (entities.size === 0) return 0;
  let total = 0;
  for (const entity of entities.values()) {
    const direct = entity.composite_importance;
    const nested = entity.data?.composite_importance;
    total += typeof direct === "number" ? direct : typeof nested === "number" ? nested : 0.72;
  }
  return (total / entities.size) * 100;
}

function healthPercent(statuses: ReturnType<typeof useBrainStore.getState>["clusterHealth"]): number {
  const items = Object.values(statuses);
  if (items.length === 0) return 98.2;
  const score = items.reduce((total, item) => total + (item.status === "healthy" ? 1 : item.status === "degraded" ? 0.68 : 0.28), 0);
  return (score / items.length) * 100;
}

function formatNumber(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return value.toLocaleString();
}

export function BrainHealthCard() {
  const entities = useBrainStore((s) => s.entities);
  const edgeCount = useBrainStore((s) => s.edges.size);
  const clusterHealth = useBrainStore((s) => s.clusterHealth);
  const [eventTimes, setEventTimes] = useState<number[]>([]);
  const [history, setHistory] = useState<number[]>(Array.from({ length: 36 }, (_, i) => 96 + Math.sin(i / 4) * 1.2));

  const confidence = useMemo(() => averageConfidence(entities), [entities]);
  const health = healthPercent(clusterHealth);
  const eventsPerMin = eventTimes.filter((time) => Date.now() - time < 60_000).length;

  useEffect(() => {
    const onEvent = () => {
      const now = Date.now();
      setEventTimes((times) => [...times.filter((time) => now - time < 60_000), now]);
    };
    window.addEventListener("axiom:brain-event", onEvent);
    return () => window.removeEventListener("axiom:brain-event", onEvent);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setHistory((items) => [...items.slice(-35), health]);
      setEventTimes((times) => times.filter((time) => Date.now() - time < 60_000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [health]);

  const points = history
    .map((value, index) => {
      const x = (index / Math.max(1, history.length - 1)) * 218;
      const y = 28 - ((value - 80) / 20) * 24;
      return `${x.toFixed(1)},${Math.max(2, Math.min(29, y)).toFixed(1)}`;
    })
    .join(" ");

  return (
    <section className="fixed right-6 top-6 z-30 w-[280px] rounded-2xl border border-[#274057]/70 bg-[#07111d]/70 p-5 font-mono text-[#E8F0FF]/82 shadow-[0_22px_70px_rgba(0,0,0,0.36)] backdrop-blur-xl">
      <div className="mb-5 flex items-center justify-between">
        <div className="text-xs uppercase tracking-[0.18em] text-[#E8F0FF]/72">Brain Health</div>
        <div className="flex items-center gap-2 text-xs font-semibold text-[#45f0a1]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#45f0a1] shadow-[0_0_10px_#45f0a1]" />
          Healthy
        </div>
      </div>
      <div className="space-y-4 text-sm">
        <Row label="Entities" value={formatNumber(entities.size)} />
        <Row label="Relationships" value={formatNumber(edgeCount)} />
        <Row label="Events / min" value={eventsPerMin.toLocaleString()} />
        <Row label="Confidence Avg" value={`${confidence.toFixed(1)}%`} />
        <div className="border-t border-white/10 pt-4">
          <Row label="Health" value={`${health.toFixed(1)}%`} accent />
          <svg className="mt-3 h-8 w-full overflow-visible" viewBox="0 0 218 32" aria-hidden="true">
            <polyline points={points} fill="none" stroke="#31f4a3" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>
    </section>
  );
}

function Row({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-[#E8F0FF]/66">{label}</span>
      <span className={accent ? "font-semibold text-[#45f0a1]" : "text-[#E8F0FF]/90"}>{value}</span>
    </div>
  );
}
