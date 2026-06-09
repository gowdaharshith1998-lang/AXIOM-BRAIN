import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { GraphPage } from "@/app-shell/GraphPage";
import { StudioShell } from "@/app-shell/StudioShell";
import { WsStatusBridge } from "@/app-shell/WsStatusBridge";
import { ConnectorBootstrap } from "@/components/ConnectorBootstrap";
import { TokenGate } from "@/components/TokenGate";
import { AgentsPage } from "@/pages/AgentsPage";
import { ActivityPage } from "@/pages/agents/ActivityPage";
import { ConnectorsPage } from "@/pages/ConnectorsPage";
import { ExplorePage } from "@/pages/ExplorePage";
import { InsightsPage } from "@/pages/InsightsPage";
import { PassportsPage } from "@/pages/PassportsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SkillFileDetailPage } from "@/pages/SkillFileDetailPage";
import { SkillsPage } from "@/pages/SkillsPage";

export function App() {
  return (
    <BrowserRouter>
      <TokenGate />
      <ConnectorBootstrap />
      <WsStatusBridge />
      <Routes>
        <Route element={<StudioShell />}>
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/passports" element={<PassportsPage />} />
          <Route path="/settings/connectors" element={<ConnectorsPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/activity" element={<ActivityPage />} />
          <Route path="/skills" element={<SkillsPage />} />
          <Route path="/skills/:name" element={<SkillFileDetailPage />} />
          <Route path="/explore/*" element={<ExplorePage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="*" element={<Navigate to="/graph" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
