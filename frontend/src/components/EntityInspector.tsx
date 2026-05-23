import { useEffect, useMemo, useState, type ReactNode } from "react";

import { CLUSTER_LABELS, isClusterId, type ClusterId } from "@/lib/cluster-layout";
import { superClusterIdForEntity } from "@/lib/cluster-reframe";
import type { BrainEvent } from "@/lib/websocket";
import { useBrainStore, type Edge, type Entity } from "@/state/brain.store";

// HIDDEN-V2: "Activity" (receipt feed) tab removed for YC company-brain positioning. uncomment to restore.
const tabs = ["Overview", "Connections", "Lineage"];

type InspectorReceipt = {
  id?: string;
  receipt_id?: string;
  action_id: string;
  agent_name: string;
  intent?: string;
  target_entity_id?: string | null;
  decision: string;
  policy_id?: string;
  this_hash?: string;
  merkle_root?: string;
  signing_scheme?: string;
  verification_status?: string;
  created_at?: string;
  timestamp?: string | null;
};

type SourceRow = {
  id?: string;
  source_id?: string;
  name?: string;
  display_name?: string;
};

type EntityEdges = {
  incoming: Edge[];
  outgoing: Edge[];
};

type EntityLineage = {
  nodes: Entity[];
  edges: Edge[];
};

type ActivePolicyRule = {
  rule_id: string;
  description: string;
  action: string;
  severity: string;
  mode?: string;
  reason?: string | null;
  metadata?: Record<string, unknown>;
};

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

function titleForEntity(entity: Entity): string {
  for (const key of ["title", "name", "subject", "label", "file_path"]) {
    const value = entity.data?.[key];
    if (typeof value === "string" && value.trim()) return key === "file_path" ? (value.split("/").pop() ?? value) : value;
  }
  return entity.id;
}

function stringField(entity: Entity, keys: string[], fallback = "Unassigned"): string {
  for (const key of keys) {
    const value = entity.data?.[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return fallback;
}

function confidence(entity: Entity): number {
  const direct = entity.composite_importance;
  const nested = entity.data?.composite_importance;
  return Math.max(0, Math.min(1, typeof direct === "number" ? direct : typeof nested === "number" ? nested : 0.72));
}

function criticality(entity: Entity): "Low" | "Med" | "High" {
  const raw = stringField(entity, ["criticality", "severity", "priority"], "").toLowerCase();
  if (raw.includes("high") || raw.includes("critical")) return "High";
  if (raw.includes("med") || confidence(entity) > 0.65) return "Med";
  return "Low";
}

function titleCase(value: string | null | undefined): string {
  if (!value) return "";
  return value.slice(0, 1).toUpperCase() + value.slice(1).toLowerCase();
}

function receiptId(receipt: InspectorReceipt): string | null {
  return receipt.receipt_id ?? receipt.id ?? null;
}

function receiptHash(receipt: InspectorReceipt | null): string | null {
  return receipt?.this_hash ?? receipt?.merkle_root ?? null;
}

export function EntityInspector() {
  const selectedId = useBrainStore((s) => s.selectedId);
  const selectedClusterId = useBrainStore((s) => s.selectedClusterId);
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);
  const select = useBrainStore((s) => s.select);
  const [activeTab, setActiveTab] = useState("Overview");

  const selectedEntity = selectedId ? entities.get(selectedId) : null;
  const cluster = isClusterId(selectedClusterId) ? selectedClusterId : selectedEntity ? superClusterIdForEntity(selectedEntity) : null;
  const open = Boolean(selectedEntity || cluster);

  const connected = useMemo(() => {
    if (!selectedEntity) return [];
    const ids = new Set<string>();
    for (const edge of edges.values()) {
      if (edge.source_id === selectedEntity.id) ids.add(edge.target_id);
      if (edge.target_id === selectedEntity.id) ids.add(edge.source_id);
    }
    return Array.from(ids)
      .map((id) => entities.get(id))
      .filter((item): item is Entity => Boolean(item))
      .slice(0, 10);
  }, [edges, entities, selectedEntity]);

  const clusterEntities = useMemo(() => {
    if (!cluster) return [];
    return Array.from(entities.values())
      .filter((entity) => superClusterIdForEntity(entity) === cluster)
      .slice(0, 80);
  }, [cluster, entities]);

  return (
    <aside
      className={`fixed right-0 top-0 z-40 h-screen w-[360px] border-l border-[#274057]/70 bg-[#06101b]/86 font-mono text-[#E8F0FF] shadow-[-22px_0_70px_rgba(0,0,0,0.38)] backdrop-blur-xl transition-transform duration-300 ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      {selectedEntity ? (
        <EntityView entity={selectedEntity} connected={connected} onSelect={select} activeTab={activeTab} setActiveTab={setActiveTab} />
      ) : cluster ? (
        <ClusterView cluster={cluster} entities={clusterEntities} onSelect={select} />
      ) : null}
    </aside>
  );
}

function EntityView({
  entity,
  connected,
  onSelect,
  activeTab,
  setActiveTab,
}: {
  entity: Entity;
  connected: Entity[];
  onSelect: (id: string | null) => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
}) {
  const conf = confidence(entity);
  const [receipts, setReceipts] = useState<InspectorReceipt[]>([]);
  const [receiptDetail, setReceiptDetail] = useState<InspectorReceipt | null>(null);
  const [sourceName, setSourceName] = useState<string | null>(null);
  const [entityEdges, setEntityEdges] = useState<EntityEdges>({ incoming: [], outgoing: [] });
  const [lineage, setLineage] = useState<EntityLineage>({ nodes: [], edges: [] });
  const [activePolicies, setActivePolicies] = useState<ActivePolicyRule[]>([]);
  const latestReceipt = receipts[0] ?? null;
  const root = receiptHash(receiptDetail) ?? receiptHash(latestReceipt);
  const policyStatus = latestReceipt ? titleCase(latestReceipt.decision) : "No policy decisions yet.";
  const signatureStatus = latestReceipt ? receiptDetail?.verification_status ?? "Checking..." : "No receipts yet.";
  const dataSourceLabel = sourceName ?? entity.source_id ?? "No source recorded.";

  useEffect(() => {
    let cancelled = false;
    setReceipts([]);
    setReceiptDetail(null);
    setSourceName(null);
    setEntityEdges({ incoming: [], outgoing: [] });
    setLineage({ nodes: [], edges: [] });
    setActivePolicies([]);

    async function loadActivePolicies() {
      try {
        const payload = await requestJson<{ rules: ActivePolicyRule[] }>(`/api/internal/policies/active?entity_id=${encodeURIComponent(entity.id)}`);
        if (!cancelled) setActivePolicies(payload.rules ?? []);
      } catch {
        if (!cancelled) setActivePolicies([]);
      }
    }

    async function load() {
      try {
        const receiptPayload = await requestJson<{ receipts: InspectorReceipt[] }>(
          `/api/internal/receipts?target_entity_id=${encodeURIComponent(entity.id)}&limit=20`,
        );
        if (cancelled) return;
        const rows = receiptPayload.receipts ?? [];
        setReceipts(rows);
        const firstReceiptId = rows[0] ? receiptId(rows[0]) : null;
        if (firstReceiptId) {
          try {
            const detail = await requestJson<InspectorReceipt>(`/api/internal/receipts/${firstReceiptId}`);
            if (!cancelled) setReceiptDetail(detail);
          } catch {
            if (!cancelled) setReceiptDetail(rows[0]);
          }
        }
      } catch {
        if (!cancelled) setReceipts([]);
      }

      try {
        const sources = await requestJson<SourceRow[]>("/api/sources");
        if (!cancelled) {
          const source = sources.find((row) => (row.source_id ?? row.id) === entity.source_id);
          setSourceName(source?.display_name ?? source?.name ?? null);
        }
      } catch {
        if (!cancelled) setSourceName(null);
      }

      try {
        const edgePayload = await requestJson<EntityEdges>(`/api/entities/${encodeURIComponent(entity.id)}/edges`);
        if (!cancelled) setEntityEdges(edgePayload);
      } catch {
        if (!cancelled) setEntityEdges({ incoming: [], outgoing: [] });
      }

      try {
        const lineagePayload = await requestJson<EntityLineage>(`/api/entities/${encodeURIComponent(entity.id)}/lineage?depth=2`);
        if (!cancelled) setLineage(lineagePayload);
      } catch {
        if (!cancelled) setLineage({ nodes: [], edges: [] });
      }

      await loadActivePolicies();
    }

    void load();

    function onBrainEvent(event: Event) {
      const detail = (event as CustomEvent<BrainEvent>).detail;
      if (!detail) return;
      if (!["policy_clause_activated", "watchdog_alert_raised", "watchdog_alert_acknowledged", "watchdog_alert_resolved"].includes(detail.type)) return;
      const payload = detail.payload as { entity_id?: string } | undefined;
      if (payload?.entity_id && payload.entity_id !== entity.id) return;
      void loadActivePolicies();
    }

    window.addEventListener("axiom:brain-event", onBrainEvent);
    return () => {
      cancelled = true;
      window.removeEventListener("axiom:brain-event", onBrainEvent);
    };
  }, [entity.id, entity.source_id]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-white/10 p-5">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="break-words text-lg font-semibold tracking-[0.04em] text-[#E8F0FF]">{titleForEntity(entity)}</h2>
            <div className="mt-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.16em]">
              <span className="rounded-full border border-[#00E5D8]/35 bg-[#00E5D8]/10 px-2 py-1 text-[#00E5D8]">{entity.type}</span>
              <span className="rounded-full border border-[#45f0a1]/30 bg-[#45f0a1]/10 px-2 py-1 text-[#45f0a1]">Active</span>
            </div>
          </div>
          <button type="button" className="text-[#E8F0FF]/45 hover:text-[#E8F0FF]" onClick={() => onSelect(null)} aria-label="Close inspector">
            ×
          </button>
        </div>
        <div className="break-all text-xs leading-5 text-[#E8F0FF]/45">
          {entity.id}
          <br />
          owner: {stringField(entity, ["owner", "owner_name", "team"])}
        </div>
      </div>
      <div className="flex border-b border-white/10 px-4">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            className={`px-2 py-3 text-[11px] ${activeTab === tab ? "text-[#00E5D8]" : "text-[#E8F0FF]/45 hover:text-[#E8F0FF]/80"}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {activeTab === "Overview" ? (
          <div className="space-y-6">
            <Section title="Overview">
              <p className="text-sm leading-6 text-[#E8F0FF]/68">{stringField(entity, ["description", "summary", "body"], "No description provided by source data.")}</p>
              <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                <Fact label="Owner" value={stringField(entity, ["owner", "owner_name"])} />
                <Fact label="Team" value={stringField(entity, ["team", "department"])} />
                <Fact label="Criticality" value={criticality(entity)} />
                <Fact label="Updated" value={new Date(entity.updated_at).toLocaleDateString()} />
              </div>
              <div className="mt-4">
                <div className="mb-2 flex justify-between text-xs text-[#E8F0FF]/50">
                  <span>Confidence</span>
                  <span>{Math.round(conf * 100)}%</span>
                </div>
                <div className="h-2 rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-[#00E5D8] shadow-[0_0_18px_#00E5D8]" style={{ width: `${conf * 100}%` }} />
                </div>
              </div>
            </Section>
            {/* HIDDEN-V2: "Trust & Governance" section (Policy Status, Signed Receipt, Merkle Root, Data Source, Active Policies) removed for YC company-brain positioning. Data-fetching hooks above are kept intact. uncomment to restore.
            <Section title="Trust & Governance">
              <Fact label="Policy Status" value={policyStatus} />
              <Fact label="Signed Receipt" value={signatureStatus} />
              <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-[#E8F0FF]/38">Merkle Root</div>
                <div className="mt-1 flex items-center gap-2 text-xs text-[#E8F0FF]/72">
                  <span className="min-w-0 flex-1 truncate">{root ?? "No receipts yet."}</span>
                  {root ? (
                    <button type="button" className="text-[#00E5D8]" onClick={() => void navigator.clipboard?.writeText(root)}>
                      copy
                    </button>
                  ) : null}
                </div>
              </div>
              <div className="mt-3 text-xs text-[#E8F0FF]/55">Data Source: {dataSourceLabel}</div>
              <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-[#E8F0FF]/38">Active Policies</div>
                <div className="mt-2 space-y-2">
                  {activePolicies.length ? activePolicies.map((rule) => (
                    <div key={rule.rule_id} className="rounded-lg border border-white/10 bg-white/[0.03] p-2">
                      <div className="flex items-center justify-between gap-2 text-xs text-[#E8F0FF]/78">
                        <span className="min-w-0 truncate">{rule.rule_id}</span>
                        <span className="shrink-0 text-[10px] uppercase tracking-[0.12em] text-[#ffbf3d]">{rule.action}</span>
                      </div>
                      <div className="mt-1 text-xs text-[#E8F0FF]/45">{rule.reason ?? rule.description}</div>
                    </div>
                  )) : <div className="text-xs text-[#E8F0FF]/45">No active policy clauses.</div>}
                </div>
              </div>
            </Section>
            */}
            <Section title="Connected Entities">
              <div className="space-y-2">
                {connected.map((item) => (
                  <button key={item.id} type="button" className="w-full rounded-xl border border-white/10 bg-white/[0.03] p-3 text-left hover:border-[#00E5D8]/35" onClick={() => onSelect(item.id)}>
                    <div className="truncate text-sm text-[#E8F0FF]/82">{titleForEntity(item)}</div>
                    <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-[#E8F0FF]/38">{item.type}</div>
                  </button>
                ))}
                {connected.length === 0 && <div className="text-sm text-[#E8F0FF]/45">No visible connected entities.</div>}
              </div>
            </Section>
          </div>
        ) : activeTab === "Connections" ? (
          <ConnectionsTab edges={entityEdges} />
        ) : activeTab === "Lineage" ? (
          <LineageTab lineage={lineage} />
        ) : (
          <ActivityTab receipts={receipts} />
        )}
      </div>
    </div>
  );
}

function ConnectionsTab({ edges }: { edges: EntityEdges }) {
  const rows = [
    ...edges.incoming.map((edge) => ({ ...edge, direction: "Incoming" })),
    ...edges.outgoing.map((edge) => ({ ...edge, direction: "Outgoing" })),
  ];
  return (
    <Section title="Connections">
      <div className="space-y-2">
        {rows.map((edge) => (
          <div key={`${edge.direction}:${edge.id}`} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <div className="flex items-center justify-between gap-3 text-sm text-[#E8F0FF]/80">
              <span>{edge.relationship}</span>
              <span className="text-[10px] uppercase tracking-[0.14em] text-[#00E5D8]/70">{edge.direction}</span>
            </div>
            <div className="mt-2 break-all text-xs text-[#E8F0FF]/45">{edge.source_id} {"->"} {edge.target_id}</div>
          </div>
        ))}
        {rows.length === 0 ? <div className="text-sm text-[#E8F0FF]/45">No recorded edges for this entity.</div> : null}
      </div>
    </Section>
  );
}

function LineageTab({ lineage }: { lineage: EntityLineage }) {
  return (
    <div className="space-y-6">
      <Section title="Lineage Nodes">
        <div className="space-y-2">
          {lineage.nodes.map((node) => (
            <div key={node.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <div className="truncate text-sm text-[#E8F0FF]/82">{titleForEntity(node)}</div>
              <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-[#E8F0FF]/38">{node.type}</div>
            </div>
          ))}
          {lineage.nodes.length === 0 ? <div className="text-sm text-[#E8F0FF]/45">No lineage nodes found.</div> : null}
        </div>
      </Section>
      <Section title="Lineage Edges">
        <div className="space-y-2">
          {lineage.edges.map((edge) => (
            <div key={edge.id} className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="text-sm text-[#E8F0FF]/78">{edge.id}</div>
              <div className="mt-1 text-xs text-[#E8F0FF]/45">{edge.source_id} {"->"} {edge.target_id} · {edge.relationship}</div>
            </div>
          ))}
          {lineage.edges.length === 0 ? <div className="text-sm text-[#E8F0FF]/45">No lineage edges found.</div> : null}
        </div>
      </Section>
    </div>
  );
}

function ActivityTab({ receipts }: { receipts: InspectorReceipt[] }) {
  return (
    <Section title="Receipt Activity">
      <div className="space-y-2">
        {receipts.map((receipt) => (
          <div key={receiptId(receipt) ?? receipt.action_id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <div className="flex items-center justify-between gap-3 text-sm text-[#E8F0FF]/80">
              <span>{receipt.action_id}</span>
              <span className="text-[10px] uppercase tracking-[0.14em] text-[#00E5D8]/70">{receipt.decision}</span>
            </div>
            <div className="mt-1 text-xs text-[#E8F0FF]/45">{receipt.agent_name}{receipt.intent ? ` · ${receipt.intent}` : ""}</div>
          </div>
        ))}
        {receipts.length === 0 ? <div className="text-sm text-[#E8F0FF]/45">No receipts yet.</div> : null}
      </div>
    </Section>
  );
}

function ClusterView({ cluster, entities, onSelect }: { cluster: ClusterId; entities: Entity[]; onSelect: (id: string | null) => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-white/10 p-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-[#00E5D8]/70">Cluster</div>
            <h2 className="mt-2 text-xl font-semibold uppercase tracking-[0.12em]">{CLUSTER_LABELS[cluster]}</h2>
            <div className="mt-2 text-sm text-[#E8F0FF]/50">{entities.length.toLocaleString()} visible entities</div>
          </div>
          <button type="button" className="text-[#E8F0FF]/45 hover:text-[#E8F0FF]" onClick={() => onSelect(null)} aria-label="Close inspector">
            ×
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        <div className="space-y-2">
          {entities.map((entity) => (
            <button key={entity.id} type="button" className="w-full rounded-xl border border-white/10 bg-white/[0.03] p-3 text-left hover:border-[#00E5D8]/35" onClick={() => onSelect(entity.id)}>
              <div className="truncate text-sm text-[#E8F0FF]/82">{titleForEntity(entity)}</div>
              <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-[#E8F0FF]/38">{entity.type}</div>
            </button>
          ))}
          {entities.length === 0 && <div className="text-sm text-[#E8F0FF]/45">No backend entities mapped to this cluster yet.</div>}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-3 text-[11px] uppercase tracking-[0.18em] text-[#E8F0FF]/42">{title}</h3>
      {children}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="text-[10px] uppercase tracking-[0.16em] text-[#E8F0FF]/38">{label}</div>
      <div className="mt-1 truncate text-sm text-[#E8F0FF]/74">{value}</div>
    </div>
  );
}
