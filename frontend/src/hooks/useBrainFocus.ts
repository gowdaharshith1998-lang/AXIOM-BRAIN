import { useBrainStore } from "@/state/brain.store";

export function useBrainFocus() {
  const focus = useBrainStore((s) => s.focus);
  const focusCluster = useBrainStore((s) => s.focusCluster);
  const focusEntity = useBrainStore((s) => s.focusEntity);
  const clearFocus = useBrainStore((s) => s.clearFocus);
  const setHoveredCluster = useBrainStore((s) => s.setHoveredCluster);

  return { focus, focusCluster, focusEntity, clearFocus, setHoveredCluster };
}

