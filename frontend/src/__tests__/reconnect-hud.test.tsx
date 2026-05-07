import { render, screen } from "@testing-library/react";
import { cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { HUD } from "@/components/HUD";
import { useBrainStore } from "@/state/brain.store";

describe("reconnect HUD", () => {
  afterEach(() => cleanup());

  it("shows syncing before first event", () => {
    useBrainStore.setState({ connectionStatus: "syncing", fps: 0 });
    render(<HUD />);
    expect(screen.getByText("syncing")).toBeInTheDocument();
    expect(screen.getByText("syncing renderer")).toBeInTheDocument();
  });

  it("shows live after first event", () => {
    useBrainStore.setState({ connectionStatus: "live", fps: 60 });
    render(<HUD />);
    expect(screen.getAllByText("live").length).toBeGreaterThanOrEqual(1);
  });

  it("shows offline on disconnect", () => {
    useBrainStore.setState({ connectionStatus: "offline", fps: 60 });
    render(<HUD />);
    expect(screen.getAllByText("offline · reconnecting").length).toBeGreaterThanOrEqual(1);
  });
});
