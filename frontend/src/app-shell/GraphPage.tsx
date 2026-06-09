import { Brain } from "@/components/Brain";
import { BrainHealthCard } from "@/components/BrainHealthCard";
import { CommandPalette } from "@/components/CommandPalette";
import { ConnectorStatusBar } from "@/components/ConnectorStatusBar";
import { EdgeLegend } from "@/components/EdgeLegend";
import { EntityInspector } from "@/components/EntityInspector";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { QueryBar } from "@/components/QueryBar";
import { StatusFooter } from "@/components/StatusFooter";

export function GraphPage() {
  return (
    <>
      <ConnectorStatusBar />
      <BrainHealthCard />
      <div className="absolute inset-0">
        <ErrorBoundary label="the 3D brain view">
          <Brain />
        </ErrorBoundary>
      </div>
      <QueryBar />
      <EdgeLegend />
      <EntityInspector />
      <StatusFooter />
      <CommandPalette />
    </>
  );
}
