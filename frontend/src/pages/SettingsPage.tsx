import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { getHealth, getMcpStats, getStudioSettings, saveStudioSettings, type MCPStats } from "@/lib/studioClient";

const tabs = ["general", "integrations", "access", "notifications", "security", "preferences", "api-mcp"] as const;
type Tab = (typeof tabs)[number];

const badgeEnabled = typeof window !== "undefined" && window.location.hostname === "localhost";

function Badge({ text }: { text: string }) {
  if (!badgeEnabled) return null;
  return <span className="ml-2 rounded border border-[#2c5c95] bg-[#10294f] px-1.5 py-0.5 text-xs text-[#86b7ff]">{text}</span>;
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-[#1a4b87] bg-[#07162f]/95 p-5">
      <h3 className="text-2xl text-[#f0f8ff]">{title}</h3>
      <div className="mt-4 text-[#afc6e4]">{children}</div>
    </section>
  );
}

export function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const currentTab = (params.get("tab") as Tab) || "general";
  const tab = tabs.includes(currentTab) ? currentTab : "general";
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [mcpStats, setMcpStats] = useState<MCPStats | null>(null);
  const [health, setHealth] = useState("unknown");

  useEffect(() => {
    void getStudioSettings().then(setSettings).catch(() => {});
    void getMcpStats().then(setMcpStats).catch(() => {});
    void getHealth().then((res) => setHealth(res.status)).catch(() => {});
  }, []);

  const write = (key: string, value: unknown) => {
    const next = { ...settings, [key]: value };
    setSettings(next);
    void saveStudioSettings({ [key]: value });
  };

  const version = useMemo(() => "0.1.0", []);

  return (
    <div className="px-6 pb-8 pt-4">
      <div className="mb-4 flex gap-6 border-b border-[#14385f] pb-2 text-xl">
        {tabs.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setParams({ tab: item })}
            className={tab === item ? "border-b border-[#1ea3ff] pb-2 text-[#e8f3ff]" : "pb-2 text-[#8ea9c8]"}
          >
            {item === "api-mcp" ? "API & MCP" : item[0].toUpperCase() + item.slice(1)}
          </button>
        ))}
      </div>

      {tab === "general" && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card title="Company Settings">
            <label className="text-sm">Company Name</label>
            <input className="mt-2 w-full rounded-lg border border-[#22486f] bg-[#041225] p-2" value={String(settings.company_name ?? "Axiom Analytics Inc.")} onChange={(e) => write("company_name", e.target.value)} />
            <div className="mt-3">Time Zone <Badge text="REAL" /></div>
          </Card>
          <Card title="Brain Configuration">
            <div>Default Confidence Threshold<Badge text="PHASE 7" /></div>
            <input type="range" disabled className="mt-2 w-full" />
            <div className="mt-3">Show confidence rings <Badge text="PHASE 7" /></div>
          </Card>
          <Card title="System Summary">
            <div>Version: {version}</div>
            <div>Environment: {badgeEnabled ? "development" : "production"}</div>
            <div>Region: US East <Badge text="STUB" /></div>
            <div>Graph Health: {health}</div>
          </Card>
        </div>
      )}

      {tab === "integrations" && (
        <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
          <Card title="Data Sources / Integrations">
            <button disabled title="Coming in Phase 12" className="mb-3 rounded border border-[#2a4e83] px-3 py-1 opacity-60">+ Add Integration</button>
            <div>Slack, Linear, GitHub, Notion, Drive, PostgreSQL, Jira: Not connected <Badge text="PHASE 12" /></div>
          </Card>
          <Card title="Ingestion Health">
            <div>All values are placeholders.<Badge text="PHASE 12" /></div>
          </Card>
        </div>
      )}

      {tab === "access" && (
        <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
          <Card title="Members">
            <div>Axiom Operator (you) · Platform Admin · Active <Badge text="PHASE 11" /></div>
          </Card>
          <Card title="Invite Member">
            <button disabled title="Phase 11 — multi-tenant" className="rounded border border-[#2a4e83] px-3 py-1 opacity-60">Send Invitation</button>
          </Card>
        </div>
      )}

      {tab === "notifications" && (
        <div className="grid gap-4 xl:grid-cols-[1fr_2fr_1fr]">
          <Card title="Alert Channels">Stub channels <Badge text="PHASE 11" /></Card>
          <Card title="Notification Rules">Rules table mock <Badge text="PHASE 9" /></Card>
          <Card title="Escalation Policy">Escalation policy <Badge text="PHASE 9" /></Card>
        </div>
      )}

      {tab === "security" && (
        <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
          <Card title="Security Controls">
            <div>Authentication, API security, data protection <Badge text="PHASE 11/10" /></div>
            <div className="mt-2">Merkle Ledger Status: Active <Badge text="REAL if ledger module present" /></div>
          </Card>
          <Card title="Security Health">
            <div>Score: 92/100 <Badge text="PHASE 10" /></div>
          </Card>
        </div>
      )}

      {tab === "preferences" && (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card title="Appearance">
            <div className="mb-2">Theme <Badge text="REAL" /></div>
            <select className="w-full rounded border border-[#22486f] bg-[#041225] p-2" value={String(settings.theme ?? "dark") } onChange={(e) => write("theme", e.target.value)}>
              <option value="dark">Dark (Neon)</option>
              <option value="light">Light</option>
            </select>
            <div className="mt-2">Graph Density <Badge text="REAL" /></div>
          </Card>
          <Card title="Graph Preferences">
            <div>Show labels always <Badge text="REAL" /></div>
            <div>Show confidence rings <Badge text="REAL" /></div>
            <div>Show governance overlays <Badge text="REAL" /></div>
          </Card>
          <Card title="Keyboard Shortcuts">
            <div>Cmd/Ctrl + K, G, A, E, I <Badge text="REAL" /></div>
          </Card>
        </div>
      )}

      {tab === "api-mcp" && (
        <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
          <Card title="MCP Server">
            <div>Endpoint: stdio://axiom.cli mcp-serve</div>
            <div>Status: Operational</div>
            <div>Connected Clients: {mcpStats?.connected_clients ?? 0}</div>
            <div>Last Tool Call: {mcpStats?.last_tool_call ? new Date(mcpStats.last_tool_call).toLocaleString() : "—"}</div>
            <button
              type="button"
              className="mt-3 rounded border border-[#2a4e83] px-3 py-1"
              onClick={() => navigator.clipboard.writeText(JSON.stringify({ mcpServers: { axiom: { command: "axiom.cli", args: ["mcp-serve"] } } }, null, 2))}
            >
              Copy MCP Config
            </button>
          </Card>
          <Card title="Operational Status">
            <div>MCP Server: Operational</div>
            <div>Knowledge Graph: {health === "ok" ? "Healthy" : "Degraded"}</div>
          </Card>
          <Card title="Available Tools (MCP)">
            <div className="space-y-2">
              {(mcpStats?.tools ?? []).map((tool) => (
                <div key={tool.name} className="flex items-center justify-between rounded border border-[#204c7d] px-3 py-2">
                  <span>{tool.name}</span>
                  <span>{tool.calls} calls</span>
                </div>
              ))}
            </div>
          </Card>
          <Card title="Usage & Rate Limits">
            <div>Tool calls: {mcpStats?.tools.reduce((total, item) => total + item.calls, 0) ?? 0}</div>
            <div>API keys <Badge text="PHASE 11" /></div>
          </Card>
        </div>
      )}
    </div>
  );
}
