import type { SkillFileDoc } from "./types";
import { BlockList } from "./BlockList";
import { TriggerEditor } from "./TriggerEditor";

export function SkillFileBuilder({
  doc,
  onChange,
  errorsByLocalId,
  errorsTopLevel,
}: {
  doc: SkillFileDoc;
  onChange: (next: SkillFileDoc) => void;
  errorsByLocalId: Record<string, string[]>;
  errorsTopLevel: string[];
}) {
  return (
    <div className="space-y-4">
      {errorsTopLevel.length > 0 ? (
        <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          <div className="font-semibold mb-1">Validation errors:</div>
          <ul className="list-disc list-inside text-xs space-y-1">
            {errorsTopLevel.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      ) : null}

      <div>
        <div className="mb-2 text-xs uppercase tracking-wide text-white/55">Metadata</div>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="block text-xs text-white/55 mb-1">Name</span>
            <input
              value={doc.name}
              onChange={(e) => onChange({ ...doc, name: e.target.value })}
              className="w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 font-mono text-sm text-white/90"
            />
          </label>
          <label className="block">
            <span className="block text-xs text-white/55 mb-1">Description</span>
            <input
              value={doc.description}
              onChange={(e) => onChange({ ...doc, description: e.target.value })}
              className="w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white/90"
            />
          </label>
        </div>
      </div>

      <div>
        <div className="mb-2 text-xs uppercase tracking-wide text-white/55">When triggered by</div>
        <TriggerEditor
          triggers={doc.when_triggered_by}
          onChange={(next) => onChange({ ...doc, when_triggered_by: next })}
        />
      </div>

      <div>
        <div className="mb-2 text-xs uppercase tracking-wide text-white/55">Steps</div>
        <BlockList
          blocks={doc.steps}
          onChange={(next) => onChange({ ...doc, steps: next })}
          errors={errorsByLocalId}
        />
      </div>
    </div>
  );
}
