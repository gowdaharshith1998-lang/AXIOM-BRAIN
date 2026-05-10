import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { getMcpStats, type MCPStats } from "@/lib/studioClient";
import { useBrainStore, type ClusterHealthSnapshot, type Edge, type Entity, type WardenInsight } from "@/state/brain.store";

type Tab = "overview" | "trends" | "risk" | "adoption" | "ai-impact";
type Accent = "blue" | "cyan" | "green" | "amber" | "red" | "purple";
type TimedPoint = { label: string; value: number };

const tabs: Array<{ id: Tab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "trends", label: "Trends" },
  { id: "risk", label: "Risk" },
  { id: "adoption", label: "Adoption" },
  { id: "ai-impact", label: "AI Impact" },
];

async function request<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function isDemo(item: { demo?: boolean } | undefined): boolean {
  return item?.demo === true;
}

function toDate(value: string | number | null | undefined): Date | null {
  if (typeof value === "number" && Number.isFinite(value)) return new Date(value);
  if (typeof value !== "string" || !value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  return value.toLocaleString();
}

function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  return `${value.toFixed(digits)}%`;
}

function titleForEntity(entity: Entity): string {
  for (const key of ["title", "name", "subject", "label", "file_path"]) {
    const value = entity.data?.[key];
    if (typeof value === "string" && value.trim()) return key === "file_path" ? (value.split("/").pop() ?? value) : value;
  }
  return entity.id;
}

function clusterLabel(clusterId: string | null | undefined): string {
  if (!clusterId) return "Unclassified";
  return clusterId.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function entityTimestamp(entity: Entity): Date | null {
  return toDate(entity.created_at) ?? toDate(entity.updated_at);
}

function groupByDay(dates: Array<Date | null>, days = 30): TimedPoint[] {
  const today = new Date();
  const start = new Date(today);
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - (days - 1));

  const buckets = new Map<string, number>();
  for (let i = 0; i < days; i++) {
    const day = new Date(start);
    day.setDate(start.getDate() + i);
    buckets.set(day.toISOString().slice(0, 10), 0);
  }

  for (const date of dates) {
    if (!date || date < start) continue;
    const key = date.toISOString().slice(0, 10);
    if (buckets.has(key)) buckets.set(key, (buckets.get(key) ?? 0) + 1);
  }

  return Array.from(buckets.entries()).map(([key, value]) => ({
    label: new Date(`${key}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    value,
  }));
}

function cumulative(points: TimedPoint[]): TimedPoint[] {
  let total = 0;
  return points.map((point) => {
    total += point.value;
    return { ...point, value: total };
  });
}

function hasChartData(points: TimedPoint[]): boolean {
  return points.some((point) => point.value > 0);
}

function Icon({ name, className = "" }: { name: string; className?: string }) {
  const common = { stroke: "currentColor", strokeWidth: 1.8, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" className={cx("ins-icon", className)} aria-hidden="true">
      {name === "insights" && <path {...common} d="M4 19V9m5 10V5m5 14v-7m5 7V8M3 19h18" />}
      {name === "calendar" && <path {...common} d="M7 3v4m10-4v4M4 8h16M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z" />}
      {name === "filter" && <path {...common} d="M4 5h16l-6.5 7.2V18l-3 1.5v-7.3L4 5Z" />}
      {name === "search" && <path {...common} d="m21 21-4.5-4.5M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />}
      {name === "shield" && <path {...common} d="m12 3 7 2.8v5.7c0 4.1-2.8 7.2-7 8.8-4.2-1.6-7-4.7-7-8.8V5.8L12 3Zm-3 8.5 2 2 4-5" />}
      {name === "bolt" && <path {...common} d="m13 2-8 12h6l-1 8 8-12h-6l1-8Z" />}
      {name === "bot" && <path {...common} d="M12 3v3m-5 5H5m14 0h-2M8 8h8a3 3 0 0 1 3 3v5a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4v-5a3 3 0 0 1 3-3Zm1 5h.01M15 13h.01" />}
      {name === "target" && <path {...common} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-4a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm3-8-3 3" />}
      {name === "warning" && <path {...common} d="m12 3 9 16H3L12 3Zm0 6v4m0 4h.01" />}
      {name === "users" && <path {...common} d="M16 11a4 4 0 1 0-4-4 4 4 0 0 0 4 4ZM8 13a3 3 0 1 0-3-3 3 3 0 0 0 3 3Zm8 1c-3.3 0-6 1.6-6 3.5V20h12v-2.5c0-1.9-2.7-3.5-6-3.5ZM8 14c-2.8 0-5 1.2-5 2.8V19h5" />}
      {name === "message" && <path {...common} d="M5 5h14v10H8l-3 4V5Zm4 4h6" />}
      {name === "brain" && <path {...common} d="M9 4a3 3 0 0 0-3 3v1a3 3 0 0 0-1 5.8V15a4 4 0 0 0 4 4h1V4H9Zm6 0a3 3 0 0 1 3 3v1a3 3 0 0 1 1 5.8V15a4 4 0 0 1-4 4h-1V4h1Z" />}
      {name === "arrow" && <path {...common} d="M5 12h13m-5-5 5 5-5 5" />}
      {name === "menu" && <path {...common} d="M12 5h.01M12 12h.01M12 19h.01" />}
      {name === "cube" && <path {...common} d="m12 3 7 4v10l-7 4-7-4V7l7-4Zm0 8 7-4M12 11 5 7m7 4v10" />}
      {name === "policy" && <path {...common} d="M7 3h8l3 3v15H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm8 0v4h4M8 12h8M8 16h5" />}
    </svg>
  );
}

function HexIcon({ icon, accent = "blue" }: { icon: string; accent?: Accent }) {
  return (
    <span className={cx("ins-hex", `ins-${accent}`)}>
      <Icon name={icon} />
    </span>
  );
}

function EmptyState({ children = "No real data available for this panel yet." }: { children?: React.ReactNode }) {
  return <div className="ins-empty">{children}</div>;
}

function Sparkline({ accent = "blue", points }: { accent?: Accent; points: TimedPoint[] }) {
  if (!hasChartData(points)) return <div className="ins-spark-empty">No data</div>;
  const values = points.map((point) => point.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const poly = values.map((value, index) => `${6 + index * (128 / Math.max(values.length - 1, 1))},${58 - ((value - min) / Math.max(max - min, 1)) * 42}`).join(" ");
  return (
    <svg className={cx("ins-spark", `ins-${accent}`)} viewBox="0 0 140 64" aria-hidden="true">
      <polyline points={`6,61 ${poly} 134,61`} fill="currentColor" opacity="0.12" />
      <polyline points={poly} fill="none" stroke="currentColor" strokeWidth="2.2" />
    </svg>
  );
}

function MiniLineChart({ accent = "blue", points }: { accent?: Accent; points: TimedPoint[] }) {
  if (!hasChartData(points)) return <EmptyState>No timestamped records in the selected range.</EmptyState>;
  const values = points.map((point) => point.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const poly = values.map((value, index) => `${54 + index * (450 / Math.max(values.length - 1, 1))},${168 - ((value - min) / Math.max(max - min, 1)) * 118}`).join(" ");
  const labels = points.filter((_, index) => index === 0 || index === Math.floor(points.length / 2) || index === points.length - 1);
  return (
    <div className={cx("ins-line-chart", `ins-${accent}`)}>
      <div className="ins-y-axis"><span>{formatNumber(max)}</span><span>{formatNumber(Math.round(max / 2))}</span><span>0</span></div>
      <svg viewBox="0 0 530 192" aria-hidden="true">
        <polyline points={`54,174 ${poly} 504,174`} fill="currentColor" opacity="0.13" />
        <polyline points={poly} fill="none" stroke="currentColor" strokeWidth="2.4" />
      </svg>
      <div className="ins-x-axis">{labels.map((point) => <span key={point.label}>{point.label}</span>)}</div>
    </div>
  );
}

function KpiCard({ title, value, detail, icon, accent = "blue", points }: { title: string; value: string; detail: string; icon: string; accent?: Accent; points?: TimedPoint[] }) {
  return (
    <section className={cx("ins-kpi", `ins-${accent}`)}>
      <div className="ins-kpi-copy">
        <div className="ins-panel-title">{title} <span>ⓘ</span></div>
        <div className="ins-kpi-value">{value}</div>
        <div className="ins-kpi-detail">{detail}</div>
      </div>
      <HexIcon icon={icon} accent={accent} />
      {points ? <Sparkline accent={accent} points={points} /> : null}
    </section>
  );
}

function Panel({ title, children, className, action }: { title: string; children: React.ReactNode; className?: string; action?: React.ReactNode }) {
  return (
    <section className={cx("ins-panel", className)}>
      <div className="ins-panel-head">
        <h2>{title} <span>ⓘ</span></h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function StatusPill({ children, tone = "green" }: { children: React.ReactNode; tone?: Accent }) {
  return <span className={cx("ins-pill", `ins-${tone}`)}>{children}</span>;
}

function HeaderTools({ timeRange, setTimeRange, dataAsOf }: { timeRange: string; setTimeRange: (value: string) => void; dataAsOf: string }) {
  return (
    <div className="ins-header-tools">
      <span>{dataAsOf}</span>
      <label className="ins-select">
        <span>Time Range</span>
        <select value={timeRange} onChange={(event) => setTimeRange(event.target.value)}>
          <option>Last 30 Days</option>
          <option>Last 7 Days</option>
        </select>
        <Icon name="calendar" />
      </label>
      <button type="button"><Icon name="filter" /> Filters</button>
    </div>
  );
}

function useRealInsightsData(timeRange: string) {
  const bootstrap = useBrainStore((s) => s.bootstrap);
  const setClusterHealth = useBrainStore((s) => s.setClusterHealth);
  const entitiesMap = useBrainStore((s) => s.entities);
  const edgesMap = useBrainStore((s) => s.edges);
  const clusterHealth = useBrainStore((s) => s.clusterHealth);
  const insights = useBrainStore((s) => s.insights);
  const receipts = useBrainStore((s) => s.receipts);
  const agentActions = useBrainStore((s) => s.agentActions);
  const [mcpStats, setMcpStats] = useState<MCPStats | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [entities, edges, health, mcp] = await Promise.all([
          request<Entity[]>("/api/entities"),
          request<Edge[]>("/api/edges"),
          request<Record<string, ClusterHealthSnapshot>>("/api/cluster_health").catch(() => ({})),
          getMcpStats().catch(() => null),
        ]);
        if (!active) return;
        bootstrap(entities, edges);
        setClusterHealth(health);
        setMcpStats(mcp);
        setLoadError(null);
      } catch (error) {
        if (active) setLoadError(error instanceof Error ? error.message : "Unable to load real insight data");
      }
    }
    void load();
    const id = window.setInterval(load, 30000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [bootstrap, setClusterHealth]);

  const days = timeRange === "Last 7 Days" ? 7 : 30;
  const entities = useMemo(() => Array.from(entitiesMap.values()), [entitiesMap]);
  const edges = useMemo(() => Array.from(edgesMap.values()), [edgesMap]);
  const realInsights = useMemo(() => insights.filter((item) => !isDemo(item)), [insights]);
  const realReceipts = useMemo(() => receipts.filter((item) => !isDemo(item)), [receipts]);
  const realAgentActions = useMemo(() => agentActions.filter((item) => !isDemo(item)), [agentActions]);

  const entityDaily = useMemo(() => groupByDay(entities.map(entityTimestamp), days), [entities, days]);
  const edgeDaily = useMemo(() => groupByDay(edges.map((edge) => toDate(edge.created_at)), days), [edges, days]);
  const insightDaily = useMemo(() => groupByDay(realInsights.map((insight) => toDate(insight.timestamp)), days), [realInsights, days]);
  const actionDaily = useMemo(() => groupByDay(realAgentActions.map((action) => toDate(action.timestamp)), days), [realAgentActions, days]);
  const receiptDaily = useMemo(() => groupByDay(realReceipts.map((receipt) => toDate(receipt.timestamp)), days), [realReceipts, days]);

  return {
    entities,
    edges,
    clusterHealth,
    insights: realInsights,
    receipts: realReceipts,
    agentActions: realAgentActions,
    mcpStats,
    loadError,
    days,
    charts: {
      entityDaily,
      cumulativeEntities: cumulative(entityDaily),
      edgeDaily,
      insightDaily,
      actionDaily,
      receiptDaily,
    },
  };
}

type RealData = ReturnType<typeof useRealInsightsData>;

function buildDegreeRows(entities: Entity[], edges: Edge[]) {
  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source_id, (degree.get(edge.source_id) ?? 0) + 1);
    degree.set(edge.target_id, (degree.get(edge.target_id) ?? 0) + 1);
  }
  return entities
    .map((entity) => ({ entity, degree: degree.get(entity.id) ?? 0 }))
    .filter((row) => row.degree > 0)
    .sort((a, b) => b.degree - a.degree)
    .slice(0, 8);
}

function classifiedCoverage(entities: Entity[]): number | null {
  if (!entities.length) return null;
  const classified = entities.filter((entity) => Boolean(entity.cluster_id)).length;
  return (classified / entities.length) * 100;
}

function receiptSuccessRate(receipts: RealData["receipts"]): number | null {
  if (!receipts.length) return null;
  const allowed = receipts.filter((receipt) => receipt.decision === "allow").length;
  return (allowed / receipts.length) * 100;
}

function realAgentNames(data: RealData): string[] {
  return Array.from(
    new Set([
      ...data.agentActions.map((action) => action.agent_name).filter(Boolean),
      ...(data.mcpStats?.active_agents ?? []),
      ...(data.mcpStats?.recent_actions ?? []).map((action) => action.agent_name).filter(Boolean),
    ]),
  ).sort();
}

function latestDataDate(data: RealData): Date | null {
  const dates = [
    ...data.entities.map(entityTimestamp),
    ...data.edges.map((edge) => toDate(edge.created_at)),
    ...data.insights.map((insight) => toDate(insight.timestamp)),
    ...data.receipts.map((receipt) => toDate(receipt.timestamp)),
    ...data.agentActions.map((action) => toDate(action.timestamp)),
    toDate(data.mcpStats?.last_tool_call ?? null),
  ].filter((date): date is Date => Boolean(date));
  return dates.length ? new Date(Math.max(...dates.map((date) => date.getTime()))) : null;
}

function OverviewTab({ data }: { data: RealData }) {
  const coverage = classifiedCoverage(data.entities);
  const success = receiptSuccessRate(data.receipts);
  const degreeRows = buildDegreeRows(data.entities, data.edges).slice(0, 4);
  const latestInsight = data.insights[0];

  const highlight = () => {
    window.dispatchEvent(new CustomEvent("axiom:highlight-entities", { detail: { ids: latestInsight?.related_entity_ids ?? [] } }));
  };

  return (
    <>
      {data.loadError ? <div className="ins-load-error">Real data load failed: {data.loadError}</div> : null}
      <div className="ins-grid ins-overview-kpis">
        <KpiCard title="Entities" value={formatNumber(data.entities.length)} detail="Loaded from /api/entities" icon="cube" accent="blue" points={data.charts.cumulativeEntities} />
        <KpiCard title="Relationships" value={formatNumber(data.edges.length)} detail="Loaded from /api/edges" icon="insights" accent="cyan" points={data.charts.edgeDaily} />
        <KpiCard title="Classified Coverage" value={formatPercent(coverage, 1)} detail="Entities with a cluster assignment" icon="policy" accent="green" points={data.charts.entityDaily} />
        <KpiCard title="Real Insights" value={formatNumber(data.insights.length)} detail="Demo insights are excluded" icon="warning" accent="amber" points={data.charts.insightDaily} />
      </div>

      <div className="ins-grid ins-overview-main">
        <Panel title="Top Connection Drivers">
          <p className="ins-muted">Ranked by actual graph degree from loaded edges.</p>
          {degreeRows.length ? (
            <div className="ins-connection-map">
              {degreeRows.map((row, index) => (
                <div key={row.entity.id} className={cx("ins-map-node", `is-${["blue", "purple", "green", "amber"][index]}`)}>
                  <HexIcon icon={row.entity.type === "policy" ? "policy" : "cube"} accent={(["blue", "purple", "green", "amber"][index] ?? "blue") as Accent} />
                  <strong>{titleForEntity(row.entity)}</strong>
                  <span>{row.degree} connection{row.degree === 1 ? "" : "s"}</span>
                </div>
              ))}
              <div className="ins-map-core">
                <HexIcon icon="insights" accent="blue" />
                <strong>Axiom Company Brain</strong>
                <span>{formatNumber(data.entities.length)} entities</span>
                <b>{formatNumber(data.edges.length)} relationships</b>
              </div>
            </div>
          ) : <EmptyState>No relationships are loaded yet.</EmptyState>}
          <div className="ins-panel-foot">
            <Link to="/graph" className="ins-secondary"><Icon name="insights" /> Explore Graph</Link>
          </div>
        </Panel>

        <Panel title="Insight Summary">
          <p className="ins-muted">Only non-demo warden insights are shown.</p>
          {data.insights.length ? (
            <div className="ins-summary-list">
              {data.insights.slice(0, 5).map((insight) => (
                <div key={insight.insight_id}>
                  <i className={cx(insight.severity === "critical" ? "ins-red" : insight.severity === "warning" ? "ins-amber" : "ins-blue")} />
                  <HexIcon icon={insight.severity === "info" ? "insights" : "warning"} accent={insight.severity === "critical" ? "red" : insight.severity === "warning" ? "amber" : "blue"} />
                  <span>{insight.message}</span>
                </div>
              ))}
            </div>
          ) : <EmptyState>No real insight events have been received.</EmptyState>}
        </Panel>
      </div>

      <section className="ins-day-card">
        <div className="ins-day-art"><Icon name="brain" /></div>
        <div className="ins-day-copy">
          <div className="ins-day-label">Latest Real Insight</div>
          {latestInsight ? (
            <>
              <h2>{latestInsight.message}</h2>
              <p>{latestInsight.recommended_actions.length ? latestInsight.recommended_actions.join(" • ") : "No recommended actions provided by the event."}</p>
              <div className="ins-day-tags">
                <StatusPill tone={latestInsight.severity === "critical" ? "red" : latestInsight.severity === "warning" ? "amber" : "blue"}>Severity: {latestInsight.severity}</StatusPill>
                <StatusPill tone="blue">Confidence: {formatPercent(latestInsight.confidence * 100, 0)}</StatusPill>
              </div>
            </>
          ) : (
            <>
              <h2>No real insight available</h2>
              <p>The page is intentionally not rendering demo warden events or placeholder insight copy.</p>
            </>
          )}
        </div>
        <div className="ins-day-stats">
          <span>Related Entities <b>{latestInsight ? latestInsight.related_entity_ids.length : "N/A"}</b></span>
          <span>Detected <b>{latestInsight ? toDate(latestInsight.timestamp)?.toLocaleString() ?? "N/A" : "N/A"}</b></span>
          <span>Source <b>{latestInsight ? "Live event" : "None"}</b></span>
          <button type="button" onClick={highlight} disabled={!latestInsight}>View Recommendation <Icon name="arrow" /></button>
        </div>
      </section>
    </>
  );
}

function TrendsTab({ data }: { data: RealData }) {
  const [query, setQuery] = useState("");
  const cards = [
    { title: "Entities Created", value: data.entities.length, detail: "/api/entities", accent: "blue" as Accent, points: data.charts.entityDaily },
    { title: "Relationships Created", value: data.edges.length, detail: "/api/edges", accent: "cyan" as Accent, points: data.charts.edgeDaily },
    { title: "Real Agent Actions", value: data.agentActions.length, detail: "Demo actions excluded", accent: "purple" as Accent, points: data.charts.actionDaily },
    { title: "Real Receipts", value: data.receipts.length, detail: "Demo receipts excluded", accent: "green" as Accent, points: data.charts.receiptDaily },
    { title: "Real Insights", value: data.insights.length, detail: "Demo insights excluded", accent: "amber" as Accent, points: data.charts.insightDaily },
  ].filter((card) => card.title.toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <div className="ins-trends-top">
        <div className="ins-date"><span>{data.days}-day window</span><Icon name="calendar" /></div>
        <label className="ins-search"><Icon name="search" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search real metrics..." /></label>
        <button type="button" className="ins-filter-button"><Icon name="filter" /> Filters</button>
        <TrendHighlight title="Most Connected Entity" value={buildDegreeRows(data.entities, data.edges)[0]?.entity ? titleForEntity(buildDegreeRows(data.entities, data.edges)[0].entity) : "N/A"} delta={buildDegreeRows(data.entities, data.edges)[0] ? `${buildDegreeRows(data.entities, data.edges)[0].degree} edges` : "No edges"} accent="blue" />
        <TrendHighlight title="Active Real Agents" value={formatNumber(realAgentNames(data).length)} delta="From non-demo actions and MCP stats" accent="green" />
        <TrendHighlight title="Success Rate" value={formatPercent(receiptSuccessRate(data.receipts), 1)} delta="From real receipts" accent="purple" />
      </div>

      <div className="ins-grid ins-trend-grid">
        {cards.map((card) => (
          <Panel key={card.title} title={card.title} action={<button type="button" className="ins-icon-button"><Icon name="menu" /></button>}>
            <div className="ins-trend-metric"><strong>{formatNumber(card.value)}</strong><span>{card.detail}</span></div>
            <MiniLineChart accent={card.accent} points={card.points} />
          </Panel>
        ))}
      </div>

      <Panel title="Metric Summary Over Time" className="ins-wide-panel">
        <div className="ins-comparison-chart">
          <MiniLineChart accent="blue" points={data.charts.cumulativeEntities} />
          <div className="ins-legend">
            <span className="ins-blue">Entities: {formatNumber(data.entities.length)}</span>
            <span className="ins-cyan">Relationships: {formatNumber(data.edges.length)}</span>
            <span className="ins-purple">Real agent actions: {formatNumber(data.agentActions.length)}</span>
            <span className="ins-amber">Real insights: {formatNumber(data.insights.length)}</span>
            <span className="ins-green">Real receipts: {formatNumber(data.receipts.length)}</span>
          </div>
        </div>
      </Panel>
    </>
  );
}

function TrendHighlight({ title, value, delta, accent }: { title: string; value: string; delta: string; accent: Accent }) {
  return (
    <div className={cx("ins-trend-highlight", `ins-${accent}`)}>
      <HexIcon icon={accent === "red" ? "warning" : "shield"} accent={accent} />
      <span>{title}</span>
      <strong>{value}</strong>
      <b>{delta}</b>
    </div>
  );
}

function RiskTab({ data }: { data: RealData }) {
  const [selected, setSelected] = useState(0);
  const lowConfidence = data.entities
    .filter((entity) => typeof entity.composite_importance === "number" && entity.composite_importance < 0.4)
    .sort((a, b) => (a.composite_importance ?? 1) - (b.composite_importance ?? 1));
  const criticalInsights = data.insights.filter((insight) => insight.severity === "critical");
  const warningInsights = data.insights.filter((insight) => insight.severity === "warning");
  const deniedReceipts = data.receipts.filter((receipt) => receipt.decision === "deny");
  const deniedActions = data.agentActions.filter((action) => action.decision === "deny");
  const riskExposure = data.entities.length ? ((criticalInsights.length * 3 + warningInsights.length + lowConfidence.length + deniedReceipts.length + deniedActions.length) / data.entities.length) * 100 : null;

  return (
    <>
      <div className="ins-grid ins-risk-kpis">
        <KpiCard title="Derived Risk Exposure" value={formatPercent(riskExposure, 1)} detail="Computed from real risk signals only" icon="shield" accent="red" points={data.charts.insightDaily} />
        <KpiCard title="Critical Insights" value={formatNumber(criticalInsights.length)} detail="Non-demo critical insight events" icon="warning" accent="red" points={data.charts.insightDaily} />
        <KpiCard title="Denied Decisions" value={formatNumber(deniedReceipts.length + deniedActions.length)} detail="Real receipts and actions" icon="policy" accent="amber" points={data.charts.receiptDaily} />
        <KpiCard title="Low-Confidence Entities" value={formatNumber(lowConfidence.length)} detail="Composite importance below 0.4" icon="target" accent="amber" points={data.charts.entityDaily} />
      </div>
      <div className="ins-grid ins-risk-layout">
        <Panel title="Risk Signal Matrix">
          {data.entities.length || data.insights.length || data.receipts.length ? (
            <div className="ins-risk-matrix">
              {[criticalInsights.length, warningInsights.length, deniedReceipts.length, deniedActions.length, lowConfidence.length, data.insights.length, data.receipts.length, data.agentActions.length, data.edges.length, data.entities.length].map((value, index) => <span key={index}>{value}</span>)}
            </div>
          ) : <EmptyState>No risk inputs are available.</EmptyState>}
        </Panel>
        <Panel title="Lowest Confidence Entities">
          {lowConfidence.length ? (
            <div className="ins-table">
              {lowConfidence.slice(0, 5).map((entity, index) => (
                <button key={entity.id} type="button" onClick={() => setSelected(index)} className={cx(index === selected && "is-selected")}>
                  <span><Icon name="shield" /> <b>{titleForEntity(entity)}</b><small>{clusterLabel(entity.cluster_id)}</small></span>
                  <strong>{formatPercent((entity.composite_importance ?? 0) * 100, 0)}</strong>
                  <StatusPill tone="amber">Low confidence</StatusPill>
                </button>
              ))}
            </div>
          ) : <EmptyState>No low-confidence entities found in real data.</EmptyState>}
        </Panel>
        <div className="ins-side-stack">
          <Panel title="Real Critical / Warning Insights">
            {data.insights.length ? <InsightRows insights={data.insights} /> : <EmptyState>No real insight risks.</EmptyState>}
          </Panel>
          <Panel title="Denied Policy Decisions">
            {deniedReceipts.length || deniedActions.length ? (
              <div className="ins-compact-rows">
                {deniedReceipts.map((receipt) => <div key={receipt.receipt_id}><span>{receipt.action_id}</span><strong>{receipt.agent_name}</strong><StatusPill tone="red">Denied</StatusPill></div>)}
                {deniedActions.map((action) => <div key={action.action_id}><span>{action.skill_called}</span><strong>{action.agent_name}</strong><StatusPill tone="red">Denied</StatusPill></div>)}
              </div>
            ) : <EmptyState>No real denied decisions.</EmptyState>}
          </Panel>
        </div>
        <Panel title="Incident Correlation / Risk Propagation">
          {data.insights.some((insight) => insight.related_entity_ids.length > 0) ? (
            <div className="ins-propagation">
              {data.insights.flatMap((insight) => insight.related_entity_ids).slice(0, 6).map((id) => (
                <div key={id} className="ins-amber"><HexIcon icon="warning" accent="amber" /><span>{titleForEntity(data.entities.find((entity) => entity.id === id) ?? ({ id, type: "entity", data: {}, source_id: null, created_at: "", updated_at: "" } as Entity))}</span></div>
              ))}
            </div>
          ) : <EmptyState>No related entities in real insight events.</EmptyState>}
        </Panel>
        <Panel title="Action Recommendations">
          {data.insights.some((insight) => insight.recommended_actions.length > 0) ? (
            <div className="ins-action-table">
              {data.insights.flatMap((insight) => insight.recommended_actions.map((action) => ({ insight, action }))).slice(0, 6).map(({ insight, action }, index) => (
                <button type="button" key={`${insight.insight_id}-${action}`} className={index === selected ? "is-selected" : undefined} onClick={() => setSelected(index)}>
                  <span>{action}</span><StatusPill tone={insight.severity === "critical" ? "red" : insight.severity === "warning" ? "amber" : "blue"}>{insight.severity}</StatusPill>
                </button>
              ))}
            </div>
          ) : <EmptyState>No real recommendations available.</EmptyState>}
        </Panel>
      </div>
    </>
  );
}

function InsightRows({ insights }: { insights: WardenInsight[] }) {
  return (
    <div className="ins-compact-rows">
      {insights.slice(0, 6).map((insight) => (
        <div key={insight.insight_id}>
          <span>{insight.message}</span>
          <strong>{formatPercent(insight.confidence * 100, 0)}</strong>
          <StatusPill tone={insight.severity === "critical" ? "red" : insight.severity === "warning" ? "amber" : "blue"}>{insight.severity}</StatusPill>
        </div>
      ))}
    </div>
  );
}

function AdoptionTab({ data }: { data: RealData }) {
  const agents = realAgentNames(data);
  const toolCalls = data.mcpStats?.tools.reduce((sum, tool) => sum + tool.calls, 0) ?? 0;
  const clusterRows = Object.entries(data.clusterHealth)
    .filter(([clusterId]) => clusterId !== "overall")
    .map(([clusterId, health]) => ({ clusterId, total: health.total_entities, rate: health.ingest_rate_per_min }))
    .filter((row) => row.total > 0)
    .sort((a, b) => b.total - a.total);

  return (
    <>
      <div className="ins-grid ins-adoption-kpis">
        <KpiCard title="Active Agents" value={formatNumber(agents.length)} detail="Real agent actions and MCP stats" icon="users" accent="blue" points={data.charts.actionDaily} />
        <KpiCard title="MCP Tool Calls" value={formatNumber(toolCalls)} detail="/api/internal/mcp-stats" icon="message" accent="green" />
        <KpiCard title="Recent Agent Events" value={formatNumber(data.mcpStats?.recent_actions.length ?? data.agentActions.length)} detail="Real MCP/action events" icon="bot" accent="purple" points={data.charts.actionDaily} />
        <KpiCard title="Saved Views" value="N/A" detail="No real saved-view API exists" icon="target" accent="amber" />
      </div>
      <div className="ins-grid ins-adoption-main">
        <Panel title="Entities By Cluster">{clusterRows.length ? <ProgressRows rows={clusterRows.map((row) => [clusterLabel(row.clusterId), row.total])} /> : <EmptyState>No cluster health data loaded.</EmptyState>}</Panel>
        <Panel title="Entity Growth Over Time"><MiniLineChart accent="blue" points={data.charts.cumulativeEntities} /></Panel>
        <Panel title="Human vs Agent Query Mix">
          {toolCalls || data.agentActions.length ? <Donut primary={toolCalls} secondary={data.agentActions.length} primaryLabel="MCP tool calls" secondaryLabel="Agent actions" /> : <EmptyState>No real query mix data.</EmptyState>}
        </Panel>
        <Panel title="Active Agents">{agents.length ? <Leaderboard rows={agents.map((name) => [name, String(data.agentActions.filter((action) => action.agent_name === name).length), ""])} /> : <EmptyState>No active real agents.</EmptyState>}</Panel>
        <Panel title="MCP Tool Usage">
          {data.mcpStats?.tools.some((tool) => tool.calls > 0) ? <ProgressRows rows={data.mcpStats.tools.filter((tool) => tool.calls > 0).map((tool) => [tool.name, tool.calls])} /> : <EmptyState>No MCP tool calls recorded.</EmptyState>}
        </Panel>
        <Panel title="Recent Agent Activity">
          {data.mcpStats?.recent_actions.length ? <Champions rows={data.mcpStats.recent_actions.map((action) => [action.agent_name, action.intent || action.status, new Date(action.timestamp).toLocaleString()])} /> : <EmptyState>No recent MCP agent activity.</EmptyState>}
        </Panel>
      </div>
    </>
  );
}

function ProgressRows({ rows }: { rows: Array<[string, number]> }) {
  const max = Math.max(...rows.map(([, value]) => value), 1);
  return <div className="ins-progress-rows">{rows.map(([label, value]) => <div key={label}><span>{label}</span><i><b style={{ width: `${(value / max) * 100}%` }} /></i><strong>{formatNumber(value)}</strong></div>)}</div>;
}

function Leaderboard({ rows }: { rows: string[][] }) {
  return <div className="ins-leaderboard">{rows.map(([name, value], index) => <div key={`${name}-${index}`}><span>{index + 1}</span><b>{name}</b><strong>{value}</strong></div>)}</div>;
}

function Donut({ primary, secondary, primaryLabel, secondaryLabel }: { primary: number; secondary: number; primaryLabel: string; secondaryLabel: string }) {
  const total = primary + secondary;
  const primaryPct = total ? (primary / total) * 100 : 0;
  return (
    <div className="ins-donut-wrap">
      <div className="ins-donut" style={{ background: `conic-gradient(#2d86ff 0 ${primaryPct}%, #12e29b ${primaryPct}% 100%)` }}><span><b>{formatNumber(total)}</b>Total</span></div>
      <div className="ins-donut-legend"><span className="ins-blue">{primaryLabel} <b>{formatNumber(primary)}</b></span><span className="ins-green">{secondaryLabel} <b>{formatNumber(secondary)}</b></span></div>
    </div>
  );
}

function Champions({ rows }: { rows: string[][] }) {
  return <div className="ins-champions">{rows.slice(0, 6).map(([name, team, impact]) => <div key={`${name}-${impact}`}><span>{name.slice(0, 2).toUpperCase()}</span><b>{name}</b><small>{team}</small><strong>{impact}</strong></div>)}</div>;
}

function AiImpactTab({ data }: { data: RealData }) {
  const successRate = receiptSuccessRate(data.receipts);
  const toolCalls = data.mcpStats?.tools.reduce((sum, tool) => sum + tool.calls, 0) ?? 0;
  return (
    <>
      <div className="ins-grid ins-impact-kpis">
        <KpiCard title="Time Saved" value="N/A" detail="No real time-saved API exists" icon="bolt" accent="blue" />
        <KpiCard title="Decision Cycle Reduction" value="N/A" detail="No before/after timing data exists" icon="target" accent="green" />
        <KpiCard title="Execution Success Rate" value={formatPercent(successRate, 1)} detail="Allowed real receipts / all real receipts" icon="shield" accent="purple" points={data.charts.receiptDaily} />
        <KpiCard title="Business Value / ROI" value="N/A" detail="No real ROI API exists" icon="target" accent="amber" />
      </div>
      <div className="ins-grid ins-impact-main">
        <Panel title="Real Workflow Activity By Cluster">
          {data.agentActions.length ? <ProgressRows rows={Object.entries(data.agentActions.reduce<Record<string, number>>((acc, action) => ({ ...acc, [action.cluster_id]: (acc[action.cluster_id] ?? 0) + 1 }), {})).map(([cluster, count]) => [clusterLabel(cluster), count])} /> : <EmptyState>No real agent actions.</EmptyState>}
        </Panel>
        <Panel title="Before vs After (With AI & Agents)"><EmptyState>No real before/after metric API exists yet.</EmptyState></Panel>
        <Panel title="Top Real Outcomes">
          {data.receipts.length || data.agentActions.length ? (
            <div className="ins-outcomes">
              {data.receipts.slice(0, 5).map((receipt, index) => <div key={receipt.receipt_id}><span>{index + 1}</span><b>{receipt.action_id}<small>{receipt.agent_name}</small></b><strong>{receipt.decision}</strong></div>)}
              {data.agentActions.slice(0, 5).map((action, index) => <div key={action.action_id}><span>{index + 1}</span><b>{action.skill_called}<small>{action.agent_name}</small></b><strong>{action.decision ?? "pending"}</strong></div>)}
            </div>
          ) : <EmptyState>No real outcomes recorded.</EmptyState>}
        </Panel>
        <Panel title="Human-Agent Collaboration">
          {toolCalls || data.agentActions.length ? <Donut primary={toolCalls} secondary={data.agentActions.length} primaryLabel="MCP tool calls" secondaryLabel="Agent actions" /> : <EmptyState>No real collaboration data.</EmptyState>}
        </Panel>
        <Panel title="AI Agent Adoption & Utilization">
          <div className="ins-agent-stats">
            <span>Active Agents <b>{formatNumber(realAgentNames(data).length)}</b></span>
            <span>MCP Tool Calls <b>{formatNumber(toolCalls)}</b></span>
            <span>Real Actions <b>{formatNumber(data.agentActions.length)}</b></span>
          </div>
        </Panel>
        <Panel title="Impact Highlight"><EmptyState>No real impact-highlight API exists yet.</EmptyState></Panel>
      </div>
      <section className="ins-impact-banner">
        <Icon name="brain" />
        <div><strong>Real data only</strong><span>{formatNumber(data.entities.length)} entities</span><span>{formatNumber(data.edges.length)} relationships</span><span>{formatNumber(toolCalls)} MCP calls</span><span>{formatNumber(data.insights.length)} real insights</span></div>
        <b>{formatPercent(successRate, 1)} <small>receipt success rate</small></b>
      </section>
    </>
  );
}

export function InsightsPage() {
  const [params, setParams] = useSearchParams();
  const requested = (params.get("tab") as Tab) || "overview";
  const tab = tabs.some((item) => item.id === requested) ? requested : "overview";
  const [timeRange, setTimeRange] = useState("Last 30 Days");
  const data = useRealInsightsData(timeRange);
  const asOf = latestDataDate(data);

  const content = useMemo(() => {
    if (tab === "trends") return <TrendsTab data={data} />;
    if (tab === "risk") return <RiskTab data={data} />;
    if (tab === "adoption") return <AdoptionTab data={data} />;
    if (tab === "ai-impact") return <AiImpactTab data={data} />;
    return <OverviewTab data={data} />;
  }, [tab, data]);

  return (
    <div className="insights-stage">
      <div className="insights-shell">
        <div className="insights-title-row">
          <div className="insights-title"><Icon name="insights" /><h1>Insights</h1></div>
          <HeaderTools timeRange={timeRange} setTimeRange={setTimeRange} dataAsOf={asOf ? `Data as of ${asOf.toLocaleString()}` : "No real data loaded"} />
        </div>
        <nav className="insights-tabs" aria-label="Insight tabs">
          {tabs.map((item) => (
            <button key={item.id} type="button" onClick={() => setParams({ tab: item.id })} className={tab === item.id ? "is-active" : undefined}>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="insights-body">{content}</div>
      </div>
    </div>
  );
}
