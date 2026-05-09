import { useEffect, useState } from "react";

export function BrainHealthCard() {
  const [eventTimes, setEventTimes] = useState<number[]>([]);
  const [history, setHistory] = useState<number[]>(
    [89, 91, 90, 92, 91, 90, 92, 91, 92, 91, 92, 91, 90, 92, 91, 92, 92, 93, 92, 93, 92, 93, 92, 94, 93, 94, 93, 94, 95, 96, 94, 98, 96, 94, 92, 91],
  );
  const health = 98.2;

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
      const x = (index / Math.max(1, history.length - 1)) * 186;
      const y = 28 - ((value - 80) / 20) * 24;
      return `${x.toFixed(1)},${Math.max(2, Math.min(29, y)).toFixed(1)}`;
    })
    .join(" ");

  return (
    <section className="fixed right-6 top-6 z-30 w-[248px] rounded-2xl border border-[#274057]/70 bg-[#07111d]/70 p-5 font-mono text-[#E8F0FF]/82 shadow-[0_22px_70px_rgba(0,0,0,0.36)] backdrop-blur-xl">
      <div className="mb-5 flex items-center justify-between">
        <div className="text-xs uppercase tracking-[0.18em] text-[#E8F0FF]/72">Brain Health</div>
        <div className="flex items-center gap-2 text-xs font-semibold text-[#45f0a1]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#45f0a1] shadow-[0_0_10px_#45f0a1]" />
          Healthy
        </div>
      </div>
      <div className="space-y-4 text-sm">
        <Row label="Entities" value="2.48M" />
        <Row label="Relationships" value="18.73M" />
        <Row label="Events / min" value="3,842" />
        <Row label="Confidence Avg" value="94.7%" />
        <div className="border-t border-white/10 pt-4">
          <Row label="Health" value={`${health.toFixed(1)}%`} accent />
          <svg className="mt-3 h-8 w-full overflow-visible" viewBox="0 0 186 32" aria-hidden="true">
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
