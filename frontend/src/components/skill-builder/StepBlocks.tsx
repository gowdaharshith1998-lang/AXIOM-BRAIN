import { useState } from "react";
import type { ReactNode } from "react";
import type {
  AnyStepBlock,
  IfThenBlock,
  FetchEntityBlock,
  WriteEntityBlock,
  RequireApprovalBlock,
  LogDecisionBlock,
} from "./types";
import { STEP_TYPE_LABELS, STEP_TYPE_ORDER } from "./types";
import { newLocalId } from "./compile";

type BlockProps<T extends AnyStepBlock> = {
  block: T;
  onChange: (next: T) => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
  errors?: string[];
  depth: number;
};

const STEP_TYPE_TINT: Record<AnyStepBlock["type"], string> = {
  if_then: "border-amber-500/40 bg-amber-500/[0.04]",
  fetch_entity: "border-cyan-500/40 bg-cyan-500/[0.04]",
  write_entity: "border-emerald-500/40 bg-emerald-500/[0.04]",
  require_approval: "border-orange-500/40 bg-orange-500/[0.04]",
  log_decision: "border-blue-500/40 bg-blue-500/[0.04]",
};

function BlockShell({
  block,
  depth,
  canMoveUp,
  canMoveDown,
  onMoveUp,
  onMoveDown,
  onDelete,
  onChangeId,
  errors,
  children,
}: {
  block: AnyStepBlock;
  depth: number;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
  onChangeId: (next: string) => void;
  errors?: string[];
  children: ReactNode;
}) {
  const tint = STEP_TYPE_TINT[block.type];
  return (
    <div className={`rounded-lg border ${tint} p-3`} style={{ marginLeft: depth * 16 }}>
      <div className="flex items-center gap-2">
        <div className="flex-1 flex items-center gap-2">
          <span className="rounded border border-white/15 bg-white/5 px-2 py-0.5 text-xs uppercase tracking-wide text-white/70">
            {STEP_TYPE_LABELS[block.type]}
          </span>
          <input
            value={block.id}
            onChange={(e) => onChangeId(e.target.value)}
            placeholder="step_id"
            className="rounded border border-white/10 bg-black/30 px-2 py-1 font-mono text-xs text-white/90"
          />
        </div>
        <button onClick={onMoveUp} disabled={!canMoveUp} className="rounded border border-white/15 px-2 py-1 text-xs hover:bg-white/10 disabled:opacity-30">↑</button>
        <button onClick={onMoveDown} disabled={!canMoveDown} className="rounded border border-white/15 px-2 py-1 text-xs hover:bg-white/10 disabled:opacity-30">↓</button>
        <button onClick={onDelete} className="rounded border border-red-500/30 bg-red-500/5 px-2 py-1 text-xs text-red-300 hover:bg-red-500/20">Delete</button>
      </div>
      {errors && errors.length > 0 ? (
        <div className="mt-2 rounded border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-200">
          {errors.map((e, i) => <div key={i}>• {e}</div>)}
        </div>
      ) : null}
      <div className="mt-3 space-y-2">{children}</div>
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  placeholder,
  mono,
  multiline,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
  multiline?: boolean;
}) {
  return (
    <label className="block">
      <span className="block text-xs text-white/55 mb-1">{label}</span>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          spellCheck={false}
          className={`w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white/90 ${mono ? "font-mono" : ""}`}
          rows={2}
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          spellCheck={false}
          className={`w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white/90 ${mono ? "font-mono" : ""}`}
        />
      )}
    </label>
  );
}

function NumberInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <span className="block text-xs text-white/55 mb-1">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white/90"
      />
    </label>
  );
}

// Each step type below renders its inputs as labelled fields. The "id" field
// is in the shell header (every block has it).

export function IfThenBlockView({
  block,
  onChange,
  depth,
  errors,
  ...nav
}: BlockProps<IfThenBlock>) {
  return (
    <BlockShell
      block={block}
      depth={depth}
      errors={errors}
      onChangeId={(id) => onChange({ ...block, id })}
      {...nav}
    >
      <LabeledInput
        label="Condition (DSL expression — e.g. trigger.payload.amount > 500)"
        value={block.condition}
        onChange={(condition) => onChange({ ...block, condition })}
        placeholder="trigger.payload.amount > 500"
        mono
      />
      {/* The nested `then` blocks are rendered by the parent BlockList */}
    </BlockShell>
  );
}

export function FetchEntityBlockView({
  block,
  onChange,
  depth,
  errors,
  ...nav
}: BlockProps<FetchEntityBlock>) {
  return (
    <BlockShell block={block} depth={depth} errors={errors} onChangeId={(id) => onChange({ ...block, id })} {...nav}>
      <LabeledInput
        label="Query (entity_type:entity_id; supports {trigger.payload.x})"
        value={block.query}
        onChange={(query) => onChange({ ...block, query })}
        placeholder="customer:{trigger.payload.customer_id}"
        mono
      />
      <LabeledInput
        label="Bind result to variable name"
        value={block.bind_to}
        onChange={(bind_to) => onChange({ ...block, bind_to })}
        placeholder="customer"
        mono
      />
    </BlockShell>
  );
}

export function WriteEntityBlockView({
  block,
  onChange,
  depth,
  errors,
  ...nav
}: BlockProps<WriteEntityBlock>) {
  // For v1, render data as a JSON textarea — keeps scope tight, still no YAML.
  const [dataText, setDataText] = useState(JSON.stringify(block.data, null, 2));
  return (
    <BlockShell block={block} depth={depth} errors={errors} onChangeId={(id) => onChange({ ...block, id })} {...nav}>
      <LabeledInput
        label="Cluster"
        value={block.cluster}
        onChange={(cluster) => onChange({ ...block, cluster })}
        placeholder="billing"
        mono
      />
      <LabeledInput
        label="Entity type"
        value={block.entity_type}
        onChange={(entity_type) => onChange({ ...block, entity_type })}
        placeholder="refund_note"
        mono
      />
      <label className="block">
        <span className="block text-xs text-white/55 mb-1">Data (JSON; supports {`{trigger.payload.x}`})</span>
        <textarea
          value={dataText}
          onChange={(e) => {
            setDataText(e.target.value);
            try {
              const parsed = JSON.parse(e.target.value);
              if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                onChange({ ...block, data: parsed });
              }
            } catch {
              // Save will catch it; do not block typing.
            }
          }}
          spellCheck={false}
          className="w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 font-mono text-xs text-white/90"
          rows={3}
        />
      </label>
    </BlockShell>
  );
}

export function RequireApprovalBlockView({
  block,
  onChange,
  depth,
  errors,
  ...nav
}: BlockProps<RequireApprovalBlock>) {
  return (
    <BlockShell block={block} depth={depth} errors={errors} onChangeId={(id) => onChange({ ...block, id })} {...nav}>
      <LabeledInput
        label="Approver role"
        value={block.role}
        onChange={(role) => onChange({ ...block, role })}
        placeholder="vp_support"
      />
      <NumberInput
        label="Timeout (seconds; default 3600)"
        value={block.timeout_seconds}
        onChange={(timeout_seconds) => onChange({ ...block, timeout_seconds })}
      />
    </BlockShell>
  );
}

export function LogDecisionBlockView({
  block,
  onChange,
  depth,
  errors,
  ...nav
}: BlockProps<LogDecisionBlock>) {
  return (
    <BlockShell block={block} depth={depth} errors={errors} onChangeId={(id) => onChange({ ...block, id })} {...nav}>
      <LabeledInput
        label="Cluster"
        value={block.cluster}
        onChange={(cluster) => onChange({ ...block, cluster })}
        placeholder="billing"
        mono
      />
      <LabeledInput
        label="Note (supports {trigger.payload.x} and {bound_var.field})"
        value={block.note}
        onChange={(note) => onChange({ ...block, note })}
        placeholder="Refund for {customer.name}: ${trigger.payload.amount}"
        multiline
      />
    </BlockShell>
  );
}

// AddStepMenu — dropdown to pick which step type to add.
export function AddStepMenu({
  onAdd,
  label = "Add step",
}: {
  onAdd: (type: AnyStepBlock["type"]) => void;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen((v) => !v)}
        className="rounded border border-white/20 bg-white/[0.04] px-3 py-1.5 text-sm hover:bg-white/[0.08]"
      >
        + {label}
      </button>
      {open ? (
        <div className="absolute z-10 mt-1 w-56 rounded border border-white/20 bg-[#0a1424] p-1 shadow-lg">
          {STEP_TYPE_ORDER.map((type) => (
            <button
              key={type}
              onClick={() => {
                onAdd(type);
                setOpen(false);
              }}
              className="block w-full rounded px-3 py-1.5 text-left text-sm hover:bg-white/[0.06]"
            >
              {STEP_TYPE_LABELS[type]}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function newDefaultStep(type: AnyStepBlock["type"]): AnyStepBlock {
  const _localId = newLocalId();
  const id = `step_${_localId.slice(4, 10)}`;
  switch (type) {
    case "if_then":
      return { _localId, type, id, condition: "", then: [] };
    case "fetch_entity":
      return { _localId, type, id, query: "", bind_to: "" };
    case "write_entity":
      return { _localId, type, id, cluster: "", entity_type: "", data: {} };
    case "require_approval":
      return { _localId, type, id, role: "", timeout_seconds: 3600 };
    case "log_decision":
      return { _localId, type, id, cluster: "", note: "" };
  }
}
