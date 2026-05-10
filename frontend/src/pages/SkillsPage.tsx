import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  archiveSkill,
  listSkillRuns,
  listSkills,
  registerSkill,
  type Skill,
  type SkillRun,
} from "@/lib/skillsClient";
import type { BrainEvent } from "@/lib/websocket";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString();
}

function Icon({ name }: { name: "plus" | "x" | "archive" }) {
  const common = { stroke: "currentColor", strokeWidth: 1.8, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" className="agents-icon" aria-hidden="true">
      {name === "plus" && <path {...common} d="M12 5v14M5 12h14" />}
      {name === "x" && <path {...common} d="M6 6l12 12M18 6 6 18" />}
      {name === "archive" && <path {...common} d="M4 7h16M6 7v13h12V7M9 11h6M5 4h14v3H5V4Z" />}
    </svg>
  );
}

function Pill({ children, tone = "blue" }: { children: ReactNode; tone?: "blue" | "green" | "amber" | "red" }) {
  return <span className={cx("agents-pill", `agents-${tone}`)}>{children}</span>;
}

function EmptyState({ children }: { children: ReactNode }) {
  return <div className="agents-empty">{children}</div>;
}

type SkillForm = {
  name: string;
  description: string;
  intent: string;
  prompt_template: string;
  llm_provider: string;
  llm_model: string;
  scope_clusters: string;
};

const blankForm: SkillForm = {
  name: "",
  description: "",
  intent: "summarize",
  prompt_template: "",
  llm_provider: "openai",
  llm_model: "gpt-4o-mini",
  scope_clusters: "*",
};

export function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [runs, setRuns] = useState<Record<string, SkillRun[]>>({});
  const [selected, setSelected] = useState<Skill | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<SkillForm>(blankForm);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const rows = await listSkills();
    setSkills(rows);
    const runPairs = await Promise.all(rows.slice(0, 20).map(async (skill) => [skill.id, await listSkillRuns(skill.id).catch(() => [])] as const));
    setRuns(Object.fromEntries(runPairs));
  }

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof Error ? err.message : "Unable to load skills"));
  }, []);

  useEffect(() => {
    function onBrainEvent(event: Event) {
      const detail = (event as CustomEvent<BrainEvent>).detail;
      if (!detail) return;
      const payload = detail.payload as { skill?: Skill; run?: SkillRun };
      if (detail.type === "skill_registered" && payload.skill) {
        setSkills((current) => [payload.skill!, ...current.filter((skill) => skill.id !== payload.skill!.id)]);
      }
      if (detail.type === "skill_archived" && payload.skill) {
        setSkills((current) => current.map((skill) => (skill.id === payload.skill!.id ? payload.skill! : skill)));
      }
      if ((detail.type === "skill_run_started" || detail.type === "skill_run_completed") && payload.run) {
        setRuns((current) => ({
          ...current,
          [payload.run!.skill_id]: [
            payload.run!,
            ...(current[payload.run!.skill_id] ?? []).filter((run) => run.id !== payload.run!.id),
          ],
        }));
      }
    }
    window.addEventListener("axiom:brain-event", onBrainEvent);
    return () => window.removeEventListener("axiom:brain-event", onBrainEvent);
  }, []);

  const filteredSkills = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return skills;
    return skills.filter((skill) =>
      [skill.name, skill.intent, skill.llm_provider, skill.llm_model, skill.status]
        .some((value) => value.toLowerCase().includes(needle)),
    );
  }, [filter, skills]);

  const formValid =
    form.name.trim() &&
    form.intent.trim() &&
    form.prompt_template.trim() &&
    form.llm_provider.trim() &&
    form.llm_model.trim();

  async function submitSkill(event: FormEvent) {
    event.preventDefault();
    if (!formValid) return;
    const created = await registerSkill({
      name: form.name,
      description: form.description,
      intent: form.intent,
      prompt_template: form.prompt_template,
      llm_provider: form.llm_provider,
      llm_model: form.llm_model,
      trigger_config: { scope_clusters: form.scope_clusters.split(",").map((item) => item.trim()).filter(Boolean) },
    });
    setSkills((current) => [created, ...current.filter((skill) => skill.id !== created.id)]);
    setModalOpen(false);
    setForm(blankForm);
  }

  async function archiveSelected(skill: Skill) {
    if (!window.confirm(`Archive ${skill.name}?`)) return;
    const archived = await archiveSkill(skill.id);
    setSkills((current) => current.map((item) => (item.id === archived.id ? archived : item)));
    setSelected(archived);
  }

  return (
    <div className="agents-stage">
      <header className="agents-topbar">
        <div className="agents-title-block">
          <h1>Skills</h1>
          <p>Registered prompt skills, provider routing, run history, and archive controls.</p>
        </div>
        <button type="button" className="agents-primary" onClick={() => setModalOpen(true)}>
          <Icon name="plus" /> Register Skill
        </button>
      </header>

      <main className="agents-content">
        {error ? <EmptyState>Unable to load skills: {error}</EmptyState> : null}
        <section className="agents-panel">
          <div className="agents-panel-head">
            <h2>Skills <span>{filteredSkills.length}</span></h2>
            <label className="agents-search">
              <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter skills" />
            </label>
          </div>
          <div className="agents-table skills-table">
            <div className="agents-table-head">
              <span>Name</span>
              <span>Intent</span>
              <span>Provider / Model</span>
              <span>Status</span>
              <span>Runs 24h</span>
              <span>Actions</span>
            </div>
            {filteredSkills.length ? filteredSkills.map((skill) => (
              <div className="agents-table-row" key={skill.id}>
                <span>{skill.name}</span>
                <span>{skill.intent}</span>
                <span>{skill.llm_provider}/{skill.llm_model}</span>
                <span><Pill tone={skill.status === "active" ? "green" : skill.status === "archived" ? "red" : "amber"}>{skill.status}</Pill></span>
                <span>{(runs[skill.id] ?? []).filter((run) => Date.now() - new Date(run.run_at).getTime() <= 86_400_000).length}</span>
                <span><button type="button" className="agents-link-button" onClick={() => setSelected(skill)}>Open</button></span>
              </div>
            )) : <EmptyState>No skills registered yet.</EmptyState>}
          </div>
        </section>
      </main>

      {modalOpen ? (
        <div className="agents-modal-backdrop">
          <form className="agents-modal" aria-label="Register Skill" onSubmit={submitSkill}>
            <div className="agents-modal-head">
              <h2>Register Skill</h2>
              <button type="button" aria-label="Close" onClick={() => setModalOpen(false)}><Icon name="x" /></button>
            </div>
            <label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
            <label>Description<input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
            <label>Intent<select value={form.intent} onChange={(event) => setForm({ ...form, intent: event.target.value })}>
              {["classify", "summarize", "extract", "transform", "monitor"].map((intent) => <option key={intent}>{intent}</option>)}
            </select></label>
            <label>Prompt Template<textarea value={form.prompt_template} onChange={(event) => setForm({ ...form, prompt_template: event.target.value })} /></label>
            <label>Provider<input value={form.llm_provider} onChange={(event) => setForm({ ...form, llm_provider: event.target.value })} /></label>
            <label>Model<input value={form.llm_model} onChange={(event) => setForm({ ...form, llm_model: event.target.value })} /></label>
            <label>Scope Clusters<input value={form.scope_clusters} onChange={(event) => setForm({ ...form, scope_clusters: event.target.value })} /></label>
            <button type="submit" className="agents-primary" disabled={!formValid}>Register</button>
          </form>
        </div>
      ) : null}

      {selected ? (
        <aside className="agents-drawer" aria-label="Skill details">
          <div className="agents-modal-head">
            <h2>{selected.name}</h2>
            <button type="button" aria-label="Close details" onClick={() => setSelected(null)}><Icon name="x" /></button>
          </div>
          <Pill tone={selected.status === "archived" ? "red" : "blue"}>{selected.intent}</Pill>
          <h3>Prompt Template</h3>
          <pre className="agents-code-block">{selected.prompt_template}</pre>
          <button type="button" className="agents-secondary" onClick={() => archiveSelected(selected)} disabled={selected.status === "archived"}>
            <Icon name="archive" /> Archive
          </button>
          <h3>Recent Runs</h3>
          {(runs[selected.id] ?? []).length ? runs[selected.id].slice(0, 8).map((run) => (
            <div className="agents-drawer-row" key={run.id}>
              <span>{run.agent_name}</span>
              <b>{run.status}</b>
              <small>{formatTime(run.run_at)}</small>
              <code>{JSON.stringify(run.input_payload)}</code>
              <code>{JSON.stringify(run.output_payload ?? {})}</code>
            </div>
          )) : <EmptyState>No recent runs for this skill.</EmptyState>}
        </aside>
      ) : null}
    </div>
  );
}
