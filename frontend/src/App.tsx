import { BottomToolbar } from "@/components/BottomToolbar";
import { Brain } from "@/components/Brain";
import { CommandPalette } from "@/components/CommandPalette";
import { InspectorPanel } from "@/components/InspectorPanel";
import { LedgerRibbon } from "@/components/LedgerRibbon";
import { SourcesRail } from "@/components/SourcesRail";
import { useBrainStore } from "@/state/brain.store";
import { useEffect } from "react";

export function App() {
  const entityCount = useBrainStore((s) => s.entities.size);
  const connectionStatus = useBrainStore((s) => s.connectionStatus);
  const titleStatus = connectionStatus === "offline" ? "offline" : "live";

  useEffect(() => {
    document.title = `AXIOM · ${entityCount} · ${titleStatus}`;
  }, [entityCount, titleStatus]);

  return (
    <div
      className={`relative h-full w-full ${connectionStatus === "syncing" ? "bg-[#12081f]" : "bg-[#05050a]"}`}
    >
      <SourcesRail />
      <div className="fixed inset-y-0 left-[220px] right-[320px]">
        <Brain />
      </div>
      <InspectorPanel />
      <LedgerRibbon />
      <BottomToolbar />
      <CommandPalette />
    </div>
  );
}
