import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConnectorsPage } from "@/pages/ConnectorsPage";

const fetchMock = vi.fn();

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onmessage: ((ev: { data: string }) => void) | null = null;

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  emit(event: unknown) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  close() {}
}

function jsonResponse(payload: unknown) {
  return Promise.resolve(new Response(JSON.stringify(payload), { status: 200 }));
}

function renderPage() {
  render(
    <MemoryRouter>
      <ConnectorsPage />
    </MemoryRouter>,
  );
}

describe("ConnectorsPage", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    MockWebSocket.instances = [];
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("open", vi.fn());
    vi.stubGlobal("WebSocket", MockWebSocket);
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/internal/connectors/status") {
        return jsonResponse({
          connectors: [
            { vendor: "github", status: "connected", account_label: "Octo Org", last_sync_at: null, entities_ingested: 3, events_24h: 1, writes_blocked_week: 0 },
            { vendor: "linear", status: "connected", account_label: "Linear Workspace", last_sync_at: null, entities_ingested: 2, events_24h: 0, writes_blocked_week: 0 },
            { vendor: "slack", status: "connected", account_label: "Axiom HQ", last_sync_at: null, entities_ingested: 4, events_24h: 0, writes_blocked_week: 0 },
            { vendor: "notion", status: "connected", account_label: "Axiom Wiki", last_sync_at: null, entities_ingested: 5, events_24h: 0, writes_blocked_week: 0, watch_mode: "polling" },
            { vendor: "gmail", status: "connected", account_label: "founder@axiom.local", last_sync_at: null, entities_ingested: 6, events_24h: 0, writes_blocked_week: 0 },
          ],
        });
      }
      if (url === "/api/internal/connectors/github/events") {
        return jsonResponse({ events: [{ vendor: "github", event_type: "issue.opened", external_id: "issue_1" }] });
      }
      if (url === "/api/internal/connectors/github/install") {
        return jsonResponse({ authorize_url: "https://github.com/login/oauth/authorize?state=csrf" });
      }
      if (url === "/api/internal/connectors/linear/install") {
        return jsonResponse({ authorize_url: "https://linear.app/oauth/authorize?state=csrf" });
      }
      if (url === "/api/internal/connectors/slack/install") {
        return jsonResponse({ authorize_url: "https://slack.com/oauth/v2/authorize?state=csrf" });
      }
      if (url === "/api/internal/connectors/notion/install") {
        return jsonResponse({ authorize_url: "https://api.notion.com/v1/oauth/authorize?state=csrf" });
      }
      if (url === "/api/internal/connectors/gmail/install") {
        return jsonResponse({ authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?state=csrf" });
      }
      return jsonResponse({});
    });
  });

  it("connectors_page_lists_five_vendors", async () => {
    renderPage();
    expect(await screen.findByText("GitHub")).toBeInTheDocument();
    expect(screen.getByText("Linear")).toBeInTheDocument();
    expect(screen.getByText("Slack")).toBeInTheDocument();
    expect(screen.getByText("Notion")).toBeInTheDocument();
    expect(screen.getByText("Gmail")).toBeInTheDocument();
  });

  it("github_connect_button_opens_authorize_popup", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/internal/connectors/status") return jsonResponse({ connectors: [] });
      if (url === "/api/internal/connectors/github/install") {
        return jsonResponse({ authorize_url: "https://github.com/login/oauth/authorize?state=csrf" });
      }
      return jsonResponse({});
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Connect GitHub" }));
    await waitFor(() => expect(window.open).toHaveBeenCalledWith("https://github.com/login/oauth/authorize?state=csrf", "axiom-github-oauth", "width=720,height=780"));
  });

  it("github_connected_row_shows_account_label", async () => {
    renderPage();
    expect(await screen.findByText("Octo Org")).toBeInTheDocument();
    expect(screen.getAllByText("Connected")).toHaveLength(5);
  });

  it("github_sync_now_button_calls_sync_endpoint", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Sync GitHub" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/internal/connectors/github/sync", { method: "POST" }));
  });

  it("linear_connect_button_opens_authorize_popup", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/internal/connectors/status") return jsonResponse({ connectors: [] });
      if (url === "/api/internal/connectors/linear/install") {
        return jsonResponse({ authorize_url: "https://linear.app/oauth/authorize?state=csrf" });
      }
      return jsonResponse({});
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Connect Linear" }));
    await waitFor(() => expect(window.open).toHaveBeenCalledWith("https://linear.app/oauth/authorize?state=csrf", "axiom-linear-oauth", "width=720,height=780"));
  });

  it("linear_connected_row_shows_workspace_label", async () => {
    renderPage();
    expect(await screen.findByText("Linear Workspace")).toBeInTheDocument();
  });

  it("slack_connect_button_opens_oauth_popup", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/internal/connectors/status") return jsonResponse({ connectors: [] });
      if (url === "/api/internal/connectors/slack/install") {
        return jsonResponse({ authorize_url: "https://slack.com/oauth/v2/authorize?state=csrf" });
      }
      return jsonResponse({});
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Connect Slack" }));
    await waitFor(() => expect(window.open).toHaveBeenCalledWith("https://slack.com/oauth/v2/authorize?state=csrf", "axiom-slack-oauth", "width=720,height=780"));
  });

  it("slack_connected_row_shows_team_name", async () => {
    renderPage();
    expect(await screen.findByText("Axiom HQ")).toBeInTheDocument();
  });

  it("notion_connect_button_opens_oauth_popup", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/internal/connectors/status") return jsonResponse({ connectors: [] });
      if (url === "/api/internal/connectors/notion/install") {
        return jsonResponse({ authorize_url: "https://api.notion.com/v1/oauth/authorize?state=csrf" });
      }
      return jsonResponse({});
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Connect Notion" }));
    await waitFor(() => expect(window.open).toHaveBeenCalledWith("https://api.notion.com/v1/oauth/authorize?state=csrf", "axiom-notion-oauth", "width=720,height=780"));
  });

  it("notion_connected_row_shows_polling_badge", async () => {
    renderPage();
    expect(await screen.findByText("Axiom Wiki")).toBeInTheDocument();
    expect(screen.getByText("Polling")).toBeInTheDocument();
  });

  it("gmail_connect_button_opens_google_oauth", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/internal/connectors/status") return jsonResponse({ connectors: [] });
      if (url === "/api/internal/connectors/gmail/install") {
        return jsonResponse({ authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?state=csrf" });
      }
      return jsonResponse({});
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Connect Gmail" }));
    await waitFor(() => expect(window.open).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?state=csrf", "axiom-gmail-oauth", "width=720,height=780"));
  });

  it("gmail_connected_row_shows_email_label", async () => {
    renderPage();
    expect(await screen.findByText("founder@axiom.local")).toBeInTheDocument();
  });

  it("connectors_page_disconnect_button_revokes_token", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect Gmail" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/internal/connectors/gmail", { method: "DELETE" }));
  });

  it("connectors_page_aggregates_status_for_all_five", async () => {
    renderPage();
    expect(await screen.findByText("3 entities")).toBeInTheDocument();
    expect(screen.getByText("6 entities")).toBeInTheDocument();
    expect(screen.getAllByText("never")).toHaveLength(5);
  });

  it("connector_event_received_ws_event_increments_counter", async () => {
    renderPage();
    expect(await screen.findByText("1 events")).toBeInTheDocument();
    MockWebSocket.instances[0]?.emit({
      seq: 1,
      type: "connector_event_received",
      source_id: "github",
      persisted_id: "issue_2",
      payload: { vendor: "github", event_type: "issue.opened" },
    });
    expect(await screen.findByText("2 events")).toBeInTheDocument();
  });

  it("connector_write_blocked_ws_event_shows_in_drawer", async () => {
    renderPage();
    MockWebSocket.instances[0]?.emit({
      seq: 2,
      type: "connector_write_blocked",
      source_id: "github",
      persisted_id: "write_1",
      payload: { vendor: "github", event_type: "write.blocked" },
    });
    fireEvent.click(await screen.findByRole("button", { name: "View GitHub Events" }));
    expect(await screen.findByText(/write.blocked/)).toBeInTheDocument();
  });

  it("test_connection_button_per_row", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Test GitHub" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/internal/connectors/github/test", { method: "POST" }));
  });

  it("connect_button_opens_setup_when_connector_needs_oauth_config", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/internal/connectors/status") {
        return jsonResponse({ connectors: [{ vendor: "github", status: "disconnected", configured: false }] });
      }
      return jsonResponse({});
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Connect GitHub" }));

    expect(await screen.findByRole("dialog", { name: "Set up GitHub connector" })).toBeInTheDocument();
    expect(screen.getByText("Connector setup required")).toBeInTheDocument();
  });

  it("connector_setup_shows_error_in_modal_when_save_fails", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/internal/connectors/status") {
        return jsonResponse({ connectors: [{ vendor: "notion", status: "disconnected", configured: false }] });
      }
      if (url === "/api/internal/connectors/notion/config") {
        return Promise.resolve(new Response(JSON.stringify({ detail: "Notion connector setup required" }), { status: 409 }));
      }
      return jsonResponse({});
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Connect Notion" }));
    fireEvent.change(await screen.findByLabelText("OAuth client ID"), { target: { value: "client-id" } });
    fireEvent.change(screen.getByLabelText("OAuth client secret"), { target: { value: "client-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Save & Connect" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Notion connector setup required");
    expect(screen.getByRole("dialog", { name: "Set up Notion connector" })).toBeInTheDocument();
  });

  it("connector_setup_saves_config_then_opens_authorization", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/internal/connectors/status") {
        return jsonResponse({ connectors: [{ vendor: "github", status: "disconnected", configured: false }] });
      }
      if (url === "/api/internal/connectors/github/config") {
        expect(init?.method).toBe("PUT");
        expect(JSON.parse(String(init?.body))).toEqual(expect.objectContaining({
          oauth_client_id: "client-id",
          oauth_client_secret: "client-secret",
        }));
        return jsonResponse({ vendor: "github", configured: true });
      }
      if (url === "/api/internal/connectors/github/install") {
        return jsonResponse({ authorize_url: "https://github.com/login/oauth/authorize?client_id=client-id" });
      }
      return jsonResponse({});
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Connect GitHub" }));
    fireEvent.change(await screen.findByLabelText("OAuth client ID"), { target: { value: "client-id" } });
    fireEvent.change(screen.getByLabelText("OAuth client secret"), { target: { value: "client-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Save & Connect" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/internal/connectors/github/install",
      { method: "POST" },
    ));
    await waitFor(() => expect(window.open).toHaveBeenCalledWith(
      "https://github.com/login/oauth/authorize?client_id=client-id",
      "axiom-github-oauth",
      "width=720,height=780",
    ));
  });
});
