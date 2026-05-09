import { useEffect } from "react";

import { Brain } from "@/components/Brain";
import { BrainHealthCard } from "@/components/BrainHealthCard";
import { CommandPalette } from "@/components/CommandPalette";
import { EdgeLegend } from "@/components/EdgeLegend";
import { EntityInspector } from "@/components/EntityInspector";
import { NavRail } from "@/components/NavRail";
import { QueryBar } from "@/components/QueryBar";
import { StatusFooter } from "@/components/StatusFooter";
import { TopHeader } from "@/components/TopHeader";
import { SettingsPage } from "@/pages/SettingsPage";
import { useBrainStore } from "@/state/brain.store";
import { useSettingsStore } from "@/state/settings.store";

export function App() {
  const activeView = useSettingsStore((s) => s.activeView);
  const entityCount = useBrainStore((s) => s.entities.size);
  const connectionStatus = useBrainStore((s) => s.connectionStatus);
  const titleStatus = connectionStatus === "offline" ? "offline" : "live";

  useEffect(() => {
    if (activeView === "settings") {
      document.title = "AXIOM · Settings";
      return;
    }
    document.title = `AXIOM · ${entityCount} · ${titleStatus}`;
  }, [activeView, entityCount, titleStatus]);

  const showBrainChrome = activeView === "brain";

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-[#020711]">
      <NavRail />
      <TopHeader />
      {showBrainChrome ? <BrainHealthCard /> : null}
      <div className="fixed inset-0 left-[84px] right-0">
        {activeView === "brain" ? <Brain /> : <SettingsPage />}
      </div>
      {showBrainChrome ? <QueryBar /> : null}
      {showBrainChrome ? <EdgeLegend /> : null}
      {showBrainChrome ? <EntityInspector /> : null}
      <StatusFooter />
      <CommandPalette />
    </div>
  );
}
