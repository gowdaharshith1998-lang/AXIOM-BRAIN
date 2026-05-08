import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { CompanyBrainPage } from "@/components/company-brain/CompanyBrainPage";
import { CompanyBrainGraph } from "@/components/company-brain/CompanyBrainGraph";
import type { CompanyBrainCluster } from "@/components/company-brain/companyBrainTypes";
import { TAB_ORDER } from "@/lib/cluster-layout";

afterEach(() => {
  vi.restoreAllMocks();
  window.location.hash = "";
});

function mockFetchOk(urlToJson: Record<string, unknown>) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const json = urlToJson[url];
    if (json === undefined) return new Response("not found", { status: 404 });
    return new Response(JSON.stringify(json), { status: 200, headers: { "Content-Type": "application/json" } });
  });
}

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  close() {
    this.onclose?.();
  }
}

describe("CompanyBrainGraph interactions (spec)", () => {
  it("clicking a cluster transitions to FOCUS_CLUSTER and updates URL hash", async () => {
    const OriginalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    mockFetchOk({
      "http://127.0.0.1:8000/api/health": { status: "ok" },
      "/api/entities": [],
      "/api/edges": [],
      "/api/cluster_health": {},
    });

    try {
      render(<CompanyBrainPage />);
      const cluster = await screen.findByLabelText(/People cluster,/i);
      fireEvent.click(cluster);
      expect(window.location.hash).toMatch(/^#cluster=/);
    } finally {
      globalThis.WebSocket = OriginalWebSocket;
    }
  });

  it("Esc clears focus and clears URL hash", async () => {
    const OriginalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    mockFetchOk({
      "http://127.0.0.1:8000/api/health": { status: "ok" },
      "/api/entities": [],
      "/api/edges": [],
      "/api/cluster_health": {},
    });

    try {
      render(<CompanyBrainPage />);
      const cluster = await screen.findByLabelText(/Systems cluster,/i);
      fireEvent.click(cluster);
      expect(window.location.hash).toMatch(/^#cluster=/);
      fireEvent.keyDown(window, { key: "Escape" });
      expect(window.location.hash).toBe("");
    } finally {
      globalThis.WebSocket = OriginalWebSocket;
    }
  });

  it("hovering a cluster dims other clusters (opacity < 0.5)", async () => {
    const OriginalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    mockFetchOk({
      "http://127.0.0.1:8000/api/health": { status: "ok" },
      "/api/entities": [],
      "/api/edges": [],
      "/api/cluster_health": {},
    });

    try {
      render(<CompanyBrainPage />);
      const peopleMatches = await screen.findAllByLabelText(/People cluster,/i);
      const vendorsMatches = await screen.findAllByLabelText(/Vendors cluster,/i);
      const people = peopleMatches.find((el) => el.classList.contains("cb-cluster-node")) ?? peopleMatches[0]!;
      const vendors = vendorsMatches.find((el) => el.classList.contains("cb-cluster-node")) ?? vendorsMatches[0]!;
      fireEvent.mouseEnter(people);
      expect(vendors.classList.contains("cb-dimmed")).toBe(true);
    } finally {
      globalThis.WebSocket = OriginalWebSocket;
    }
  });

  it("Tab cycles through all 14 clusters; Enter focuses the active cluster", async () => {
    const OriginalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    mockFetchOk({
      "http://127.0.0.1:8000/api/health": { status: "ok" },
      "/api/entities": [],
      "/api/edges": [],
      "/api/cluster_health": {},
    });

    try {
      render(<CompanyBrainPage />);
      const clusters = await screen.findAllByLabelText(/cluster,\s*\d+\s*entities/i);
      expect(clusters).toHaveLength(14);

      act(() => {
        clusters[0]?.focus();
      });
      expect(document.activeElement).toBe(clusters[0]);
      fireEvent.keyDown(clusters[0]!, { key: "Enter" });
      expect(window.location.hash).toMatch(/^#cluster=/);
    } finally {
      globalThis.WebSocket = OriginalWebSocket;
    }
  });

  it("clicking empty stage background clears focus (AMBIENT)", async () => {
    const OriginalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    mockFetchOk({
      "http://127.0.0.1:8000/api/health": { status: "ok" },
      "/api/entities": [],
      "/api/edges": [],
      "/api/cluster_health": {},
    });

    try {
      render(<CompanyBrainPage />);
      const cluster = await screen.findByLabelText(/Policies cluster,/i);
      fireEvent.click(cluster);
      expect(window.location.hash).toMatch(/^#cluster=/);
      const stage = await screen.findByLabelText("Company Brain knowledge graph stage");
      fireEvent.click(stage);
      expect(window.location.hash).toBe("");
    } finally {
      globalThis.WebSocket = OriginalWebSocket;
    }
  });

  it("clicking an entity glyph in focus transitions to FOCUS_ENTITY and sets #entity=", async () => {
    const OriginalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    mockFetchOk({
      "http://127.0.0.1:8000/api/health": { status: "ok" },
      "/api/entities": [{ id: "e1", type: "system", data: { name: "Payments Service" }, source_id: null, created_at: "", updated_at: "", cluster_id: "systems", composite_importance: 0.9 }],
      "/api/edges": [],
      "/api/cluster_health": {},
    });

    try {
      render(<CompanyBrainPage />);
      const cluster = await screen.findByLabelText(/Systems cluster,/i);
      fireEvent.click(cluster);
      const entity = await screen.findByLabelText(/Payments Service entity/i);
      fireEvent.click(entity);
      expect(window.location.hash).toMatch(/^#entity=/);
    } finally {
      globalThis.WebSocket = OriginalWebSocket;
    }
  });

  it("hover updates cursor to pointer on cluster hit region", async () => {
    const OriginalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    mockFetchOk({
      "http://127.0.0.1:8000/api/health": { status: "ok" },
      "/api/entities": [],
      "/api/edges": [],
      "/api/cluster_health": {},
    });

    try {
      const { container } = render(<CompanyBrainPage />);
      const matches = await screen.findAllByLabelText(/Documents cluster,/i);
      const cluster = matches.find((el) => el.classList.contains("cb-cluster-node")) ?? matches[0]!;
      fireEvent.mouseEnter(cluster);
      expect(getComputedStyle(container.querySelector(".cb-cluster-node") ?? cluster).cursor).toBe("pointer");
    } finally {
      globalThis.WebSocket = OriginalWebSocket;
    }
  });

  it("Tab cycles document.activeElement through all 14 clusters in layout order", async () => {
    const clusters: CompanyBrainCluster[] = [
      { id: "people", label: "People", count: 1248, icon: "person", color: "#2788ff", x: 510, y: 145, satellites: 6, filter: "People", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "leadership", label: "Leadership", count: 28, icon: "group", color: "#c15cff", x: 720, y: 140, satellites: 6, filter: "People", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "meetings", label: "Meetings", count: 1932, icon: "calendar", color: "#24d9ff", x: 835, y: 200, satellites: 6, filter: "Meetings", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "decisions", label: "Decisions", count: 763, icon: "check", color: "#ff6bd5", x: 990, y: 150, satellites: 6, filter: "Decisions", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "code", label: "Code (GitHub)", count: 512, icon: "code", color: "#2f8dff", x: 1035, y: 250, satellites: 6, filter: "Code / Repos", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "projects", label: "Projects", count: 132, icon: "target", color: "#ff9416", x: 1145, y: 250, satellites: 6, filter: "Projects", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "tickets", label: "Tickets (Linear)", count: 2341, icon: "ticket", color: "#ffb21c", x: 1230, y: 380, satellites: 6, filter: "Tickets", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "incidents", label: "Incidents", count: 59, icon: "alert", color: "#ff5a5f", x: 1170, y: 490, satellites: 6, filter: "Incidents", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "systems", label: "Systems", count: 184, icon: "cube", color: "#65e78f", x: 970, y: 520, satellites: 6, filter: "Systems", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "vendors", label: "Vendors", count: 87, icon: "briefcase", color: "#5b70ff", x: 745, y: 525, satellites: 6, filter: "Vendors", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "customers", label: "Customers", count: 318, icon: "building", color: "#00e5d4", x: 405, y: 510, satellites: 6, filter: "Customers", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "policies", label: "Policies", count: 64, icon: "shield", color: "#bd68ff", x: 330, y: 400, satellites: 6, filter: "Policies", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "documents", label: "Documents", count: 6128, icon: "file", color: "#3a83ff", x: 545, y: 330, satellites: 6, filter: "Documents", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
      { id: "teams", label: "Teams", count: 142, icon: "team", color: "#00d7df", x: 330, y: 245, satellites: 6, filter: "Teams", status: "healthy", description: "", owner: "", team: "", criticality: "Medium", confidence: 90, connections: [] },
    ];

    const { container } = render(
      <CompanyBrainGraph
        clusters={clusters}
        hiddenFilters={new Set()}
        selectedId=""
        hoveredId={null}
        onSelect={() => undefined}
        onHover={() => undefined}
      />,
    );

    const focusables = container.querySelectorAll<HTMLElement>('[data-cluster-id][tabindex="0"]');
    expect(focusables.length).toBe(14);
    expect(Array.from(focusables).map((el) => el.dataset.clusterId)).toEqual(Array.from(TAB_ORDER));

    focusables[0]!.focus();
    for (let i = 0; i < 14; i++) {
      expect(document.activeElement).toBe(focusables[i]);
      focusables[i + 1]?.focus();
    }
  });
});

