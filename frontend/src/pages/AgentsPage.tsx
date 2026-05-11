import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  listAgentReceipts,
  listAgentRegistry,
  passportLabel,
  registerAgent,
  type AgentRegistryRow,
  type ReceiptRow,
} from "@/lib/agentsClient";
import { listPassports, revokePassport, type Passport } from "@/lib/passportsClient";
import { listSkillRuns, listSkills, type SkillRun } from "@/lib/skillsClient";
import type { BrainEvent } from "@/lib/websocket";

function formatTime(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString();
}

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function Icon({ name }: { name: "plus" | "x" | "shield" | "receipt" }) {
  const common = { stroke: "currentColor", strokeWidth: 1.8, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" className="agents-icon" aria-hidden="true">
      {name === "plus" && <path {...common} d="M12 5v14M5 12h14" />}
      {name === "x" && <path {...common} d="M6 6l12 12M18 6 6 18" />}
      {name === "shield" && <path {...common} d="m12 3 7 3v5.5c0 4.2-2.7 7.3-7 9-4.3-1.7-7-4.8-7-9V6l7-3Z" />}
      {name === "receipt" && <path {...common} d="M7 3h10v18l-2-1.2-2 1.2-2-1.2-2 1.2-2-1.2V3Zm3 5h4m-4 4h4m-4 4h3" />}
    </svg>
  );
}

function Pill({ children, tone = "blue" }: { children: ReactNode; tone?: "blue" | "green" | "amber" | "red" }) {
  return <span className={cx("agents-pill", `agents-${tone}`)}>{children}</span>;
}

function EmptyState({ children }: { children: ReactNode }) {
  return <div className="agents-empty">{children}</div>;
}

type AgentForm = {
  name: string;
  agent_class: string;
  owner_email: string;
  passport_id: string;
  issue_new_passport: boolean;
};

const blankForm: AgentForm = {
  name: "",
  agent_class: "",
  owner_email: "",
  passport_id: "",
  issue_new_passport: true,
};

export function AgentsPage() {
  const [agents, setAgents] = useState<AgentRegistryRow[]>([]);
  const [passports, setPassports] = useState<Passport[]>([]);
  const [receipts, setReceipts] = useState<ReceiptRow[]>([]);
  const [skillRuns, setSkillRuns] = useState<SkillRun[]>([]);
  const [selected, setSelected] = useState<AgentRegistryRow | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<AgentForm>(blankForm);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);

  async function load() {
    const [registry, passportRows, skills] = await Promise.all([
      listAgentRegistry(),
      listPassports(),
      listSkills().catch(() => []),
    ]);
    setAgents(registry);
    setPassports(passportRows);
    const runs = await Promise.all(skills.slice(0, 20).map((skill) => listSkillRuns(skill.id).catch(() => [])));
    setSkillRuns(runs.flat());
  }

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof Error ? err.message : "Unable to load agents"));
  }, []);

  useEffect(() => {
    function onBrainEvent(event: Event) {
      const detail = (event as CustomEvent<BrainEvent>).detail;
      if (detail?.type !== "agent_action") return;
      const payload = detail.payload as { agent_name?: string };
      const agentName = payload.agent_name?.trim();
      if (!agentName) return;
      setAgents((current) => {
        const existing = current.find((agent) => agent.agent_name === agentName);
        if (!existing) {
          return [
            {
              agent_name: agentName,
              name: agentName,
              agent_class: "unknown",
              owner_email: null,
              passport_id: null,
              passport_status: "missing",
              first_seen: new Date().toISOString(),
              last_seen: new Date().toISOString(),
              total_actions: 1,
              allow_count: 0,
              correct_count: 0,
              deny_count: 0,
              last_intent: null,
              last_action_id: null,
              agent_type: "external_mcp",
            },
            ...current,
          ];
        }
        return current.map((agent) =>
          agent.agent_name === agentName
            ? { ...agent, total_actions: agent.total_actions + 1, last_seen: new Date().toISOString() }
            : agent,
        );
      });
    }
    window.addEventListener("axiom:brain-event", onBrainEvent);
    return () => window.removeEventListener("axiom:brain-event", onBrainEvent);
  }, []);

  useEffect(() => {
    if (!selected) return;
    listAgentReceipts(selected.agent_name).then(setReceipts).catch(() => setReceipts([]));
  }, [selected]);

  const filteredAgents = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return agents;
    return agents.filter((agent) =>
      [agent.agent_name, agent.agent_class, agent.owner_email, agent.passport_status]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle)),
    );
  }, [agents, filter]);

  const selectedRuns = useMemo(
    () => skillRuns.filter((run) => run.agent_name === selected?.agent_name).slice(0, 8),
    [selected?.agent_name, skillRuns],
  );

  const formValid =
    form.name.trim() &&
    form.agent_class.trim() &&
    form.owner_email.trim().includes("@") &&
    (form.issue_new_passport || form.passport_id);

  async function submitAgent(event: FormEvent) {
    event.preventDefault();
    if (!formValid || registering) return;
    setRegisterError(null);
    setRegistering(true);
    try {
      const created = await registerAgent({
        name: form.name,
        agent_class: form.agent_class,
        owner_email: form.owner_email,
        passport_id: form.issue_new_passport ? null : form.passport_id,
        issue_new_passport: form.issue_new_passport,
        ttl_hours: 24,
      });
      setAgents((current) => [created, ...current.filter((agent) => agent.agent_name !== created.agent_name)]);
      setModalOpen(false);
      setForm(blankForm);
      setPassports(await listPassports());
    } catch (err) {
      setRegisterError(err instanceof Error ? err.message : "Unable to register agent");
    } finally {
      setRegistering(false);
    }
  }

  async function revokeSelectedPassport() {
    if (!selected?.passport_id) return;
    await revokePassport(selected.passport_id);
    await load();
    setSelected((current) => (current ? { ...current, passport_status: "revoked" } : current));
  }

  return (
    <div className="agents-stage">
      <header className="agents-topbar">
        <div className="agents-title-block">
          <h1>Agents</h1>
          <p>Registry, passports, receipts, and skill activity from live backend records.</p>
        </div>
        <button type="button" className="agents-primary" onClick={() => { setRegisterError(null); setModalOpen(true); }}>
          <Icon name="plus" /> Register Agent
        </button>
      </header>

      <main className="agents-content">
        {error ? <EmptyState>Unable to load agents: {error}</EmptyState> : null}
        <section className="agents-panel">
          <div className="agents-panel-head">
            <h2>Registry <span>{filteredAgents.length}</span></h2>
            <label className="agents-search">
              <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter agents" />
            </label>
          </div>
          <div className="agents-table agents-registry-table">
            <div className="agents-table-head">
              <span>Name</span>
              <span>Class</span>
              <span>Owner</span>
              <span>Passport</span>
              <span>Total Actions</span>
              <span>Last Seen</span>
              <span>Actions</span>
            </div>
            {filteredAgents.length ? filteredAgents.map((agent) => (
              <div className="agents-table-row" key={agent.agent_name}>
                <span>{agent.agent_name}</span>
                <span>{agent.agent_class}</span>
                <span>{agent.owner_email ?? "Not recorded"}</span>
                <span><Pill tone={agent.passport_status === "active" ? "green" : "amber"}>{agent.passport_status}</Pill></span>
                <span>{agent.total_actions.toLocaleString()}</span>
                <span>{formatTime(agent.last_seen)}</span>
                <span><button type="button" className="agents-link-button" onClick={() => setSelected(agent)}>Open</button></span>
              </div>
            )) : <EmptyState>No registered agents yet.</EmptyState>}
          </div>
        </section>
      </main>

      {modalOpen ? (
        <div className="agents-modal-backdrop">
          <form className="agents-modal" aria-label="Register Agent" onSubmit={submitAgent}>
            <div className="agents-modal-head">
              <h2>Register Agent</h2>
              <button type="button" aria-label="Close" onClick={() => setModalOpen(false)}><Icon name="x" /></button>
            </div>
            <label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
            <label>Class<input value={form.agent_class} onChange={(event) => setForm({ ...form, agent_class: event.target.value })} /></label>
            <label>Owner Email<input value={form.owner_email} onChange={(event) => setForm({ ...form, owner_email: event.target.value })} /></label>
            <label className="agents-checkbox"><input type="checkbox" checked={form.issue_new_passport} onChange={(event) => setForm({ ...form, issue_new_passport: event.target.checked })} /> Issue new passport</label>
            {!form.issue_new_passport ? (
              <label>Passport<select value={form.passport_id} onChange={(event) => setForm({ ...form, passport_id: event.target.value })}>
                <option value="">Select passport</option>
                {passports.map((passport) => <option key={passport.passport_id} value={passport.passport_id}>{passportLabel(passport)}</option>)}
              </select></label>
            ) : null}
            {registerError ? <p className="agents-error" role="alert">{registerError}</p> : null}
            <button type="submit" className="agents-primary" disabled={!formValid || registering}>{registering ? "Registering..." : "Register"}</button>
          </form>
        </div>
      ) : null}

      {selected ? (
        <aside className="agents-drawer" aria-label="Agent details">
          <div className="agents-modal-head">
            <h2>{selected.agent_name}</h2>
            <button type="button" aria-label="Close details" onClick={() => setSelected(null)}><Icon name="x" /></button>
          </div>
          <div className="agents-drawer-summary">
            <Pill>{selected.agent_class}</Pill>
            <Pill tone={selected.passport_status === "active" ? "green" : "amber"}>{selected.passport_status}</Pill>
            <span>{selected.owner_email ?? "No owner recorded"}</span>
          </div>
          <button type="button" className="agents-secondary" disabled={!selected.passport_id} onClick={revokeSelectedPassport}>
            <Icon name="shield" /> Revoke Passport
          </button>
          <h3>Recent Receipts</h3>
          {receipts.length ? receipts.slice(0, 8).map((receipt) => (
            <div className="agents-drawer-row" key={receipt.receipt_id}>
              <Icon name="receipt" />
              <span>{receipt.intent}</span>
              <b>{receipt.decision}</b>
            </div>
          )) : <EmptyState>No recent receipts for this agent.</EmptyState>}
          <h3>Recent Skills Run</h3>
          {selectedRuns.length ? selectedRuns.map((run) => (
            <div className="agents-drawer-row" key={run.id}>
              <span>{run.skill_id}</span>
              <b>{run.status}</b>
              <small>{formatTime(run.run_at)}</small>
            </div>
          )) : <EmptyState>No recent skill runs for this agent.</EmptyState>}
        </aside>
      ) : null}
    </div>
  );
}
