import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  archiveSkill,
  compileSkillsFromProcesses,
  listSkillRuns,
  listSkills,
  registerSkill,
  runSkill,
  uploadSkillMd,
  downloadSkillMd,
  type Skill,
  type CompileSkillItem,
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

function previewJson(value: unknown, max = 160): string {
  const text = JSON.stringify(value ?? {}, null, 2);
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function idempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `run-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function Icon({ name }: { name: "plus" | "x" | "archive" | "play" | "copy" }) {
  const common = { stroke: "currentColor", strokeWidth: 1.8, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" className="agents-icon" aria-hidden="true">
      {name === "plus" && <path {...common} d="M12 5v14M5 12h14" />}
      {name === "x" && <path {...common} d="M6 6l12 12M18 6 6 18" />}
      {name === "archive" && <path {...common} d="M4 7h16M6 7v13h12V7M9 11h6M5 4h14v3H5V4Z" />}
      {name === "play" && <path {...common} d="M8 5v14l11-7L8 5Z" />}
      {name === "copy" && <path {...common} d="M8 8h10v12H8zM5 4h10v3M5 4v12h2" />}
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

type RunField = {
  name: string;
  type: string;
};

type RunFormValue = string | boolean;
type RegisterTab = "upload" | "form";
type ProcessEntity = {
  id: string;
  type: string;
  data?: Record<string, unknown>;
  cluster_id?: string | null;
};
type MdPreview = {
  name: string;
  description: string;
  intent: string;
  llm_provider: string;
  llm_model: string;
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

function runFields(skill: Skill): RunField[] {
  const properties = skill.output_schema?.properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) return [];
  return Object.entries(properties as Record<string, unknown>).map(([name, spec]) => ({
    name,
    type: spec && typeof spec === "object" && "type" in spec ? String((spec as { type?: unknown }).type ?? "string") : "string",
  }));
}

function initialRunValues(fields: RunField[]): Record<string, RunFormValue> {
  return Object.fromEntries(fields.map((field) => [field.name, field.type === "boolean" ? false : field.type === "object" ? "{}" : ""]));
}

function coerceRunPayload(fields: RunField[], values: Record<string, RunFormValue>, inputJson: string): Record<string, unknown> {
  if (!fields.length) {
    const parsed = JSON.parse(inputJson || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Input JSON must be an object");
    return parsed as Record<string, unknown>;
  }
  return Object.fromEntries(fields.map((field) => {
    const value = values[field.name];
    if (field.type === "number" || field.type === "integer") return [field.name, Number(value || 0)];
    if (field.type === "boolean") return [field.name, Boolean(value)];
    if (field.type === "object") return [field.name, JSON.parse(String(value || "{}"))];
    return [field.name, String(value ?? "")];
  }));
}

function parseSkillMdPreview(content: string): { preview: MdPreview | null; error: string | null } {
  if (!content.trim()) return { preview: null, error: null };
  const lines = content.replace(/\\n/g, "\n").split(/\r?\n/);
  if (lines[0]?.trim() !== "---") return { preview: null, error: "line 1: SKILL.md must start with ---" };
  const end = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (end < 0) return { preview: null, error: "line 1: missing closing ---" };
  const fields: Record<string, string> = {};
  for (let index = 1; index < end; index += 1) {
    const match = /^([a-zA-Z_][\w-]*):\s*(.*)$/.exec(lines[index]);
    if (match) fields[match[1]] = match[2].replace(/^["']|["']$/g, "");
  }
  for (const key of ["name", "description", "intent", "llm_provider", "llm_model"]) {
    if (!fields[key]) return { preview: null, error: `line 2: missing required field ${key}` };
  }
  return {
    preview: {
      name: fields.name,
      description: fields.description,
      intent: fields.intent,
      llm_provider: fields.llm_provider,
      llm_model: fields.llm_model,
    },
    error: null,
  };
}

function processName(entity: ProcessEntity): string {
  const data = entity.data ?? {};
  for (const key of ["name", "title", "label"]) {
    const value = data[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return entity.id;
}

function isSkill(item: CompileSkillItem): item is Skill {
  return typeof item.id === "string" && typeof item.created_at === "string";
}

function dedupeProcesses(rows: ProcessEntity[]): ProcessEntity[] {
  const seen = new Set<string>();
  const unique: ProcessEntity[] = [];
  for (const row of rows) {
    const key = `${processName(row).toLowerCase()}::${row.cluster_id ?? "*"}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(row);
  }
  return unique;
}

type SkillFileSummary = {
  name: string;
  description: string;
  current_version: number;
  validation_status: string;
  updated_at: string;
};

export function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [runs, setRuns] = useState<Record<string, SkillRun[]>>({});
  const [selected, setSelected] = useState<Skill | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [registerTab, setRegisterTab] = useState<RegisterTab>("upload");
  const [runModalSkill, setRunModalSkill] = useState<Skill | null>(null);
  const [form, setForm] = useState<SkillForm>(blankForm);
  const [skillMdContent, setSkillMdContent] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [runValues, setRunValues] = useState<Record<string, RunFormValue>>({});
  const [inputJson, setInputJson] = useState("{}");
  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<SkillRun | null>(null);
  const [lastRunInput, setLastRunInput] = useState<Record<string, unknown> | null>(null);
  const [compileOpen, setCompileOpen] = useState(false);
  const [processes, setProcesses] = useState<ProcessEntity[]>([]);
  const [selectedProcessIds, setSelectedProcessIds] = useState<string[]>([]);
  const [compileDryRun, setCompileDryRun] = useState(false);
  const [compileLoading, setCompileLoading] = useState(false);
  const [compileResults, setCompileResults] = useState<CompileSkillItem[]>([]);
  const [registerLoading, setRegisterLoading] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [skillFiles, setSkillFiles] = useState<SkillFileSummary[]>([]);

  const mdPreview = useMemo(() => parseSkillMdPreview(skillMdContent), [skillMdContent]);

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
    // The SkillFiles list is supplementary to the primary skills table; defer
    // it to a macrotask so it never interleaves with other mount-time loads.
    const timer = setTimeout(() => {
      fetch("/api/internal/skill-files")
        .then((response) => (response.ok ? response.json() : { skill_files: [] }))
        .then((data: { skill_files?: SkillFileSummary[] }) => setSkillFiles(data.skill_files ?? []))
        .catch(() => setSkillFiles([]));
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  function upsertRun(run: SkillRun) {
    setRuns((current) => ({
      ...current,
      [run.skill_id]: [
        run,
        ...(current[run.skill_id] ?? []).filter((item) => item.id !== run.id),
      ],
    }));
  }

  useEffect(() => {
    function onBrainEvent(event: Event) {
      const detail = (event as CustomEvent<BrainEvent>).detail;
      if (!detail) return;
      const payload = detail.payload as { skill?: Skill; run?: SkillRun };
      if ((detail.type === "skill_registered" || detail.type === "skill_compiled") && payload.skill) {
        setSkills((current) => [payload.skill!, ...current.filter((skill) => skill.id !== payload.skill!.id)]);
      }
      if (detail.type === "skill_archived" && payload.skill) {
        setSkills((current) => current.map((skill) => (skill.id === payload.skill!.id ? payload.skill! : skill)));
      }
      if ((detail.type === "skill_run_started" || detail.type === "skill_run_completed" || detail.type === "skill_run_failed") && payload.run) {
        upsertRun(payload.run);
        if (detail.type === "skill_run_failed") setToast(`skill_run_failed: ${payload.run.error_message ?? "run failed"}`);
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

  function openRunModal(skill: Skill, input?: Record<string, unknown>) {
    const fields = runFields(skill);
    setRunModalSkill(skill);
    setRunValues(input ? Object.fromEntries(fields.map((field) => [field.name, field.type === "boolean" ? Boolean(input[field.name]) : field.type === "object" ? JSON.stringify(input[field.name] ?? {}, null, 2) : String(input[field.name] ?? "")])) : initialRunValues(fields));
    setInputJson(input ? JSON.stringify(input, null, 2) : "{}");
    setRunError(null);
    setRunResult(null);
    setLastRunInput(input ?? null);
  }

  async function executeRun(skill: Skill, input: Record<string, unknown>) {
    setRunLoading(true);
    setRunError(null);
    setLastRunInput(input);
    try {
      const result = await runSkill(skill.id, input, idempotencyKey());
      upsertRun(result.run);
      setRunResult(result.run);
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Skill run failed");
    } finally {
      setRunLoading(false);
    }
  }

  async function submitRun(event: FormEvent) {
    event.preventDefault();
    if (!runModalSkill) return;
    try {
      await executeRun(runModalSkill, coerceRunPayload(runFields(runModalSkill), runValues, inputJson));
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Invalid input");
    }
  }

  async function submitSkillMd(event: FormEvent) {
    event.preventDefault();
    if (mdPreview.error || !mdPreview.preview || registerLoading) return;
    setRegisterError(null);
    setRegisterLoading(true);
    try {
      const created = await uploadSkillMd(skillMdContent);
      setSkills((current) => [created, ...current.filter((skill) => skill.id !== created.id)]);
      setModalOpen(false);
      setSkillMdContent("");
      setRegisterTab("upload");
    } catch (err) {
      setRegisterError(err instanceof Error ? err.message : "Unable to register SKILL.md");
    } finally {
      setRegisterLoading(false);
    }
  }

  async function submitSkill(event: FormEvent) {
    event.preventDefault();
    if (!formValid || registerLoading) return;
    setRegisterError(null);
    setRegisterLoading(true);
    try {
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
    } catch (err) {
      setRegisterError(err instanceof Error ? err.message : "Unable to register skill");
    } finally {
      setRegisterLoading(false);
    }
  }

  async function openCompileModal() {
    setCompileOpen(true);
    setCompileResults([]);
    setCompileError(null);
    try {
      const response = await fetch("/api/entities?type=process");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const rows = dedupeProcesses((await response.json()) as ProcessEntity[]);
      setProcesses(rows);
      setSelectedProcessIds(rows.map((row) => row.id));
    } catch (err) {
      setProcesses([]);
      setSelectedProcessIds([]);
      setCompileError(err instanceof Error ? err.message : "Unable to load process entities");
    }
  }

  async function submitCompile(event: FormEvent) {
    event.preventDefault();
    setCompileLoading(true);
    setCompileError(null);
    try {
      const result = await compileSkillsFromProcesses({
        dryRun: compileDryRun,
        processIds: selectedProcessIds,
      });
      setCompileResults(result.compiled);
      if (!result.dry_run) {
        const compiledSkills = result.compiled.filter(isSkill);
        setSkills((current) => [
          ...compiledSkills,
          ...current.filter((skill) => !compiledSkills.some((compiled) => compiled.id === skill.id)),
        ]);
      }
      setToast(result.dry_run ? `Dry run produced ${result.count} skill manifest${result.count === 1 ? "" : "s"}` : `Compiled ${result.count} skill${result.count === 1 ? "" : "s"}`);
    } catch (err) {
      setCompileError(err instanceof Error ? err.message : "Unable to compile skills");
    } finally {
      setCompileLoading(false);
    }
  }

  async function downloadSelectedSkillMd(skill: Skill) {
    const content = await downloadSkillMd(skill.id);
    setToast(`Downloaded SKILL.md for ${skill.name}`);
    void navigator.clipboard?.writeText(content);
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
        <div className="agents-panel-head">
          <button type="button" className="agents-secondary" onClick={() => void openCompileModal()}>
            Compile from Processes
          </button>
          <button type="button" className="agents-primary" onClick={() => { setRegisterError(null); setModalOpen(true); }}>
            <Icon name="plus" /> Register Skill
          </button>
        </div>
      </header>

      <main className="agents-content">
        {error ? <EmptyState>Unable to load skills: {error}</EmptyState> : null}
        {toast ? <div className="agents-empty" role="status">{toast}</div> : null}
        {skillFiles.length > 0 ? (
          <section className="agents-panel">
            <div className="agents-panel-head">
              <h2>Workflow SkillFiles <span>{skillFiles.length}</span></h2>
            </div>
            <p className="mb-3 text-sm text-white/55">
              Executable YAML workflows that codify how your company handles recurring
              decisions — editable by the team, no engineer needed.
            </p>
            <div className="flex flex-col gap-2">
              {skillFiles.map((file) => (
                <a
                  key={file.name}
                  href={`/skills/${file.name}`}
                  className="block rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 transition-colors hover:border-white/20 hover:bg-white/[0.06]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-sm text-cyan-300">{file.name}</span>
                    <span className="flex items-center gap-3 text-xs">
                      <span className="text-white/40">v{file.current_version}</span>
                      <span className={file.validation_status === "valid" ? "text-emerald-400" : "text-red-400"}>
                        {file.validation_status === "valid" ? "✓ valid" : "⚠ invalid"}
                      </span>
                    </span>
                  </div>
                  {file.description ? (
                    <p className="mt-1 text-sm text-white/65">{file.description}</p>
                  ) : null}
                </a>
              ))}
            </div>
          </section>
        ) : null}
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
                <span>
                  <button type="button" className="agents-link-button" onClick={() => setSelected(skill)}>Open</button>
                  <button type="button" className="agents-link-button" aria-label={`Run ${skill.name}`} onClick={() => openRunModal(skill)}>
                    Run
                  </button>
                </span>
              </div>
            )) : <EmptyState>No skills registered yet.</EmptyState>}
          </div>
        </section>
      </main>

      {compileOpen ? (
        <div className="agents-modal-backdrop">
          <form className="agents-modal" aria-label="Compile from Processes" onSubmit={submitCompile}>
            <div className="agents-modal-head">
              <h2>Compile from Processes</h2>
              <button type="button" aria-label="Close compile modal" onClick={() => setCompileOpen(false)}><Icon name="x" /></button>
            </div>
            <label>
              <input type="checkbox" checked={compileDryRun} onChange={(event) => setCompileDryRun(event.target.checked)} />
              Dry run
            </label>
            <div className="agents-table">
              <div className="agents-table-head">
                <span>Use</span>
                <span>Process</span>
                <span>Cluster</span>
              </div>
              {processes.length ? processes.map((process) => (
                <label className="agents-table-row" key={process.id}>
                  <span><input type="checkbox" checked={selectedProcessIds.includes(process.id)} onChange={(event) => {
                    setSelectedProcessIds((current) => event.target.checked ? [...current, process.id] : current.filter((id) => id !== process.id));
                  }} /></span>
                  <span>{processName(process)}</span>
                  <span>{process.cluster_id ?? "*"}</span>
                </label>
              )) : <EmptyState>No process entities found.</EmptyState>}
            </div>
            {compileError ? <p className="agents-error" role="alert">{compileError}</p> : null}
            <button type="submit" className="agents-primary" disabled={compileLoading || selectedProcessIds.length === 0}>
              {compileLoading ? "Compiling..." : "Compile"}
            </button>
            {compileResults.length ? (
              <div className="agents-table">
                <div className="agents-table-head">
                  <span>Skill</span>
                  <span>Intent</span>
                  <span>Status</span>
                </div>
                {compileResults.map((item) => (
                  <div className="agents-table-row" key={`${item.id ?? item.name}`}>
                    <span>{item.name}</span>
                    <span>{item.intent ?? "transform"}</span>
                    <span>{compileDryRun ? "dry_run" : "compiled"}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </form>
        </div>
      ) : null}

      {modalOpen ? (
        <div className="agents-modal-backdrop">
          <form className="agents-modal" aria-label="Register Skill" onSubmit={registerTab === "upload" ? submitSkillMd : submitSkill}>
            <div className="agents-modal-head">
              <h2>Register Skill</h2>
              <button type="button" aria-label="Close" onClick={() => setModalOpen(false)}><Icon name="x" /></button>
            </div>
            <div className="agents-panel-head">
              <button type="button" className={registerTab === "upload" ? "agents-primary" : "agents-secondary"} onClick={() => setRegisterTab("upload")}>Upload SKILL.md</button>
              <button type="button" className={registerTab === "form" ? "agents-primary" : "agents-secondary"} onClick={() => setRegisterTab("form")}>Form</button>
            </div>
            {registerTab === "upload" ? (
              <>
                <div
                  className="agents-empty"
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    event.preventDefault();
                    const file = event.dataTransfer.files[0];
                    if (file) void file.text().then(setSkillMdContent);
                  }}
                >
                  Drop a SKILL.md file here or paste content below.
                </div>
                <label>SKILL.md content<textarea value={skillMdContent} onChange={(event) => setSkillMdContent(event.target.value)} /></label>
                {mdPreview.error ? <p className="agents-error">{mdPreview.error}</p> : null}
                {mdPreview.preview ? (
                  <div className="agents-drawer-row">
                    <b>{mdPreview.preview.name}</b>
                    <span>{mdPreview.preview.description}</span>
                    <Pill>{mdPreview.preview.intent}</Pill>
                    <code>{mdPreview.preview.llm_provider} / {mdPreview.preview.llm_model}</code>
                  </div>
                ) : null}
                {registerError ? <p className="agents-error" role="alert">{registerError}</p> : null}
                <button type="submit" className="agents-primary" disabled={!mdPreview.preview || Boolean(mdPreview.error) || registerLoading}>{registerLoading ? "Registering..." : "Register SKILL.md"}</button>
              </>
            ) : (
              <>
                <label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
                <label>Description<input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
                <label>Intent<select value={form.intent} onChange={(event) => setForm({ ...form, intent: event.target.value })}>
                  {["classify", "summarize", "extract", "transform", "monitor"].map((intent) => <option key={intent}>{intent}</option>)}
                </select></label>
                <label>Prompt Template<textarea value={form.prompt_template} onChange={(event) => setForm({ ...form, prompt_template: event.target.value })} /></label>
                <label>Provider<input value={form.llm_provider} onChange={(event) => setForm({ ...form, llm_provider: event.target.value })} /></label>
                <label>Model<input value={form.llm_model} onChange={(event) => setForm({ ...form, llm_model: event.target.value })} /></label>
                <label>Scope Clusters<input value={form.scope_clusters} onChange={(event) => setForm({ ...form, scope_clusters: event.target.value })} /></label>
                {registerError ? <p className="agents-error" role="alert">{registerError}</p> : null}
                <button type="submit" className="agents-primary" disabled={!formValid || registerLoading}>{registerLoading ? "Registering..." : "Register"}</button>
              </>
            )}
          </form>
        </div>
      ) : null}

      {runModalSkill ? (
        <div className="agents-modal-backdrop">
          <form className="agents-modal" aria-label={`Run ${runModalSkill.name}`} onSubmit={submitRun}>
            <div className="agents-modal-head">
              <h2>Run {runModalSkill.name}</h2>
              <button type="button" aria-label="Close run modal" onClick={() => setRunModalSkill(null)}><Icon name="x" /></button>
            </div>
            {runFields(runModalSkill).length ? runFields(runModalSkill).map((field) => (
              <label key={field.name}>{field.name}
                {field.type === "boolean" ? (
                  <input type="checkbox" checked={Boolean(runValues[field.name])} onChange={(event) => setRunValues({ ...runValues, [field.name]: event.target.checked })} />
                ) : field.type === "object" ? (
                  <textarea value={String(runValues[field.name] ?? "{}") } onChange={(event) => setRunValues({ ...runValues, [field.name]: event.target.value })} />
                ) : (
                  <input type={field.type === "number" || field.type === "integer" ? "number" : "text"} value={String(runValues[field.name] ?? "")} onChange={(event) => setRunValues({ ...runValues, [field.name]: event.target.value })} />
                )}
              </label>
            )) : (
              <label>Input JSON<textarea value={inputJson} onChange={(event) => setInputJson(event.target.value)} /></label>
            )}
            <button type="submit" className="agents-primary" disabled={runLoading}>{runLoading ? "Running..." : "Run Skill"}</button>
            {runError ? <p className="agents-error">{runError}</p> : null}
            {runError && lastRunInput ? <button type="button" className="agents-secondary" onClick={() => executeRun(runModalSkill, lastRunInput)}>Retry</button> : null}
            {runResult ? (
              <div className="agents-drawer-row">
                <b>Run ID {runResult.id}</b>
                <Pill tone={runResult.status === "success" ? "green" : runResult.status === "failed" ? "red" : "amber"}>{runResult.status}</Pill>
                <pre className="agents-code-block">{previewJson(runResult.output_payload ?? { error: runResult.error_message })}</pre>
                <button type="button" className="agents-secondary" onClick={() => navigator.clipboard?.writeText(previewJson(runResult.output_payload ?? {}))}>
                  <Icon name="copy" /> Copy output
                </button>
              </div>
            ) : null}
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
          <button type="button" className="agents-secondary" onClick={() => downloadSelectedSkillMd(selected)}>
            <Icon name="copy" /> Download SKILL.md
          </button>
          <h3>Recent Runs</h3>
          {(runs[selected.id] ?? []).length ? runs[selected.id].slice(0, 8).map((run) => (
            <div className="agents-drawer-row" key={run.id}>
              <span>{run.agent_name}</span>
              <Pill tone={run.status === "success" ? "green" : run.status === "failed" ? "red" : "amber"}>{run.status}</Pill>
              <small>{formatTime(run.run_at)}</small>
              <code>{previewJson(run.input_payload)}</code>
              <code>{run.error_message ? run.error_message : previewJson(run.output_payload ?? {})}</code>
              <button type="button" className="agents-link-button" onClick={() => executeRun(selected, run.input_payload)}>Re-run with same input</button>
            </div>
          )) : <EmptyState>No recent runs for this skill.</EmptyState>}
        </aside>
      ) : null}
    </div>
  );
}
