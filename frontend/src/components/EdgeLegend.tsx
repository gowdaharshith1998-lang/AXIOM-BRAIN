// HIDDEN-V2: "Governance" legend chip removed for YC company-brain positioning. uncomment to restore.
const rows = [
  ["#00E5D8", "Knowledge"],
  ["#2B7FFF", "Execution"],
  ["#4DD3B8", "External"],
] as const;

export function EdgeLegend() {
  return (
    <aside className="fixed bottom-[42px] right-6 z-30 w-[180px] rounded-2xl border border-[#274057]/70 bg-[#07111d]/70 p-4 font-mono text-xs text-[#E8F0FF]/68 shadow-[0_18px_50px_rgba(0,0,0,0.3)] backdrop-blur-xl">
      <div className="space-y-3">
        {rows.map(([color, label]) => (
          <div key={label} className="flex items-center gap-3">
            <span className="h-2.5 w-2.5 rounded-full shadow-[0_0_12px_currentColor]" style={{ color, backgroundColor: color }} />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}
