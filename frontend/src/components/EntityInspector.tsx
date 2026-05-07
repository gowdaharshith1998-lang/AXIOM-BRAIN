import { useEffect, useState } from "react";

import { prettyMetadata } from "@/lib/inspector";
import { useBrainStore } from "@/state/brain.store";

export function EntityInspector() {
  const selectedId = useBrainStore((s) => s.selectedId);
  const entities = useBrainStore((s) => s.entities);
  const [renderedId, setRenderedId] = useState<string | null>(selectedId);
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    if (selectedId) {
      setRenderedId(selectedId);
      setClosing(false);
      return;
    }
    if (!renderedId) return;
    setClosing(true);
    const timer = window.setTimeout(() => {
      setRenderedId(null);
      setClosing(false);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [renderedId, selectedId]);

  const entity = renderedId ? entities.get(renderedId) : null;
  if (!entity) return null;
  const metadata = prettyMetadata(entity.data);

  return (
    <div
      className="absolute top-0 right-0 h-full w-[340px] bg-black/30 backdrop-blur-md border-l border-white/10 pointer-events-auto transition-opacity duration-300 ease-out"
      style={{ opacity: closing ? 0 : 1 }}
    >
      <div className="p-4 space-y-2">
        <div className="text-xs uppercase tracking-wider text-white/50">entity</div>
        <div className="text-white/90 font-mono text-sm break-all">{entity.id}</div>
        <div className="text-white/70 text-sm">{entity.type}</div>
        {metadata && (
          <>
            <div className="mt-4 text-xs uppercase tracking-wider text-white/50">data</div>
            <pre className="text-xs text-white/70 whitespace-pre-wrap break-words">{metadata}</pre>
          </>
        )}
      </div>
    </div>
  );
}
