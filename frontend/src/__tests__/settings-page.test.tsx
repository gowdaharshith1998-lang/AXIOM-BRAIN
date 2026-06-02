import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "@/pages/SettingsPage";
import { saveStudioSettings } from "@/lib/studioClient";

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

const llmKeys = vi.hoisted(() => ({
  listLLMKeys: vi.fn().mockResolvedValue([]),
  saveLLMKey: vi.fn().mockResolvedValue({
    provider: "openai",
    key_fingerprint: "1234",
    connected_at: "2026-05-10T00:00:00",
    last_tested_at: null,
    last_test_status: "untested",
    demo_flag: false,
  }),
  testLLMKey: vi.fn().mockResolvedValue({
    provider: "openai",
    key_fingerprint: "1234",
    connected_at: "2026-05-10T00:00:00",
    last_tested_at: "2026-05-10T00:01:00",
    last_test_status: "valid",
    demo_flag: false,
  }),
  disconnectLLMKey: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/lib/llmKeysClient", () => llmKeys);

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
    llmKeys.listLLMKeys.mockResolvedValue([]);
    window.confirm = vi.fn(() => true);
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
    fireEvent.click(screen.getAllByRole("button", { name: "Connect" }).at(-1)!);
    expect(screen.getByRole("dialog")).toHaveTextContent("Connect OpenAI");
  });

  it("saves and tests an OpenAI vault key through Phase 7.D endpoints", async () => {
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "API & MCP" }));
    await waitFor(() => expect(screen.getByText("OpenAI")).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("button", { name: "Connect" }).at(-1)!);
    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "sk-test-1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Save & Test" }));
    await waitFor(() => expect(llmKeys.saveLLMKey).toHaveBeenCalledWith("openai", "sk-test-1234"));
    expect(llmKeys.testLLMKey).toHaveBeenCalledWith("openai");
    expect(await screen.findByText("Valid")).toBeInTheDocument();
  });

  it("tests a saved vault key", async () => {
    llmKeys.listLLMKeys.mockResolvedValue([
      {
        provider: "openai",
        key_fingerprint: "1234",
        connected_at: "2026-05-10T00:00:00",
        last_tested_at: null,
        last_test_status: "untested",
        demo_flag: false,
      },
    ]);
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "API & MCP" }));
    await waitFor(() => expect(screen.getByText("OpenAI")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    await waitFor(() => expect(llmKeys.testLLMKey).toHaveBeenCalledWith("openai"));
  });

  it("disconnects a saved vault key", async () => {
    llmKeys.listLLMKeys.mockResolvedValue([
      {
        provider: "openai",
        key_fingerprint: "1234",
        connected_at: "2026-05-10T00:00:00",
        last_tested_at: null,
        last_test_status: "untested",
        demo_flag: false,
      },
    ]);
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "API & MCP" }));
    await waitFor(() => expect(screen.getByText("OpenAI")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(llmKeys.disconnectLLMKey).toHaveBeenCalledWith("openai"));
  });

  it("links to the passports page from agent access policies", async () => {
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "API & MCP" }));
    await waitFor(() => expect(screen.getByText("Agent Access Policies")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Manage Passports" })).toHaveAttribute("href", "/settings/passports");
  });

  it("sends a member invitation into persisted workspace settings", async () => {
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "Access" }));
    fireEvent.change(screen.getByLabelText("Invite Email"), { target: { value: "teammate@example.com" } });
    fireEvent.change(screen.getByLabelText("Invite Role"), { target: { value: "Editor" } });
    fireEvent.click(screen.getByRole("button", { name: "Send Invitation" }));
    await waitFor(() => expect(saveStudioSettings).toHaveBeenCalledWith(expect.objectContaining({
      member_invites: [expect.objectContaining({ email: "teammate@example.com", role: "Editor", status: "Pending" })],
    })));
    expect(screen.getByText("teammate@example.com")).toBeInTheDocument();
    expect(screen.getByText("Invitation queued")).toBeInTheDocument();
  });

  it.each([
    ["Integrations", "Connectors"],
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
