import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { AddKeyDialog } from "@/components/settings/AddKeyDialog";
import { ProviderCard } from "@/components/settings/ProviderCard";
import { getHealth, getMcpStats, getStudioSettings, saveStudioSettings, type MCPStats } from "@/lib/studioClient";
import { ConnectorsPage } from "@/pages/ConnectorsPage";
import { secretForProvider, useSettingsStore, visibleProviders } from "@/state/settings.store";

const tabs = ["general", "integrations", "access", "notifications", "security", "preferences", "api-mcp"] as const;
type Tab = (typeof tabs)[number];
type MemberInvite = { email: string; role: string; status: string; invited_at: string };

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="settings-panel">
      <h3 className="settings-panel-title">{title}</h3>
      {subtitle ? <p className="settings-panel-subtitle">{subtitle}</p> : null}
      <div className="settings-panel-body">{children}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-[#173657] py-2">
      <span className="text-[#a9bed8]">{label}</span>
      <span className="text-[#e8f2ff]">{value}</span>
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange?: (value: string) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[#9fb5d0]">{label}</span>
      <input
        className="h-[41px] w-full rounded-md border border-[#223b5c] bg-[#071225] px-3 text-[#e6f0ff] outline-none focus:border-[#2389ff]"
        value={value}
        readOnly={!onChange}
        onChange={(event) => onChange?.(event.target.value)}
      />
    </label>
  );
}

function DataTable({ headers, rows }: { headers: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-hidden rounded-md border border-[#1d446f] bg-[#071327]">
      <div className="grid grid-cols-[repeat(var(--cols),minmax(0,1fr))] border-b border-[#1d446f] px-3 py-2 text-[12px] text-[#83a6cb]" style={{ "--cols": headers.length } as CSSProperties}>
        {headers.map((header) => <span key={header}>{header}</span>)}
      </div>
      {rows.map((row, index) => (
        <div key={index} className="grid grid-cols-[repeat(var(--cols),minmax(0,1fr))] border-b border-[#12365d]/60 px-3 py-2 text-[13px]" style={{ "--cols": headers.length } as CSSProperties}>
          {row.map((cell, cellIndex) => <span key={cellIndex}>{cell}</span>)}
        </div>
      ))}
    </div>
  );
}

function parseSettingBoolean(settings: Record<string, unknown>, key: string, fallback: boolean): boolean {
  const value = settings[key];
  return typeof value === "boolean" ? value : fallback;
}

function parseSettingNumber(settings: Record<string, unknown>, key: string, fallback: number): number {
  const value = settings[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function parseSettingString(settings: Record<string, unknown>, key: string, fallback: string): string {
  const value = settings[key];
  return typeof value === "string" ? value : fallback;
}

function parseSettingArray(settings: Record<string, unknown>, key: string): string[] {
  const value = settings[key];
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : [];
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Math.max(0, bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function SettingSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="inline-flex h-8 min-w-0 rounded border border-[#1a3550] bg-[#071225] px-2 text-[#e6f0ff] outline-none focus:border-[#2389ff]"
    >
      {options.map((item) => <option key={item} value={item}>{item}</option>)}
    </select>
  );
}

function SettingToggle({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="inline-flex items-center gap-2 text-[13px] text-[#9aa8c4]">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{checked ? "On" : "Off"}</span>
    </label>
  );
}

function memberInvitesFromSettings(value: unknown): MemberInvite[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Partial<MemberInvite>;
    if (typeof record.email !== "string" || !record.email.includes("@")) return [];
    return [{
      email: record.email,
      role: typeof record.role === "string" && record.role ? record.role : "Viewer",
      status: typeof record.status === "string" && record.status ? record.status : "Pending",
      invited_at: typeof record.invited_at === "string" ? record.invited_at : new Date().toISOString(),
    }];
  });
}

export function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const requested = (params.get("tab") as Tab) || "general";
  const tab = tabs.includes(requested) ? requested : "general";
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [mcpStats, setMcpStats] = useState<MCPStats | null>(null);
  const [health, setHealth] = useState("unknown");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("Viewer");
  const [inviteStatus, setInviteStatus] = useState<string | null>(null);

  const providers = useSettingsStore((s) => s.providers);
  const secrets = useSettingsStore((s) => s.secrets);
  const vaultLocked = useSettingsStore((s) => s.vaultLocked);
  const bootstrapError = useSettingsStore((s) => s.bootstrapError);
  const providerPhase = useSettingsStore((s) => s.providerPhase);
  const connectTarget = useSettingsStore((s) => s.connectTarget);
  const dialogError = useSettingsStore((s) => s.dialogError);
  const loadSettingsData = useSettingsStore((s) => s.loadSettingsData);
  const openConnectDialog = useSettingsStore((s) => s.openConnectDialog);
  const closeConnectDialog = useSettingsStore((s) => s.closeConnectDialog);
  const saveAndTestNewKey = useSettingsStore((s) => s.saveAndTestNewKey);
  const runTest = useSettingsStore((s) => s.runTest);
  const removeSecret = useSettingsStore((s) => s.removeSecret);
  const { llm, connectors } = visibleProviders(providers);

  useEffect(() => {
    void getStudioSettings().then((loaded) => setSettings((current) => ({ ...loaded, member_invites: current.member_invites ?? loaded.member_invites }))).catch(() => {});
    void getMcpStats().then(setMcpStats).catch(() => {});
    void getHealth().then((res) => setHealth(res.status)).catch(() => {});
    void loadSettingsData();
  }, [loadSettingsData]);

  const write = (key: string, value: unknown) => {
    const next = { ...settings, [key]: value };
    setSettings(next);
    void saveStudioSettings({ [key]: value });
  };

  const graphMode = parseSettingString(settings, "graph_mode", "Smart (Auto)");
  const autoRefreshSeconds = parseSettingNumber(settings, "graph_auto_refresh_seconds", 30);
  const defaultConfidence = parseSettingNumber(settings, "default_confidence_threshold", 70);
  const relationshipVisibility = parseSettingString(settings, "relationship_visibility", "Show All Relationships");
  const showConfidenceRings = parseSettingBoolean(settings, "show_confidence_rings", true);

  const environment = parseSettingString(settings, "environment", "Production");
  const region = parseSettingString(settings, "region", Intl.DateTimeFormat().resolvedOptions().timeZone || "Unknown");
  const storageUsedBytes = parseSettingNumber(settings, "storage_used_bytes", 0);
  const storageLimitBytes = parseSettingNumber(settings, "storage_total_bytes", 0);
  const storageStatus = storageLimitBytes > 0
    ? `${formatBytes(storageUsedBytes)} / ${formatBytes(storageLimitBytes)} (${Math.round((storageUsedBytes / storageLimitBytes) * 100)}%)`
    : parseSettingString(settings, "storage_status", "Unknown");

  const queryMode = parseSettingString(settings, "query_mode", "Balanced");
  const animationIntensity = parseSettingString(settings, "animation_intensity", "Medium");
  const graphDensity = parseSettingString(settings, "graph_density", "Optimal");
  const notificationSummary = parseSettingString(settings, "notification_summary", "Brief");
  const theme = parseSettingString(settings, "theme", "Dark (Neon)");
  const showLabelsAlways = parseSettingBoolean(settings, "show_labels_always", true);
  const showGovernanceOverlays = parseSettingBoolean(settings, "show_governance_overlays", true);
  const showTraversalPaths = parseSettingBoolean(settings, "show_traversal_paths", true);
  const saveQueryHistory = parseSettingBoolean(settings, "save_query_history", true);

  const notificationChannels = parseSettingArray(settings, "notification_channels");
  const multiUserEnabled = parseSettingBoolean(settings, "multi_user_enabled", false);
  const inviteDefaultRole = parseSettingString(settings, "invite_default_role", "Viewer");

  const securitySettings = {
    ssoEnabled: parseSettingBoolean(settings, "sso_enabled", false),
    mfaRequired: parseSettingBoolean(settings, "mfa_required", false),
    apiKeysTracked: parseSettingBoolean(settings, "api_keys_tracked", false),
    dataRetentionDays: parseSettingNumber(settings, "data_retention_days", 30),
    securityHealthScore: parseSettingNumber(settings, "security_health_score", 88),
  };
  const accessRules = parseSettingArray(settings, "access_rules");
  const alertRecipients = parseSettingArray(settings, "notification_recipients");
  const escalationMinutes = parseSettingNumber(settings, "escalation_minutes", 15);

  const toolRows = useMemo(
    () => (mcpStats?.tools ?? []).map((tool) => [tool.name, "Read", tool.last_called ? new Date(tool.last_called).toLocaleTimeString() : "—", `${tool.calls}`]),
    [mcpStats],
  );
  const memberInvites = useMemo(() => memberInvitesFromSettings(settings.member_invites), [settings.member_invites]);
  const memberRows = useMemo(
    () => [
      ["Axiom Operator", "you@axiom.local", "Platform Admin", "Platform", "Active"],
      ...memberInvites.map((invite) => ["Invited Member", invite.email, invite.role, "Pending", invite.status]),
    ],
    [memberInvites],
  );

  const sendInvite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const email = inviteEmail.trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setInviteStatus("Enter a valid email address");
      return;
    }
    const invite = { email, role: inviteRole, status: "Pending", invited_at: new Date().toISOString() };
    const nextInvites = [invite, ...memberInvites.filter((item) => item.email !== email)];
    const nextSettings = { ...settings, member_invites: nextInvites };
    setSettings(nextSettings);
    setInviteStatus("Sending invitation...");
    try {
      await saveStudioSettings({ member_invites: nextInvites });
      setInviteEmail("");
      setInviteStatus("Invitation queued");
    } catch (error) {
      setInviteStatus(error instanceof Error ? error.message : "Invitation failed");
    }
  };

  return (
    <div className="settings-stage">
      <nav className="settings-tabs" aria-label="Settings tabs">
        {tabs.map((item) => (
          <button key={item} type="button" onClick={() => setParams({ tab: item })} className={tab === item ? "settings-tab-active" : "settings-tab"}>
            {item === "api-mcp" ? "API & MCP" : item[0].toUpperCase() + item.slice(1)}
          </button>
        ))}
      </nav>

      <div className="settings-content">
      {tab === "general" && (
        <div className="settings-grid">
          <Panel title="Company Settings" subtitle="Manage your company and workspace preferences.">
            <div className="space-y-3">
              <Field label="Company Name" value={String(settings.company_name ?? "Axiom Analytics Inc.")} onChange={(value) => write("company_name", value)} />
              <Field label="Workspace Name" value="Axiom Global Workspace" />
              <Field label="Time Zone" value={String(settings.time_zone ?? "(UTC-05:00) Eastern Time (US & Canada)")} onChange={(value) => write("time_zone", value)} />
              <Field label="Default View" value={String(settings.default_view ?? "Live Graph")} onChange={(value) => write("default_view", value)} />
              <Field label="Language" value={String(settings.language ?? "English (US)")} onChange={(value) => write("language", value)} />
              <Field label="Date Format" value={String(settings.date_format ?? "MMM DD, YYYY")} onChange={(value) => write("date_format", value)} />
            </div>
          </Panel>
          <Panel title="Brain Configuration" subtitle="Configure how your Company Brain behaves and displays.">
            <Row
              label="Default Graph Mode"
              value={<SettingSelect value={graphMode} options={["Smart (Auto)", "Graph Only", "Timeline"]} onChange={(value) => write("graph_mode", value)} />}
            />
            <Row
              label="Auto-refresh Interval"
              value={<SettingSelect value={`${autoRefreshSeconds}s`} options={["10s", "30s", "60s", "120s"]} onChange={(value) => write("graph_auto_refresh_seconds", Number.parseInt(value, 10))} />}
            />
            <Row
              label="Default Confidence Threshold"
              value={<SettingSelect value={`${defaultConfidence}%`} options={["60%", "70%", "80%", "85%", "90%", "95%"]} onChange={(value) => write("default_confidence_threshold", Number.parseInt(value, 10))} />}
            />
            <Row label="Default Landing Page" value="Insights Overview" />
            <Row
              label="Relationship Visibility"
              value={<SettingSelect value={relationshipVisibility} options={["Show All Relationships", "Filtered", "High Confidence Only"]} onChange={(value) => write("relationship_visibility", value)} />}
            />
            <Row label="Show confidence rings" value={<SettingToggle checked={showConfidenceRings} onChange={(value) => write("show_confidence_rings", value)} />} />
          </Panel>
          <div className="settings-stack">
            <Panel title="System Summary" subtitle="Overview of your system environment and health.">
              <Row label="Version" value="0.1.0" />
              <Row label="Environment" value={environment} />
              <Row label="Region" value={region} />
              <Row label="Graph Health" value={health} />
              <Row label="Storage Status" value={storageStatus} />
            </Panel>
            <Panel title="Operational Defaults" subtitle="Default operational parameters for the workspace.">
              <Row label="Query Mode" value={<SettingSelect value={queryMode} options={["Balanced", "Precise", "Creative", "Fast"]} onChange={(value) => write("query_mode", value)} />} />
              <Row label="Animation Intensity" value={<SettingSelect value={animationIntensity} options={["Low", "Medium", "High"]} onChange={(value) => write("animation_intensity", value)} />} />
              <Row label="Graph Density" value={<SettingSelect value={graphDensity} options={["Sparse", "Optimal", "Dense"]} onChange={(value) => write("graph_density", value)} />} />
              <Row label="Notification Summary" value={<SettingSelect value={notificationSummary} options={["Off", "Brief", "Full"]} onChange={(value) => write("notification_summary", value)} />} />
            </Panel>
          </div>
        </div>
      )}

      {tab === "integrations" && (
        <ConnectorsPage embedded />
      )}

      {tab === "access" && (
        <div className="settings-grid">
          <div className="settings-stack">
            <Panel title="Members" subtitle="Manage users, roles, and access across your Company Brain.">
              <DataTable headers={["Name", "Email", "Role", "Team", "Status"]} rows={memberRows} />
              <Row label="Multi-user" value={<SettingToggle checked={multiUserEnabled} onChange={(value) => write("multi_user_enabled", value)} />} />
            </Panel>
            <div className="settings-grid">
              <Panel title="Teams">
                <div className="space-y-2 text-[13px] text-[#9fb5d0]">
                  {memberRows.length > 1 ? (
                    <DataTable headers={["Member Team", "Default Access"]} rows={memberRows.slice(1).map((member) => [member[3], member[2] === "Viewer" ? "Read-only" : "Elevated"])} />
                  ) : (
                    <span>No teams configured yet</span>
                  )}
                </div>
              </Panel>
              <Panel title="Access Rules">
                <div className="space-y-2">
                  <Row label="Invite default role" value={inviteDefaultRole} />
                  <Row
                    label="Current rules"
                    value={
                      <SettingSelect
                        value={accessRules[0] ?? "Standard"}
                        options={["Standard", "Strict", "Open"]}
                        onChange={(value) => write("access_rules", [value, ...accessRules.filter((entry, index) => index > 0)])}
                      />
                    }
                  />
                </div>
              </Panel>
            </div>
          </div>
          <Panel title="Invite Member" subtitle="Add a new member to your workspace.">
            <form className="space-y-3" onSubmit={sendInvite}>
              <label className="block">
                <span className="mb-1 block text-[#9fb5d0]">Invite Email</span>
                <input
                  className="h-[41px] w-full rounded-md border border-[#223b5c] bg-[#071225] px-3 text-[#e6f0ff] outline-none focus:border-[#2389ff]"
                  value={inviteEmail}
                  onChange={(event) => setInviteEmail(event.target.value)}
                  placeholder="name@company.com"
                  type="email"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-[#9fb5d0]">Invite Role</span>
                <select
                  className="h-[41px] w-full rounded-md border border-[#223b5c] bg-[#071225] px-3 text-[#e6f0ff] outline-none focus:border-[#2389ff]"
                  value={inviteRole}
                  onChange={(event) => setInviteRole(event.target.value)}
                >
                  <option>Viewer</option>
                  <option>Editor</option>
                  <option>Platform Admin</option>
                </select>
              </label>
              <button type="submit" className="h-[38px] w-full rounded-md border border-[#2389ff] bg-[#12386c] text-[#e8f2ff] hover:bg-[#174680]">Send Invitation</button>
              {inviteStatus ? <div className="rounded-md border border-[#1d446f] bg-[#071327] px-3 py-2 text-[13px] text-[#9fb5d0]">{inviteStatus}</div> : null}
            </form>
          </Panel>
        </div>
      )}

      {tab === "notifications" && (
        <div className="settings-grid">
          <Panel title="Alert Channels">
            <div className="space-y-2">
              <Row
                label="Email"
                value={<SettingToggle
                  checked={notificationChannels.includes("Email")}
                  onChange={(value) => {
                    const next = value
                      ? [...new Set([...notificationChannels, "Email"])]
                      : notificationChannels.filter((item) => item !== "Email");
                    write("notification_channels", next);
                  }}
                />}
              />
              <Row
                label="Slack"
                value={<SettingToggle
                  checked={notificationChannels.includes("Slack")}
                  onChange={(value) => {
                    const next = value
                      ? [...new Set([...notificationChannels, "Slack"])]
                      : notificationChannels.filter((item) => item !== "Slack");
                    write("notification_channels", next);
                  }}
                />}
              />
              <Row
                label="In-app"
                value={<SettingToggle
                  checked={notificationChannels.includes("In-app")}
                  onChange={(value) => {
                    const next = value
                      ? [...new Set([...notificationChannels, "In-app"])]
                      : notificationChannels.filter((item) => item !== "In-app");
                    write("notification_channels", next);
                  }}
                />}
              />
              <Row
                label="Webhook"
                value={<SettingToggle
                  checked={notificationChannels.includes("Webhook")}
                  onChange={(value) => {
                    const next = value
                      ? [...new Set([...notificationChannels, "Webhook"])]
                      : notificationChannels.filter((item) => item !== "Webhook");
                    write("notification_channels", next);
                  }}
                />}
              />
            </div>
          </Panel>
          <Panel title="Notification Rules">
            <DataTable headers={["Rule", "Severity", "Frequency", "Escalation"]} rows={["Policy Violation", "Agent Action Denied", "Low-confidence Entity Created", "Integration Sync Failed"].map((rule) => [rule, "Medium", "Immediate", "15 min"])} />
            <div className="mt-3">
              <Row label="Escalation minutes" value={<SettingSelect value={`${escalationMinutes}m`} options={["5m", "15m", "30m", "60m"]} onChange={(value) => write("escalation_minutes", Number.parseInt(value, 10))} />} />
            </div>
          </Panel>
          <div className="settings-stack">
            <Panel title="Escalation Policy">Tiered escalation by channel and severity.</Panel>
            <Panel title="Notification Recipients">
              {alertRecipients.length > 0 ? (
                <DataTable headers={["Recipient Group"]} rows={alertRecipients.map((recipient) => [recipient])} />
              ) : (
                <span className="text-[13px] text-[#9fb5d0]">No recipient groups configured</span>
              )}
            </Panel>
          </div>
        </div>
      )}

      {tab === "security" && (
        <div className="settings-grid">
          <div className="settings-stack">
            <div className="settings-grid">
              <Panel title="Authentication">
                <div className="space-y-2">
                  <Row label="SSO" value={<SettingToggle checked={securitySettings.ssoEnabled} onChange={(value) => write("sso_enabled", value)} />} />
                  <Row label="MFA required" value={<SettingToggle checked={securitySettings.mfaRequired} onChange={(value) => write("mfa_required", value)} />} />
                </div>
              </Panel>
              <Panel title="API Security">
                <div className="space-y-2">
                  <Row label="Track API keys" value={<SettingToggle checked={securitySettings.apiKeysTracked} onChange={(value) => write("api_keys_tracked", value)} />} />
                  <Row label="Data retention days" value={<SettingSelect value={`${securitySettings.dataRetentionDays}`} options={["7", "14", "30", "60", "90"]} onChange={(value) => write("data_retention_days", Number.parseInt(value, 10))} />} />
                </div>
              </Panel>
            </div>
            <div className="settings-grid">
              <Panel title="Data Protection">Encryption and redaction controls <span className="text-[#9fb5d0]">Enabled</span></Panel>
              <Panel title="Audit Controls">Merkle Ledger Status: <span className="text-[#9fb5d0]">Active</span></Panel>
            </div>
            <Panel title="Risk Controls">
              <Row label="Require approvals" value={<SettingToggle checked={parseSettingBoolean(settings, "risk_approvals_required", false)} onChange={(value) => write("risk_approvals_required", value)} />} />
            </Panel>
          </div>
          <div className="settings-stack">
            <Panel title="Security Health">Score: {securitySettings.securityHealthScore}/100</Panel>
            <Panel title="Recent Security Events">Latest security events <span className="text-[#9fb5d0]">{mcpStats?.recent_actions?.slice(0, 3).length ?? 0}</span></Panel>
          </div>
        </div>
      )}

      {tab === "preferences" && (
        <div className="settings-grid">
          <Panel title="Appearance" subtitle="Customize how AXIOM looks and feels.">
            <Row label="Theme" value={<SettingSelect value={theme} options={["Dark (Neon)", "Dark (Slate)", "High Contrast"]} onChange={(value) => write("theme", value)} />} />
            <Row label="Graph Density" value={<SettingSelect value={graphDensity} options={["Sparse", "Optimal", "Dense"]} onChange={(value) => write("graph_density", value)} />} />
            <Row label="Glow Intensity" value={<SettingSelect value={animationIntensity} options={["Low", "Medium", "High"]} onChange={(value) => write("animation_intensity", value)} />} />
            <Row label="Animation Intensity" value={<SettingSelect value={animationIntensity} options={["Low", "Medium", "High"]} onChange={(value) => write("animation_intensity", value)} />} />
          </Panel>
          <Panel title="Graph Preferences" subtitle="Control what is shown on the graph.">
            <Row label="Show labels always" value={<SettingToggle checked={showLabelsAlways} onChange={(value) => write("show_labels_always", value)} />} />
            <Row label="Show confidence rings" value={<SettingToggle checked={showConfidenceRings} onChange={(value) => write("show_confidence_rings", value)} />} />
            <Row label="Show governance overlays" value={<SettingToggle checked={showGovernanceOverlays} onChange={(value) => write("show_governance_overlays", value)} />} />
            <Row label="Show agent traversal paths" value={<SettingToggle checked={showTraversalPaths} onChange={(value) => write("show_traversal_paths", value)} />} />
          </Panel>
          <Panel title="Query Preferences" subtitle="Set defaults for searching and asking the brain.">
            <Row label="Default Query Mode" value={<SettingSelect value={queryMode} options={["Balanced", "Precise", "Creative", "Fast"]} onChange={(value) => write("query_mode", value)} />} />
            <Row label="Save query history" value={<SettingToggle checked={saveQueryHistory} onChange={(value) => write("save_query_history", value)} />} />
          </Panel>
          <Panel title="Profile">Axiom Operator · Platform Administrator</Panel>
          <Panel title="Keyboard Shortcuts">Cmd/Ctrl+K, G, A, E, I</Panel>
          <Panel title="About Preferences">Scoped to your workspace.</Panel>
        </div>
      )}

      {tab === "api-mcp" && (
        <div className="settings-grid">
          <div className="settings-stack">
            <div className="settings-grid">
              <Panel title="MCP Server" subtitle="Your Company Brain is an executable tools file for AI agents.">
                <Row label="Endpoint URL" value="stdio://axiom.cli mcp-serve" />
                <Row label="Status" value="Operational" />
                <Row label="Connected Clients" value={mcpStats?.connected_clients ?? 0} />
                <Row label="Protocol Version" value="MCP 1.1.0" />
              </Panel>
              <Panel title="Available Tools">
                <DataTable headers={["Tool", "Type", "Last Called", "Calls"]} rows={toolRows} />
              </Panel>
            </div>
            <div className="settings-grid">
              <Panel title="API Key Vault" subtitle="Manage API keys for programmatic access.">
                {vaultLocked ? <div className="mb-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-amber-100">Key vault unavailable.</div> : null}
                {bootstrapError ? <div className="mb-3 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-red-100">{bootstrapError}</div> : null}
                <div className="max-h-[350px] space-y-2 overflow-auto pr-1">
                  {[...llm, ...connectors].map((provider) => (
                    <ProviderCard
                      key={provider.id}
                      provider={provider}
                      secret={secretForProvider(secrets, provider.id)}
                      phase={providerPhase[provider.id] ?? "idle"}
                      vaultLocked={vaultLocked}
                      onConnect={() => openConnectDialog(provider)}
                      onTest={() => void runTest(provider.id)}
                      onRemove={() => {
                        if (window.confirm(`Disconnect ${provider.display_name} credential?`)) void removeSecret(provider.id);
                      }}
                    />
                  ))}
                </div>
              </Panel>
              <Panel title="Agent Access Policies">
                <Link className="text-[#00E5D8] hover:underline" to="/settings/passports">Manage Passports</Link>
              </Panel>
            </div>
          </div>
          <div className="settings-stack">
            <Panel title="Usage & Rate Limits"><Row label="Tool Calls" value={mcpStats?.tools.reduce((sum, tool) => sum + tool.calls, 0) ?? 0} /></Panel>
            <Panel title="Operational Status"><Row label="Knowledge Graph" value={health === "ok" ? "Healthy" : "Degraded"} /></Panel>
          </div>
        </div>
      )}

      </div>

      {connectTarget ? (
        <AddKeyDialog
          provider={connectTarget}
          vaultLocked={vaultLocked}
          phase={providerPhase[connectTarget.id] ?? "idle"}
          dialogError={dialogError}
          onCancel={() => closeConnectDialog()}
          onSaveAndTest={async (plaintext) => {
            await saveAndTestNewKey(connectTarget.id, plaintext);
          }}
        />
      ) : null}
    </div>
  );
}
