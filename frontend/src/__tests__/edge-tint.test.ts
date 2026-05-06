import { describe, expect, it } from "vitest";

import { FALLBACK_RELATIONSHIP_COLOR, RELATIONSHIP_COLORS, colorForRelationship } from "@/lib/edge-tint";

describe("edge-tint", () => {
  it("maps known relationships to the Phase 4.1 palette", () => {
    expect(colorForRelationship("PERSON_PARTICIPATES_IN_THREAD")).toBe("#8BE9FD");
    expect(colorForRelationship("TICKET_ASSIGNED_TO_PERSON")).toBe("#FF79C6");
    expect(colorForRelationship("CODE_RESOLVES_TICKET")).toBe("#7CFC9F");
    expect(Object.isFrozen(RELATIONSHIP_COLORS)).toBe(true);
  });

  it("falls back to white for unknown relationships", () => {
    expect(colorForRelationship("UNKNOWN")).toBe(FALLBACK_RELATIONSHIP_COLOR);
  });
});
