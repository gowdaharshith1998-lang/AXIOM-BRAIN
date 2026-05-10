import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { getMcpStats, type MCPStats } from "@/lib/studioClient";
import { useBrainStore, type AgentActionLog, type LedgerReceipt } from "@/state/brain.store";

type Accent = "blue" | "cyan" | "green" | "amber" | "red" | "purple" | "teal";
type RouteKey = "dashboard" | "registry" | "live-runs" | "autonomous-mode" | "schedules" | "triggers" | "approvals" | "runtime" | "activity" | "agent-detail";

type GovernanceReceipt = {
  receipt_id: string;
  action_id: string | null;
  decision: string | null;
  agent_name: string | null;
  signed: boolean;
  created_at: string | null;
};

type GovernanceAuditEvent = {
  id: string;
  timestamp?: string | null;
  timestamp_ms?: number;
  actor: string | null;
  action: string | null;
  entity: string | null;
  category: string;
  result: string | null;
  source: string;
};

type GovernanceSnapshot = {
  summary: {
    action_count: number;
    denied_action_count: number;
    receipt_count: number;
    signed_receipt_count: number;
    current_seq: number;
    latest_event_at: number | null;
  };
  receipts: GovernanceReceipt[];
  audit_events: GovernanceAuditEvent[];
};

type AgentSummary = {
  name: string;
  actionCount: number;
  recentMcpCount: number;
  receiptCount: number;
  deniedCount: number;
  lastActiveMs: number | null;
  lastIntent: string;
  lastStatus: string;
};

type AgentsData = {
  mcpStats: MCPStats | null;
  governance: GovernanceSnapshot | null;
  actions: AgentActionLog[];
  receipts: LedgerReceipt[];
  agents: AgentSummary[];
  loading: boolean;
  error: string | null;
};

const routeMeta: Record<RouteKey, { title: string; subtitle: string; primaryAction?: string }> = {
  dashboard: { title: "Agents", subtitle: "Run, govern, and observe real agent activity inside AXIOM Company Brain.", primaryAction: "Run Agent" },
  registry: { title: "Agent Registry", subtitle: "Real agents observed from MCP stats, action events, and signed receipts.", primaryAction: "Run Agent" },
  "live-runs": { title: "Live Runs", subtitle: "Live run data is shown only when real MCP/action events exist.", primaryAction: "Run Agent" },
  "autonomous-mode": { title: "Autonomous Mode", subtitle: "Autonomy controls require persisted agent configuration before values can be shown.", primaryAction: "Run Agent" },
  schedules: { title: "Schedules", subtitle: "Schedules require a real schedules API before rows can be displayed.", primaryAction: "Run Now" },
  triggers: { title: "Triggers", subtitle: "Triggers require real trigger definitions before rows can be displayed.", primaryAction: "Run Agent" },
  approvals: { title: "Approvals", subtitle: "Approval rows come from real denied or pending governance events only.", primaryAction: "Run Agent" },
  runtime: { title: "Runtime", subtitle: "Runtime health is limited to real connection, MCP, and governance data currently exposed.", primaryAction: "Run Agent" },
  activity: { title: "Activity", subtitle: "Audit real agent actions, governance decisions, tool calls, and receipts.", primaryAction: "Run Agent" },
  "agent-detail": { title: "Agent Detail", subtitle: "Real per-agent activity assembled from observed events.", primaryAction: "Run Agent" },
};

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function isDemo(item: { demo?: boolean } | undefined): boolean {
  return item?.demo === true;
}

function formatNumber(value: number | null | undefined): string {
  return (value ?? 0).toLocaleString();
}

function toMs(value: string | number | null | undefined): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string" || !value) return null;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function formatTime(value: string | number | null | undefined): string {
  const ms = toMs(value);
  if (!ms) return "Not recorded";
  return new Date(ms).toLocaleString();
}

function formatRelative(value: string | number | null | undefined): string {
  const ms = toMs(value);
  if (!ms) return "Not recorded";
  const diffSeconds = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
  return `${Math.floor(diffSeconds / 86400)}d ago`;
}

function toneForStatus(value: string | null | undefined): Accent {
  const normalized = (value ?? "").toLowerCase();
  if (normalized.includes("deny") || normalized.includes("fail") || normalized.includes("blocked")) return "red";
  if (normalized.includes("pending") || normalized.includes("running") || normalized.includes("review")) return "amber";
  if (normalized.includes("allow") || normalized.includes("success") || normalized.includes("signed")) return "green";
  return "blue";
}

function iconForAgent(name: string): string {
  const normalized = name.toLowerCase();
  if (normalized.includes("finance")) return "dollar";
  if (normalized.includes("policy")) return "book";
  if (normalized.includes("support")) return "headset";
  if (normalized.includes("risk") || normalized.includes("vendor")) return "shield";
  if (normalized.includes("incident")) return "warning";
  return "bot";
}

function accentForAgent(name: string): Accent {
  const normalized = name.toLowerCase();
  if (normalized.includes("finance")) return "green";
  if (normalized.includes("policy")) return "purple";
  if (normalized.includes("support")) return "teal";
  if (normalized.includes("risk") || normalized.includes("vendor")) return "purple";
  if (normalized.includes("incident")) return "red";
  return "blue";
}

function Icon({ name, className = "" }: { name: string; className?: string }) {
  const common = { stroke: "currentColor", strokeWidth: 1.75, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" className={className || "agents-icon"} aria-hidden="true">
      {name === "arrow-left" && <path {...common} d="M19 12H5m6-6-6 6 6 6" />}
      {name === "arrow" && <path {...common} d="M5 12h13m-5-5 5 5-5 5" />}
      {name === "plus" && <path {...common} d="M12 5v14M5 12h14" />}
      {name === "play" && <path {...common} d="m8 5 11 7-11 7V5Z" />}
      {name === "bell" && <path {...common} d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Zm-8 12h4" />}
      {name === "bot" && <path {...common} d="M8 7V5m8 2V5M6.5 9.5h11A2.5 2.5 0 0 1 20 12v4.5a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V12a2.5 2.5 0 0 1 2.5-2.5Zm2.5 4h.01M15 13.5h.01M9 17h6" />}
      {name === "pulse" && <path {...common} d="M3 12h4l2-6 4 12 2-6h6" />}
      {name === "shield" && <path {...common} d="m12 3 7 3v5.5c0 4.2-2.7 7.3-7 9-4.3-1.7-7-4.8-7-9V6l7-3Z" />}
      {name === "hourglass" && <path {...common} d="M6 3h12M6 21h12M8 3v4.5L12 12l4 4.5V21M16 3v4.5L12 12l-4 4.5V21" />}
      {name === "warning" && <path {...common} d="m12 3 10 18H2L12 3Zm0 6v5m0 3h.01" />}
      {name === "network" && <path {...common} d="M12 5v6m0 0-5 4m5-4 5 4M6 18h.01M18 18h.01M12 5h.01" />}
      {name === "receipt" && <path {...common} d="M7 3h10v18l-2-1.2-2 1.2-2-1.2-2 1.2-2-1.2V3Zm3 5h4m-4 4h4m-4 4h3" />}
      {name === "user" && <path {...common} d="M12 12.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7 8a7 7 0 0 0-14 0" />}
      {name === "book" && <path {...common} d="M5 4h10a4 4 0 0 1 4 4v12H8a3 3 0 0 1-3-3V4Zm0 13a3 3 0 0 1 3-3h11" />}
      {name === "headset" && <path {...common} d="M4 13a8 8 0 0 1 16 0v3a2 2 0 0 1-2 2h-2v-6h4M4 16v-3m0 3a2 2 0 0 0 2 2h2v-6H4m10 8h2a2 2 0 0 0 2-2" />}
      {name === "dollar" && <path {...common} d="M12 3v18m4-14.5H9.5a2.5 2.5 0 0 0 0 5H14a2.5 2.5 0 0 1 0 5H7" />}
      {name === "calendar" && <path {...common} d="M7 3v4m10-4v4M5 7h14M5 7v13h14V7M8 11h3m2 0h3m-8 4h3m2 0h3" />}
      {name === "bolt" && <path {...common} d="m13 2-8 12h6l-1 8 9-13h-6l1-7Z" />}
      {name === "clock" && <path {...common} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v5l3 2" />}
      {name === "filter" && <path {...common} d="M4 5h16l-6 7v5l-4 2v-7L4 5Z" />}
      {name === "search" && <path {...common} d="m21 21-4.4-4.4M10.6 18a7.4 7.4 0 1 1 0-14.8 7.4 7.4 0 0 1 0 14.8Z" />}
      {!["arrow-left", "arrow", "plus", "play", "bell", "bot", "pulse", "shield", "hourglass", "warning", "network", "receipt", "user", "book", "headset", "dollar", "calendar", "bolt", "clock", "filter", "search"].includes(name) && <path {...common} d="M12 3 4 8v8l8 5 8-5V8l-8-5Z" />}
    </svg>
  );
}

async function fetchGovernance(): Promise<GovernanceSnapshot> {
  const response = await fetch("/api/governance");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as GovernanceSnapshot;
}

function useAgentsData(): AgentsData {
  const rawActions = useBrainStore((s) => s.agentActions);
  const rawReceipts = useBrainStore((s) => s.receipts);
  const [mcpStats, setMcpStats] = useState<MCPStats | null>(null);
  const [governance, setGovernance] = useState<GovernanceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [stats, gov] = await Promise.all([getMcpStats(), fetchGovernance()]);
        if (!cancelled) {
          setMcpStats(stats);
          setGovernance(gov);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load agent data");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    const id = window.setInterval(load, 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const actions = useMemo(() => rawActions.filter((item) => !isDemo(item)), [rawActions]);
  const receipts = useMemo(() => rawReceipts.filter((item) => !isDemo(item)), [rawReceipts]);

  const agents = useMemo(() => {
    const names = new Set<string>();
    for (const name of mcpStats?.active_agents ?? []) if (name.trim()) names.add(name.trim());
    for (const action of mcpStats?.recent_actions ?? []) if (action.agent_name.trim()) names.add(action.agent_name.trim());
    for (const action of actions) if (action.agent_name?.trim()) names.add(action.agent_name.trim());
    for (const receipt of receipts) if (receipt.agent_name?.trim()) names.add(receipt.agent_name.trim());
    for (const receipt of governance?.receipts ?? []) if (receipt.agent_name?.trim()) names.add(receipt.agent_name.trim());
    for (const event of governance?.audit_events ?? []) if (event.actor?.trim()) names.add(event.actor.trim());

    return Array.from(names)
      .sort()
      .map((name) => {
        const actionRows = actions.filter((action) => action.agent_name === name);
        const mcpRows = (mcpStats?.recent_actions ?? []).filter((action) => action.agent_name === name);
        const receiptRows = [
          ...receipts.filter((receipt) => receipt.agent_name === name),
          ...(governance?.receipts ?? []).filter((receipt) => receipt.agent_name === name),
        ];
        const deniedCount =
          actionRows.filter((action) => action.decision === "deny").length +
          receiptRows.filter((receipt) => receipt.decision === "deny").length +
          (governance?.audit_events ?? []).filter((event) => event.actor === name && toneForStatus(event.result) === "red").length;
        const timestamps = [
          ...actionRows.map((action) => toMs(action.timestamp)),
          ...mcpRows.map((action) => toMs(action.timestamp)),
          ...receiptRows.map((receipt) => toMs("timestamp" in receipt ? receipt.timestamp : receipt.created_at)),
        ].filter((value): value is number => Boolean(value));
        const latestMcp = mcpRows.sort((a, b) => b.timestamp - a.timestamp)[0];
        const latestAction = actionRows.sort((a, b) => (toMs(b.timestamp) ?? 0) - (toMs(a.timestamp) ?? 0))[0];
        return {
          name,
          actionCount: actionRows.length,
          recentMcpCount: mcpRows.length,
          receiptCount: receiptRows.length,
          deniedCount,
          lastActiveMs: timestamps.length ? Math.max(...timestamps) : null,
          lastIntent: latestMcp?.intent || latestAction?.skill_called || "Not recorded",
          lastStatus: latestMcp?.status || latestAction?.decision || "recorded",
        };
      })
      .sort((a, b) => (b.lastActiveMs ?? 0) - (a.lastActiveMs ?? 0));
  }, [actions, governance, mcpStats, receipts]);

  return { mcpStats, governance, actions, receipts, agents, loading, error };
}

function AgentBadge({ name }: { name: string }) {
  const accent = accentForAgent(name);
  return (
    <span className="agents-name-cell">
      <span className={cx("agents-agent-icon", `agents-${accent}`)}><Icon name={iconForAgent(name)} /></span>
      <span>{name}</span>
    </span>
  );
}

function Pill({ children, tone = "blue" }: { children: ReactNode; tone?: Accent | "neutral" }) {
  return <span className={cx("agents-pill", tone !== "neutral" && `agents-${tone}`)}>{children}</span>;
}

function DotStatus({ children, tone = "green" }: { children: ReactNode; tone?: Accent | "neutral" }) {
  return <span className={cx("agents-dot-status", tone !== "neutral" && `agents-${tone}`)}><i />{children}</span>;
}

function MetricCard({ icon, title, value, delta, tone = "blue" }: { icon: string; title: string; value: string; delta: string; tone?: Accent }) {
  return (
    <section className={cx("agents-metric", `agents-${tone}`)}>
      <span className="agents-metric-icon"><Icon name={icon} /></span>
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
        <small>{delta}</small>
      </div>
    </section>
  );
}

function Panel({ title, count, action, className, children }: { title: string; count?: string; action?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <section className={cx("agents-panel", className)}>
      <div className="agents-panel-head">
        <h2>{title} {count ? <span>{count}</span> : null}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function EmptyState({ children }: { children: ReactNode }) {
  return <div className="agents-empty">{children}</div>;
}

function RowsTable({ headers, rows, columns }: { headers: ReactNode[]; rows: ReactNode[][]; columns: string }) {
  return (
    <div className="agents-table" style={{ "--agents-cols": columns } as React.CSSProperties}>
      <div className="agents-table-head">
        {headers.map((header, index) => <span key={index}>{header}</span>)}
      </div>
      {rows.map((row, rowIndex) => (
        <div key={rowIndex} className={cx("agents-table-row", rowIndex === 0 && "is-selected")}>
          {row.map((cell, cellIndex) => <span key={cellIndex}>{cell}</span>)}
        </div>
      ))}
    </div>
  );
}

function CompactRows({ rows }: { rows: ReactNode[][] }) {
  return <div className="agents-compact-rows">{rows.map((row, index) => <div key={index}>{row.map((cell, cellIndex) => <span key={cellIndex}>{cell}</span>)}</div>)}</div>;
}

function Header({ route, data, agentName }: { route: RouteKey; data: AgentsData; agentName?: string | null }) {
  const meta = routeMeta[route];
  const title = route === "agent-detail" ? agentName || data.agents[0]?.name || meta.title : meta.title;
  return (
    <header className="agents-topbar">
      <div className="agents-title-block">
        {route !== "dashboard" ? (
          <Link className="agents-back-button" to="/agents">
            <Icon name="arrow-left" />
            Back to Agents
          </Link>
        ) : null}
        <div className="agents-detail-heading">
          <div>
            <h1>{title}</h1>
            <p>{meta.subtitle}</p>
          </div>
        </div>
      </div>
      <div className="agents-top-actions">
        <div className="agents-live-pill"><i /> Runtime {data.mcpStats ? "Live" : "Unknown"} <span>{data.error ? "Data unavailable" : "Real data only"}</span></div>
        <button type="button" className="agents-secondary"><Icon name="plus" /> New Agent</button>
        <button type="button" className="agents-primary"><Icon name="play" /> {meta.primaryAction}</button>
        <button type="button" className="agents-round"><Icon name="bell" /></button>
        <button type="button" className="agents-avatar">AK</button>
      </div>
    </header>
  );
}

function PageNav() {
  const items: Array<[string, string]> = [
    ["/agents/registry", "Registry"],
    ["/agents/live-runs", "Live Runs"],
    ["/agents/autonomous-mode", "Autonomous Mode"],
    ["/agents/approvals", "Approvals"],
    ["/agents/schedules", "Schedules"],
    ["/agents/triggers", "Triggers"],
    ["/agents/runtime", "Runtime"],
    ["/agents/activity", "Activity"],
  ];
  return <nav className="agents-page-nav">{items.map(([to, label]) => <Link key={to} to={to}>{label}</Link>)}</nav>;
}

function AgentsFooter() {
  return (
    <footer className="agents-footer">
      <span>All times local</span>
      <span><i /> Data source: MCP, websocket, governance API</span>
      <b>No demo or placeholder rows are rendered.</b>
      <Link to="/governance">Learn about agent governance <Icon name="arrow" /></Link>
    </footer>
  );
}

function SummaryMetrics({ data }: { data: AgentsData }) {
  const toolCalls = data.mcpStats?.tools.reduce((sum, tool) => sum + tool.calls, 0) ?? 0;
  const signedReceipts = data.governance?.summary.signed_receipt_count ?? data.receipts.length;
  const denied = data.governance?.summary.denied_action_count ?? data.actions.filter((action) => action.decision === "deny").length;
  return (
    <div className="agents-five-metrics">
      <MetricCard icon="bot" title="Observed Agents" value={formatNumber(data.agents.length)} delta="From real agent events" />
      <MetricCard icon="pulse" title="Recent MCP Events" value={formatNumber(data.mcpStats?.recent_actions.length ?? 0)} delta="Last hour buffer" tone="cyan" />
      <MetricCard icon="network" title="Tool Calls" value={formatNumber(toolCalls)} delta="Recorded MCP tool calls" tone="purple" />
      <MetricCard icon="receipt" title="Signed Receipts" value={formatNumber(signedReceipts)} delta="Governance ledger" tone="green" />
      <MetricCard icon="warning" title="Denied / Blocked" value={formatNumber(denied)} delta="Real governance outcomes" tone={denied ? "red" : "green"} />
    </div>
  );
}

function AgentTable({ agents }: { agents: AgentSummary[] }) {
  if (!agents.length) return <EmptyState>No real agents have reported activity yet.</EmptyState>;
  return (
    <RowsTable
      columns="1.45fr .75fr .8fr .75fr .75fr 1.3fr 1fr"
      headers={["Agent", "Actions", "MCP Events", "Receipts", "Denied", "Last Intent", "Last Active"]}
      rows={agents.map((agent) => [
        <Link to={`/agents/${encodeURIComponent(agent.name)}`}><AgentBadge name={agent.name} /></Link>,
        formatNumber(agent.actionCount),
        formatNumber(agent.recentMcpCount),
        formatNumber(agent.receiptCount),
        <span className={agent.deniedCount ? "agents-red" : "agents-green"}>{formatNumber(agent.deniedCount)}</span>,
        agent.lastIntent,
        formatRelative(agent.lastActiveMs),
      ])}
    />
  );
}

function DashboardPage({ data }: { data: AgentsData }) {
  return (
    <>
      <SummaryMetrics data={data} />
      {data.error ? <EmptyState>Unable to load some agent data: {data.error}</EmptyState> : null}
      <div className="agents-two-col">
        <Panel title="Observed Agents" count={formatNumber(data.agents.length)} action={<Link to="/agents/registry">View registry <Icon name="arrow" /></Link>}>
          <AgentTable agents={data.agents.slice(0, 6)} />
        </Panel>
        <Panel title="Recent Real MCP Activity" count={formatNumber(data.mcpStats?.recent_actions.length ?? 0)} action={<Link to="/agents/activity">View activity <Icon name="arrow" /></Link>}>
          <RecentMcpTable data={data} />
        </Panel>
      </div>
      <div className="agents-four-col">
        <Panel title="Tool Calls" action={<Link to="/agents/runtime">Runtime <Icon name="arrow" /></Link>}>
          {data.mcpStats?.tools.some((tool) => tool.calls > 0) ? <CompactRows rows={data.mcpStats.tools.filter((tool) => tool.calls > 0).map((tool) => [tool.name, formatNumber(tool.calls), formatTime(tool.last_called)])} /> : <EmptyState>No MCP tool calls recorded.</EmptyState>}
        </Panel>
        <Panel title="Receipt Ledger" action={<Link to="/governance">Governance <Icon name="arrow" /></Link>}>
          <ReceiptList data={data} />
        </Panel>
        <Panel title="Governance Outcomes" action={<Link to="/agents/approvals">Approvals <Icon name="arrow" /></Link>}>
          <GovernanceEventList data={data} filter="governance" />
        </Panel>
        <Panel title="Runtime Availability" action={<Link to="/agents/runtime">Details <Icon name="arrow" /></Link>}>
          <CompactRows rows={[["MCP stats", data.mcpStats ? <Pill tone="green">Available</Pill> : <Pill tone="amber">Unavailable</Pill>], ["Governance API", data.governance ? <Pill tone="green">Available</Pill> : <Pill tone="amber">Unavailable</Pill>], ["Loaded", data.loading ? "Loading" : "Complete"]]} />
        </Panel>
      </div>
    </>
  );
}

function RegistryPage({ data }: { data: AgentsData }) {
  return (
    <>
      <SummaryMetrics data={data} />
      <Panel title="Agent Registry" count={formatNumber(data.agents.length)} action={null}>
        <AgentTable agents={data.agents} />
      </Panel>
    </>
  );
}

function RecentMcpTable({ data }: { data: AgentsData }) {
  const rows = data.mcpStats?.recent_actions ?? [];
  if (!rows.length) return <EmptyState>No real MCP agent events in the recent action buffer.</EmptyState>;
  return (
    <RowsTable
      columns="1.1fr 1.35fr 1fr .8fr .8fr"
      headers={["Time", "Agent", "Intent", "Status", "Duration"]}
      rows={rows.map((row) => [
        formatRelative(row.timestamp),
        <AgentBadge name={row.agent_name} />,
        row.intent || "Not recorded",
        <Pill tone={toneForStatus(row.status)}>{row.status || "recorded"}</Pill>,
        row.duration_ms ? `${row.duration_ms}ms` : "Not recorded",
      ])}
    />
  );
}

function LiveRunsPage({ data }: { data: AgentsData }) {
  return (
    <>
      <SummaryMetrics data={data} />
      <div className="agents-live-layout">
        <Panel title="Live / Recent Runs" count={formatNumber(data.mcpStats?.recent_actions.length ?? 0)} action={null}>
          <RecentMcpTable data={data} />
        </Panel>
        <aside className="agents-inspector">
          <div className="agents-inspector-head"><h2>Run Inspector</h2><DotStatus tone={data.mcpStats?.recent_actions.length ? "green" : "amber"}>{data.mcpStats?.recent_actions.length ? "Observed" : "Empty"}</DotStatus></div>
          {data.mcpStats?.recent_actions[0] ? (
            <CompactRows rows={Object.entries({
              Agent: data.mcpStats.recent_actions[0].agent_name,
              Intent: data.mcpStats.recent_actions[0].intent || "Not recorded",
              Status: data.mcpStats.recent_actions[0].status,
              Timestamp: formatTime(data.mcpStats.recent_actions[0].timestamp),
              Duration: data.mcpStats.recent_actions[0].duration_ms ? `${data.mcpStats.recent_actions[0].duration_ms}ms` : "Not recorded",
            })} />
          ) : (
            <EmptyState>No active run event has been received.</EmptyState>
          )}
        </aside>
      </div>
    </>
  );
}

function ReceiptList({ data }: { data: AgentsData }) {
  const rows = [
    ...data.receipts.map((receipt) => ({ id: receipt.receipt_id, agent: receipt.agent_name, decision: receipt.decision, time: receipt.timestamp, signed: true })),
    ...(data.governance?.receipts ?? []).map((receipt) => ({ id: receipt.receipt_id, agent: receipt.agent_name ?? "Not recorded", decision: receipt.decision ?? "recorded", time: receipt.created_at, signed: receipt.signed })),
  ].slice(0, 8);
  if (!rows.length) return <EmptyState>No real receipts recorded.</EmptyState>;
  return <CompactRows rows={rows.map((row) => [row.id, row.agent, <Pill tone={row.signed ? "green" : "amber"}>{row.signed ? "Signed" : "Unsigned"}</Pill>, formatRelative(row.time)])} />;
}

function GovernanceEventList({ data, filter }: { data: AgentsData; filter?: "governance" | "approval" }) {
  const events = (data.governance?.audit_events ?? []).filter((event) => {
    if (!filter) return true;
    if (filter === "approval") return toneForStatus(event.result) === "red" || toneForStatus(event.result) === "amber";
    return event.category === "persisted_action" || event.category === "mcp_event";
  });
  if (!events.length) return <EmptyState>No real governance events match this view.</EmptyState>;
  return (
    <RowsTable
      columns=".95fr 1fr 1.15fr 1.15fr .85fr"
      headers={["Time", "Actor", "Action", "Entity", "Result"]}
      rows={events.slice(0, 12).map((event) => [
        formatRelative(event.timestamp_ms ?? event.timestamp),
        event.actor ? <AgentBadge name={event.actor} /> : "Not recorded",
        event.action ?? "Not recorded",
        event.entity ?? "Not recorded",
        <Pill tone={toneForStatus(event.result)}>{event.result ?? "recorded"}</Pill>,
      ])}
    />
  );
}

function ActivityPage({ data }: { data: AgentsData }) {
  return (
    <>
      <SummaryMetrics data={data} />
      <div className="agents-activity-layout">
        <Panel title="Real Activity Events" count={formatNumber(data.governance?.audit_events.length ?? 0)} action={null}>
          <GovernanceEventList data={data} />
        </Panel>
        <aside className="agents-detail-panel">
          <div className="agents-inspector-head"><h2>Activity Inspector</h2></div>
          {data.governance?.audit_events[0] ? (
            <CompactRows rows={Object.entries({
              Actor: data.governance.audit_events[0].actor ?? "Not recorded",
              Action: data.governance.audit_events[0].action ?? "Not recorded",
              Entity: data.governance.audit_events[0].entity ?? "Not recorded",
              Category: data.governance.audit_events[0].category,
              Result: data.governance.audit_events[0].result ?? "recorded",
              Source: data.governance.audit_events[0].source,
            })} />
          ) : (
            <EmptyState>No event selected because no real activity exists.</EmptyState>
          )}
        </aside>
      </div>
    </>
  );
}

function ApprovalsPage({ data }: { data: AgentsData }) {
  return (
    <>
      <SummaryMetrics data={data} />
      <Panel title="Approval / Block Queue" action={null}>
        <GovernanceEventList data={data} filter="approval" />
      </Panel>
    </>
  );
}

function RuntimePage({ data }: { data: AgentsData }) {
  const toolCalls = data.mcpStats?.tools.reduce((sum, tool) => sum + tool.calls, 0) ?? 0;
  return (
    <>
      <div className="agents-five-metrics">
        <MetricCard icon="pulse" title="MCP Stats" value={data.mcpStats ? "Available" : "Unavailable"} delta="Real endpoint status" tone={data.mcpStats ? "green" : "amber"} />
        <MetricCard icon="user" title="Connected Agents" value={formatNumber(data.mcpStats?.connected_clients ?? 0)} delta="Recent active agents" />
        <MetricCard icon="network" title="Tool Calls" value={formatNumber(toolCalls)} delta="Total recorded calls" tone="purple" />
        <MetricCard icon="receipt" title="Governance Seq" value={formatNumber(data.governance?.summary.current_seq ?? 0)} delta="Broadcaster sequence" tone="cyan" />
        <MetricCard icon="clock" title="Last Tool Call" value={formatRelative(data.mcpStats?.last_tool_call ?? null)} delta="Real MCP timestamp" tone="teal" />
      </div>
      <div className="agents-runtime-grid">
        <Panel title="Tool Counters" action={null}>{data.mcpStats?.tools.length ? <CompactRows rows={data.mcpStats.tools.map((tool) => [tool.name, formatNumber(tool.calls), formatTime(tool.last_called)])} /> : <EmptyState>No runtime tool data available.</EmptyState>}</Panel>
        <Panel title="Exposed Runtime Data" action={null}><CompactRows rows={[["Worker fleet", "No real API exposed"], ["Queue health", "No real API exposed"], ["Retry policy", "No real API exposed"], ["Current executions", data.mcpStats?.recent_actions.length ? `${data.mcpStats.recent_actions.length} recent events` : "No real events"]]} /></Panel>
        <Panel title="Data Contract" action={null}><EmptyState>Worker, queue, schedule, and trigger rows are intentionally empty until backend APIs exist.</EmptyState></Panel>
      </div>
    </>
  );
}

function EmptyFeaturePage({ data, feature }: { data: AgentsData; feature: string }) {
  return (
    <>
      <SummaryMetrics data={data} />
      <Panel title={feature} action={null}>
        <EmptyState>{feature} has no real backend data contract in this repo yet, so the page does not render placeholder rows.</EmptyState>
      </Panel>
    </>
  );
}

function AgentDetailPage({ data, name }: { data: AgentsData; name: string }) {
  const agent = data.agents.find((item) => item.name === name) ?? data.agents[0];
  if (!agent) return <EmptyFeaturePage data={data} feature="Agent Detail" />;
  const actions = data.actions.filter((action) => action.agent_name === agent.name);
  const mcpRows = data.mcpStats?.recent_actions.filter((action) => action.agent_name === agent.name) ?? [];
  return (
    <>
      <div className="agents-detail-summary">
        <div><Icon name={iconForAgent(agent.name)} /><span>Observed Agent</span><b>{agent.name}</b></div>
        <div><Icon name="pulse" /><span>Action Events</span><b>{formatNumber(agent.actionCount)}</b></div>
        <div><Icon name="network" /><span>MCP Events</span><b>{formatNumber(agent.recentMcpCount)}</b></div>
        <div><Icon name="receipt" /><span>Receipts</span><b>{formatNumber(agent.receiptCount)}</b></div>
        <div><Icon name="warning" /><span>Denied</span><b>{formatNumber(agent.deniedCount)}</b></div>
        <div><Icon name="clock" /><span>Last Active</span><b>{formatRelative(agent.lastActiveMs)}</b></div>
      </div>
      <div className="agents-detail-grid">
        <Panel title="Recent MCP Events" action={null}>{mcpRows.length ? <RowsTable columns="1fr 1.3fr .9fr .8fr" headers={["Time", "Intent", "Status", "Duration"]} rows={mcpRows.map((row) => [formatRelative(row.timestamp), row.intent || "Not recorded", <Pill tone={toneForStatus(row.status)}>{row.status}</Pill>, row.duration_ms ? `${row.duration_ms}ms` : "Not recorded"])} /> : <EmptyState>No recent MCP events for this agent.</EmptyState>}</Panel>
        <Panel title="Agent Action Events" action={null}>{actions.length ? <RowsTable columns="1fr 1.2fr 1.1fr .85fr 1.2fr" headers={["Time", "Skill", "Cluster", "Decision", "Action ID"]} rows={actions.map((row) => [formatRelative(row.timestamp), row.skill_called, row.cluster_id, <Pill tone={toneForStatus(row.decision)}>{row.decision ?? "recorded"}</Pill>, row.action_id])} /> : <EmptyState>No websocket action events for this agent.</EmptyState>}</Panel>
      </div>
    </>
  );
}

function routeFromPath(pathname: string): { route: RouteKey; agentName: string | null } {
  const route = pathname.replace(/^\/agents\/?/, "").split("/")[0] || "dashboard";
  if (route === "runs") return { route: "live-runs", agentName: null };
  if (route in routeMeta) return { route: route as RouteKey, agentName: null };
  return { route: "agent-detail", agentName: decodeURIComponent(route) };
}

export function AgentsPage() {
  const location = useLocation();
  const data = useAgentsData();
  const { route, agentName } = routeFromPath(location.pathname);

  const page: Record<RouteKey, ReactNode> = {
    dashboard: <DashboardPage data={data} />,
    registry: <RegistryPage data={data} />,
    "live-runs": <LiveRunsPage data={data} />,
    "autonomous-mode": <EmptyFeaturePage data={data} feature="Autonomous Mode" />,
    schedules: <EmptyFeaturePage data={data} feature="Schedules" />,
    triggers: <EmptyFeaturePage data={data} feature="Triggers" />,
    approvals: <ApprovalsPage data={data} />,
    runtime: <RuntimePage data={data} />,
    activity: <ActivityPage data={data} />,
    "agent-detail": <AgentDetailPage data={data} name={agentName ?? ""} />,
  };

  return (
    <div className="agents-stage">
      <Header route={route} data={data} agentName={agentName} />
      {route === "dashboard" ? <PageNav /> : null}
      <main className={cx("agents-content", `is-${route}`)}>{page[route]}</main>
      <AgentsFooter />
    </div>
  );
}
