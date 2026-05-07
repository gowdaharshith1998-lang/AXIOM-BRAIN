import { Brain } from "@/components/Brain";
import { CommandPalette } from "@/components/CommandPalette";
import { EntityInspector } from "@/components/EntityInspector";
import { HUD } from "@/components/HUD";

export function App() {
  return (
    <div className="relative h-full w-full">
      <Brain />
      <HUD />
      <CommandPalette />
      <EntityInspector />
    </div>
  );
}

