import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as vaultClient from "@/lib/vaultClient";
import type { ProviderMetadata, SecretMetadata } from "@/lib/vaultTypes";
import { SettingsPage } from "@/pages/SettingsPage";
import { useSettingsStore } from "@/state/settings.store";

vi.mock("@/lib/vaultClient", async () => {
  const actual = await vi.importActual<typeof import("@/lib/vaultClient")>("@/lib/vaultClient");
  return {
    ...actual,
    listProviders: vi.fn(),
    listSecrets: vi.fn(),
    storeSecret: vi.fn(),
    testSecret: vi.fn(),
    deleteSecret: vi.fn(),
  };
});

const credentialOne = [{ name: "api_key", label: "API Key", secret: true }] as const;

function meta(
  id: string,
  display: string,
  kind: ProviderMetadata["kind"],
): ProviderMetadata {
  return {
    id,
    display_name: display,
    kind,
    credential_shape: [...credentialOne],
    docs_url: `https://docs.example.com/${id}`,
    verify_endpoint: "GET https://example.com",
  };
}

const MOCK_PROVIDERS: ProviderMetadata[] = [
  meta("anthropic", "Anthropic", "llm"),
  meta("groq", "Groq", "llm"),
  meta("mistral", "Mistral AI", "llm"),
  meta("openai", "OpenAI", "llm"),
  meta("github", "GitHub", "connector"),
  meta("linear", "Linear", "connector"),
  meta("notion", "Notion", "connector"),
  meta("slack", "Slack", "connector"),
  meta("google", "Google", "oauth"),
  meta("microsoft", "Microsoft", "oauth"),
];

function resetStore() {
  useSettingsStore.setState({
    activeView: "settings",
    providers: [],
    secrets: [],
    vaultLocked: false,
    bootstrapError: null,
    providerPhase: {},
    dialogError: null,
    connectTarget: null,
  });
}

describe("SettingsPage", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    vi.mocked(vaultClient.listProviders).mockResolvedValue(MOCK_PROVIDERS);
    vi.mocked(vaultClient.listSecrets).mockResolvedValue([]);
    vi.mocked(vaultClient.storeSecret).mockReset();
    vi.mocked(vaultClient.testSecret).mockReset();
    vi.mocked(vaultClient.deleteSecret).mockReset();
  });

  it("renders API KEYS and CONNECTORS with eight provider cards (no oauth)", async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(vaultClient.listProviders).toHaveBeenCalled());
    expect(screen.getByText("API Keys")).toBeInTheDocument();
    expect(screen.getByText("Connectors")).toBeInTheDocument();
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
    expect(screen.getByText("GitHub")).toBeInTheDocument();
    expect(screen.queryByText("Google")).not.toBeInTheDocument();
    expect(screen.queryByText("Microsoft")).not.toBeInTheDocument();
    const connectButtons = screen.getAllByRole("button", { name: /^Connect$/ });
    expect(connectButtons).toHaveLength(8);
  });

  it("opens AddKeyDialog when Connect is clicked", async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(vaultClient.listProviders).toHaveBeenCalled());
    fireEvent.click(screen.getAllByRole("button", { name: /^Connect$/ })[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Connect Anthropic/i)).toBeInTheDocument();
  });

  it("closes dialog on Cancel", async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(vaultClient.listProviders).toHaveBeenCalled());
    fireEvent.click(screen.getAllByRole("button", { name: /^Connect$/ })[0]);
    fireEvent.click(screen.getByRole("button", { name: /^Cancel$/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("Save & Test calls storeSecret then testSecret and closes dialog on success", async () => {
    const stored: SecretMetadata = {
      id: "sid",
      provider_id: "anthropic",
      key_name: "default",
      status: "untested",
      last_tested_at: null,
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
    };
    const tested: SecretMetadata = { ...stored, status: "invalid", last_tested_at: "2026-01-02T00:00:00" };
    vi.mocked(vaultClient.storeSecret).mockResolvedValue(stored);
    vi.mocked(vaultClient.testSecret).mockResolvedValue({
      result: { status: "auth_error", detail: "bad key" },
      secret: tested,
    });

    render(<SettingsPage />);
    await waitFor(() => expect(vaultClient.listProviders).toHaveBeenCalled());
    fireEvent.click(screen.getAllByRole("button", { name: /^Connect$/ })[0]);

    const dialog = screen.getByRole("dialog");
    const input = within(dialog).getByLabelText(/^API Key$/i);
    fireEvent.change(input, { target: { value: "fake-key" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /Save & Test/i }));

    await waitFor(() => expect(vaultClient.storeSecret).toHaveBeenCalledTimes(1));
    expect(vaultClient.storeSecret).toHaveBeenCalledWith({
      provider_id: "anthropic",
      key_name: "default",
      plaintext: "fake-key",
    });
    await waitFor(() => expect(vaultClient.testSecret).toHaveBeenCalledWith("anthropic", "default"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("Invalid")).toBeInTheDocument();
  });

  it("Test on connected card calls testSecret and updates pill", async () => {
    vi.mocked(vaultClient.listSecrets).mockResolvedValue([
      {
        id: "sid",
        provider_id: "anthropic",
        key_name: "default",
        status: "untested",
        last_tested_at: null,
        created_at: "2026-01-01T00:00:00",
        updated_at: "2026-01-01T00:00:00",
      },
    ]);
    vi.mocked(vaultClient.testSecret).mockResolvedValue({
      result: { status: "ok", detail: null },
      secret: {
        id: "sid",
        provider_id: "anthropic",
        key_name: "default",
        status: "valid",
        last_tested_at: "2026-01-03T00:00:00",
        created_at: "2026-01-01T00:00:00",
        updated_at: "2026-01-03T00:00:00",
      },
    });

    render(<SettingsPage />);
    await waitFor(() => expect(vaultClient.listProviders).toHaveBeenCalled());
    const anthropicCard = screen.getByText("Anthropic").closest("article");
    expect(anthropicCard).toBeTruthy();
    const testBtn = within(anthropicCard as HTMLElement).getByRole("button", { name: /^Test$/ });
    fireEvent.click(testBtn);
    await waitFor(() => expect(vaultClient.testSecret).toHaveBeenCalledWith("anthropic", "default"));
    await waitFor(() => expect(within(anthropicCard as HTMLElement).getByText("Valid")).toBeInTheDocument());
  });

  it("Remove confirms then calls deleteSecret and returns to disconnected", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(vaultClient.listSecrets).mockResolvedValue([
      {
        id: "sid",
        provider_id: "anthropic",
        key_name: "default",
        status: "valid",
        last_tested_at: "2026-01-01T00:00:00",
        created_at: "2026-01-01T00:00:00",
        updated_at: "2026-01-01T00:00:00",
      },
    ]);
    vi.mocked(vaultClient.deleteSecret).mockResolvedValue(undefined);

    render(<SettingsPage />);
    await waitFor(() => expect(vaultClient.listProviders).toHaveBeenCalled());
    const anthropicCard = screen.getByText("Anthropic").closest("article") as HTMLElement;
    fireEvent.click(within(anthropicCard).getByRole("button", { name: /^Remove$/ }));
    await waitFor(() => expect(vaultClient.deleteSecret).toHaveBeenCalledWith("anthropic", "default"));
    await waitFor(() => expect(within(anthropicCard).getByText(/Not connected/i)).toBeInTheDocument());
    confirmSpy.mockRestore();
  });

  it("shows vault locked banner when vaultLocked is true", async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(vaultClient.listProviders).toHaveBeenCalled());
    await act(async () => {
      useSettingsStore.setState({ vaultLocked: true });
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/Vault is locked/i);
  });
});
