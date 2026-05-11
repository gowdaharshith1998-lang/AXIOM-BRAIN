import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BrainHealthCard } from "@/components/BrainHealthCard";
import { useBrainStore } from "@/state/brain.store";

function mockHistoryFetch(snapshots: Array<{ date: string; brain_health_score: number }>) {
  const fetchMock = vi.fn(async () => {
    return new Response(
      JSON.stringify({
        metric: "brain_health",
        snapshots,
        timeseries: snapshots.map((snapshot) => ({
          date: snapshot.date,
          value: snapshot.brain_health_score,
        })),
      }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("BrainHealthCard history", () => {
  beforeEach(() => {
    useBrainStore.setState({
      entities: new Map(),
      edges: new Map(),
      fps: 60,
      clusterHealth: {},
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("brainhealthcard_fetches_real_history_metric", async () => {
    const fetchMock = mockHistoryFetch([
      { date: "2026-05-10", brain_health_score: 0.74 },
    ]);

    render(<BrainHealthCard />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/internal/metrics-snapshots?days=2&metric=brain_health",
        expect.any(Object),
      );
    });
  });

  it("brainhealthcard_empty_history_state", async () => {
    mockHistoryFetch([]);

    render(<BrainHealthCard />);

    expect(await screen.findByText("Collecting health history...")).toBeInTheDocument();
  });

  it("brainhealthcard_renders_only_real_history_points", async () => {
    mockHistoryFetch([
      { date: "2026-05-09", brain_health_score: 0.70 },
      { date: "2026-05-10", brain_health_score: 0.95 },
    ]);

    const { container } = render(<BrainHealthCard />);

    await waitFor(() => {
      const points = container.querySelector("polyline")?.getAttribute("points") ?? "";
      expect(points.trim().split(/\s+/)).toHaveLength(2);
    });
  });

  it("brainhealthcard_uses_metric_timeseries_values", async () => {
    mockHistoryFetch([
      { date: "2026-05-08", brain_health_score: 0.10 },
      { date: "2026-05-09", brain_health_score: 0.50 },
      { date: "2026-05-10", brain_health_score: 0.90 },
    ]);

    const { container } = render(<BrainHealthCard />);

    await waitFor(() => {
      const points = container.querySelector("polyline")?.getAttribute("points") ?? "";
      expect(points).toBe("0.0,29.0 93.0,17.0 186.0,5.0");
    });
  });
});
