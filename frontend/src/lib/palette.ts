export const ENTITY_TYPES = [
  "code",
  "people",
  "decision",
  "thread",
  "ticket",
  "document",
  "process",
] as const;

export type EntityType = (typeof ENTITY_TYPES)[number];

export const PALETTE: Record<EntityType, string> = {
  code: "#7CFC9F",
  people: "#FFB86C",
  decision: "#BD93F9",
  thread: "#8BE9FD",
  ticket: "#FF79C6",
  document: "#F1FA8C",
  process: "#50FA7B",
};

export const FALLBACK_COLOR = "#6272A4";

export function colorForType(type: string): string {
  if ((ENTITY_TYPES as readonly string[]).includes(type)) {
    return PALETTE[type as EntityType];
  }
  return FALLBACK_COLOR;
}
