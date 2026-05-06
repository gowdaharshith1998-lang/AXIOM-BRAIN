import { useBrainStore } from "@/state/brain.store";

export function EntityInspector() {
  const selectedId = useBrainStore((s) => s.selectedId);
  const entity = useBrainStore((s) => (selectedId ? s.entities.get(selectedId) : null));

  if (!entity) return null;

  return (
    <div className="absolute top-0 right-0 h-full w-[340px] bg-black/30 backdrop-blur-md border-l border-white/10 pointer-events-auto">
      <div className="p-4 space-y-2">
        <div className="text-xs uppercase tracking-wider text-white/50">entity</div>
        <div className="text-white/90 font-mono text-sm break-all">{entity.id}</div>
        <div className="text-white/70 text-sm">{entity.type}</div>
        <div className="mt-4 text-xs uppercase tracking-wider text-white/50">data</div>
        <pre className="text-xs text-white/70 whitespace-pre-wrap break-words">
          {JSON.stringify(entity.data, null, 2)}
        </pre>
      </div>
    </div>
  );
}

