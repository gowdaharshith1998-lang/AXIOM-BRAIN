import {
  IfThenBlockView,
  FetchEntityBlockView,
  WriteEntityBlockView,
  RequireApprovalBlockView,
  LogDecisionBlockView,
  AddStepMenu,
  newDefaultStep,
} from "./StepBlocks";
import type { AnyStepBlock, IfThenBlock } from "./types";

type ErrorsByLocalId = Record<string, string[]>;

export function BlockList({
  blocks,
  onChange,
  errors,
  depth = 0,
}: {
  blocks: AnyStepBlock[];
  onChange: (next: AnyStepBlock[]) => void;
  errors: ErrorsByLocalId;
  depth?: number;
}) {
  const updateAt = (index: number, next: AnyStepBlock) => {
    const copy = blocks.slice();
    copy[index] = next;
    onChange(copy);
  };
  const removeAt = (index: number) => {
    const target = blocks[index];
    if (target.type === "if_then" && target.then.length > 0) {
      if (!window.confirm("This block has nested steps. Delete anyway?")) return;
    }
    const copy = blocks.slice();
    copy.splice(index, 1);
    onChange(copy);
  };
  const moveUp = (index: number) => {
    if (index === 0) return;
    const copy = blocks.slice();
    [copy[index - 1], copy[index]] = [copy[index], copy[index - 1]];
    onChange(copy);
  };
  const moveDown = (index: number) => {
    if (index === blocks.length - 1) return;
    const copy = blocks.slice();
    [copy[index], copy[index + 1]] = [copy[index + 1], copy[index]];
    onChange(copy);
  };
  const addStep = (type: AnyStepBlock["type"]) => {
    onChange([...blocks, newDefaultStep(type)]);
  };

  return (
    <div className="space-y-2">
      {blocks.map((block, index) => {
        const nav = {
          onDelete: () => removeAt(index),
          onMoveUp: () => moveUp(index),
          onMoveDown: () => moveDown(index),
          canMoveUp: index > 0,
          canMoveDown: index < blocks.length - 1,
          errors: errors[block._localId],
          depth,
        };
        if (block.type === "if_then") {
          return (
            <div key={block._localId}>
              <IfThenBlockView
                block={block}
                onChange={(next) => updateAt(index, next)}
                {...nav}
              />
              <div className="ml-4 mt-2 border-l-2 border-amber-500/30 pl-3">
                <div className="mb-1 text-xs uppercase tracking-wide text-amber-300/70">Then:</div>
                <BlockList
                  blocks={block.then}
                  onChange={(nextNested) =>
                    updateAt(index, { ...block, then: nextNested } as IfThenBlock)
                  }
                  errors={errors}
                  depth={depth + 1}
                />
              </div>
            </div>
          );
        }
        if (block.type === "fetch_entity") {
          return <FetchEntityBlockView key={block._localId} block={block} onChange={(next) => updateAt(index, next)} {...nav} />;
        }
        if (block.type === "write_entity") {
          return <WriteEntityBlockView key={block._localId} block={block} onChange={(next) => updateAt(index, next)} {...nav} />;
        }
        if (block.type === "require_approval") {
          return <RequireApprovalBlockView key={block._localId} block={block} onChange={(next) => updateAt(index, next)} {...nav} />;
        }
        if (block.type === "log_decision") {
          return <LogDecisionBlockView key={block._localId} block={block} onChange={(next) => updateAt(index, next)} {...nav} />;
        }
        return null;
      })}
      <div className="pt-1">
        <AddStepMenu onAdd={addStep} label={depth === 0 ? "Add step" : "Add nested step"} />
      </div>
    </div>
  );
}
