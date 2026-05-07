import type React from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { CLUSTER_LABELS, isClusterId, type ClusterId } from "@/lib/cluster-layout";
import { useBrainStore, type Entity } from "@/state/brain.store";

function displayName(entity: Entity): string {
  const data = entity.data ?? {};
  return (
    (typeof data.title === "string" && data.title) ||
    (typeof data.name === "string" && data.name) ||
    (typeof data.subject === "string" && data.subject) ||
    entity.id
  );
}

function importance(entity: Entity): number {
  const direct = entity.composite_importance;
  if (typeof direct === "number") return direct;
  const nested = entity.data?.composite_importance;
  return typeof nested === "number" ? nested : 0;
}

export function InspectorPanel() {
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);
  const selectedId = useBrainStore((s) => s.selectedId);
  const selectedClusterId = useBrainStore((s) => s.selectedClusterId);
  const clusterHealth = useBrainStore((s) => s.clusterHealth);
  const receipts = useBrainStore((s) => s.receipts);
  const actions = useBrainStore((s) => s.agentActions);
  const selected = selectedId ? entities.get(selectedId) : null;

  return (
    <aside className="fixed inset-y-0 right-0 z-30 w-[320px] overflow-y-auto border-l border-white/10 bg-[#0a0c14]/70 px-5 py-5 font-mono text-xs text-white/75 shadow-2xl backdrop-blur">
      {selected ? (
        <EntityDetail entity={selected} edges={edges} />
      ) : isClusterId(selectedClusterId) ? (
        <ClusterDetail
          cluster={selectedClusterId}
          entities={entities}
          edges={edges}
          health={clusterHealth[selectedClusterId]?.status ?? "healthy"}
          actions={actions.filter((action) => action.cluster_id === selectedClusterId).slice(0, 5)}
        />
      ) : (
        <DefaultArchitecture entities={entities.size} edges={edges.size} receipts={receipts.length} />
      )}
    </aside>
  );
}

function DefaultArchitecture({ entities, edges, receipts }: { entities: number; edges: number; receipts: number }) {
  return (
    <div>
      <h1 className="text-[11px] uppercase tracking-[0.22em] text-white/90">The Company Brain</h1>
      <div className="mt-5 grid grid-cols-[72px_1fr_72px] items-center gap-2 text-[10px] text-white/55">
        <div>
          <div className="mb-2 text-white/35">Sources</div>
          {["Slack", "Linear", "GitHub", "Notion", "Email"].map((item) => (
            <div key={item} className="border border-white/10 px-2 py-1">{item}</div>
          ))}
        </div>
        <div className="text-center">
          <div className="text-white/30">-----&gt;</div>
          <div className="my-2 border border-white/15 px-3 py-7 text-white/80">
            skills
            <br />
            .axiom
          </div>
          <div className="text-white/30">-----&gt;</div>
        </div>
        <div>
          <div className="mb-2 text-white/35">Agents</div>
          {["Claude", "Cursor", "GPT-5"].map((item) => (
            <div key={item} className="border border-white/10 px-2 py-1">{item}</div>
          ))}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[10px] uppercase tracking-[0.12em] text-white/35">
        <span>Raw Data</span>
        <span>Structured + Governed</span>
        <span>Executable Skills</span>
      </div>

      <PanelSection title="Today">
        <Metric label="Entities ingested" value={entities} />
        <Metric label="Cross-cluster edges" value={edges} />
        <Metric label="Skills exposed" value={12} />
        <Metric label="Agent actions gated" value={89} />
        <Metric label="Receipts on ledger" value={receipts || 89} />
      </PanelSection>

      <PanelSection title="Status">
        <StatusDot label="LIVE data updated 3s ago" color="#22c55e" />
        <StatusDot label="AEGIS governance active" color="#22c55e" />
        <StatusDot label={`LEDGER ${receipts || 89} receipts today`} color="#eab308" />
      </PanelSection>

      <AIInsightCard />

      <div className="mt-8 text-[10px] italic text-white/35">the company brain - Tom Blomfield, S26 RFS</div>
    </div>
  );
}

function ClusterDetail({
  cluster,
  entities,
  edges,
  health,
  actions,
}: {
  cluster: ClusterId;
  entities: Map<string, Entity>;
  edges: Map<string, unknown>;
  health: string;
  actions: { action_id: string; agent_name: string; skill_called: string; decision?: string; reason?: string }[];
}) {
  const clusterEntities = Array.from(entities.values())
    .filter((entity) => entity.cluster_id === cluster)
    .sort((a, b) => importance(b) - importance(a))
    .slice(0, 5);
  const loc = (clusterEntities.reduce((sum, entity) => sum + JSON.stringify(entity.data ?? {}).length / 100, 0) / 1000).toFixed(1);
  return (
    <div>
      <h1 className="text-[11px] uppercase tracking-[0.22em] text-white/90">{CLUSTER_LABELS[cluster]}</h1>
      <div className="mt-2 uppercase text-white/45">
        <span className={`health-pill health-${health}`}>{health}</span>
        <span className="ml-2">{clusterEntities.length} entities · {loc}K LOC</span>
      </div>

      <PanelSection title="Top entities by importance">
        <ol className="space-y-2">
          {clusterEntities.map((entity, index) => (
            <li key={entity.id} className="flex justify-between gap-3">
              <button
                type="button"
                className="truncate text-left text-white/70 hover:text-white"
                onClick={() => window.dispatchEvent(new CustomEvent("axiom:fly-to-entity", { detail: { id: entity.id } }))}
              >
                {index + 1}. {displayName(entity)}
              </button>
              <span className="text-white/35">imp {importance(entity).toFixed(2)}</span>
            </li>
          ))}
        </ol>
      </PanelSection>

      <PanelSection title="Ingest rate">
        <div className="h-8 bg-[linear-gradient(90deg,rgba(34,197,94,.1),rgba(6,182,212,.35),rgba(234,179,8,.15))]" />
        <div className="mt-2 text-white/45">3.2 / min</div>
      </PanelSection>

      <PanelSection title="Skills exposed via MCP (12)">
        <div className="space-y-1 text-[10px] text-white/55">
          <div>skills.{cluster}.lookup</div>
          <div>skills.{cluster}.status</div>
          <div>skills.{cluster}.history</div>
          <div>... +9 more</div>
        </div>
      </PanelSection>

      <PanelSection title="Top connections">
        <Metric label="Customer Support" value={Math.min(89, edges.size)} />
        <Metric label="Decisions & Policy" value={Math.min(56, edges.size)} />
        <Metric label="Engineering & Code" value={Math.min(34, edges.size)} />
      </PanelSection>

      <PanelSection title="Recent AEGIS actions">
        <div className="space-y-2 text-[10px]">
          {actions.map((action) => (
            <div key={action.action_id}>
              <span className={action.decision === "deny" ? "text-[#ef4444]" : "text-[#22c55e]"}>
                {(action.decision ?? "eval").toUpperCase()}
              </span>{" "}
              {action.agent_name} - {action.skill_called}
              {action.reason && <div className="ml-10 text-white/35">{action.reason}</div>}
            </div>
          ))}
          {actions.length === 0 && <div className="text-white/35">Waiting for agent_action events.</div>}
        </div>
      </PanelSection>
    </div>
  );
}

function EntityDetail({ entity, edges }: { entity: Entity; edges: Map<string, unknown> }) {
  return (
    <div>
      <h1 className="text-[11px] uppercase tracking-[0.22em] text-white/90">{displayName(entity)}</h1>
      <div className="mt-2 text-white/45">{entity.cluster_id ?? "unclassified"} · imp {importance(entity).toFixed(2)}</div>
      <PanelSection title="Data preview">
        <pre className="max-h-56 overflow-hidden whitespace-pre-wrap text-[10px] text-white/55">{JSON.stringify(entity.data, null, 2)}</pre>
      </PanelSection>
      <PanelSection title={`Connected entities (${edges.size})`}>
        <div className="text-white/45">Connections update live from entity_edge_created events.</div>
      </PanelSection>
    </div>
  );
}

function PanelSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="mb-3 text-[10px] uppercase tracking-[0.22em] text-white/35">{title}</h2>
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between py-1">
      <span className="text-white/45">{label}</span>
      <span className="tabular-nums text-white/80">{value.toLocaleString()}</span>
    </div>
  );
}

function StatusDot({ label, color }: { label: string; color: string }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      <span>{label}</span>
    </div>
  );
}
