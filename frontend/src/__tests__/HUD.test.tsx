import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HUD } from "@/components/HUD";
import { useBrainStore } from "@/state/brain.store";

describe("HUD", () => {
  it("renders entity count", () => {
    useBrainStore.setState({
      entities: new Map([
        [
          "e1",
          {
            id: "e1",
            type: "thread",
            data: {},
            source_id: null,
            created_at: "t",
            updated_at: "t",
          },
        ],
      ]),
      edges: new Map(),
      lastSeq: 0,
      fps: 60,
      selectedId: null,
    });

    render(<HUD />);
    expect(screen.getByText("entities")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });
});

