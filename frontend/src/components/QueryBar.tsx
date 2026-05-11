import { useState, type KeyboardEvent } from "react";

const prompts = [
  "What impacted Q2 revenue?",
  "Show risks to launch",
  "Which policy applies?",
  "Trace decision D-4821",
  "Summarize incident 1021",
];

export function QueryBar() {
  const [value, setValue] = useState("");

  const openPalette = () => window.dispatchEvent(new Event("axiom:open-palette"));
  const submit = (text = value) => {
    const query = text.trim();
    if (!query) {
      openPalette();
      return;
    }
    setValue(query);
    window.dispatchEvent(new CustomEvent("axiom:traverse-clusters", { detail: { query } }));
    window.dispatchEvent(new CustomEvent("axiom:palette-query", { detail: { query } }));
  };
  const onInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    submit();
  };

  return (
    <div className="fixed bottom-[36px] left-1/2 z-30 w-[min(900px,70vw)] -translate-x-1/2 max-xl:w-[calc(100vw-220px)] max-md:w-[calc(100vw-104px)]">
      <div className="mx-auto mb-2 flex w-max items-center gap-2 rounded-xl border border-white/10 bg-[#07111d]/68 px-4 py-2 font-mono text-xs text-[#E8F0FF]/62 shadow-xl backdrop-blur-xl">
        <span className="h-2 w-2 rounded-full bg-[#45f0a1] shadow-[0_0_10px_#45f0a1]" />
        Queryable by humans + AI agents
      </div>
      <div className="flex items-center gap-3 rounded-2xl border border-[#00E5D8]/55 bg-[#07111d]/72 px-5 py-3 shadow-[0_0_60px_rgba(0,229,216,0.11)] backdrop-blur-xl">
        <SearchIcon />
        <div className="h-8 w-px bg-white/12" />
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onInputKeyDown}
          placeholder="Ask the Company Brain anything..."
          className="min-w-0 flex-1 bg-transparent font-mono text-base text-[#E8F0FF] outline-none placeholder:text-[#E8F0FF]/38"
        />
        <button
          type="button"
          className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 font-mono text-sm text-[#E8F0FF]/70 transition hover:border-[#00E5D8]/45 hover:text-[#00E5D8]"
          onClick={openPalette}
        >
          ⌘ K
        </button>
        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-full border border-[#00E5D8]/35 bg-[#00E5D8]/12 text-[#00E5D8] shadow-[0_0_24px_rgba(0,229,216,0.22)] transition hover:scale-105"
          aria-label="Send query"
          onClick={() => submit()}
        >
          <SendIcon />
        </button>
      </div>
      <div className="mt-6 flex flex-nowrap justify-center gap-2 overflow-hidden">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="shrink-0 rounded-full border border-white/12 bg-[#07111d]/68 px-3 py-1.5 font-mono text-[11px] text-[#E8F0FF]/68 backdrop-blur transition hover:border-[#00E5D8]/45 hover:text-[#E8F0FF]"
            onClick={() => submit(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 text-[#00E5D8]" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M5 12 20 4l-4.8 16-3.5-6.8L5 12Z" />
    </svg>
  );
}
