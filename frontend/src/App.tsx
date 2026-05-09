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
import { useBrainStore } from "@/state/brain.store";

export function App() {
  const entityCount = useBrainStore((s) => s.entities.size);
  const connectionStatus = useBrainStore((s) => s.connectionStatus);
  const titleStatus = connectionStatus === "offline" ? "offline" : "live";

  useEffect(() => {
    document.title = `AXIOM · ${entityCount} · ${titleStatus}`;
  }, [entityCount, titleStatus]);

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-[#020711]">
      <NavRail />
      <TopHeader />
      <BrainHealthCard />
      <div className="fixed inset-0 left-[84px] right-0">
        <Brain />
      </div>
      <QueryBar />
      <EdgeLegend />
      <EntityInspector />
      <StatusFooter />
      <CommandPalette />
    </div>
  );
}
