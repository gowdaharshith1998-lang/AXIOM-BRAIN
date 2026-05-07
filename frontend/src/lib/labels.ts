import type { FpsGuardState } from "@/lib/fps-guard";
import type { Entity } from "@/state/brain.store";

export const MAX_LABEL_LEN = 24;
export const LABEL_SHOW_DISTANCE = 80;
export const LABEL_HIDE_DISTANCE = 120;
export const CLUSTER_LABEL_VISIBLE_DISTANCE = 200;
export const LABEL_FPS_HIDE_THRESHOLD = 50;
export const LABEL_FPS_RECOVER_THRESHOLD = 55;

export interface LabelVisibilityInput {
  nodeId: string;
  cameraDistance: number;
  selectedId: string | null;
  selectedNeighborIds: ReadonlySet<string>;
  fpsGuardState: FpsGuardState;
  currentlyVisible?: boolean;
}

export function truncate(text: string, maxLen = MAX_LABEL_LEN): string {
  if (text.length <= maxLen) return text;
  if (maxLen <= 1) return "…".slice(0, maxLen);
  return `${text.slice(0, maxLen - 1)}…`;
}

export function displayLabelFor(entity: Entity): string {
  const data = entity.data ?? {};
  let raw: string | null = null;

  switch (entity.type) {
    case "ticket":
    case "thread":
    case "document":
    case "decision":
      raw = typeof data.title === "string" ? data.title : null;
      break;
    case "process":
    case "people":
      raw = typeof data.name === "string" ? data.name : null;
      break;
    case "code": {
      const filePath = typeof data.file_path === "string" ? data.file_path : null;
      raw = filePath ? (filePath.split("/").pop() ?? filePath) : null;
      break;
    }
  }

  const fallback = entity.id.slice(0, 8);
  const label = raw?.trim() ? raw.trim() : fallback;
  return truncate(label);
}

export function shouldShowLabel(input: LabelVisibilityInput): boolean {
  if (input.nodeId === input.selectedId) return true;
  if (input.selectedId !== null && input.selectedNeighborIds.has(input.nodeId)) return true;
  if (input.fpsGuardState === "emergency") return false;
  if (input.currentlyVisible) return input.cameraDistance <= LABEL_HIDE_DISTANCE;
  return input.cameraDistance <= LABEL_SHOW_DISTANCE;
}
