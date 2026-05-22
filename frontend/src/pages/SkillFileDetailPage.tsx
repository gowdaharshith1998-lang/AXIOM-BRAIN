import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { SkillFileBuilder } from "@/components/skill-builder/SkillFileBuilder";
import { compile, decompile, DecompileError } from "@/components/skill-builder/compile";
import type { AnyStepBlock, SkillFileDoc } from "@/components/skill-builder/types";

type SkillFileDetail = {
  name: string;
  yaml_text: string;
  description: string;
  current_version: number;
  validation_status: string;
  validation_errors: string[];
  updated_at: string;
};

type StepResult = {
  step_id: string;
  step_type: string;
  status: string;
  detail: Record<string, unknown>;
};

type RunResult = {
  skill_file_name: string;
  status: "success" | "paused" | "failed";
  approval_id: string | null;
  steps_executed: number;
  step_results: StepResult[];
  final_receipt_id: string | null;
  error: string | null;
};

type EditorMode = "visual" | "yaml_readonly" | "yaml_edit";

const DEFAULT_TRIGGER = JSON.stringify(
  {
    intent: "refund",
    source: "slack",
    payload: { amount: 750, customer_id: "cust_acme_001" },
  },
  null,
  2,
);

function statusTone(status: string): string {
  if (status === "success" || status === "valid" || status === "executed") {
    return "text-emerald-400";
  }
  if (status === "paused") return "text-amber-400";
  if (status === "skipped") return "text-white/40";
  return "text-red-400";
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

// Locate a block by its step id (recurses into if_then.then), so server
// validation errors that name a step can be scoped to the offending block.
function findBlockByStepId(
  blocks: AnyStepBlock[],
  stepId: string,
): AnyStepBlock | null {
  for (const b of blocks) {
    if (b.id === stepId) return b;
    if (b.type === "if_then") {
      const found = findBlockByStepId(b.then, stepId);
      if (found) return found;
    }
  }
  return null;
}

export function SkillFileDetailPage() {
  const { name } = useParams<{ name: string }>();
  const [detail, setDetail] = useState<SkillFileDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [yamlText, setYamlText] = useState("");
  const [editorMode, setEditorMode] = useState<EditorMode>("visual");
  const [doc, setDoc] = useState<SkillFileDoc | null>(null);
  const [decompileError, setDecompileError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [triggerJson, setTriggerJson] = useState(DEFAULT_TRIGGER);
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!name) return;
    fetch(`/api/internal/skill-files/${name}`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data: SkillFileDetail) => {
        setDetail(data);
        setErrors(data.validation_errors ?? []);
      })
      .catch(() => setNotFound(true));
  }, [name]);

  // Whenever the detail (re)loads, decompile its YAML into the block IR. If the
  // hand-rolled reader cannot handle it, fall back to writable YAML mode.
  useEffect(() => {
    if (!detail) return;
    setYamlText(detail.yaml_text);
    try {
      setDoc(decompile(detail.yaml_text));
      setDecompileError(null);
    } catch (err) {
      setDoc(null);
      setDecompileError(
        err instanceof DecompileError ? err.message : String(err),
      );
      setEditorMode("yaml_edit");
    }
  }, [detail]);

  // Live-compiled YAML for the read-only YAML tab. The YAML editor buffer wins
  // while the user is editing it directly.
  const liveYaml = useMemo(() => {
    if (editorMode === "yaml_edit") return yamlText;
    if (!doc) return yamlText;
    try {
      return compile(doc);
    } catch {
      return yamlText;
    }
  }, [doc, editorMode, yamlText]);

  // Scope server validation errors to individual blocks by step id.
  const errorsByLocalId = useMemo<Record<string, string[]>>(() => {
    if (!doc) return {};
    const map: Record<string, string[]> = {};
    for (const err of errors) {
      const stepIdMatch = err.match(/step ['"]?([\w-]+)['"]?/);
      if (stepIdMatch) {
        const localBlock = findBlockByStepId(doc.steps, stepIdMatch[1]);
        if (localBlock) {
          map[localBlock._localId] = [...(map[localBlock._localId] ?? []), err];
        }
      }
    }
    return map;
  }, [doc, errors]);

  const errorsTopLevel = useMemo<string[]>(() => {
    if (!doc) return errors;
    return errors.filter((err) => {
      const stepIdMatch = err.match(/step ['"]?([\w-]+)['"]?/);
      if (!stepIdMatch) return true;
      const localBlock = findBlockByStepId(doc.steps, stepIdMatch[1]);
      return !localBlock || !(localBlock._localId in errorsByLocalId);
    });
  }, [doc, errors, errorsByLocalId]);

  async function handleSave() {
    if (!name) return;
    // Visual mode compiles blocks → YAML; YAML-edit mode uses the textarea.
    const yamlToSave =
      editorMode === "yaml_edit" ? yamlText : doc ? compile(doc) : yamlText;
    setSaveStatus("Saving…");
    try {
      const response = await fetch(`/api/internal/skill-files/${name}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml_text: yamlToSave }),
      });
      const body = await response.json();
      if (body.validation_status === "invalid") {
        setErrors(body.validation_errors ?? []);
        setSaveStatus(`Save failed — version not bumped (still v${body.version})`);
        // KEEP the user's in-memory edits — do not overwrite doc / yamlText.
        return;
      }
      setErrors([]);
      setSaveStatus(`Saved as v${body.version}`);
      // Refresh from server; the decompile effect re-derives doc + yamlText.
      const fresh = await fetch(`/api/internal/skill-files/${name}`).then((r) =>
        r.json(),
      );
      setDetail(fresh);
    } catch (exc) {
      setSaveStatus(`Save failed: ${String(exc)}`);
    }
  }

  async function handleRun() {
    if (!name) return;
    setRunning(true);
    setRunError(null);
    setRunResult(null);
    try {
      const trigger = JSON.parse(triggerJson);
      const response = await fetch(`/api/internal/skill-files/${name}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trigger }),
      });
      const body = await response.json();
      if (!response.ok) {
        setRunError(
          typeof body.detail === "string"
            ? body.detail
            : `HTTP ${response.status}`,
        );
        return;
      }
      setRunResult(body as RunResult);
    } catch (exc) {
      setRunError(String(exc));
    } finally {
      setRunning(false);
    }
  }

  if (notFound) {
    return (
      <div className="agents-stage">
        <div className="agents-empty">SkillFile not found: {name}</div>
      </div>
    );
  }
  if (!detail) {
    return (
      <div className="agents-stage">
        <div className="agents-empty">Loading…</div>
      </div>
    );
  }

  return (
    <div className="agents-stage">
      <header className="agents-topbar">
        <div className="agents-title-block">
          <h1 className="font-mono">{detail.name}</h1>
          <p>{detail.description || "Executable workflow SkillFile"}</p>
        </div>
      </header>

      <main className="agents-content">
        <div className="mb-4 flex flex-wrap items-center gap-3 text-xs">
          <span className="rounded border border-white/20 px-2 py-0.5 font-mono text-white/60">
            v{detail.current_version}
          </span>
          <span className={statusTone(detail.validation_status)}>
            {detail.validation_status === "valid" ? "✓ valid" : "⚠ invalid"}
          </span>
          <span className="text-white/40">
            updated {formatTimestamp(detail.updated_at)}
          </span>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <section className="lg:col-span-2">
            {/* Tab bar */}
            <div className="flex items-center gap-1 border-b border-white/10">
              <button
                type="button"
                onClick={() => setEditorMode("visual")}
                disabled={decompileError !== null}
                className={`border-b-2 px-3 py-2 text-sm ${
                  editorMode === "visual"
                    ? "border-cyan-400 text-cyan-300"
                    : "border-transparent text-white/60 hover:text-white/80 disabled:opacity-40"
                }`}
              >
                Visual
              </button>
              <button
                type="button"
                onClick={() =>
                  setEditorMode(
                    editorMode === "yaml_edit" ? "yaml_edit" : "yaml_readonly",
                  )
                }
                className={`border-b-2 px-3 py-2 text-sm ${
                  editorMode.startsWith("yaml")
                    ? "border-cyan-400 text-cyan-300"
                    : "border-transparent text-white/60 hover:text-white/80"
                }`}
              >
                YAML
              </button>
              <div className="ml-auto flex items-center gap-2 pb-2">
                {editorMode === "yaml_readonly" ? (
                  <button
                    type="button"
                    onClick={() => setEditorMode("yaml_edit")}
                    className="rounded border border-white/20 px-3 py-1 text-xs hover:bg-white/10"
                  >
                    Edit YAML
                  </button>
                ) : null}
                {editorMode === "yaml_edit" ? (
                  <button
                    type="button"
                    onClick={() => {
                      try {
                        setDoc(decompile(yamlText));
                        setDecompileError(null);
                        setEditorMode("visual");
                      } catch (err) {
                        setDecompileError(
                          err instanceof Error ? err.message : String(err),
                        );
                      }
                    }}
                    className="rounded border border-white/20 px-3 py-1 text-xs hover:bg-white/10"
                  >
                    Back to Visual
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => void handleSave()}
                  className="rounded border border-emerald-500/50 bg-emerald-500/10 px-3 py-1 text-sm text-emerald-300 hover:bg-emerald-500/20"
                >
                  Save
                </button>
              </div>
            </div>

            {saveStatus ? (
              <div className="mt-2 rounded border border-white/10 bg-white/5 p-2 text-xs text-white/70">
                {saveStatus}
              </div>
            ) : null}

            {/* Tab body */}
            <div className="mt-3">
              {decompileError && editorMode === "visual" ? (
                <div className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
                  Cannot render visual editor: {decompileError}. Switch to YAML
                  to edit.
                </div>
              ) : editorMode === "visual" && doc ? (
                <SkillFileBuilder
                  doc={doc}
                  onChange={setDoc}
                  errorsByLocalId={errorsByLocalId}
                  errorsTopLevel={errorsTopLevel}
                />
              ) : (
                <>
                  {errors.length > 0 ? (
                    <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                      <div className="mb-1 font-semibold">Validation errors</div>
                      <ul className="list-inside list-disc space-y-1 text-xs">
                        {errors.map((message, index) => (
                          <li key={index}>{message}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {editorMode === "yaml_edit" ? (
                    <textarea
                      value={yamlText}
                      onChange={(event) => setYamlText(event.target.value)}
                      spellCheck={false}
                      aria-label="SkillFile YAML editor"
                      className="h-[60vh] w-full resize-y rounded-lg border border-white/20 bg-[#040a16] p-3 font-mono text-sm leading-relaxed text-white/90 outline-none focus:border-cyan-500/50"
                    />
                  ) : (
                    <pre className="h-[60vh] w-full overflow-auto whitespace-pre rounded-lg border border-white/10 bg-[#040a16] p-3 font-mono text-sm leading-relaxed text-white/85">
                      {liveYaml}
                    </pre>
                  )}
                </>
              )}
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <div>
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-white/50">
                Test trigger
              </h2>
              <p className="mb-2 text-xs text-white/45">
                Edit the JSON trigger payload, then run the workflow.
              </p>
              <textarea
                value={triggerJson}
                onChange={(event) => setTriggerJson(event.target.value)}
                spellCheck={false}
                aria-label="Trigger JSON"
                className="h-48 w-full resize-y rounded-lg border border-white/20 bg-[#040a16] p-3 font-mono text-xs leading-relaxed text-white/90 outline-none focus:border-cyan-500/50"
              />
              <button
                type="button"
                className="agents-primary mt-2 w-full justify-center"
                onClick={() => void handleRun()}
                disabled={running}
              >
                {running ? "Running…" : "Run with this trigger"}
              </button>
            </div>

            {runError ? (
              <div className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                Run failed: {runError}
              </div>
            ) : null}

            {runResult ? (
              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="mb-2 flex items-center gap-2">
                  <span
                    className={`font-mono text-sm font-semibold ${statusTone(runResult.status)}`}
                  >
                    {runResult.status.toUpperCase()}
                  </span>
                  <span className="text-xs text-white/50">
                    {runResult.steps_executed} step
                    {runResult.steps_executed === 1 ? "" : "s"} executed
                  </span>
                </div>
                {runResult.approval_id ? (
                  <div className="mb-2 text-xs text-white/65">
                    Approval id:{" "}
                    <span className="font-mono text-amber-300">
                      {runResult.approval_id}
                    </span>
                  </div>
                ) : null}
                <ol className="space-y-1">
                  {runResult.step_results.map((step) => (
                    <li
                      key={step.step_id}
                      className="flex items-center gap-2 font-mono text-xs"
                    >
                      <span className={statusTone(step.status)}>
                        {step.status}
                      </span>
                      <span className="text-white/70">{step.step_id}</span>
                      <span className="text-white/35">{step.step_type}</span>
                    </li>
                  ))}
                </ol>
                {runResult.error ? (
                  <div className="mt-2 text-xs text-red-300">
                    {runResult.error}
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        </div>
      </main>
    </div>
  );
}
