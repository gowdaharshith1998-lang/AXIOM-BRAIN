import { useEffect, useState } from "react";

import { CommandPalette } from "@/components/CommandPalette";
import { ConnectorStatusBar } from "@/components/ConnectorStatusBar";
import { EdgeLegend } from "@/components/EdgeLegend";
import { EntityInspector } from "@/components/EntityInspector";
import { GraphCanvas } from "@/components/graph/GraphCanvas";
import { HomeEntityList } from "@/components/home/HomeEntityList";
import { RecentActivityFeed } from "@/components/home/RecentActivityFeed";
import { SourceTiles } from "@/components/home/SourceTiles";
import { ViewToggle, type GraphViewMode } from "@/components/home/ViewToggle";
import { QueryBar } from "@/components/QueryBar";
import { StatusFooter } from "@/components/StatusFooter";
import { useBrainBootstrap } from "@/hooks/useBrainBootstrap";
import { useDatasetLineageProbe } from "@/hooks/useDatasetLineageProbe";

const VIEW_STORAGE_KEY = "axiom.graph.view";

function readStoredView(): GraphViewMode {
  if (typeof window === "undefined") return "list";
  const stored = window.localStorage.getItem(VIEW_STORAGE_KEY);
  return stored === "graph" ? "graph" : "list";
}

export function GraphPage() {
  const [view, setView] = useState<GraphViewMode>(() => readStoredView());

  useBrainBootstrap();
  useDatasetLineageProbe();

  useEffect(() => {
    window.localStorage.setItem(VIEW_STORAGE_KEY, view);
  }, [view]);

  return (
    <>
      <ConnectorStatusBar />
      <div className="absolute inset-0 flex flex-col pt-[41px]">
        <div className="relative z-10 flex shrink-0 items-center justify-between border-b border-[#132339]/80 bg-[#040b16]/70 px-6 py-3 backdrop-blur-md">
          <ViewToggle value={view} onChange={setView} />
          <div className="text-[12px] text-[#7fa2c8]">
            {view === "list" ? "Browse entities by source" : "Explore connections by source"}
          </div>
        </div>

        {view === "list" ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
            <div className="mx-auto flex max-w-[1200px] flex-col gap-6">
              <SourceTiles />
              <div className="grid grid-cols-2 gap-6">
                <RecentActivityFeed />
                <HomeEntityList />
              </div>
            </div>
          </div>
        ) : (
          <div className="relative min-h-0 flex-1">
            <GraphCanvas />
            <QueryBar />
            <EdgeLegend />
          </div>
        )}
      </div>
      <EntityInspector />
      <StatusFooter />
      <CommandPalette />
    </>
  );
}
