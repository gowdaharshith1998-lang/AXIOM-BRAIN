import { useEffect, useRef, useState } from "react";

import type { AskCitation, AskError, AskResponse } from "@/lib/brainAskClient";
import { askBrain } from "@/lib/brainAskClient";

type AskState =
  | { status: "idle" }
  | { status: "loading"; question: string }
  | { status: "error"; question: string; message: string; httpStatus: number }
  | { status: "answered"; response: AskResponse };

function inlineCitations(answer: string, citations: AskCitation[]): React.ReactNode {
  if (!answer) return null;
  const parts: React.ReactNode[] = [];
  const regex = /\[(\d+)\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(answer)) !== null) {
    const index = match.index;
    if (index > lastIndex) parts.push(answer.slice(lastIndex, index));
    const refNum = Number(match[1]);
    const citation = citations[refNum - 1];
    const label = `[${refNum}]`;
    if (citation) {
      parts.push(
        <button
          key={`cite-${index}`}
          type="button"
          className="mx-0.5 rounded bg-[#00E5D8]/15 px-1.5 text-[12px] font-semibold text-[#00E5D8] hover:bg-[#00E5D8]/25"
          onClick={() =>
            window.dispatchEvent(
              new CustomEvent("axiom:focus-entity", {
                detail: { entityId: citation.entity_id },
              }),
            )
          }
          title={citation.title}
        >
          {label}
        </button>,
      );
    } else {
      parts.push(label);
    }
    lastIndex = index + label.length;
  }
  if (lastIndex < answer.length) parts.push(answer.slice(lastIndex));
  return parts;
}

export function AskPanel({ initialQuestion = "" }: { initialQuestion?: string }) {
  const [question, setQuestion] = useState(initialQuestion);
  const [state, setState] = useState<AskState>({ status: "idle" });
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!initialQuestion) return;
    setQuestion(initialQuestion);
  }, [initialQuestion]);

  const submit = async (text: string) => {
    const trimmed = text.trim();
    if (trimmed.length < 3) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: "loading", question: trimmed });
    try {
      const response = await askBrain({ question: trimmed }, { signal: controller.signal });
      setState({ status: "answered", response });
    } catch (raw) {
      if ((raw as { name?: string }).name === "AbortError") return;
      const err = raw as AskError;
      setState({
        status: "error",
        question: trimmed,
        httpStatus: typeof err.status === "number" ? err.status : 0,
        message: typeof err.detail === "string" ? err.detail : "ask the brain failed",
      });
    }
  };

  return (
    <section className="mt-3 rounded-2xl border border-white/10 bg-[#07111d]/82 p-4 shadow-xl backdrop-blur-xl" data-testid="ask-panel">
      <header className="mb-2 flex items-center gap-2 text-[12px] uppercase tracking-[0.18em] text-[#9ad6ff]">
        <span className="h-2 w-2 rounded-full bg-[#00E5D8] shadow-[0_0_10px_#00E5D8]" />
        Ask the Brain
      </header>
      <div className="flex items-center gap-3">
        <input
          aria-label="Ask the Brain"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void submit(question);
            }
          }}
          placeholder="Ask the Company Brain anything…"
          className="min-w-0 flex-1 rounded-xl border border-white/10 bg-[#0a1626]/80 px-3 py-2 font-mono text-sm text-[#E8F0FF] outline-none focus:border-[#00E5D8]/55"
        />
        <button
          type="button"
          onClick={() => void submit(question)}
          disabled={state.status === "loading"}
          className="rounded-xl border border-[#00E5D8]/45 bg-[#00E5D8]/12 px-3 py-2 font-mono text-sm text-[#00E5D8] transition hover:bg-[#00E5D8]/20 disabled:opacity-50"
        >
          {state.status === "loading" ? "…" : "Ask"}
        </button>
      </div>
      {state.status === "loading" && (
        <div className="mt-3 text-sm text-[#9aaac0]">Searching brain & drafting answer…</div>
      )}
      {state.status === "error" && (
        <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200" data-testid="ask-error">
          <div className="text-[12px] uppercase tracking-wide text-rose-300/80">Error · {state.httpStatus || "—"}</div>
          <div className="mt-1 font-mono">{state.message}</div>
          {state.httpStatus === 409 && (
            <div className="mt-2 text-[12px] text-rose-200/85">
              Add a provider key in <span className="font-mono">Settings → LLM Keys</span> to enable Ask.
            </div>
          )}
        </div>
      )}
      {state.status === "answered" && (
        <article className="mt-3 space-y-3 text-sm text-[#E8F0FF]" data-testid="ask-answer">
          <div className="whitespace-pre-wrap font-mono leading-relaxed">
            {inlineCitations(state.response.answer, state.response.citations)}
          </div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[#9ad6ff]">
            Cited entities ({state.response.citations.length})
          </div>
          <ul className="space-y-1.5">
            {state.response.citations.map((citation, index) => (
              <li key={citation.entity_id}>
                <button
                  type="button"
                  onClick={() =>
                    window.dispatchEvent(
                      new CustomEvent("axiom:focus-entity", {
                        detail: { entityId: citation.entity_id },
                      }),
                    )
                  }
                  className="flex w-full items-baseline gap-2 rounded-lg border border-white/8 bg-[#0a1626]/60 px-3 py-2 text-left hover:border-[#00E5D8]/40"
                  data-testid={`ask-citation-${citation.entity_id}`}
                >
                  <span className="font-mono text-[12px] text-[#00E5D8]">[{index + 1}]</span>
                  <span className="flex-1">
                    <span className="block font-mono text-sm text-[#E8F0FF]">{citation.title}</span>
                    <span className="block text-[12px] text-[#9aaac0]">
                      {citation.type}
                      {citation.cluster_id ? ` · ${citation.cluster_id}` : ""} · score {citation.score.toFixed(3)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
            {state.response.citations.length === 0 && (
              <li className="text-[12px] text-[#9aaac0]">
                No entities matched this question — the answer is unsourced. Ingest more data.
              </li>
            )}
          </ul>
          <div className="text-[11px] text-[#9aaac0]">
            {state.response.provider} · {state.response.model} · {state.response.duration_ms} ms
          </div>
        </article>
      )}
    </section>
  );
}
