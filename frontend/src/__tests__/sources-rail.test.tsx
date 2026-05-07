import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourcesRail } from "@/components/SourcesRail";

describe("SourcesRail", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });
  it("renders synthetic source rows", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      json: async () => [
        { name: "Slack", count: 1247, freshness: "live", live: true },
        { name: "Linear", count: 312, freshness: "2m ago", live: false },
      ],
    } as Response);
    render(<SourcesRail />);
    expect(await screen.findByText("Slack")).toBeInTheDocument();
    expect(screen.getByText("Linear")).toBeInTheDocument();
  });

  it("dispatches layer toggle events", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new Error("offline"));
    const dispatch = vi.spyOn(window, "dispatchEvent");
    render(<SourcesRail />);
    await waitFor(() => expect(screen.getByText("Traffic Flow")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("Traffic Flow"));
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "axiom:layer-toggle" }));
  });

  it("shows AEGIS governance status", () => {
    render(<SourcesRail />);
    expect(screen.getAllByText("AEGIS governance active").length).toBeGreaterThanOrEqual(1);
  });

  it("keeps placeholder layers disabled", () => {
    render(<SourcesRail />);
    expect(screen.getByLabelText("Dark Matter")).toBeDisabled();
    expect(screen.getByLabelText("Tests")).toBeDisabled();
  });
});
