import { Brain } from "@/components/Brain";
import { BrandMark } from "@/components/BrandMark";
import { CommandPalette } from "@/components/CommandPalette";
import { EntityInspector } from "@/components/EntityInspector";
import { HUD } from "@/components/HUD";
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
      <Brain />
      <BrandMark />
      <HUD />
      <CommandPalette />
      <EntityInspector />
    </div>
  );
}
