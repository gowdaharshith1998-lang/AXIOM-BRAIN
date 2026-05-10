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

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders general tab by default", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Company Settings")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByDisplayValue("Axiom Analytics Inc.")).toBeInTheDocument());
  });

  it("switches to API & MCP tab and shows tool stats", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "API & MCP" }));
    await waitFor(() => expect(screen.getByText("MCP Server")).toBeInTheDocument());
    expect(screen.getByText("axiom_query_brain")).toBeInTheDocument();
  });

  it("shows stub badge in integrations", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));
    await waitFor(() => expect(screen.getByText(/Data Sources/i)).toBeInTheDocument());
    expect(screen.getAllByText(/PHASE 12/i).length).toBeGreaterThan(0);
  });

  it("renders access tab content", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Access" }));
    await waitFor(() => expect(screen.getByText("Members")).toBeInTheDocument());
  });

  it("renders notifications tab content", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    await waitFor(() => expect(screen.getByText("Notification Rules")).toBeInTheDocument());
  });

  it("renders security tab content", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Security" }));
    await waitFor(() => expect(screen.getByText("Security Controls")).toBeInTheDocument());
  });

  it("renders preferences tab content", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Preferences" }));
    await waitFor(() => expect(screen.getByText("Appearance")).toBeInTheDocument());
  });

  it("keeps integrations button disabled", async () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /add integration/i })).toBeDisabled());
  });
});
