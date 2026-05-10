import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PassportsPage } from "@/pages/PassportsPage";

const api = vi.hoisted(() => ({
  listPassports: vi.fn(),
  issuePassport: vi.fn(),
  revokePassport: vi.fn(),
  setPassportKillSwitch: vi.fn(),
}));

vi.mock("@/lib/passportsClient", () => api);

const basePassport = {
  passport_id: "pp_1",
  agent_name: "researcher",
  agent_class: "reader",
  owner_email: "owner@example.com",
  scope_clusters: ["*"],
  scope_intents: ["read"],
  scope_skills: ["*"],
  issued_at: "2026-05-10T00:00:00",
  expires_at: "2026-05-11T00:00:00",
  kill_switch: false,
  revoked_at: null,
  revocation_reason: null,
  status: "active" as const,
};

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onmessage: ((message: { data: string }) => void) | null = null;
  close = vi.fn();

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

describe("PassportsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
    api.listPassports.mockResolvedValue([basePassport]);
    api.issuePassport.mockResolvedValue({ ...basePassport, passport_id: "pp_2", bearer_token: "Bearer pp_2.secret" });
    api.revokePassport.mockResolvedValue({ ...basePassport, status: "revoked", revoked_at: "2026-05-10T00:10:00" });
    api.setPassportKillSwitch.mockResolvedValue({ ...basePassport, kill_switch: true, status: "kill_switch" });
  });

  it("lists passports with scope and status", async () => {
    render(<PassportsPage />);
    expect(await screen.findByText("researcher")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("* / read / *")).toBeInTheDocument();
  });

  it("opens the issue modal", async () => {
    render(<PassportsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Issue Passport" }));
    expect(await screen.findByRole("dialog", { name: "Issue passport" })).toBeInTheDocument();
  });

  it("issues a passport and shows the bearer token once", async () => {
    render(<PassportsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Issue Passport" }));
    fireEvent.change(screen.getByText("agent_name").nextSibling as HTMLInputElement, { target: { value: "builder" } });
    fireEvent.change(screen.getByText("agent_class").nextSibling as HTMLInputElement, { target: { value: "worker" } });
    fireEvent.change(screen.getByText("owner_email").nextSibling as HTMLInputElement, { target: { value: "ops@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Issue" }));
    expect(await screen.findByRole("dialog", { name: "Bearer token" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Bearer pp_2.secret")).toBeInTheDocument();
  });

  it("copies and confirms the bearer token modal", async () => {
    render(<PassportsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Issue Passport" }));
    fireEvent.change(screen.getByText("agent_name").nextSibling as HTMLInputElement, { target: { value: "builder" } });
    fireEvent.change(screen.getByText("agent_class").nextSibling as HTMLInputElement, { target: { value: "worker" } });
    fireEvent.change(screen.getByText("owner_email").nextSibling as HTMLInputElement, { target: { value: "ops@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Issue" }));
    await screen.findByDisplayValue("Bearer pp_2.secret");
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("Bearer pp_2.secret");
    fireEvent.click(screen.getByRole("button", { name: "I saved it" }));
    expect(screen.queryByRole("dialog", { name: "Bearer token" })).not.toBeInTheDocument();
  });

  it("revokes a passport", async () => {
    render(<PassportsPage />);
    await screen.findByText("researcher");
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(api.revokePassport).toHaveBeenCalledWith("pp_1"));
    expect(await screen.findByText("revoked")).toBeInTheDocument();
  });

  it("toggles the kill switch", async () => {
    render(<PassportsPage />);
    await screen.findByText("researcher");
    fireEvent.click(screen.getByRole("button", { name: "Kill-switch" }));
    await waitFor(() => expect(api.setPassportKillSwitch).toHaveBeenCalledWith("pp_1", true));
    expect(await screen.findByText("kill_switch")).toBeInTheDocument();
  });

  it("applies passport issued websocket events", async () => {
    render(<PassportsPage />);
    await screen.findByText("researcher");
    MockWebSocket.instances[0].emit({ type: "passport_issued", payload: { ...basePassport, passport_id: "pp_ws", agent_name: "ws-agent" } });
    expect(await screen.findByText("ws-agent")).toBeInTheDocument();
  });

  it("applies passport revoked websocket events", async () => {
    render(<PassportsPage />);
    await screen.findByText("researcher");
    MockWebSocket.instances[0].emit({ type: "passport_revoked", payload: { ...basePassport, status: "revoked" } });
    expect(await screen.findByText("revoked")).toBeInTheDocument();
  });

  it("applies passport kill-switch websocket events", async () => {
    render(<PassportsPage />);
    await screen.findByText("researcher");
    MockWebSocket.instances[0].emit({ type: "passport_kill_switch_toggled", payload: { ...basePassport, kill_switch: true, status: "kill_switch" } });
    expect(await screen.findByText("kill_switch")).toBeInTheDocument();
  });
});
