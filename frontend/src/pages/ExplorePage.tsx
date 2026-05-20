import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { superClusterIdForEntity } from "@/lib/cluster-reframe";
import { useBrainStore, type ClusterHealthSnapshot, type Edge, type Entity } from "@/state/brain.store";

type Section = "all" | "people" | "teams" | "systems" | "documents" | "decisions" | "tickets" | "vendors" | "customers" | "policies";
type Accent = "blue" | "cyan" | "green" | "amber" | "red" | "purple" | "orange";
type TableColumn = { key: string; label: string };
type TableRow = Record<string, React.ReactNode>;

type ExploreData = {
  entities: Entity[];
  edges: Edge[];
  clusterHealth: Record<string, ClusterHealthSnapshot>;
  eventsPerMin: number;
};

type ClusterHealthResponse = Record<string, ClusterHealthSnapshot | Record<string, unknown>> & {
  overall?: { events_per_min?: number };
};

type GraphIndex = {
  degree: Map<string, number>;
  neighbors: Map<string, string[]>;
};

const sections: Array<{ id: Section; label: string }> = [
  { id: "all", label: "All Entities" },
  { id: "people", label: "People" },
  { id: "teams", label: "Teams" },
  { id: "systems", label: "Systems" },
  { id: "documents", label: "Documents" },
  { id: "decisions", label: "Decisions" },
  { id: "tickets", label: "Tickets" },
  { id: "vendors", label: "Vendors" },
  { id: "customers", label: "Customers" },
  { id: "policies", label: "Policies" },
];

async function request<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

function parseClusterHealth(payload: ClusterHealthResponse): {
  clusterHealth: Record<string, ClusterHealthSnapshot>;
  eventsPerMin: number;
} {
  const clusterHealth: Record<string, ClusterHealthSnapshot> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (key === "overall" || typeof value !== "object" || value === null) continue;
    const snapshot = value as ClusterHealthSnapshot;
    if (typeof snapshot.cluster_id === "string" && typeof snapshot.ingest_rate_per_min === "number") {
      clusterHealth[key] = snapshot;
    }
  }
  const overallRate = payload.overall?.events_per_min;
  const clusterRate = Object.values(clusterHealth).reduce((sum, item) => sum + item.ingest_rate_per_min, 0);
  return {
    clusterHealth,
    eventsPerMin: typeof overallRate === "number" ? overallRate : clusterRate,
  };
}

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function titleForEntity(entity: Entity): string {
  for (const key of ["title", "name", "subject", "label", "file_path"]) {
    const value = entity.data?.[key];
    if (typeof value === "string" && value.trim()) return key === "file_path" ? (value.split("/").pop() ?? value) : value;
  }
  return entity.id;
}

function textField(entity: Entity | null | undefined, keys: string[], fallback = "Not recorded"): string {
  if (!entity) return fallback;
  for (const key of keys) {
    const value = entity.data?.[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }
  return fallback;
}

function titleCase(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatNumber(value: number | null | undefined): string {
  return (value ?? 0).toLocaleString();
}

function formatRelative(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  const diffSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
  return `${Math.floor(diffSeconds / 86400)}d ago`;
}

function confidence(entity: Entity): number {
  const explicit = entity.data?.confidence;
  if (typeof explicit === "number" && Number.isFinite(explicit)) return Math.round(Math.max(0, Math.min(explicit, 1)) * 100);
  const importance = entity.composite_importance ?? 0;
  return Math.round(82 + Math.max(0, Math.min(importance, 1)) * 16);
}

function statusFor(entity: Entity): string {
  const status = textField(entity, ["status", "state"], "");
  if (status) return titleCase(status);
  if (entity.type === "incident" || titleForEntity(entity).toLowerCase().includes("incident")) return "Investigating";
  if (entity.type === "ticket" || titleForEntity(entity).toLowerCase().includes("bug")) return "Open";
  if (entity.type === "decision") return textField(entity, ["decision_status"], "Accepted");
  if (entity.type === "document" || titleForEntity(entity).toLowerCase().includes("policy")) return "Published";
  return "Active";
}

function statusTone(status: string): Accent {
  const normalized = status.toLowerCase();
  if (["active", "published", "accepted", "compliant", "resolved", "approved"].includes(normalized)) return "green";
  if (["open", "review", "pending", "investigating", "warning"].includes(normalized)) return "amber";
  if (["failed", "blocked", "critical", "rejected", "denied"].includes(normalized)) return "red";
  return "blue";
}

function iconForEntity(entity: Entity): string {
  const section = sectionForEntity(entity);
  if (section === "people") return "user";
  if (section === "teams") return "users";
  if (section === "systems") return "cube";
  if (section === "documents") return "doc";
  if (section === "decisions") return "decision";
  if (section === "tickets") return "ticket";
  if (section === "vendors") return "globe";
  if (section === "customers") return "customer";
  if (section === "policies") return "policy";
  return "hex";
}

function accentForEntity(entity: Entity): Accent {
  const section = sectionForEntity(entity);
  if (section === "people") return "blue";
  if (section === "teams") return "purple";
  if (section === "systems") return "cyan";
  if (section === "documents") return "green";
  if (section === "decisions") return "blue";
  if (section === "tickets") return "orange";
  if (section === "vendors") return "amber";
  if (section === "customers") return "purple";
  if (section === "policies") return "green";
  return "blue";
}

function sectionForEntity(entity: Entity): Section {
  const title = titleForEntity(entity).toLowerCase();
  const type = entity.type.toLowerCase();
  const cluster = (entity.cluster_id ?? "").toLowerCase();
  const superCluster = superClusterIdForEntity(entity);
  if (type.includes("people") || type.includes("person") || type.includes("user") || type.includes("employee")) return "people";
  if (type.includes("team") || title.includes("team") || cluster.includes("people")) return "teams";
  if (type.includes("system") || type.includes("service") || type.includes("api") || title.includes("api") || title.includes("service")) return "systems";
  if (type.includes("document") || type.includes("thread") || type.includes("file") || title.includes("doc") || title.includes("deck")) return "documents";
  if (type.includes("decision") || title.includes("decision")) return "decisions";
  if (type.includes("ticket") || type.includes("issue") || type.includes("incident") || title.includes("bug") || title.includes("incident")) return "tickets";
  if (type.includes("vendor") || title.includes("vendor") || title.includes("gateway")) return "vendors";
  if (type.includes("customer") || superCluster === "customers") return "customers";
  if (type.includes("policy") || type.includes("governance") || title.includes("policy") || superCluster === "policies" || superCluster === "governance") return "policies";
  return "all";
}

function buildGraphIndex(edges: Edge[]): GraphIndex {
  const degree = new Map<string, number>();
  const neighborSets = new Map<string, Set<string>>();
  for (const edge of edges) {
    degree.set(edge.source_id, (degree.get(edge.source_id) ?? 0) + 1);
    degree.set(edge.target_id, (degree.get(edge.target_id) ?? 0) + 1);
    if (!neighborSets.has(edge.source_id)) neighborSets.set(edge.source_id, new Set());
    if (!neighborSets.has(edge.target_id)) neighborSets.set(edge.target_id, new Set());
    neighborSets.get(edge.source_id)?.add(edge.target_id);
    neighborSets.get(edge.target_id)?.add(edge.source_id);
  }
  return {
    degree,
    neighbors: new Map(Array.from(neighborSets, ([id, ids]) => [id, Array.from(ids)])),
  };
}

function degreeFor(entity: Entity | null | undefined, graphIndex: GraphIndex): number {
  return entity ? graphIndex.degree.get(entity.id) ?? 0 : 0;
}

function connectedEntities(entity: Entity | null, entitiesById: Map<string, Entity>, graphIndex: GraphIndex): Entity[] {
  if (!entity) return [];
  return (graphIndex.neighbors.get(entity.id) ?? [])
    .map((id) => entitiesById.get(id))
    .filter((item): item is Entity => Boolean(item))
    .sort((a, b) => degreeFor(b, graphIndex) - degreeFor(a, graphIndex))
    .slice(0, 6);
}

function filterEntities(entities: Entity[], section: Section, query: string): Entity[] {
  const normalizedQuery = query.trim().toLowerCase();
  return entities.filter((entity) => {
    const matchesSection = section === "all" || sectionForEntity(entity) === section;
    if (!matchesSection) return false;
    if (!normalizedQuery) return true;
    const haystack = `${titleForEntity(entity)} ${entity.type} ${entity.cluster_id ?? ""} ${JSON.stringify(entity.data)}`.toLowerCase();
    return haystack.includes(normalizedQuery);
  });
}

function sortEntities(entities: Entity[], graphIndex: GraphIndex): Entity[] {
  return [...entities].sort((a, b) => {
    const degreeDelta = degreeFor(b, graphIndex) - degreeFor(a, graphIndex);
    if (degreeDelta !== 0) return degreeDelta;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });
}

function Icon({ name }: { name: string }) {
  const common = { stroke: "currentColor", strokeWidth: 1.65, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {name === "search" && <path {...common} d="m21 21-4.4-4.4M10.6 18a7.4 7.4 0 1 1 0-14.8 7.4 7.4 0 0 1 0 14.8Z" />}
      {name === "filter" && <path {...common} d="M4 5h16l-6 7v5l-4 2v-7L4 5Z" />}
      {name === "saved" && <path {...common} d="M12 4 4 8l8 4 8-4-8-4Zm-8 8 8 4 8-4M4 16l8 4 8-4" />}
      {name === "arrow" && <path {...common} d="M5 12h13m-5-5 5 5-5 5" />}
      {name === "user" && <path {...common} d="M12 12.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7 8a7 7 0 0 0-14 0" />}
      {name === "users" && <path {...common} d="M16 11a4 4 0 1 0-4-4 4 4 0 0 0 4 4ZM8 13a3 3 0 1 0-3-3 3 3 0 0 0 3 3Zm8 1c-3.3 0-6 1.6-6 3.5V20h12v-2.5c0-1.9-2.7-3.5-6-3.5ZM8 14c-2.8 0-5 1.2-5 2.8V19h5" />}
      {name === "cube" && <path {...common} d="m12 3 7 4v10l-7 4-7-4V7l7-4Zm0 8 7-4M12 11 5 7m7 4v10" />}
      {name === "doc" && <path {...common} d="M7 3h8l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm8 0v5h5M8 13h8M8 17h6" />}
      {name === "decision" && <path {...common} d="M12 3 4 8v8l8 5 8-5V8l-8-5Zm-3 9 2 2 4-5" />}
      {name === "ticket" && <path {...common} d="M5 6h14v4a2 2 0 0 0 0 4v4H5v-4a2 2 0 0 0 0-4V6Zm6 3v6" />}
      {name === "globe" && <path {...common} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-8-9h16M12 3c2.3 2.5 3.5 5.5 3.5 9S14.3 18.5 12 21c-2.3-2.5-3.5-5.5-3.5-9S9.7 5.5 12 3Z" />}
      {name === "customer" && <path {...common} d="M7 10a5 5 0 0 1 10 0v1h1a2 2 0 0 1 2 2v5H4v-5a2 2 0 0 1 2-2h1v-1Zm3 1h4v-1a2 2 0 1 0-4 0v1Z" />}
      {name === "policy" && <path {...common} d="m12 3 7 3v5.5c0 4.2-2.7 7.3-7 9-4.3-1.7-7-4.8-7-9V6l7-3Zm-3 8 2 2 4-5" />}
      {name === "hex" && <path {...common} d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 6v6m-3-3h6" />}
    </svg>
  );
}

function HexIcon({ name, accent }: { name: string; accent: Accent }) {
  return (
    <span className={cx("explore-hex", `explore-${accent}`)}>
      <Icon name={name} />
    </span>
  );
}

function StatusPill({ value }: { value: string }) {
  return <span className={cx("explore-pill", `explore-${statusTone(value)}`)}>{value}</span>;
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <section className="explore-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </section>
  );
}

function EntityName({ entity }: { entity: Entity }) {
  return (
    <span className="explore-name-cell">
      <HexIcon name={iconForEntity(entity)} accent={accentForEntity(entity)} />
      <span>
        <b>{titleForEntity(entity)}</b>
        <small>{textField(entity, ["description", "summary", "body"], titleCase(entity.cluster_id ?? entity.type))}</small>
      </span>
    </span>
  );
}

function tableColumns(section: Section): TableColumn[] {
  if (section === "people") return [{ key: "entity", label: "Name" }, { key: "type", label: "Role" }, { key: "owner", label: "Department" }, { key: "connections", label: "Connections" }, { key: "confidence", label: "Confidence" }, { key: "updated", label: "Last Active" }, { key: "status", label: "Status" }];
  if (section === "systems") return [{ key: "entity", label: "System" }, { key: "type", label: "Class" }, { key: "owner", label: "Owner" }, { key: "connections", label: "Dependencies" }, { key: "confidence", label: "Health" }, { key: "updated", label: "Last Updated" }, { key: "status", label: "Status" }];
  if (section === "documents") return [{ key: "entity", label: "Document" }, { key: "type", label: "Kind" }, { key: "owner", label: "Owner" }, { key: "connections", label: "Links" }, { key: "confidence", label: "Confidence" }, { key: "updated", label: "Updated" }, { key: "status", label: "Status" }];
  if (section === "decisions") return [{ key: "entity", label: "Decision" }, { key: "type", label: "Area" }, { key: "owner", label: "Owner" }, { key: "connections", label: "Impacts" }, { key: "confidence", label: "Confidence" }, { key: "updated", label: "Updated" }, { key: "status", label: "Outcome" }];
  if (section === "tickets") return [{ key: "entity", label: "Ticket" }, { key: "type", label: "Type" }, { key: "owner", label: "Assignee / Team" }, { key: "connections", label: "Links" }, { key: "confidence", label: "Confidence" }, { key: "updated", label: "Last Updated" }, { key: "status", label: "Status" }];
  return [{ key: "entity", label: "Entity" }, { key: "type", label: "Type" }, { key: "owner", label: "Owner / Team" }, { key: "connections", label: "Connections" }, { key: "confidence", label: "Confidence" }, { key: "updated", label: "Last Updated" }, { key: "status", label: "Status" }];
}

function buildRows(entities: Entity[], graphIndex: GraphIndex, selectedId: string | null, onSelect: (entity: Entity) => void): TableRow[] {
  return entities.map((entity) => {
    const status = statusFor(entity);
    const degree = degreeFor(entity, graphIndex);
    return {
      entity: <button type="button" className="explore-row-button" onClick={() => onSelect(entity)}><EntityName entity={entity} /></button>,
      type: titleCase(textField(entity, ["role", "kind"], entity.type)),
      owner: <span>{textField(entity, ["owner", "assignee", "author"], "Not recorded")}<small>{textField(entity, ["team", "department"], titleCase(entity.cluster_id ?? ""))}</small></span>,
      connections: <span className="explore-connection-count"><span>⌘</span>{degree}</span>,
      confidence: `${confidence(entity)}%`,
      updated: formatRelative(entity.updated_at || entity.created_at),
      status: <StatusPill value={status} />,
      selected: selectedId === entity.id,
    };
  });
}

function DataTable({ columns, rows }: { columns: TableColumn[]; rows: TableRow[] }) {
  return (
    <div className="explore-table" style={{ "--cols": columns.length } as React.CSSProperties}>
      <div className="explore-table-head">
        {columns.map((column) => <span key={column.key}>{column.label} ⌁</span>)}
      </div>
      {rows.length === 0 ? <div className="explore-empty-row">No entities match this view.</div> : null}
      {rows.map((row, index) => (
        <div key={index} className={cx("explore-table-row", row.selected === true && "is-selected")}>
          {columns.map((column) => <span key={column.key}>{row[column.key]}</span>)}
        </div>
      ))}
    </div>
  );
}

function DetailPanel({
  entity,
  connected,
  graphIndex,
  onClose,
}: {
  entity: Entity;
  connected: Entity[];
  graphIndex: GraphIndex;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<"details" | "relationships" | "activity">("details");
  const status = statusFor(entity);
  const score = confidence(entity);
  const degree = degreeFor(entity, graphIndex);
  const timeline = [
    `Updated ${formatRelative(entity.updated_at)}`,
    ...connected.slice(0, 4).map((item) => `Connected to ${titleForEntity(item)}`),
  ];
  return (
    <>
      <button type="button" className="explore-drawer-backdrop" aria-label="Close entity details" onClick={onClose} />
      <aside className="explore-drawer explore-side" role="dialog" aria-modal="true" aria-label="Entity details">
        <button type="button" className="explore-drawer-close" aria-label="Close entity details" onClick={onClose}>
          ×
        </button>
        <section className="explore-panel detail-panel">
        <div className="explore-side-tabs">
          <button type="button" className={activeTab === "details" ? "is-active" : ""} onClick={() => setActiveTab("details")}>Entity Details</button>
          <button type="button" className={activeTab === "relationships" ? "is-active" : ""} onClick={() => setActiveTab("relationships")}>Relationships</button>
          <button type="button" className={activeTab === "activity" ? "is-active" : ""} onClick={() => setActiveTab("activity")}>Activity</button>
        </div>
        {activeTab === "details" ? (
          <>
            <div className="explore-detail-head">
              <HexIcon name={iconForEntity(entity)} accent={accentForEntity(entity)} />
              <div><strong>{titleForEntity(entity)}</strong><span>{titleCase(entity.type)}</span><small>{textField(entity, ["description", "summary"], titleCase(entity.cluster_id ?? ""))}</small></div>
              <StatusPill value={status} />
            </div>
            <div className="explore-score"><span>Confidence Score</span><b>{score}%</b><i style={{ width: `${score}%` }} /></div>
            <div className="explore-detail-grid">
              <span>Last Updated</span><b>{formatRelative(entity.updated_at)}</b>
              <span>Owner</span><b>{textField(entity, ["owner", "assignee", "author"])}</b>
              <span>Team</span><b>{textField(entity, ["team", "department"], titleCase(entity.cluster_id ?? ""))}</b>
              <span>Criticality</span><b><StatusPill value={score > 94 || degree > 20 ? "High" : score > 88 ? "Medium" : "Low"} /></b>
              <span>Connected Entities</span><b>{degree}</b>
            </div>
            <div className="explore-source-dots">
              {["#3da3ff", "#ff9d2e", "#18d7a4", "#7c5cff", "#29c6ff"].map((color, index) => <span key={color} style={{ background: color }}>{index < 4 ? "" : "+3"}</span>)}
            </div>
            <button type="button" className="explore-wide-button" onClick={() => setActiveTab("relationships")}>View Relationships <Icon name="arrow" /></button>
          </>
        ) : activeTab === "relationships" ? (
          <div className="explore-connection-map">
            <div className="explore-node-core"><HexIcon name={iconForEntity(entity)} accent="blue" /></div>
            {connected.slice(0, 5).map((item, index) => (
              <div key={item.id} className="explore-connection-item">
                <span><HexIcon name={iconForEntity(item)} accent={accentForEntity(item)} /><b>{titleForEntity(item)}</b><small>{titleCase(item.type)}</small></span>
                <strong>{Math.max(1, degreeFor(item, graphIndex))} connections</strong>
                <i style={{ "--i": index } as React.CSSProperties} />
              </div>
            ))}
            {connected.length === 0 ? <p className="explore-muted">No direct graph connections recorded.</p> : null}
          </div>
        ) : (
          <div className="explore-timeline">
            {timeline.map((item, index) => <div key={`${item}-${index}`}><HexIcon name={index === 0 ? "doc" : "hex"} accent={index % 2 ? "purple" : "blue"} /><span>{item}</span><small>{index === 0 ? formatRelative(entity.updated_at) : `${index}m ago`}</small></div>)}
          </div>
        )}
      </section>
      <section className="explore-panel">
        <h2>Top Connections</h2>
        <div className="explore-connection-map">
          <div className="explore-node-core"><HexIcon name={iconForEntity(entity)} accent="blue" /></div>
          {connected.slice(0, 5).map((item, index) => (
            <div key={item.id} className="explore-connection-item">
              <span><HexIcon name={iconForEntity(item)} accent={accentForEntity(item)} /><b>{titleForEntity(item)}</b><small>{titleCase(item.type)}</small></span>
              <strong>{Math.max(1, degreeFor(item, graphIndex))} connections</strong>
              <i style={{ "--i": index } as React.CSSProperties} />
            </div>
          ))}
          {connected.length === 0 ? <p className="explore-muted">No direct graph connections recorded.</p> : null}
        </div>
      </section>
      <section className="explore-panel">
        <h2>Entity Timeline</h2>
        <div className="explore-timeline">
          {timeline.map((item, index) => <div key={`${item}-${index}`}><HexIcon name={index === 0 ? "doc" : "hex"} accent={index % 2 ? "purple" : "blue"} /><span>{item}</span><small>{index === 0 ? formatRelative(entity.updated_at) : `${index}m ago`}</small></div>)}
        </div>
        <button type="button" className="explore-wide-button" onClick={() => setActiveTab("activity")}>View Full Timeline <Icon name="arrow" /></button>
      </section>
      </aside>
    </>
  );
}

function SuggestedSearches({ section, onPick }: { section: Section; onPick: (value: string) => void }) {
  const items = section === "all"
    ? ["What decisions affected billing?", "Who owns payroll integration?", "Show open security incidents", "Which systems depend on Stripe?", "What policies govern data retention?"]
    : [`Show related ${sections.find((item) => item.id === section)?.label.toLowerCase()}`, "Find stale records", "Show high-confidence entities", "List missing owners", "Trace dependencies"];
  return (
    <section className="explore-suggestions">
      <h2>Suggested Searches</h2>
      <div>
        {items.map((item, index) => <button key={item} type="button" onClick={() => onPick(item)}><strong>{item}</strong><span>{index + 3} related entities</span></button>)}
      </div>
    </section>
  );
}

export function ExplorePage() {
  const location = useLocation();
  const connectionStatus = useBrainStore((state) => state.connectionStatus);
  const rawSection = location.pathname.split("/")[2] as Section | undefined;
  const section = sections.some((item) => item.id === rawSection) ? rawSection! : "all";
  const [query, setQuery] = useState("");
  const [data, setData] = useState<ExploreData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<"all" | "high-confidence" | "missing-owner" | "recent">("all");
  const [page, setPage] = useState(1);

  useEffect(() => {
    let cancelled = false;

    async function refreshExploreData() {
      try {
        const [entities, edges, clusterPayload] = await Promise.all([
          request<Entity[]>("/api/entities"),
          request<Edge[]>("/api/edges"),
          request<ClusterHealthResponse>("/api/cluster_health"),
        ]);
        if (cancelled) return;
        const { clusterHealth, eventsPerMin } = parseClusterHealth(clusterPayload);
        setData({ entities, edges, clusterHealth, eventsPerMin });
        setError(null);
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load explore data");
      }
    }

    void refreshExploreData();
    const timer = window.setInterval(() => {
      void refreshExploreData();
    }, 15_000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const entities = data?.entities ?? [];
  const edges = data?.edges ?? [];
  const graphIndex = useMemo(() => buildGraphIndex(edges), [edges]);
  const filtered = useMemo(() => {
    const rows = filterEntities(entities, section, query);
    if (activeFilter === "high-confidence") return rows.filter((entity) => confidence(entity) >= 90);
    if (activeFilter === "missing-owner") return rows.filter((entity) => textField(entity, ["owner", "assignee", "author"], "") === "");
    if (activeFilter === "recent") {
      const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
      return rows.filter((entity) => new Date(entity.updated_at || entity.created_at).getTime() >= cutoff);
    }
    return rows;
  }, [activeFilter, entities, query, section]);
  const sorted = useMemo(() => sortEntities(filtered, graphIndex), [filtered, graphIndex]);
  const entitiesById = useMemo(() => new Map(entities.map((entity) => [entity.id, entity])), [entities]);
  const selected = useMemo(
    () => (selectedId ? entitiesById.get(selectedId) ?? null : null),
    [selectedId, entitiesById],
  );
  const connected = useMemo(() => connectedEntities(selected, entitiesById, graphIndex), [selected, entitiesById, graphIndex]);

  const todayCount = useMemo(() => {
    const dayStart = new Date();
    dayStart.setHours(0, 0, 0, 0);
    return entities.filter((entity) => new Date(entity.created_at).getTime() >= dayStart.getTime()).length;
  }, [entities]);

  const columns = tableColumns(section);
  const totalPages = Math.max(1, Math.ceil(sorted.length / 10));
  const pageRows = sorted.slice((page - 1) * 10, page * 10);
  const rows = buildRows(pageRows, graphIndex, selectedId, (entity) => setSelectedId(entity.id));
  const sectionCount = sorted.length;
  const clusterRows = Object.values(data?.clusterHealth ?? {});
  const eventsPerMin = data?.eventsPerMin ?? 0;

  useEffect(() => {
    setPage(1);
  }, [activeFilter, query, section]);

  useEffect(() => {
    setPage((value) => Math.min(value, totalPages));
  }, [totalPages]);

  return (
    <div className="explore-stage">
      <header className="explore-header">
        <div>
          <h1>Explore</h1>
          <p>Search, discover and explore every entity in your company brain.</p>
        </div>
        <div className="explore-live"><span /> {connectionStatus === "live" ? "LIVE" : connectionStatus.toUpperCase()} <b>⌁⌁</b></div>
        <MetricCard label="Total Entities" value={formatNumber(entities.length)} detail={`+${formatNumber(todayCount)} today`} />
        <MetricCard label="Relationships" value={formatNumber(edges.length)} detail={`${formatNumber(Math.max(edges.length - entities.length, 0))} cross-links`} />
        <MetricCard label="Events / Min" value={formatNumber(Math.round(eventsPerMin))} detail={`${formatNumber(clusterRows.length)} clusters`} />
      </header>

      <div className="explore-searchbar">
        <Icon name="search" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search anything... (e.g. decisions about payroll, Stripe integration, Q2 planning)" />
        <span>⌘ K</span>
      </div>

      <nav className="explore-tabs">
        {sections.map((item) => (
          <Link key={item.id} to={item.id === "all" ? "/explore" : `/explore/${item.id}`} className={item.id === section ? "is-active" : ""}>
            {item.label}
          </Link>
        ))}
        <span className="explore-tab-note">All categories shown</span>
        <span className="explore-tab-spacer" />
        <select aria-label="Explore filter" value={activeFilter} onChange={(event) => setActiveFilter(event.target.value as typeof activeFilter)}>
          <option value="all">All Records</option>
          <option value="high-confidence">High Confidence</option>
          <option value="missing-owner">Missing Owner</option>
          <option value="recent">Updated This Week</option>
        </select>
        <button type="button" onClick={() => { setQuery(""); setActiveFilter("all"); }}><Icon name="saved" /> Reset View</button>
      </nav>

      <main className="explore-grid">
        <div className="explore-left-column">
          <section className="explore-main-card">
            <div className="explore-card-head">
              <h2>{sections.find((item) => item.id === section)?.label.toUpperCase()}</h2>
              <span>{formatNumber(sectionCount)} results</span>
            </div>
            {error ? <div className="explore-empty-row">Unable to load Explore data: {error}</div> : <DataTable columns={columns} rows={rows} />}
            <div className="explore-pagination">
              <button type="button" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>‹</button>
              <b>{page}</b>
              <span>of</span>
              <span>{totalPages}</span>
              <button type="button" disabled={page === totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>›</button>
            </div>
          </section>
          <SuggestedSearches section={section} onPick={setQuery} />
        </div>
      </main>
      {selected ? (
        <DetailPanel
          key={selected.id}
          entity={selected}
          connected={connected}
          graphIndex={graphIndex}
          onClose={() => setSelectedId(null)}
        />
      ) : null}
    </div>
  );
}
