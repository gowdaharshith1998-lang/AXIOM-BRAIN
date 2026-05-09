import { AxiomGlyph } from "@/components/AxiomGlyph";

type NavItem = {
  label: string;
  icon: string;
  active?: boolean;
};

const topItems: NavItem[] = [
  { label: "Brain", icon: "brain", active: true },
  { label: "Explore", icon: "search" },
  { label: "Agents", icon: "bot" },
  { label: "Insights", icon: "chart" },
  { label: "Governance", icon: "shield" },
];

const bottomItems: NavItem[] = [
  { label: "Settings", icon: "gear" },
  { label: "Account", icon: "user" },
];

function Icon({ name }: { name: string }) {
  if (name === "brain") return <AxiomGlyph className="h-5 w-5" />;
  const common = { stroke: "currentColor", strokeWidth: 1.8, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true">
      {name === "search" && <path {...common} d="m21 21-4.4-4.4M10.7 18a7.3 7.3 0 1 1 0-14.6 7.3 7.3 0 0 1 0 14.6Z" />}
      {name === "bot" && <path {...common} d="M8 7V5m8 2V5M6.5 9.5h11A2.5 2.5 0 0 1 20 12v4.5a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V12a2.5 2.5 0 0 1 2.5-2.5Zm2.5 4h.01M15 13.5h.01M9 17h6" />}
      {name === "chart" && <path {...common} d="M4 19V5m4 14v-5m4 5V9m4 10V7m4 12H4" />}
      {name === "shield" && <path {...common} d="M12 3.5 19 6v5.5c0 4.2-2.7 7.3-7 9-4.3-1.7-7-4.8-7-9V6l7-2.5Zm0 5v6" />}
      {name === "gear" && <path {...common} d="M12 8.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Zm8 3.5-2 .5a6.3 6.3 0 0 1-.7 1.7l1.1 1.7-2 2-1.7-1.1a6.3 6.3 0 0 1-1.7.7l-.5 2h-3l-.5-2a6.3 6.3 0 0 1-1.7-.7l-1.7 1.1-2-2 1.1-1.7a6.3 6.3 0 0 1-.7-1.7l-2-.5v-3l2-.5a6.3 6.3 0 0 1 .7-1.7L3.6 5.1l2-2 1.7 1.1A6.3 6.3 0 0 1 9 3.5l.5-2h3l.5 2a6.3 6.3 0 0 1 1.7.7l1.7-1.1 2 2-1.1 1.7a6.3 6.3 0 0 1 .7 1.7l2 .5v3Z" />}
      {name === "user" && <path {...common} d="M12 12.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7 8a7 7 0 0 0-14 0" />}
    </svg>
  );
}

function NavButton({ item }: { item: NavItem }) {
  return (
    <button
      type="button"
      title={item.label}
      className={`group relative flex h-[54px] w-full items-center justify-center transition ${
        item.active ? "text-[#00E5D8]" : "text-[#8d9bbb] hover:text-[#E8F0FF]"
      }`}
    >
      {item.active && <span className="absolute left-0 h-8 w-[2px] rounded-r-full bg-[#00E5D8] shadow-[0_0_14px_#00E5D8]" />}
      <span className={`rounded-xl p-2 ${item.active ? "bg-[#00E5D8]/12 shadow-[0_0_24px_rgba(0,229,216,0.18)]" : "bg-transparent"}`}>
        <Icon name={item.icon} />
      </span>
      <span className="pointer-events-none absolute left-[62px] z-50 rounded-md border border-white/10 bg-[#06101b]/95 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-[#E8F0FF]/75 opacity-0 shadow-xl backdrop-blur transition group-hover:opacity-100">
        {item.label}
      </span>
    </button>
  );
}

export function NavRail() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-[56px] flex-col items-center border-r border-[#1a3550]/55 bg-[#06101b]/72 shadow-[18px_0_50px_rgba(0,0,0,0.3)] backdrop-blur-xl">
      <div className="mt-4 flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 text-[#E8F0FF]/85">
        <AxiomGlyph className="h-5 w-5" />
      </div>
      <div className="mt-8 w-full space-y-1">
        {topItems.map((item) => (
          <NavButton key={item.label} item={item} />
        ))}
      </div>
      <div className="mb-5 mt-auto w-full space-y-1">
        {bottomItems.map((item) => (
          <NavButton key={item.label} item={item} />
        ))}
      </div>
    </aside>
  );
}
