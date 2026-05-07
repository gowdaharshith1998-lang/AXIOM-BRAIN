import { describe, expect, it } from "vitest";

import { PhaseStubApp } from "@/components/PhaseStubApp";

describe("PhaseStubApp", () => {
  it("throws as a Phase 4 stub", () => {
    expect(() => PhaseStubApp()).toThrow(/PhaseStubApp is removed in Phase 4/);
  });
});

