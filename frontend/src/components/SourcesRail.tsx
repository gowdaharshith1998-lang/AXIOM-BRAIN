import { useEffect, useState } from "react";
import type React from "react";

import { BrandMark } from "@/components/BrandMark";
import { CLUSTER_COLORS, CLUSTER_IDS } from "@/lib/cluster-layout";
import { useBrainStore } from "@/state/brain.store";

type SourceRow = {
  name: string;
  count: number;
  freshness?: string;
  live: boolean;
};

const layerLabels = [
  ["traffic_flow", "Traffic Flow", true],
  ["dependencies", "Dependencies", true],
  ["health", "Health", true],
  ["dark_matter", "Dark Matter", false],
  ["tests", "Tests", false],
] as const;

export function SourcesRail() {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [layers, setLayers] = useState<Record<string, boolean>>({
    traffic_flow: true,
    dependencies: true,
    health: true,
  });
  const receipts = useBrainStore((s) => s.receipts?.length ?? 0);
  const actions = useBrainStore((s) => s.agentActions ?? []);
  const denied = actions.filter((action) => action.decision === "deny").length;
  const allowed = actions.filter((action) => action.decision === "allow").length;

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/api/sources");
        const json = (await res.json()) as SourceRow[];
        if (!cancelled) setSources(Array.isArray(json) ? json : []);
      } catch {
        if (!cancelled) {
          setSources([
            { name: "Slack", count: 1247, freshness: "live", live: true },
            { name: "Linear", count: 312, freshness: "2m ago", live: false },
            { name: "GitHub", count: 89, freshness: "5m ago", live: false },
            { name: "Notion", count: 156, freshness: "1h ago", live: false },
            { name: "Email", count: 2890, freshness: "live", live: true },
            { name: "Meetings", count: 47, freshness: "3h ago", live: false },
          ]);
        }
      }
    };
    void load();
    const timer = window.setInterval(load, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const toggleLayer = (layer: string, enabled: boolean) => {
    setLayers((current) => ({ ...current, [layer]: enabled }));
    window.dispatchEvent(new CustomEvent("axiom:layer-toggle", { detail: { layer, enabled } }));
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-30 w-[220px] border-r border-white/10 bg-[#0a0c14]/70 px-4 py-5 font-mono text-xs text-white/75 shadow-2xl backdrop-blur">
      <BrandMark />

      <RailSection title="Sources">
        <div className="space-y-3">
          {sources.map((source, index) => (
            <div key={source.name} className="grid grid-cols-[10px_1fr] gap-2">
              <span
                className={`mt-1.5 h-2 w-2 rounded-full ${source.live ? "animate-pulse" : ""}`}
                style={{ backgroundColor: CLUSTER_COLORS[CLUSTER_IDS[index % CLUSTER_IDS.length]] }}
              />
              <div>
                <div className="flex items-center justify-between text-white/85">
                  <span>{source.name}</span>
                  <span className="text-white/35">{source.live ? "live" : source.freshness}</span>
                </div>
                <div className="text-[10px] text-white/45">{source.count.toLocaleString()} items</div>
              </div>
            </div>
          ))}
        </div>
      </RailSection>

      <RailSection title="View Layers">
        <div className="space-y-2">
          {layerLabels.map(([id, label, enabled]) => (
            <label key={id} className={`flex items-center gap-2 ${enabled ? "text-white/75" : "text-white/30"}`}>
              <input
                type="checkbox"
                checked={Boolean(layers[id])}
                disabled={!enabled}
                onChange={(event) => toggleLayer(id, event.currentTarget.checked)}
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </RailSection>

      <RailSection title="Explore">
        <div className="grid gap-2 text-white/55">
          {["Graph", "Services", "Files", "AI Insights", "Timeline"].map((item) => (
            <button key={item} type="button" className="text-left transition hover:text-white">
              {item}
            </button>
          ))}
        </div>
      </RailSection>

      <div className="absolute bottom-4 left-4 right-4 border-t border-white/10 pt-3 text-[10px] text-white/45">
        <div className="text-[#22c55e]">AEGIS governance active</div>
        <div>Actions allowed today: {allowed}</div>
        <div>Actions denied today: {denied}</div>
        <div>Receipts on ledger: {receipts}</div>
      </div>
    </aside>
  );
}

function RailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="mb-3 text-[10px] uppercase tracking-[0.22em] text-white/35">{title}</h2>
      {children}
    </section>
  );
}
