import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { AddKeyDialog } from "@/components/settings/AddKeyDialog";
import { ProviderCard } from "@/components/settings/ProviderCard";
import { getHealth, getMcpStats, getStudioSettings, saveStudioSettings, type MCPStats } from "@/lib/studioClient";
import { secretForProvider, useSettingsStore, visibleProviders } from "@/state/settings.store";

const tabs = ["general", "integrations", "access", "notifications", "security", "preferences", "api-mcp"] as const;
type Tab = (typeof tabs)[number];

function Phase({ children }: { children: string }) {
  return <span className="ml-2 rounded border border-[#2c5c95] bg-[#10294f] px-1.5 py-0.5 text-[10px] leading-none text-[#86b7ff]">{children}</span>;
}

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

export function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const requested = (params.get("tab") as Tab) || "general";
  const tab = tabs.includes(requested) ? requested : "general";
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [mcpStats, setMcpStats] = useState<MCPStats | null>(null);
  const [health, setHealth] = useState("unknown");

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
    void getStudioSettings().then(setSettings).catch(() => {});
    void getMcpStats().then(setMcpStats).catch(() => {});
    void getHealth().then((res) => setHealth(res.status)).catch(() => {});
    void loadSettingsData();
  }, [loadSettingsData]);

  const write = (key: string, value: unknown) => {
    const next = { ...settings, [key]: value };
    setSettings(next);
    void saveStudioSettings({ [key]: value });
  };

  const toolRows = useMemo(
    () => (mcpStats?.tools ?? []).map((tool) => [tool.name, "Read", tool.last_called ? new Date(tool.last_called).toLocaleTimeString() : "—", `${tool.calls}`]),
    [mcpStats],
  );

  return (
    <div className="settings-stage">
      <nav className="settings-tabs" aria-label="Settings tabs">
        {tabs.map((item) => (
          <button key={item} type="button" onClick={() => setParams({ tab: item })} className={tab === item ? "settings-tab-active" : "settings-tab"}>
            {item === "api-mcp" ? "API & MCP" : item[0].toUpperCase() + item.slice(1)}
          </button>
        ))}
      </nav>

      {tab === "general" && (
        <div className="grid grid-cols-[428px_460px_475px] gap-[14px]">
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
            <Row label="Default Graph Mode" value="Smart (Auto)" />
            <Row label="Auto-refresh Interval" value="30 seconds" />
            <Row label="Default Confidence Threshold" value={<span>70% <Phase>PHASE 7</Phase></span>} />
            <Row label="Default Landing Page" value="Insights Overview" />
            <Row label="Relationship Visibility" value="Show All Relationships" />
            <Row label="Show confidence rings" value={<Phase>PHASE 7</Phase>} />
          </Panel>
          <div className="space-y-[14px]">
            <Panel title="System Summary" subtitle="Overview of your system environment and health.">
              <Row label="Version" value="0.1.0" />
              <Row label="Environment" value="Production" />
              <Row label="Region" value={<span>US East <Phase>STUB</Phase></span>} />
              <Row label="Graph Health" value={health} />
              <Row label="Storage Status" value="78% used" />
            </Panel>
            <Panel title="Operational Defaults" subtitle="Default operational parameters for the workspace.">
              <Row label="Query Mode" value="Balanced" />
              <Row label="Animation Intensity" value="Medium" />
              <Row label="Graph Density" value="Optimal" />
              <Row label="Notification Summary" value="Brief" />
            </Panel>
          </div>
        </div>
      )}

      {tab === "integrations" && (
        <div className="grid grid-cols-[986px_394px] gap-[14px]">
          <Panel title="Data Sources / Integrations" subtitle="Connect and manage the data sources that power your Company Brain.">
            <DataTable
              headers={["Source", "Connection", "Live Sync", "Last Sync", "Scope", "Actions"]}
              rows={["Slack", "Linear", "GitHub", "Notion", "Google Drive", "PostgreSQL", "Jira"].map((name) => [name, "Not connected", "—", "—", <Phase>PHASE 12</Phase>, "Disabled"])}
            />
          </Panel>
          <div className="space-y-[14px]">
            <Panel title="Ingestion Health"><Row label="Total Sources" value={<span>0 <Phase>PHASE 12</Phase></span>} /></Panel>
            <Panel title="Source Mapping"><Row label="Coverage" value={<span>Pending <Phase>PHASE 12</Phase></span>} /></Panel>
          </div>
        </div>
      )}

      {tab === "access" && (
        <div className="grid grid-cols-[1040px_346px] gap-[14px]">
          <div className="space-y-[14px]">
            <Panel title="Members" subtitle="Manage users, roles, and access across your Company Brain.">
              <DataTable headers={["Name", "Email", "Role", "Team", "Status"]} rows={[["Axiom Operator", "you@axiom.local", "Platform Admin", "Platform", "Active"]]} />
              <div className="mt-3"><Phase>PHASE 11 multi-user</Phase></div>
            </Panel>
            <div className="grid grid-cols-2 gap-[14px]">
              <Panel title="Teams">Platform Engineering <Phase>PHASE 11</Phase></Panel>
              <Panel title="Access Rules">Global access matrix <Phase>PHASE 11</Phase></Panel>
            </div>
          </div>
          <Panel title="Invite Member" subtitle="Add a new member to your workspace.">
            <div title="Phase 11 — multi-tenant" className="flex h-[38px] w-full items-center justify-center rounded-md border border-[#2b558a] text-[#88add5] opacity-70">Invitations are not enabled yet</div>
          </Panel>
        </div>
      )}

      {tab === "notifications" && (
        <div className="grid grid-cols-[320px_734px_320px] gap-[14px]">
          <Panel title="Alert Channels">Email, Slack, In-app, Webhook, PagerDuty <Phase>PHASE 11</Phase></Panel>
          <Panel title="Notification Rules">
            <DataTable headers={["Rule", "Severity", "Frequency", "Escalation"]} rows={["Policy Violation", "Agent Action Denied", "Low-confidence Entity Created", "Integration Sync Failed"].map((rule) => [rule, "Medium", "Immediate", "15 min"])} />
            <div className="mt-3"><Phase>PHASE 9</Phase></div>
          </Panel>
          <div className="space-y-[14px]">
            <Panel title="Escalation Policy">Tiered escalation <Phase>PHASE 9</Phase></Panel>
            <Panel title="Notification Recipients">Recipient groups <Phase>PHASE 9</Phase></Panel>
          </div>
        </div>
      )}

      {tab === "security" && (
        <div className="grid grid-cols-[870px_450px] gap-[14px]">
          <div className="space-y-[14px]">
            <div className="grid grid-cols-2 gap-[14px]">
              <Panel title="Authentication">SSO / MFA <Phase>PHASE 11</Phase></Panel>
              <Panel title="API Security">No API keys yet <Phase>PHASE 11</Phase></Panel>
            </div>
            <div className="grid grid-cols-2 gap-[14px]">
              <Panel title="Data Protection">Encryption and redaction controls <Phase>PHASE 10</Phase></Panel>
              <Panel title="Audit Controls">Merkle Ledger Status: Active <Phase>REAL</Phase></Panel>
            </div>
            <Panel title="Risk Controls">Approval and confidence controls <Phase>PHASE 9</Phase></Panel>
          </div>
          <div className="space-y-[14px]">
            <Panel title="Security Health">92/100 <Phase>PHASE 10</Phase></Panel>
            <Panel title="Recent Security Events">Latest security events <Phase>PHASE 9+</Phase></Panel>
          </div>
        </div>
      )}

      {tab === "preferences" && (
        <div className="grid grid-cols-[452px_448px_456px] gap-[14px]">
          <Panel title="Appearance" subtitle="Customize how AXIOM looks and feels.">
            <Row label="Theme" value="Dark (Neon)" />
            <Row label="Graph Density" value="Optimal" />
            <Row label="Glow Intensity" value="Medium" />
            <Row label="Animation Intensity" value="Medium" />
          </Panel>
          <Panel title="Graph Preferences" subtitle="Control what is shown on the graph.">
            <Row label="Show labels always" value="On" />
            <Row label="Show confidence rings" value="On" />
            <Row label="Show governance overlays" value="On" />
            <Row label="Show agent traversal paths" value="On" />
          </Panel>
          <Panel title="Query Preferences" subtitle="Set defaults for searching and asking the brain.">
            <Row label="Default Query Mode" value={<span>Balanced <Phase>PHASE 13</Phase></span>} />
            <Row label="Save query history" value={<Phase>PHASE 13</Phase>} />
          </Panel>
          <Panel title="Profile">Axiom Operator · Platform Administrator</Panel>
          <Panel title="Keyboard Shortcuts">Cmd/Ctrl+K, G, A, E, I</Panel>
          <Panel title="About Preferences">Scoped to your workspace.</Panel>
        </div>
      )}

      {tab === "api-mcp" && (
        <div className="grid grid-cols-[1076px_332px] gap-[14px]">
          <div className="space-y-[14px]">
            <div className="grid grid-cols-[364px_698px] gap-[14px]">
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
            <div className="grid grid-cols-[555px_507px] gap-[14px]">
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
          <div className="space-y-[14px]">
            <Panel title="Usage & Rate Limits"><Row label="Tool Calls" value={mcpStats?.tools.reduce((sum, tool) => sum + tool.calls, 0) ?? 0} /></Panel>
            <Panel title="Operational Status"><Row label="Knowledge Graph" value={health === "ok" ? "Healthy" : "Degraded"} /></Panel>
          </div>
        </div>
      )}

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
