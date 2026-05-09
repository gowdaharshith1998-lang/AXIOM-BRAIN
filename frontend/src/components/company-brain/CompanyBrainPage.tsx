import { type CSSProperties, type FormEvent, useEffect, useMemo, useState } from "react";

import { Brain } from "@/components/Brain";
import { CommandPalette } from "@/components/CommandPalette";
import {
  FALLBACK_QUERIES,
  FILTERS,
  QUICK_QUERIES,
  buildCompanyBrainViewModel,
} from "@/components/company-brain/companyBrainData";
import { CompanyBrainGraph } from "@/components/company-brain/CompanyBrainGraph";
import type { BrainQueryRow, CompanyBrainCluster } from "@/components/company-brain/companyBrainTypes";
import { useBrainFocus } from "@/hooks/useBrainFocus";
import { useBrainStore } from "@/state/brain.store";
import "@/styles/company-brain.css";

const GRAPH_MODES = [
  ["Live Graph", "Real-time view"],
  ["Knowledge State", "Snapshot view"],
  ["Impact Analysis", "What-if simulation"],
  ["Skill Paths", "Execution paths"],
] as const;

const NAV_ITEMS = ["Graph", "Flow", "Knowledge", "Agents", "Governance", "Timeline", "Search", "Receipts", "Console"];
const BOTTOM_NAV = ["Graph", "Flow", "Governance", "Timeline", "Search", "Receipts", "Agent Console"];
const INSPECTOR_TABS = ["Overview", "Connections", "Lineage", "Activity"] as const;

function nowTime(): string {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date());
}

export function CompanyBrainPage() {
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);
  const clusterHealth = useBrainStore((s) => s.clusterHealth);
  const agentActions = useBrainStore((s) => s.agentActions);
  const receipts = useBrainStore((s) => s.receipts);
  const connectionStatus = useBrainStore((s) => s.connectionStatus);
  const selectCluster = useBrainStore((s) => s.selectCluster);
  const { focus } = useBrainFocus();

  const viewModel = useMemo(
    () => buildCompanyBrainViewModel({ entities, edges, clusterHealth, agentActions, receipts, connectionStatus }),
    [agentActions, clusterHealth, connectionStatus, edges, entities, receipts],
  );

  const [query, setQuery] = useState("");
  const [recentQueries, setRecentQueries] = useState<BrainQueryRow[]>(viewModel.queries);
  const [selectedCluster, setSelectedCluster] = useState<CompanyBrainCluster>(
    () => viewModel.clusters.find((cluster) => cluster.id === "systems") ?? viewModel.clusters[0],
  );
  const [activeMode, setActiveMode] = useState("Live Graph");
  const [activeInspectorTab, setActiveInspectorTab] = useState<(typeof INSPECTOR_TABS)[number]>("Overview");
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [hoveredClusterId, setHoveredClusterId] = useState<string | null>(null);
  const [enabledFilters, setEnabledFilters] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(FILTERS.map((filter) => [filter, true])),
  );

  useEffect(() => {
    let cancelled = false;
    void fetch("http://127.0.0.1:8000/api/health")
      .then((res) => {
        if (!cancelled) setBackendAvailable(res.ok);
      })
      .catch(() => {
        if (!cancelled) setBackendAvailable(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const currentSelected =
    viewModel.clusters.find((cluster) => cluster.id === focus.clusterId) ??
    viewModel.clusters.find((cluster) => cluster.id === selectedCluster.id) ??
    selectedCluster;
  const hiddenFilters = useMemo(
    () => new Set(Object.entries(enabledFilters).filter(([, enabled]) => !enabled).map(([filter]) => filter)),
    [enabledFilters],
  );

  const chooseCluster = (cluster: CompanyBrainCluster) => {
    setSelectedCluster(cluster);
    selectCluster(cluster.id);
  };

  const submitQuery = async (event?: FormEvent<HTMLFormElement>, override?: string) => {
    event?.preventDefault();
    const text = (override ?? query).trim();
    if (!text) return;
    setQuery("");

    let response = "Local placeholder: no Company Brain query endpoint is available in this build.";
    try {
      const res = await fetch(`/api/entities/search?q=${encodeURIComponent(text)}&limit=3`);
      if (res.ok) {
        const results = (await res.json()) as unknown[];
        response = `Backend entity search returned ${results.length} result${results.length === 1 ? "" : "s"}.`;
      }
    } catch {
      response = "Local placeholder: backend search is unavailable.";
    }

    setRecentQueries((current) => [{ text, actor: "human" as const, time: nowTime(), response }, ...current].slice(0, 6));
  };

  return (
    <div className="company-brain-shell">
      <LeftNavRail />
      <main className="cb-workspace">
        <CompanyBrainHeader query={query} onQueryChange={setQuery} onSubmit={submitQuery} dataMode={viewModel.summary.dataMode} />
        <div className="cb-dashboard-grid">
          <LeftBrainPanel
            summary={viewModel.summary}
            activeMode={activeMode}
            onModeChange={setActiveMode}
            enabledFilters={enabledFilters}
            onToggleFilter={(filter) => setEnabledFilters((current) => ({ ...current, [filter]: !current[filter] }))}
          />
          <section className="cb-center-stage">
            <div className="cb-webgl-underlay">
              {backendAvailable ? <Brain /> : <div className="cb-webgl-empty">Studio API not connected</div>}
            </div>
            <CompanyBrainGraph
              clusters={viewModel.clusters}
              hiddenFilters={hiddenFilters}
              selectedId={currentSelected.id}
              hoveredId={hoveredClusterId}
              onSelect={chooseCluster}
              onHover={setHoveredClusterId}
            />
          </section>
          <EntityInspector cluster={currentSelected} activeTab={activeInspectorTab} onTabChange={setActiveInspectorTab} />
          <BottomBrainDock activity={viewModel.activity} queries={recentQueries.length ? recentQueries : FALLBACK_QUERIES} skills={viewModel.skills} />
        </div>
        <BottomStatusNav />
      </main>
      <CommandPalette />
    </div>
  );
}

function CompanyBrainHeader({
  query,
  onQueryChange,
  onSubmit,
  dataMode,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  onSubmit: (event?: FormEvent<HTMLFormElement>, override?: string) => void;
  dataMode: "real" | "fallback" | "mixed";
}) {
  return (
    <header className="cb-header">
      <div className="cb-brand">
        <div className="cb-logo" aria-hidden="true">⬡</div>
        <div className="cb-wordmark">AXIOM</div>
        <span className="cb-divider" />
        <span className="cb-product-name">Company Brain</span>
        <span className="cb-live-badge"><span className="cb-live-dot" />LIVE</span>
      </div>
      <form className="cb-ask-bar" onSubmit={(event) => void onSubmit(event)}>
        <label className="sr-only" htmlFor="company-brain-query">Ask the Company Brain</label>
        <span className="cb-search-icon" aria-hidden="true">⌕</span>
        <input
          id="company-brain-query"
          value={query}
          onChange={(event) => onQueryChange(event.currentTarget.value)}
          placeholder="Ask the Company Brain anything..."
        />
        <span className="cb-kbd">⌘ K</span>
        <div className="cb-query-chips">
          {QUICK_QUERIES.slice(0, 4).map((item) => (
            <button key={item} type="button" onClick={() => void onSubmit(undefined, item)}>
              {item}
            </button>
          ))}
        </div>
      </form>
      <div className="cb-header-actions">
        <span className="cb-governance">▣ Governance checked ✓</span>
        <span className="cb-data-mode">{dataMode} data</span>
        <button type="button" title="Help">?</button>
        <button type="button" title="Notifications">♢</button>
        <button type="button" className="cb-avatar" title="Account">AK</button>
      </div>
    </header>
  );
}

function LeftNavRail() {
  return (
    <aside className="cb-nav-rail" aria-label="Company Brain navigation">
      <div className="cb-nav-logo">⬡</div>
      <nav>
        {NAV_ITEMS.map((item, index) => (
          <button key={item} type="button" className={index === 0 ? "is-active" : ""} title={item} aria-label={item}>
            {item.slice(0, 1)}
          </button>
        ))}
      </nav>
      <div className="cb-user-pill">OP<span /></div>
    </aside>
  );
}

function LeftBrainPanel({
  summary,
  activeMode,
  onModeChange,
  enabledFilters,
  onToggleFilter,
}: {
  summary: { entities: number; relationships: number; eventsPerMinute: number; confidenceAvg: number; health: number };
  activeMode: string;
  onModeChange: (mode: string) => void;
  enabledFilters: Record<string, boolean>;
  onToggleFilter: (filter: string) => void;
}) {
  return (
    <aside className="cb-left-column">
      <section className="cb-panel">
        <h2>Graph Overview</h2>
        <Metric label="Entities" value={summary.entities.toLocaleString()} delta="↑ 8.1%" />
        <Metric label="Relationships" value={summary.relationships.toLocaleString()} delta="↑ 11.3%" />
        <Metric label="Events / min" value={String(summary.eventsPerMinute)} delta="Live ingestion" />
        <Metric label="Confidence Avg" value={`${summary.confidenceAvg.toFixed(1)}%`} delta="↑ 2.7%" />
      </section>

      <section className="cb-panel">
        <h2>Graph Mode</h2>
        <div className="cb-mode-list">
          {GRAPH_MODES.map(([mode, caption]) => (
            <button key={mode} type="button" className={activeMode === mode ? "is-active" : ""} onClick={() => onModeChange(mode)}>
              <span>{mode}</span>
              <small>{caption}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="cb-panel cb-filters">
        <div className="cb-panel-title-row">
          <h2>Legend & Filters</h2>
          <button type="button">Clear</button>
        </div>
        {FILTERS.map((filter) => (
          <label key={filter}>
            <span>{filter}</span>
            <input type="checkbox" checked={enabledFilters[filter]} onChange={() => onToggleFilter(filter)} />
          </label>
        ))}
      </section>

      <section className="cb-panel cb-health">
        <h2>Graph Health</h2>
        <strong>{summary.health}%</strong>
        <div><span style={{ width: `${summary.health}%` }} /></div>
        <p>Live ingestion</p>
        <b>3,842 events/min</b>
        <p>Last updated</p>
        <b>2s ago</b>
      </section>
    </aside>
  );
}

function Metric({ label, value, delta }: { label: string; value: string; delta: string }) {
  return (
    <div className="cb-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{delta}</em>
    </div>
  );
}

function EntityInspector({
  cluster,
  activeTab,
  onTabChange,
}: {
  cluster: CompanyBrainCluster;
  activeTab: (typeof INSPECTOR_TABS)[number];
  onTabChange: (tab: (typeof INSPECTOR_TABS)[number]) => void;
}) {
  const isSystems = cluster.id === "systems";
  const title = isSystems ? "Payments Service" : cluster.label;
  const subtitle = isSystems ? "payments-service" : `${cluster.id}-cluster`;
  const connections = isSystems
    ? ["Stripe Billing API", "Billing Team", "Invoice Paid Decision", "Billing DB (Postgres)", "PAY-1234: Refund flow bug"]
    : cluster.connections;

  return (
    <aside className="cb-inspector cb-panel">
      <div className="cb-inspector-heading">
        <span className="cb-inspector-icon" style={{ "--cluster-color": cluster.color } as CSSProperties}>{cluster.icon.slice(0, 1).toUpperCase()}</span>
        <div>
          <div className="cb-inspector-title-row">
            <h2>{title}</h2>
            <span>{cluster.id === "systems" ? "System" : cluster.label}</span>
            <b>Active</b>
          </div>
          <p>{subtitle}</p>
          <p>Owned by {cluster.owner}</p>
        </div>
      </div>

      <div className="cb-tabs">
        {INSPECTOR_TABS.map((tab) => (
          <button key={tab} type="button" className={activeTab === tab ? "is-active" : ""} onClick={() => onTabChange(tab)}>
            {tab}
          </button>
        ))}
      </div>

      <p className="cb-description">{isSystems ? "Handles payment processing, invoicing, subscriptions, and refunds." : cluster.description}</p>
      <dl className="cb-inspector-facts">
        <div><dt>Owner</dt><dd>{isSystems ? "Maya Patel @maya" : cluster.owner}</dd></div>
        <div><dt>Team</dt><dd>{cluster.team}</dd></div>
        <div><dt>Criticality</dt><dd><span className={`cb-criticality cb-${cluster.criticality.toLowerCase()}`}>{cluster.criticality}</span></dd></div>
        <div><dt>Confidence</dt><dd><span className="cb-confidence"><b style={{ width: `${cluster.confidence}%` }} />{cluster.confidence}%</span></dd></div>
      </dl>

      <section className="cb-trust">
        <h3>Trust & Governance</h3>
        {[
          ["Policy Status", "Compliant"],
          ["Signed Receipt", "Verified"],
          ["Merkle Root", "a1b2c3d4...f9e8d7c6"],
          ["Proof", "View Merkle Proof"],
        ].map(([label, value]) => (
          <div key={label}><span>{label}</span><b>{value}</b></div>
        ))}
      </section>

      <section className="cb-connections">
        <h3>Connected Entities ({connections.length})</h3>
        {connections.map((item) => (
          <button key={item} type="button">
            <span>{item.slice(0, 1)}</span>
            {item}
            <em>⌄</em>
          </button>
        ))}
      </section>

      <section className="cb-ai-execution">
        <h3>This Graph Powers AI Execution</h3>
        <div><b>Pre-execution context</b><span>Agents pull verified knowledge before acting.</span></div>
        <div><b>Governed by policy</b><span>Every action is checked, signed, and auditable.</span></div>
        <div><b>Executable skills</b><span>Structured knowledge becomes agent skills.</span></div>
      </section>
    </aside>
  );
}

function BottomBrainDock({
  activity,
  queries,
  skills,
}: {
  activity: { label: string; detail: string; time: string; tone: string }[];
  queries: BrainQueryRow[];
  skills: { skill: string; status: string; time: string }[];
}) {
  return (
    <section className="cb-bottom-dock">
      <div className="cb-panel cb-list-panel">
        <h2>Live Activity Feed <span><span className="cb-live-dot" />Live</span></h2>
        {activity.map((item) => (
          <div key={`${item.label}-${item.time}`} className="cb-row">
            <i className={`tone-${item.tone}`}>{item.label.slice(0, 1)}</i>
            <span>{item.label}</span>
            <em>{item.detail}</em>
            <time>{item.time}</time>
          </div>
        ))}
      </div>
      <div className="cb-panel cb-list-panel">
        <h2>Recent Queries</h2>
        {queries.slice(0, 5).map((item) => (
          <div key={`${item.text}-${item.time}`} className="cb-row">
            <i>⌕</i>
            <span>{item.text}</span>
            <b>{item.actor}</b>
            <time>{item.time}</time>
          </div>
        ))}
      </div>
      <div className="cb-panel cb-list-panel cb-skills-panel">
        <h2>Agent Execution (Skills)</h2>
        {skills.map((item) => (
          <div key={`${item.skill}-${item.time}`} className="cb-row">
            <i>◎</i>
            <span>{item.skill}</span>
            <b className={item.status === "Blocked" ? "is-blocked" : ""}>{item.status}</b>
            <time>{item.time}</time>
          </div>
        ))}
      </div>
    </section>
  );
}

function BottomStatusNav() {
  return (
    <footer className="cb-bottom-nav">
      {BOTTOM_NAV.map((item, index) => (
        <button key={item} type="button" className={index === 0 ? "is-active" : ""}>
          {item}
        </button>
      ))}
      <span><span className="cb-live-dot" />All systems operational</span>
    </footer>
  );
}
