import { useState } from "react";
import type { TriggerMatcher } from "./types";

export function TriggerEditor({
  triggers,
  onChange,
}: {
  triggers: TriggerMatcher[];
  onChange: (next: TriggerMatcher[]) => void;
}) {
  const update = (i: number, next: TriggerMatcher) => {
    const copy = triggers.slice();
    copy[i] = next;
    onChange(copy);
  };
  const remove = (i: number) => {
    const copy = triggers.slice();
    copy.splice(i, 1);
    onChange(copy);
  };
  const add = () => onChange([...triggers, { intent: "", source: [] }]);

  return (
    <div className="space-y-2">
      {triggers.map((t, i) => (
        <TriggerRow key={i} trigger={t} onChange={(n) => update(i, n)} onDelete={() => remove(i)} />
      ))}
      <button onClick={add} className="rounded border border-white/20 bg-white/[0.04] px-3 py-1.5 text-sm hover:bg-white/[0.08]">
        + Add trigger
      </button>
    </div>
  );
}

function TriggerRow({
  trigger,
  onChange,
  onDelete,
}: {
  trigger: TriggerMatcher;
  onChange: (next: TriggerMatcher) => void;
  onDelete: () => void;
}) {
  const [sourceText, setSourceText] = useState(trigger.source.join(", "));
  return (
    <div className="rounded-lg border border-fuchsia-500/30 bg-fuchsia-500/[0.04] p-3">
      <div className="flex items-center gap-2">
        <span className="rounded border border-white/15 bg-white/5 px-2 py-0.5 text-xs uppercase tracking-wide text-white/70">
          Trigger
        </span>
        <button onClick={onDelete} className="ml-auto rounded border border-red-500/30 bg-red-500/5 px-2 py-1 text-xs text-red-300 hover:bg-red-500/20">
          Delete
        </button>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <label className="block">
          <span className="block text-xs text-white/55 mb-1">Intent</span>
          <input
            value={trigger.intent}
            onChange={(e) => onChange({ ...trigger, intent: e.target.value })}
            placeholder="refund"
            className="w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white/90"
          />
        </label>
        <label className="block">
          <span className="block text-xs text-white/55 mb-1">Sources (comma-separated; optional)</span>
          <input
            value={sourceText}
            onChange={(e) => {
              setSourceText(e.target.value);
              const parts = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
              onChange({ ...trigger, source: parts });
            }}
            placeholder="slack, gmail, linear"
            className="w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white/90"
          />
        </label>
      </div>
    </div>
  );
}
