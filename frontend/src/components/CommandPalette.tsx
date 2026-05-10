import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";

import { colorForType } from "@/lib/palette";
import { useBrainStore } from "@/state/brain.store";
import type { Entity } from "@/state/brain.store";

type EntitySearchResult = {
  id: string;
  type: string;
  title: string;
  connection_count?: number;
  methods?: SearchMode[];
  breakdown?: Partial<Record<SearchMode, { rank: number; score: number }>>;
};

type SearchMode = "hybrid" | "lexical" | "semantic" | "graph";

const SEARCH_URL = "/api/internal/search";
const SEARCH_MODE_KEY = "axiom.search.mode";
const SEARCH_MODES: SearchMode[] = ["hybrid", "lexical", "semantic", "graph"];
const TITLE_KEYS = ["title", "name", "subject", "label", "file_path"] as const;

function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}

function titleForEntity(entity: Entity): string {
  for (const key of TITLE_KEYS) {
    const value = entity.data[key];
    if (typeof value === "string" && value.trim()) {
      return key === "file_path" ? (value.split("/").pop() ?? value) : value.trim();
    }
  }
  return entity.id;
}

function localSearch(query: string, limit: number): EntitySearchResult[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];

  const { entities, edges } = useBrainStore.getState();
  type LocalResult = EntitySearchResult & { score: number; connection_count: number };
  const connectionCounts = new Map<string, number>();
  for (const edge of edges.values()) {
    connectionCounts.set(edge.source_id, (connectionCounts.get(edge.source_id) ?? 0) + 1);
    connectionCounts.set(edge.target_id, (connectionCounts.get(edge.target_id) ?? 0) + 1);
  }

  return Array.from(entities.values())
    .map<LocalResult | null>((entity) => {
      const title = titleForEntity(entity);
      const normalizedTitle = title.toLowerCase();
      const prefix = normalizedTitle.startsWith(q);
      const substring = normalizedTitle.includes(q);
      if (!prefix && !substring) return null;
      return {
        id: entity.id,
        type: entity.type,
        title,
        connection_count: connectionCounts.get(entity.id) ?? 0,
        methods: ["lexical" as const],
        breakdown: { lexical: { rank: 1, score: prefix ? 2 : 1 } },
        score: prefix ? 2 : 1,
      };
    })
    .filter((result): result is LocalResult => result !== null)
    .sort((a, b) => b.score - a.score || b.connection_count - a.connection_count || a.title.localeCompare(b.title))
    .slice(0, limit)
    .map(({ score: _score, ...result }) => result);
}

function initialSearchMode(): SearchMode {
  const saved = window.localStorage.getItem(SEARCH_MODE_KEY);
  return SEARCH_MODES.includes(saved as SearchMode) ? (saved as SearchMode) : "hybrid";
}

function methodLabel(method: SearchMode): string {
  return method[0].toUpperCase() + method.slice(1);
}

function tooltipFor(result: EntitySearchResult): string {
  const entries = Object.entries(result.breakdown ?? {});
  if (!entries.length) return "No method breakdown";
  return entries
    .map(([method, item]) => `${method}: rank ${item.rank}, score ${item.score}`)
    .join("\n");
}

export function CommandPalette() {
  const select = useBrainStore((s) => s.select);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<EntitySearchResult[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [hintDismissed, setHintDismissed] = useState(false);
  const [mode, setMode] = useState<SearchMode>(initialSearchMode);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const openPalette = () => {
    setOpen(true);
    setHintDismissed(true);
  };

  const closePalette = () => {
    setOpen(false);
    setQuery("");
    setResults([]);
    setActiveIndex(0);
  };

  const activeResult = useMemo(() => results[activeIndex] ?? null, [activeIndex, results]);

  const choose = (result: EntitySearchResult) => {
    select(result.id);
    window.dispatchEvent(new CustomEvent("axiom:fly-to-entity", { detail: { id: result.id } }));
    closePalette();
  };

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("axiom:palette-state", { detail: { open } }));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    window.localStorage.setItem(SEARCH_MODE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      const commandKey = (event.metaKey || event.ctrlKey) && key === "k";
      const slashKey = event.key === "/" && !isTypingTarget(event.target);
      if (commandKey || slashKey) {
        event.preventDefault();
        openPalette();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("axiom:open-palette", openPalette);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("axiom:open-palette", openPalette);
    };
  }, []);

  useEffect(() => {
    if (!open || !query.trim()) {
      setResults([]);
      setActiveIndex(0);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void fetch(SEARCH_URL, {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, mode, top_k: 8 }),
      })
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json() as Promise<{ results: EntitySearchResult[] }>;
        })
        .then(({ results: items }) => {
          setResults(items.length > 0 ? items : localSearch(query, 8));
          setActiveIndex(0);
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          setResults(localSearch(query, 8));
        });
    }, 150);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [mode, open, query]);

  const onPaletteKeyDown = (event: ReactKeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closePalette();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, Math.max(results.length - 1, 0)));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter" && activeResult) {
      event.preventDefault();
      choose(activeResult);
    }
  };

  return (
    <>
      {!hintDismissed && (
        <div className="absolute bottom-4 right-4 z-20 flex items-center gap-2 rounded-full border border-white/10 bg-black/35 px-3 py-1.5 font-mono text-xs text-white/55 shadow-lg backdrop-blur">
          <span>Press ⌘K to find anything</span>
          <button
            type="button"
            aria-label="Dismiss search hint"
            className="rounded-full px-1 text-white/35 transition hover:text-white/80 focus:outline-none focus:ring-1 focus:ring-white/40"
            onClick={() => setHintDismissed(true)}
          >
            ×
          </button>
        </div>
      )}

      {open && (
        <div
          className="absolute inset-0 z-30 bg-black/20 backdrop-blur-[2px]"
          role="dialog"
          aria-modal="true"
          aria-label="Ask the brain"
          onKeyDown={onPaletteKeyDown}
        >
          <div className="mx-auto mt-16 w-[min(600px,calc(100vw-32px))] overflow-hidden rounded-2xl border border-white/10 bg-[#070914]/85 shadow-2xl shadow-cyan-500/10 backdrop-blur-xl">
            <div className="border-b border-white/10 p-4">
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ask the brain… (e.g. how do refunds work)"
                className="w-full bg-transparent font-mono text-base text-white outline-none placeholder:text-white/35"
              />
              <div className="mt-3 grid grid-cols-4 rounded-lg border border-white/10 bg-black/20 p-1">
                {SEARCH_MODES.map((item) => (
                  <button
                    key={item}
                    type="button"
                    aria-pressed={mode === item}
                    className={`h-8 rounded-md text-[12px] transition ${mode === item ? "bg-[#00E5D8]/18 text-[#00E5D8]" : "text-white/50 hover:text-white"}`}
                    onClick={() => setMode(item)}
                  >
                    {methodLabel(item)}
                  </button>
                ))}
              </div>
            </div>
            <div className="max-h-[420px] overflow-y-auto p-2">
              {results.map((result, index) => {
                const active = index === activeIndex;
                return (
                  <button
                    key={result.id}
                    type="button"
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition ${
                      active ? "bg-white/10 text-white" : "text-white/70 hover:bg-white/5 hover:text-white"
                    }`}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => choose(result)}
                  >
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full shadow-[0_0_14px_currentColor]"
                      style={{ color: colorForType(result.type), backgroundColor: colorForType(result.type) }}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{result.title}</span>
                      <span className="mt-1 block text-xs text-white/40">
                        {result.type} · {result.connection_count ?? 0} connections
                      </span>
                    </span>
                    <span className="flex shrink-0 gap-1" title={tooltipFor(result)}>
                      {(result.methods ?? ["lexical"]).map((method) => (
                        <span key={method} className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] uppercase text-white/55">
                          {method.slice(0, 3)}
                        </span>
                      ))}
                    </span>
                  </button>
                );
              })}
              {query.trim() && results.length === 0 && (
                <div className="px-3 py-8 text-center font-mono text-xs text-white/35">No matching entities</div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
