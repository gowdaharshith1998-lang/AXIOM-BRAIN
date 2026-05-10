import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import {
  acknowledgeWatchdogAlert,
  listWatchdogAlerts,
  resolveWatchdogAlert,
} from "@/lib/watchdogClient";
import type { BrainEvent } from "@/lib/websocket";
import type { WatchdogAlert } from "@/state/brain.store";

type Tab = "overview" | "policies" | "checks" | "receipts" | "lineage" | "audit-log";
type Accent = "cyan" | "blue" | "green" | "amber" | "red" | "purple";
type TableColumn = { key: string; label: string; className?: string };
type TableRow = Record<string, ReactNode>;

type GovernancePolicy = {
  id: string;
  name: string;
  type: string;
  scope: string;
  owner: string | null;
  team: string | null;
  mode: string | null;
  status: string;
  updated_at: string | null;
  source_id: string | null;
};

type GovernanceCheck = {
  id: string;
  entity: string;
  type: string;
  severity: string;
  result: string;
  last_run: string | null;
  owner: string;
  ingest_rate_per_min: number;
  total_entities: number;
};

type GovernanceReceipt = {
  id: string;
  receipt_id: string;
  receipt_type: string;
  action_id: string | null;
  decision: string | null;
  agent_name: string | null;
  signing_scheme: string | null;
  merkle_root: string | null;
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

type GovernanceSource = {
  id: string;
  source_type: string;
  display_name: string;
  connected: boolean;
  created_at: string | null;
  updated_at: string | null;
};

type GovernanceLineageEntity = {
  id: string;
  name: string;
  type: string;
  cluster_id: string | null;
  updated_at: string | null;
};

type GovernanceLineageEdge = {
  id: string;
  source_id: string;
  target_id: string;
  relationship: string;
  created_at: string | null;
};

type GovernanceSnapshot = {
  generated_at: string;
  summary: {
    policy_count: number;
    active_policy_count: number;
    check_count: number;
    healthy_check_count: number;
    degraded_check_count: number;
    critical_check_count: number;
    receipt_count: number;
    signed_receipt_count: number;
    action_count: number;
    denied_action_count: number;
    current_merkle_root: string | null;
    graph_entity_count: number;
    graph_edge_count: number;
    source_count: number;
    latest_event_at: number | null;
    current_seq: number;
    generated_at_ms: number;
  };
  policies: GovernancePolicy[];
  checks: GovernanceCheck[];
  receipts: GovernanceReceipt[];
  audit_events: GovernanceAuditEvent[];
  sources: GovernanceSource[];
  lineage: {
    entities: GovernanceLineageEntity[];
    edges: GovernanceLineageEdge[];
  };
};

const tabs: Array<{ id: Tab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "policies", label: "Policies" },
  { id: "checks", label: "Checks" },
  { id: "receipts", label: "Receipts" },
  { id: "lineage", label: "Lineage" },
  { id: "audit-log", label: "Audit Log" },
];

async function fetchGovernanceSnapshot(): Promise<GovernanceSnapshot> {
  const response = await fetch("/api/governance");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as GovernanceSnapshot;
}

function formatNumber(value: number | null | undefined) {
  return new Intl.NumberFormat().format(value ?? 0);
}

function formatPercent(numerator: number, denominator: number) {
  if (denominator <= 0) return "0%";
  return `${Math.round((numerator / denominator) * 100)}%`;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleString();
}

function formatEventTime(event: GovernanceAuditEvent) {
  if (event.timestamp) return formatDate(event.timestamp);
  if (event.timestamp_ms) return new Date(event.timestamp_ms).toLocaleString();
  return "Not recorded";
}

function shortHash(value: string | null | undefined) {
  if (!value) return "Not recorded";
  if (value.length <= 16) return value;
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

function recorded(value: string | null | undefined) {
  return value && value.trim() ? value : "Not recorded";
}

function titleCase(value: string | null | undefined) {
  return recorded(value)
    .split(/[_\s-]+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function resultTone(value: string | null | undefined): Accent {
  const normalized = (value || "").toLowerCase();
  if (["critical", "failed", "fail", "deny", "denied", "unsigned"].includes(normalized)) return "red";
  if (["degraded", "warning", "correct"].includes(normalized)) return "amber";
  if (["healthy", "allow", "allowed", "signed", "recorded", "active"].includes(normalized)) return "green";
  return "blue";
}

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function Icon({ name, className = "" }: { name: string; className?: string }) {
  const common = { stroke: "currentColor", strokeWidth: 1.75, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" className={cx("h-5 w-5", className)} aria-hidden="true">
      {name === "shield" && <path {...common} d="M12 3.5 19 6v5.5c0 4.2-2.7 7.3-7 9-4.3-1.7-7-4.8-7-9V6l7-2.5Zm-3 8 2 2 4-5" />}
      {name === "policy" && <path {...common} d="M7 3h8l3 3v15H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm8 0v4h4M8 11h8M8 15h6" />}
      {name === "warning" && <path {...common} d="m12 3 9 16H3L12 3Zm0 6v4m0 4h.01" />}
      {name === "database" && <path {...common} d="M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3Zm0 0v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />}
      {name === "check" && <path {...common} d="M20 6 9 17l-5-5" />}
      {name === "x" && <path {...common} d="M6 6l12 12M18 6 6 18" />}
      {name === "link" && <path {...common} d="M10 13a5 5 0 0 0 7.1 0l1.4-1.4a5 5 0 0 0-7.1-7.1L10.5 5M14 11a5 5 0 0 0-7.1 0l-1.4 1.4a5 5 0 0 0 7.1 7.1l.9-.9" />}
      {name === "lock" && <path {...common} d="M7 11V8a5 5 0 0 1 10 0v3M6 11h12v10H6V11Zm6 4v2" />}
      {name === "clock" && <path {...common} d="M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />}
      {name === "receipt" && <path {...common} d="M7 3h10v18l-2-1.2-2 1.2-2-1.2-2 1.2-2-1.2V3Zm3 5h4m-4 4h4m-4 4h2" />}
      {name === "target" && <path {...common} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-4a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-4a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" />}
      {name === "cube" && <path {...common} d="m12 3 7 4v10l-7 4-7-4V7l7-4Zm0 8 7-4M12 11 5 7m7 4v10" />}
      {name === "download" && <path {...common} d="M12 4v10m0 0 4-4m-4 4-4-4M4 20h16" />}
      {name === "search" && <path {...common} d="m21 21-4.5-4.5M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />}
      {name === "filter" && <path {...common} d="M4 5h16l-6 7v5l-4 2v-7L4 5Z" />}
      {name === "menu" && <path {...common} d="M5 7h14M5 12h14M5 17h14" />}
      {name === "external" && <path {...common} d="M14 4h6v6m0-6-9 9M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5" />}
      {name === "user" && <path {...common} d="M12 12.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7 8a7 7 0 0 0-14 0" />}
      {name === "code" && <path {...common} d="m9 18-6-6 6-6m6 0 6 6-6 6" />}
      {name === "globe" && <path {...common} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-8-9h16M12 3c2.3 2.5 3.5 5.5 3.5 9S14.3 18.5 12 21c-2.3-2.5-3.5-5.5-3.5-9S9.7 5.5 12 3Z" />}
      {name === "activity" && <path {...common} d="M3 12h4l2-6 4 12 2-6h6" />}
      {name === "spark" && <path {...common} d="M12 2v5m0 10v5M4.2 4.2l3.5 3.5m8.6 8.6 3.5 3.5M2 12h5m10 0h5M4.2 19.8l3.5-3.5m8.6-8.6 3.5-3.5" />}
    </svg>
  );
}

function HexIcon({ icon, accent = "cyan" }: { icon: string; accent?: Accent }) {
  return (
    <div className={cx("gov-hex", `gov-${accent}`)}>
      <Icon name={icon} />
    </div>
  );
}

function StatusPill({ children, tone = "green" }: { children: ReactNode; tone?: Accent }) {
  return <span className={cx("gov-pill", `gov-${tone}`)}>{children}</span>;
}

function severityTone(severity: string): Accent {
  if (severity === "critical") return "red";
  if (severity === "warning") return "amber";
  return "blue";
}

function Panel({ title, action, children, className }: { title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("gov-panel", className)}>
      <div className="gov-panel-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function KpiCard({
  title,
  value,
  detail,
  accent = "cyan",
  icon = "shield",
}: {
  title: string;
  value: string;
  detail: string;
  accent?: Accent;
  icon?: string;
}) {
  return (
    <div className={cx("gov-kpi", `gov-${accent}`)}>
      <div>
        <div className="gov-kpi-title">{title}</div>
        <div className="gov-kpi-value">{value}</div>
        <div className="gov-kpi-detail">{detail}</div>
      </div>
      <HexIcon icon={icon} accent={accent} />
    </div>
  );
}

function ProgressRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="gov-progress-row">
      <span>{label}</span>
      <div className="gov-progress-track">
        <span style={{ width: `${value}%` }} />
      </div>
      <strong>{value}%</strong>
    </div>
  );
}

function Donut({ accent = "blue", center, labels }: { accent?: Accent; center: ReactNode; labels?: Array<[string, string]> }) {
  return (
    <div className="gov-donut-wrap">
      <div className={cx("gov-donut", `gov-${accent}`)}><span>{center}</span></div>
      {labels ? (
        <div className="gov-donut-legend">
          {labels.map(([label, value]) => (
            <div key={label}><span />{label}<strong>{value}</strong></div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function GovernanceTable({
  columns,
  rows,
  selectedIndex = -1,
  emptyMessage = "No records found.",
}: {
  columns: TableColumn[];
  rows: TableRow[];
  selectedIndex?: number;
  emptyMessage?: string;
}) {
  return (
    <div className="gov-table" style={{ "--cols": columns.length } as CSSProperties}>
      <div className="gov-table-header">
        {columns.map((col) => <span key={col.key} className={col.className}>{col.label}</span>)}
      </div>
      {rows.length === 0 ? <div className="gov-table-row"><span className="gov-muted">{emptyMessage}</span></div> : null}
      {rows.map((row, rowIndex) => (
        <div key={rowIndex} className={cx("gov-table-row", rowIndex === selectedIndex && "is-selected")}>
          {columns.map((col) => <span key={col.key} className={col.className}>{row[col.key]}</span>)}
        </div>
      ))}
    </div>
  );
}

function SearchAndFilters({ placeholder, dense = false }: { placeholder: string; dense?: boolean }) {
  return (
    <div className={cx("gov-filters", dense && "is-dense")}>
      <label className="gov-search"><Icon name="search" /> <input placeholder={placeholder} /></label>
      <button type="button">Scope <strong>All</strong></button>
      <button type="button">Status <strong>All</strong></button>
      <button type="button">Category <strong>All</strong></button>
      <button type="button"><Icon name="filter" /> More Filters</button>
      {dense ? <button type="button"><Icon name="download" /> Export</button> : <button type="button" aria-label="List"><Icon name="menu" /></button>}
    </div>
  );
}

function OverviewPage({ snapshot }: { snapshot: GovernanceSnapshot }) {
  const summary = snapshot.summary;
  const healthyPct = summary.check_count ? Math.round((summary.healthy_check_count / summary.check_count) * 100) : 0;
  const signedPct = summary.receipt_count ? Math.round((summary.signed_receipt_count / summary.receipt_count) * 100) : 0;
  const allowedPct = summary.action_count ? Math.round(((summary.action_count - summary.denied_action_count) / summary.action_count) * 100) : 0;
  const policyRows = snapshot.policies.slice(0, 6).map((policy) => ({
    name: <span className="gov-name-cell"><Icon name="policy" />{policy.name}</span>,
    scope: <StatusPill tone="blue">{titleCase(policy.scope)}</StatusPill>,
    status: <StatusPill tone={resultTone(policy.status)}>{titleCase(policy.status)}</StatusPill>,
    updated: formatDate(policy.updated_at),
  }));
  const receiptRowsPreview = snapshot.receipts.slice(0, 5).map((receipt) => ({
    entity: recorded(receipt.agent_name || receipt.action_id),
    action: titleCase(receipt.decision || receipt.receipt_type),
    policy: receipt.receipt_type,
    status: <StatusPill tone={receipt.signed ? "green" : "red"}>{receipt.signed ? "Signed" : "Unsigned"}</StatusPill>,
    time: formatDate(receipt.created_at),
  }));
  return (
    <>
      <div className="gov-grid overview-top">
        <Panel title="Governance Health">
          <div className="gov-health">
            <div>
              <div className="gov-hero-metric">{healthyPct}%</div>
              <div className="gov-hero-label">{summary.healthy_check_count} of {summary.check_count} checks healthy</div>
            </div>
            <HexIcon icon="shield" accent="cyan" />
          </div>
          <ProgressRow label="Cluster Health" value={healthyPct} />
          <ProgressRow label="Signed Receipts" value={signedPct} />
          <ProgressRow label="Allowed Actions" value={allowedPct} />
          <ProgressRow label="Active Policies" value={summary.policy_count ? Math.round((summary.active_policy_count / summary.policy_count) * 100) : 0} />
          <div className="gov-muted mt-6">Last updated: {formatDate(snapshot.generated_at)}</div>
        </Panel>
        <Panel title="Recorded Governance Totals">
          <div className="gov-grid policies-kpis">
            <KpiCard title="Policies" value={formatNumber(summary.policy_count)} detail="Entities classified as policy or governance" accent="cyan" icon="policy" />
            <KpiCard title="Actions" value={formatNumber(summary.action_count)} detail="Persisted actions plus live MCP events" accent="blue" icon="activity" />
            <KpiCard title="Receipts" value={formatNumber(summary.receipt_count)} detail={`${formatNumber(summary.signed_receipt_count)} signed`} accent="purple" icon="receipt" />
          </div>
        </Panel>
        <Panel title="Policy Status">
          <GovernanceTable
            columns={[
              { key: "name", label: "Policy" },
              { key: "scope", label: "Scope" },
              { key: "status", label: "Status" },
              { key: "updated", label: "Updated" },
            ]}
            rows={policyRows}
            emptyMessage="No policy or governance entities are recorded."
          />
          <div className="gov-mini-summary"><span>Total Policies<strong>{formatNumber(summary.policy_count)}</strong></span><span>Active<strong className="text-[#1cf4a6]">{formatNumber(summary.active_policy_count)}</strong></span><span>Sources<strong>{formatNumber(summary.source_count)}</strong></span></div>
        </Panel>
      </div>
      <div className="gov-grid overview-mid">
        <Panel title="Recent Receipts">
          <GovernanceTable
            columns={[
              { key: "entity", label: "Entity" },
              { key: "action", label: "Action" },
              { key: "policy", label: "Policy" },
              { key: "status", label: "Status" },
              { key: "time", label: "Time" },
            ]}
            rows={receiptRowsPreview}
            emptyMessage="No receipts are recorded."
          />
        </Panel>
        <Panel title="Merkle Root">
          <div className="gov-merkle-card">
            <div className="gov-cube-art"><Icon name="cube" /></div>
            <div>
              <span>Current Merkle Root</span>
              <strong>{shortHash(summary.current_merkle_root)}</strong>
              <div className="gov-two-col"><span>Signed Receipts<br /><b>{formatNumber(summary.signed_receipt_count)}</b></span><span>Total Receipts<br /><b>{formatNumber(summary.receipt_count)}</b></span></div>
              <span>Source<br /><b>receipts table</b></span>
            </div>
          </div>
          <button type="button" className="gov-wide-button">Current Sequence {formatNumber(summary.current_seq)}</button>
        </Panel>
      </div>
    </>
  );
}

function PoliciesPage({ snapshot }: { snapshot: GovernanceSnapshot }) {
  const rows = snapshot.policies.map((policy) => ({
    name: <span className="gov-name-cell"><Icon name="policy" />{policy.name}</span>,
    scope: <StatusPill tone="blue">{titleCase(policy.scope)}</StatusPill>,
    owner: <span>{recorded(policy.owner)}<small>{recorded(policy.team || policy.source_id)}</small></span>,
    mode: <StatusPill tone={policy.mode ? "green" : "blue"}>{titleCase(policy.mode || "recorded")}</StatusPill>,
    updated: formatDate(policy.updated_at),
    status: <StatusPill tone={resultTone(policy.status)}>{titleCase(policy.status)}</StatusPill>,
  }));
  const first = snapshot.policies[0];
  const byType = new Map<string, number>();
  snapshot.policies.forEach((policy) => byType.set(policy.type, (byType.get(policy.type) || 0) + 1));
  const categoryLabels = [...byType.entries()].slice(0, 5).map(([label, count]) => [titleCase(label), `${count}`] as [string, string]);
  return (
    <>
      <div className="gov-grid policies-kpis">
        <KpiCard title="Policy Entities" value={formatNumber(snapshot.summary.policy_count)} detail="From entities table" accent="cyan" icon="shield" />
        <KpiCard title="Active Policies" value={formatNumber(snapshot.summary.active_policy_count)} detail="Status not archived or inactive" accent="green" icon="shield" />
        <KpiCard title="Governance Sources" value={formatNumber(snapshot.summary.source_count)} detail="Connected source records" accent="blue" icon="database" />
        <Panel title="Policy Categories">
          <Donut
            center={<><strong>{formatNumber(byType.size)}</strong><span>Types</span></>}
            labels={categoryLabels.length ? categoryLabels : [["Recorded", "0"]]}
          />
        </Panel>
      </div>
      <SearchAndFilters placeholder="Search policies..." />
      <div className="gov-grid policies-main">
        <Panel title="Policy Registry">
          <GovernanceTable
            columns={[
              { key: "name", label: "Policy Name" },
              { key: "scope", label: "Scope" },
              { key: "owner", label: "Owner" },
              { key: "mode", label: "Enforcement Mode" },
              { key: "updated", label: "Last Updated" },
              { key: "status", label: "Status" },
            ]}
            rows={rows}
            emptyMessage="No policy or governance entities are recorded."
          />
          <div className="gov-pagination">Showing {formatNumber(rows.length)} of {formatNumber(snapshot.summary.policy_count)} policy records</div>
        </Panel>
        <div className="gov-side-stack">
          <Panel title="Policy Details">
            {first ? (
              <>
                <div className="gov-detail-title"><HexIcon icon="database" accent="blue" /><div><strong>{first.name}</strong><span>{titleCase(first.type)} · {titleCase(first.status)}</span></div><StatusPill tone={resultTone(first.status)}>{titleCase(first.status)}</StatusPill></div>
                <DetailRows rows={[["Owner", recorded(first.owner)], ["Team", recorded(first.team)], ["Scope", titleCase(first.scope)], ["Mode", titleCase(first.mode || "recorded")], ["Last Updated", formatDate(first.updated_at)]]} />
                <p className="gov-detail-copy">This detail panel is populated directly from the selected entity record.</p>
              </>
            ) : <p className="gov-muted">No policy record is available.</p>}
          </Panel>
          <Panel title="Policy Status Distribution">
            <Donut center={<><strong>{formatNumber(snapshot.summary.policy_count)}</strong><span>Policies</span></>} accent="amber" labels={[[ "Active", `${snapshot.summary.active_policy_count}` ], [ "Other", `${Math.max(snapshot.summary.policy_count - snapshot.summary.active_policy_count, 0)}` ]]} />
          </Panel>
        </div>
      </div>
    </>
  );
}

function ChecksPage({ snapshot }: { snapshot: GovernanceSnapshot }) {
  const rows = snapshot.checks.map((check) => ({
    entity: <span className="gov-name-cell"><Icon name="database" />{check.entity}</span>,
    type: titleCase(check.type),
    severity: <span className={cx("gov-dot-label", check.severity.toLowerCase())}>{titleCase(check.severity)}</span>,
    result: <StatusPill tone={resultTone(check.result)}>{titleCase(check.result)}</StatusPill>,
    lastRun: formatDate(check.last_run),
    owner: check.owner,
  }));
  const selected = snapshot.checks.find((check) => check.result === "critical" || check.result === "degraded") || snapshot.checks[0];
  return (
    <>
      <div className="gov-grid checks-kpis">
        <KpiCard title="Total Checks" value={formatNumber(snapshot.summary.check_count)} detail="Cluster health checks" accent="cyan" icon="shield" />
        <KpiCard title="Healthy" value={formatNumber(snapshot.summary.healthy_check_count)} detail={formatPercent(snapshot.summary.healthy_check_count, snapshot.summary.check_count)} accent="green" icon="check" />
        <KpiCard title="Degraded" value={formatNumber(snapshot.summary.degraded_check_count)} detail="Needs ingest activity" accent="amber" icon="warning" />
        <KpiCard title="Critical" value={formatNumber(snapshot.summary.critical_check_count)} detail="No recent ingest" accent="red" icon="x" />
        <KpiCard title="Graph Entities" value={formatNumber(snapshot.summary.graph_entity_count)} detail={`${formatNumber(snapshot.summary.graph_edge_count)} edges`} accent="blue" icon="cube" />
      </div>
      <div className="gov-grid checks-main">
        <Panel title="Checks Queue" action={<StatusPill>Live</StatusPill>}>
          <div className="gov-table-tools"><button type="button"><Icon name="filter" /> Filters</button><label className="gov-search"><Icon name="search" /><input placeholder="Search checks..." /></label></div>
          <GovernanceTable
            columns={[
              { key: "entity", label: "Entity" },
              { key: "type", label: "Check Type" },
              { key: "severity", label: "Severity" },
              { key: "result", label: "Result" },
              { key: "lastRun", label: "Last Run" },
              { key: "owner", label: "Owner" },
            ]}
            rows={rows}
            emptyMessage="No cluster health checks are available."
          />
          <div className="gov-pagination">Showing {formatNumber(rows.length)} recorded checks</div>
        </Panel>
        <Panel title="Check Details">
          {selected ? (
            <>
              <div className="gov-detail-status"><StatusPill tone={resultTone(selected.result)}>{titleCase(selected.result)}</StatusPill><span>Check ID: {selected.id}</span></div>
              <h3 className="gov-detail-heading">{selected.entity}</h3>
              <DetailRows rows={[["Check Type", titleCase(selected.type)], ["Total Entities", formatNumber(selected.total_entities)], ["Ingest Rate / Min", formatNumber(selected.ingest_rate_per_min)], ["Last Ingest", formatDate(selected.last_run)], ["Owner", selected.owner]]} />
            </>
          ) : <p className="gov-muted">No check record is available.</p>}
        </Panel>
        <Panel title="Recent Check Events" action={<StatusPill>Live</StatusPill>}>
          <Timeline items={snapshot.checks.map((check) => `${titleCase(check.result)} · ${check.entity}`)} />
        </Panel>
      </div>
    </>
  );
}

function ReceiptsPage({ snapshot }: { snapshot: GovernanceSnapshot }) {
  const rows = snapshot.receipts.map((receipt) => ({
    entity: <span className="gov-name-cell"><Icon name="cube" />{recorded(receipt.agent_name || receipt.action_id)}</span>,
    action: titleCase(receipt.decision || receipt.receipt_type),
    policy: receipt.receipt_type,
    signedBy: recorded(receipt.signing_scheme),
    status: <StatusPill tone={receipt.signed ? "green" : "red"}>{receipt.signed ? "Signed" : "Unsigned"}</StatusPill>,
    timestamp: formatDate(receipt.created_at),
    id: shortHash(receipt.receipt_id),
  }));
  const first = snapshot.receipts[0];
  return (
    <>
      <div className="gov-grid receipts-kpis">
        <KpiCard title="Receipts Recorded" value={formatNumber(snapshot.summary.receipt_count)} detail="Rows in receipts table" accent="blue" icon="receipt" />
        <KpiCard title="Signed Receipts" value={formatNumber(snapshot.summary.signed_receipt_count)} detail={formatPercent(snapshot.summary.signed_receipt_count, snapshot.summary.receipt_count)} accent="green" icon="shield" />
        <KpiCard title="Current Merkle Root" value={shortHash(snapshot.summary.current_merkle_root)} detail="Latest recorded root" accent="purple" icon="cube" />
        <KpiCard title="Actions Recorded" value={formatNumber(snapshot.summary.action_count)} detail="Actions plus live MCP events" accent="blue" icon="clock" />
      </div>
      <div className="gov-grid receipts-main">
        <Panel title="Receipts Ledger">
          <SearchAndFilters placeholder="Search receipts..." dense />
          <GovernanceTable
            columns={[
              { key: "entity", label: "Entity" },
              { key: "action", label: "Action" },
              { key: "policy", label: "Policy" },
              { key: "signedBy", label: "Signed By" },
              { key: "status", label: "Verification Status" },
              { key: "timestamp", label: "Timestamp" },
              { key: "id", label: "Receipt ID" },
            ]}
            rows={rows}
            emptyMessage="No receipts are recorded."
          />
          <div className="gov-pagination">Showing {formatNumber(rows.length)} of {formatNumber(snapshot.summary.receipt_count)} receipts</div>
        </Panel>
        <Panel title="Receipt Details" action={first ? <StatusPill tone={first.signed ? "green" : "red"}>{first.signed ? "Signed" : "Unsigned"}</StatusPill> : null}>
          {first ? (
            <>
              <DetailRows rows={[["Receipt ID", first.receipt_id], ["Action ID", recorded(first.action_id)], ["Decision", titleCase(first.decision)], ["Signing Scheme", recorded(first.signing_scheme)], ["Merkle Root", shortHash(first.merkle_root)], ["Created At", formatDate(first.created_at)]]} />
              <div className="gov-lineage-mini"><Icon name="receipt" /><span /><Icon name="activity" /><span /><Icon name="shield" /><span /><Icon name="cube" /></div>
            </>
          ) : <p className="gov-muted">No receipt record is available.</p>}
        </Panel>
      </div>
    </>
  );
}

function LineagePage({ snapshot }: { snapshot: GovernanceSnapshot }) {
  const edgeRows = snapshot.lineage.edges.slice(0, 12).map((edge) => ({
    source: shortHash(edge.source_id),
    relationship: edge.relationship,
    target: shortHash(edge.target_id),
    created: formatDate(edge.created_at),
  }));
  const entityRows = snapshot.lineage.entities.slice(0, 8).map((entity) => ({
    name: <span className="gov-name-cell"><Icon name="database" />{entity.name}</span>,
    type: titleCase(entity.type),
    cluster: recorded(entity.cluster_id),
    updated: formatDate(entity.updated_at),
  }));
  return (
    <>
      <div className="gov-lineage-controls">
        <button type="button">Source <strong>entities and edges tables</strong></button>
        <button type="button">Records <strong>{formatNumber(snapshot.summary.graph_entity_count)}</strong></button>
        <button type="button">Edges <strong>{formatNumber(snapshot.summary.graph_edge_count)}</strong></button>
      </div>
      <div className="gov-grid lineage-kpis">
        <KpiCard title="Entities" value={formatNumber(snapshot.summary.graph_entity_count)} detail="Stored graph nodes" accent="green" icon="shield" />
        <KpiCard title="Edges" value={formatNumber(snapshot.summary.graph_edge_count)} detail="Stored graph relationships" accent="cyan" icon="target" />
        <KpiCard title="Sources" value={formatNumber(snapshot.summary.source_count)} detail="Rows in sources table" accent="amber" icon="database" />
        <KpiCard title="Recent Entities" value={formatNumber(snapshot.lineage.entities.length)} detail="Shown by updated_at" accent="purple" icon="target" />
      </div>
      <div className="gov-grid lineage-main">
        <Panel title={`Source Systems (${snapshot.sources.length})`}>
          <div className="gov-source-list">
            {snapshot.sources.length ? snapshot.sources.map((source, index) => (
              <div key={source.id} className={index === 0 ? "is-active" : ""}><Icon name="database" /><strong>{source.display_name}</strong><span>{source.source_type}</span><small>{source.connected ? "connected" : "not connected"}</small><small>Updated {formatDate(source.updated_at)}</small></div>
            )) : <p className="gov-muted">No source records are available.</p>}
          </div>
        </Panel>
        <Panel title="Recent Graph Edges">
          <GovernanceTable
            columns={[
              { key: "source", label: "Source" },
              { key: "relationship", label: "Relationship" },
              { key: "target", label: "Target" },
              { key: "created", label: "Created" },
            ]}
            rows={edgeRows}
            emptyMessage="No graph edges are recorded."
          />
        </Panel>
        <div className="gov-side-stack">
          <Panel title="Recent Entities">
            <GovernanceTable
              columns={[
                { key: "name", label: "Entity" },
                { key: "type", label: "Type" },
                { key: "cluster", label: "Cluster" },
                { key: "updated", label: "Updated" },
              ]}
              rows={entityRows}
              emptyMessage="No entity records are available."
            />
          </Panel>
          <Panel title="Graph Summary">
            <DetailRows rows={[["Entity Count", formatNumber(snapshot.summary.graph_entity_count)], ["Edge Count", formatNumber(snapshot.summary.graph_edge_count)], ["Source Count", formatNumber(snapshot.summary.source_count)], ["Snapshot Time", formatDate(snapshot.generated_at)]]} />
          </Panel>
        </div>
      </div>
    </>
  );
}

function AuditLogPage({ snapshot }: { snapshot: GovernanceSnapshot }) {
  const rows = snapshot.audit_events.map((event) => ({
    timestamp: formatEventTime(event),
    actor: <span className="gov-name-cell"><Icon name={event.actor?.includes("@") ? "user" : "code"} />{recorded(event.actor)}</span>,
    action: recorded(event.action),
    entity: recorded(event.entity),
    category: <StatusPill tone={event.category === "mcp_event" ? "cyan" : "blue"}>{titleCase(event.category)}</StatusPill>,
    result: <StatusPill tone={resultTone(event.result)}>{titleCase(event.result)}</StatusPill>,
    source: event.source,
  }));
  const first = snapshot.audit_events[0];
  return (
    <>
      <div className="gov-grid audit-kpis">
        <KpiCard title="Total Events" value={formatNumber(snapshot.summary.action_count)} detail="Actions and MCP events" accent="blue" icon="receipt" />
        <KpiCard title="Denied Actions" value={formatNumber(snapshot.summary.denied_action_count)} detail="Decision or status is deny" accent="red" icon="x" />
        <KpiCard title="Shown Events" value={formatNumber(snapshot.audit_events.length)} detail="Most recent records" accent="green" icon="shield" />
        <KpiCard title="Current Sequence" value={formatNumber(snapshot.summary.current_seq)} detail="WebSocket broadcaster sequence" accent="purple" icon="activity" />
        <KpiCard title="Sources" value={formatNumber(snapshot.summary.source_count)} detail="Recorded source rows" accent="amber" icon="database" />
      </div>
      <div className="gov-audit-tabs">
        {["All Events", "Persisted Actions", "MCP Events"].map((item, index) => <button key={item} type="button" className={index === 0 ? "is-active" : ""}>{item}</button>)}
      </div>
      <SearchAndFilters placeholder="Search events, actors, entities, actions..." />
      <div className="gov-grid audit-main">
        <Panel title="Audit Events">
          <GovernanceTable
            columns={[
              { key: "timestamp", label: "Timestamp" },
              { key: "actor", label: "Actor" },
              { key: "action", label: "Action" },
              { key: "entity", label: "Entity" },
              { key: "category", label: "Category" },
              { key: "result", label: "Result" },
              { key: "source", label: "Source" },
            ]}
            rows={rows}
            emptyMessage="No action or MCP audit events are recorded."
          />
          <div className="gov-pagination">Showing {formatNumber(rows.length)} events</div>
        </Panel>
        <Panel title="Event Details">
          {first ? (
            <>
              <div className="gov-detail-status"><StatusPill tone={resultTone(first.result)}>{titleCase(first.result)}</StatusPill><span>{formatEventTime(first)}</span></div>
              <h3 className="gov-detail-heading">{recorded(first.action)}</h3>
              <p className="gov-muted">{titleCase(first.category)}</p>
              <DetailRows rows={[["Actor", recorded(first.actor)], ["Entity", recorded(first.entity)], ["Source", first.source], ["Result", titleCase(first.result)], ["Event ID", first.id]]} />
            </>
          ) : <p className="gov-muted">No event record is available.</p>}
        </Panel>
      </div>
    </>
  );
}

function DetailRows({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <div className="gov-detail-rows">
      {rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
    </div>
  );
}

function Timeline({ items, compact }: { items: string[]; compact?: boolean }) {
  return (
    <div className={cx("gov-timeline", compact && "is-compact")}>
      {items.map((item, index) => <div key={item}><span>{index + 1}</span><p>{item}</p></div>)}
    </div>
  );
}

function WatchdogFeedPanel() {
  const [alerts, setAlerts] = useState<WatchdogAlert[]>([]);
  const [resolving, setResolving] = useState<WatchdogAlert | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    listWatchdogAlerts().then(setAlerts).catch(() => setAlerts([]));
  }, []);

  useEffect(() => {
    function onBrainEvent(event: Event) {
      const detail = (event as CustomEvent<BrainEvent>).detail;
      if (!detail) return;
      const payload = detail.payload as WatchdogAlert;
      if (detail.type === "watchdog_alert_raised" && payload.alert_id) {
        setAlerts((current) => [payload, ...current.filter((alert) => alert.alert_id !== payload.alert_id)]);
      }
      if ((detail.type === "watchdog_alert_acknowledged" || detail.type === "watchdog_alert_resolved") && payload.alert_id) {
        setAlerts((current) =>
          current
            .map((alert) => (alert.alert_id === payload.alert_id ? payload : alert))
            .filter((alert) => alert.status === "open"),
        );
      }
    }
    window.addEventListener("axiom:brain-event", onBrainEvent);
    return () => window.removeEventListener("axiom:brain-event", onBrainEvent);
  }, []);

  async function acknowledge(alert: WatchdogAlert) {
    const updated = await acknowledgeWatchdogAlert(alert.alert_id);
    setAlerts((current) =>
      current
        .map((item) => (item.alert_id === alert.alert_id ? updated : item))
        .filter((item) => item.status === "open"),
    );
  }

  async function resolveCurrent(event: FormEvent) {
    event.preventDefault();
    if (!resolving) return;
    const updated = await resolveWatchdogAlert(resolving.alert_id, note);
    setAlerts((current) =>
      current
        .map((item) => (item.alert_id === resolving.alert_id ? updated : item))
        .filter((item) => item.status === "open"),
    );
    setResolving(null);
    setNote("");
  }

  return (
    <aside className="watchdog-feed-panel" aria-label="Watchdog feed">
      <div className="watchdog-feed-head">
        <h2>Watchdog</h2>
        <StatusPill tone={alerts.length ? "amber" : "green"}>{alerts.length ? `${alerts.length} open` : "Clear"}</StatusPill>
      </div>
      {alerts.length ? alerts.slice(0, 5).map((alert) => (
        <div className="watchdog-feed-row" key={alert.alert_id}>
          <StatusPill tone={severityTone(alert.severity)}>{titleCase(alert.severity)}</StatusPill>
          <p>{alert.reason}</p>
          <div>
            <button type="button" onClick={() => acknowledge(alert)}>Acknowledge</button>
            <button type="button" onClick={() => setResolving(alert)}>Resolve</button>
          </div>
        </div>
      )) : <p className="gov-muted">No open watchdog alerts.</p>}
      {resolving ? (
        <form className="watchdog-resolve-modal" aria-label="Resolve watchdog alert" onSubmit={resolveCurrent}>
          <h3>Resolve Alert</h3>
          <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Resolution note" />
          <button type="submit">Resolve</button>
          <button type="button" onClick={() => setResolving(null)}>Cancel</button>
        </form>
      ) : null}
    </aside>
  );
}

export function GovernancePage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab") as Tab | null;
  const activeTab = tabs.some((tab) => tab.id === requested) ? requested! : "overview";
  const [snapshot, setSnapshot] = useState<GovernanceSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchGovernanceSnapshot()
      .then((data) => {
        if (!cancelled) {
          setSnapshot(data);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load governance data");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const tabBody = useMemo(() => {
    if (error) {
      return <Panel title="Governance Data"><p className="gov-muted">Unable to load governance data: {error}</p></Panel>;
    }
    if (!snapshot) {
      return <Panel title="Governance Data"><p className="gov-muted">Loading recorded governance data...</p></Panel>;
    }
    if (activeTab === "overview") return <OverviewPage snapshot={snapshot} />;
    if (activeTab === "policies") return <PoliciesPage snapshot={snapshot} />;
    if (activeTab === "checks") return <ChecksPage snapshot={snapshot} />;
    if (activeTab === "receipts") return <ReceiptsPage snapshot={snapshot} />;
    if (activeTab === "lineage") return <LineagePage snapshot={snapshot} />;
    return <AuditLogPage snapshot={snapshot} />;
  }, [activeTab, error, snapshot]);

  return (
    <div className="governance-stage">
      <section className="governance-shell">
        <div className="governance-title">
          <Icon name="shield" className="h-9 w-9 text-[#b6c9ea]" />
          <h1>Governance</h1>
        </div>
        <WatchdogFeedPanel />
        <nav className="governance-tabs" aria-label="Governance sections">
          {tabs.map((tab) => (
            <button key={tab.id} type="button" className={activeTab === tab.id ? "is-active" : ""} onClick={() => setParams(tab.id === "overview" ? {} : { tab: tab.id })}>
              {tab.label}
            </button>
          ))}
        </nav>
        <div className="governance-body">
          {tabBody}
        </div>
      </section>
    </div>
  );
}
