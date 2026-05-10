import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "@/pages/SettingsPage";

vi.mock("@/lib/studioClient", () => ({
  getStudioSettings: vi.fn().mockResolvedValue({ company_name: "Axiom Analytics Inc." }),
  saveStudioSettings: vi.fn().mockResolvedValue({}),
  getMcpStats: vi.fn().mockResolvedValue({
    connected_clients: 2,
    last_tool_call: 1710000000000,
    active_agents: ["organizer"],
    recent_actions: [],
    tools: [
      { name: "axiom_query_brain", calls: 1, last_called: 1710000000000 },
      { name: "axiom_get_entity", calls: 0, last_called: null },
    ],
  }),
  getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
}));

vi.mock("@/lib/vaultClient", async () => {
  const actual = await vi.importActual<typeof import("@/lib/vaultClient")>("@/lib/vaultClient");
  return {
    ...actual,
    listProviders: vi.fn().mockResolvedValue([
      {
        id: "openai",
        display_name: "OpenAI",
        kind: "llm",
        credential_shape: [{ name: "api_key", label: "API Key", secret: true }],
        docs_url: "https://example.com",
        verify_endpoint: "GET https://example.com",
      },
    ]),
    listSecrets: vi.fn().mockResolvedValue([]),
  };
});

function renderSettings() {
  render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders general settings with real company field", async () => {
    renderSettings();
    await waitFor(() => expect(screen.getByDisplayValue("Axiom Analytics Inc.")).toBeInTheDocument());
  });

  it("switches to API & MCP and shows real MCP stats plus vault", async () => {
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "API & MCP" }));
    await waitFor(() => expect(screen.getByText("MCP Server")).toBeInTheDocument());
    expect(screen.getByText("axiom_query_brain")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("OpenAI")).toBeInTheDocument());
  });

  it("opens the real API key vault dialog", async () => {
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "API & MCP" }));
    await waitFor(() => expect(screen.getByText("OpenAI")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Connect OpenAI");
  });

  it.each([
    ["Integrations", "Data Sources / Integrations"],
    ["Access", "Members"],
    ["Notifications", "Notification Rules"],
    ["Security", "Authentication"],
    ["Preferences", "Appearance"],
  ])("renders %s tab content", async (tab, heading) => {
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: tab }));
    await waitFor(() => expect(screen.getByText(heading)).toBeInTheDocument());
  });
});
