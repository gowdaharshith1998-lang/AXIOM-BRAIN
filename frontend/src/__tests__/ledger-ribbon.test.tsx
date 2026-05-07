import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LedgerRibbon } from "@/components/LedgerRibbon";
import { useBrainStore } from "@/state/brain.store";

describe("LedgerRibbon", () => {
  afterEach(cleanup);
  it("renders fallback receipt hashes", () => {
    useBrainStore.setState({ receipts: [] });
    render(<LedgerRibbon />);
    expect(screen.getByText("Ledger")).toBeInTheDocument();
    expect(screen.getByText(/merkle root/)).toBeInTheDocument();
  });

  it("renders live receipts from the store", () => {
    useBrainStore.setState({
      receipts: [
        {
          receipt_id: "7a3f000000000000000000000000e2c9",
          action_id: "act_1",
          decision: "deny",
          agent_name: "gpt-5",
          merkle_root: "8c2d000000000000000000000000ff04",
          timestamp: "t",
        },
      ],
    });
    render(<LedgerRibbon />);
    expect(screen.getAllByText("deny").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("gpt-5").length).toBeGreaterThanOrEqual(1);
  });

  it("shows fallback receipt count for demos", () => {
    useBrainStore.setState({ receipts: [] });
    render(<LedgerRibbon />);
    expect(screen.getByText("89")).toBeInTheDocument();
  });
});
