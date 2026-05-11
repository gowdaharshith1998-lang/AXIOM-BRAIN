import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConnectorsPage } from "@/pages/ConnectorsPage";

const fetchMock = vi.fn();

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
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("open", vi.fn());
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/internal/connectors/status") {
        return jsonResponse({
          connectors: [
            { vendor: "github", status: "connected", account_label: "Octo Org", last_sync_at: null },
            { vendor: "linear", status: "connected", account_label: "Linear Workspace", last_sync_at: null },
          ],
        });
      }
      if (url === "/api/internal/connectors/github/install") {
        return jsonResponse({ authorize_url: "https://github.com/login/oauth/authorize?state=csrf" });
      }
      if (url === "/api/internal/connectors/linear/install") {
        return jsonResponse({ authorize_url: "https://linear.app/oauth/authorize?state=csrf" });
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
    expect(screen.getAllByText("Connected")).toHaveLength(2);
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
});
