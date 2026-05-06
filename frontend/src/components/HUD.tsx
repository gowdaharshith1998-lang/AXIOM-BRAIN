import { useEffect, useState } from "react";

import { useBrainStore } from "@/state/brain.store";

export function HUD() {
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);
  const fps = useBrainStore((s) => s.fps);
  const selectedId = useBrainStore((s) => s.selectedId);
  const lastSeq = useBrainStore((s) => s.lastSeq);
  const [liveUntil, setLiveUntil] = useState(0);
  const selected = selectedId ? entities.get(selectedId) : null;

  const fpsColor = fps >= 55 ? "#50FA7B" : fps >= 30 ? "#F1FA8C" : "#FF5555";
  const live = Date.now() < liveUntil;
  const data = selected?.data ?? {};
  const name =
    (typeof data["name"] === "string" && data["name"]) ||
    (typeof data["title"] === "string" && data["title"]) ||
    (selected ? selected.id.slice(0, 8) : "");

  useEffect(() => {
    if (lastSeq === 0) return;
    setLiveUntil(Date.now() + 3000);
    const timer = window.setTimeout(() => setLiveUntil(0), 3000);
    return () => window.clearTimeout(timer);
  }, [lastSeq]);

  return (
    <div className="absolute top-4 left-4 font-mono text-sm text-white/80 select-none pointer-events-none space-y-1">
      <div className="flex items-center gap-2 text-lg font-semibold tracking-wider text-white/90">
        <span>AXIOM</span>
        <span
          className={`h-2 w-2 rounded-full bg-[#50FA7B] ${live ? "opacity-100 animate-pulse" : "opacity-25"}`}
          aria-hidden="true"
        />
      </div>
      <div>
        entities <span className="text-white">{entities.size}</span>
      </div>
      <div>
        edges <span className="text-white">{edges.size}</span>
      </div>
      <div>
        fps <span style={{ color: fpsColor }}>{fps}</span>
      </div>
      {selected && (
        <div className="mt-3 pt-3 border-t border-white/10">
          <div className="text-white/40 text-xs uppercase tracking-wider">selected</div>
          <div>
            {selected.type} · {name.slice(0, 32)}
          </div>
          <div className="text-white/40 text-xs">{selected.id.slice(0, 8)}</div>
        </div>
      )}
    </div>
  );
}

