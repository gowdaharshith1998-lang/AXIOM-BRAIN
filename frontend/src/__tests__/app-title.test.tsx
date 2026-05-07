import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/App";
import { useBrainStore } from "@/state/brain.store";

vi.mock("@/components/Brain", () => ({ Brain: () => <div /> }));
vi.mock("@/components/SourcesRail", () => ({ SourcesRail: () => <div /> }));
vi.mock("@/components/InspectorPanel", () => ({ InspectorPanel: () => <div /> }));

describe("browser title", () => {
  it("includes entity count when live", () => {
    useBrainStore.setState({
      entities: new Map([
        ["a", { id: "a", type: "document", data: {}, source_id: null, created_at: "", updated_at: "" }],
      ]),
      connectionStatus: "live",
    });
    render(<App />);
    expect(document.title).toBe("AXIOM · 1 · live");
  });

  it("changes on disconnect", () => {
    useBrainStore.setState({ entities: new Map(), connectionStatus: "offline" });
    render(<App />);
    expect(document.title).toBe("AXIOM · 0 · offline");
  });
});
