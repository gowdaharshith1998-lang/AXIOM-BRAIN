import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InsightsPage } from "@/pages/InsightsPage";
import { useBrainStore } from "@/state/brain.store";

vi.mock("@/lib/studioClient", () => ({
  getMcpStats: vi.fn().mockResolvedValue({
    connected_clients: 1,
    last_tool_call: 1710000000000,
    active_agents: ["researcher"],
    recent_actions: [],
    tools: [],
  }),
}));

function renderInsights() {
  return render(
    <MemoryRouter initialEntries={["/insights?tab=trends"]}>
      <InsightsPage />
    </MemoryRouter>,
  );
}

describe("insights interactive controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBrainStore.setState({
      entities: new Map(),
      edges: new Map(),
      insights: [],
      receipts: [],
      agentActions: [],
    });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input.toString();
      if (path === "/api/entities") {
        return new Response(JSON.stringify([{ id: "doc_1", type: "document", data: { title: "Design Doc" }, source_id: null, cluster_id: "product", created_at: "2026-05-10T00:00:00", updated_at: "2026-05-10T00:00:00" }]), { status: 200 });
      }
      if (path === "/api/edges") return new Response(JSON.stringify([]), { status: 200 });
      if (path === "/api/cluster_health") return new Response(JSON.stringify({}), { status: 200 });
      return new Response("{}", { status: 404 });
    }));
    URL.createObjectURL = vi.fn(() => "blob:trend");
    URL.revokeObjectURL = vi.fn();
  });

  it("trends filters empty metrics and exports a chart csv from each card", async () => {
    renderInsights();
    expect(await screen.findByText("Entities Created")).toBeInTheDocument();
    expect(screen.getByText("Relationships Created")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hide Empty Metrics" }));
    await waitFor(() => expect(screen.queryByText("Relationships Created")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Download Entities Created trend" }));
    expect(URL.createObjectURL).toHaveBeenCalled();
  });
});
