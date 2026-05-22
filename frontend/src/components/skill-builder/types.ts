// Block IR — mirrors src/axiom/skills/skill_file.py
// Every block carries a `_localId` for React keys + reorder.

export type LocalId = string;

export type TriggerMatcher = {
  intent: string;
  source: string[];
};

export type IfThenBlock = {
  _localId: LocalId;
  type: "if_then";
  id: string;
  condition: string;
  then: AnyStepBlock[];
};

export type FetchEntityBlock = {
  _localId: LocalId;
  type: "fetch_entity";
  id: string;
  query: string;
  bind_to: string;
};

export type WriteEntityBlock = {
  _localId: LocalId;
  type: "write_entity";
  id: string;
  cluster: string;
  entity_type: string;
  data: Record<string, unknown>;
};

export type RequireApprovalBlock = {
  _localId: LocalId;
  type: "require_approval";
  id: string;
  role: string;
  timeout_seconds: number;
};

export type LogDecisionBlock = {
  _localId: LocalId;
  type: "log_decision";
  id: string;
  cluster: string;
  note: string;
};

export type AnyStepBlock =
  | IfThenBlock
  | FetchEntityBlock
  | WriteEntityBlock
  | RequireApprovalBlock
  | LogDecisionBlock;

export type SkillFileDoc = {
  name: string;
  description: string;
  version: number;
  when_triggered_by: TriggerMatcher[];
  steps: AnyStepBlock[];
};

export const STEP_TYPE_LABELS: Record<AnyStepBlock["type"], string> = {
  if_then: "If / Then",
  fetch_entity: "Look Up Entity",
  write_entity: "Create Entity",
  require_approval: "Require Approval",
  log_decision: "Log Decision",
};

export const STEP_TYPE_ORDER: AnyStepBlock["type"][] = [
  "if_then",
  "fetch_entity",
  "write_entity",
  "require_approval",
  "log_decision",
];
