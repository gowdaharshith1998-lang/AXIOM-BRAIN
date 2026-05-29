export type GraphViewMode = "list" | "graph";

type ViewToggleProps = {
  value: GraphViewMode;
  onChange: (mode: GraphViewMode) => void;
};

export function ViewToggle({ value, onChange }: ViewToggleProps) {
  return (
    <div
      className="inline-flex rounded-lg border border-[#1d3452] bg-[#071328]/90 p-0.5"
      role="tablist"
      aria-label="View mode"
    >
      {(["list", "graph"] as const).map((mode) => (
        <button
          key={mode}
          type="button"
          role="tab"
          aria-selected={value === mode}
          className={`rounded-md px-4 py-1.5 text-[13px] font-medium capitalize transition ${
            value === mode
              ? "bg-[#10266a]/80 text-[#eef5ff] shadow-[inset_0_0_0_1px_#2389ff]"
              : "text-[#8ba8cb] hover:text-[#dce8ff]"
          }`}
          onClick={() => onChange(mode)}
        >
          {mode}
        </button>
      ))}
    </div>
  );
}
