import { AxiomGlyph } from "@/components/AxiomGlyph";
import { useSettingsStore } from "@/state/settings.store";

type NavItem = {
  label: string;
  icon: string;
  /** Top-section items use this view id when wired */
  view?: "brain";
};

type BottomNavItem = {
  label: string;
  icon: string;
  view?: "settings";
};

const topItems: NavItem[] = [
  { label: "Brain", icon: "brain", view: "brain" },
  { label: "Explore", icon: "search" },
  { label: "Agents", icon: "bot" },
  { label: "Insights", icon: "chart" },
  { label: "Governance", icon: "shield" },
];

const bottomItems: BottomNavItem[] = [
  { label: "Settings", icon: "gear", view: "settings" },
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

function NavButton({
  item,
  active,
  onActivate,
}: {
  item: NavItem | BottomNavItem;
  active: boolean;
  onActivate?: () => void;
}) {
  return (
    <button
      type="button"
      title={item.label}
      onClick={onActivate}
      className={`group relative flex h-[86px] w-full flex-col items-center justify-center gap-2 transition ${
        active ? "text-[#00E5D8]" : "text-[#8d9bbb] hover:text-[#E8F0FF]"
      }`}
    >
      {active && <span className="absolute left-0 h-12 w-[2px] rounded-r-full bg-[#00E5D8] shadow-[0_0_14px_#00E5D8]" />}
      <span className={`rounded-xl p-2 ${active ? "bg-[#00E5D8]/12 shadow-[0_0_24px_rgba(0,229,216,0.22)]" : "bg-transparent"}`}>
        <Icon name={item.icon} />
      </span>
      <span className={`font-mono text-[12px] ${active ? "text-[#00E5D8]" : "text-[#9aa8c4]"}`}>
        {item.label}
      </span>
    </button>
  );
}

export function NavRail() {
  const activeView = useSettingsStore((s) => s.activeView);
  const setActiveView = useSettingsStore((s) => s.setActiveView);

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-[84px] flex-col items-center border-r border-[#1a3550]/60 bg-[#06101b]/78 shadow-[18px_0_50px_rgba(0,0,0,0.34)] backdrop-blur-xl">
      <div className="mt-6 flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 text-[#E8F0FF]/85">
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path d="M5 7h14M5 12h14M5 17h14" />
        </svg>
      </div>
      <div className="mt-8 w-full">
        {topItems.map((item) => (
          <NavButton
            key={item.label}
            item={item}
            active={item.view === "brain" ? activeView === "brain" : false}
            onActivate={item.view === "brain" ? () => setActiveView("brain") : undefined}
          />
        ))}
      </div>
      <div className="mb-5 mt-auto w-full">
        {bottomItems.map((item) => (
          <NavButton
            key={item.label}
            item={item}
            active={item.view === "settings" ? activeView === "settings" : false}
            onActivate={item.view === "settings" ? () => setActiveView("settings") : undefined}
          />
        ))}
      </div>
    </aside>
  );
}
