import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EntityInspector } from "@/components/EntityInspector";
import { prettyMetadata } from "@/lib/inspector";
import { useBrainStore } from "@/state/brain.store";

const entity = {
  id: "e1",
  type: "document",
  source_id: null,
  created_at: "2026-05-07T00:00:00Z",
  updated_at: "2026-05-07T00:00:00Z",
};

describe("inspector metadata", () => {
  afterEach(() => vi.useRealTimers());

  it("hides null Calibra fields", () => {
    expect(prettyMetadata({ calibra: null, name: "Invoice" })).toBe('{\n  "name": "Invoice"\n}');
  });

  it("hides empty string fields", () => {
    expect(prettyMetadata({ name: "", title: "Policy" })).toContain("Policy");
    expect(prettyMetadata({ name: "", title: "Policy" })).not.toContain("name");
  });

  it("hides empty metadata objects", () => {
    expect(prettyMetadata({ calibra: { id: null }, empty: {} })).toBeNull();
  });

  it("shows populated fields unchanged", () => {
    expect(prettyMetadata({ nested: { id: "c1" } })).toBe('{\n  "nested": {\n    "id": "c1"\n  }\n}');
  });

  it("fades out for three hundred ms before unmounting", () => {
    vi.useFakeTimers();
    useBrainStore.setState({
      entities: new Map([["e1", { ...entity, data: { title: "A" } }]]),
      selectedId: "e1",
    });
    render(<EntityInspector />);
    expect(screen.getByText("e1")).toBeInTheDocument();
    act(() => useBrainStore.setState({ selectedId: null }));
    expect(screen.getByText("e1").closest("div[style]")).toHaveStyle({ opacity: "0" });
    act(() => vi.advanceTimersByTime(300));
    expect(screen.queryByText("e1")).not.toBeInTheDocument();
  });
});
