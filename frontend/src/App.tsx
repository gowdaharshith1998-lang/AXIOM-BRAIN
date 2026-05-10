import { useEffect } from "react";
import { BrowserRouter, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { Brain } from "@/components/Brain";
import { BrainHealthCard } from "@/components/BrainHealthCard";
import { CommandPalette } from "@/components/CommandPalette";
import { EdgeLegend } from "@/components/EdgeLegend";
import { EntityInspector } from "@/components/EntityInspector";
import { QueryBar } from "@/components/QueryBar";
import { StatusFooter } from "@/components/StatusFooter";
import { BrainSocket } from "@/lib/websocket";
import { AgentsPage } from "@/pages/AgentsPage";
import { ExplorePage } from "@/pages/ExplorePage";
import { GovernancePage } from "@/pages/GovernancePage";
import { InsightsPage } from "@/pages/InsightsPage";
import { PassportsPage } from "@/pages/PassportsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { useBrainStore } from "@/state/brain.store";

const navItems = [
  ["/graph", "Graph"],
  ["/explore", "Explore"],
  ["/insights", "Insights"],
  ["/governance", "Governance"],
  ["/agents", "Agents"],
  ["/settings", "Settings"],
] as const;

const agentNavItems = [
  ["/graph", "Graph"],
  ["/explore", "Explore"],
  ["/insights", "Insights"],
  ["/governance", "Governance"],
  ["/agents", "Agents"],
  ["/agents/schedules", "Schedules"],
  ["/agents/triggers", "Triggers"],
  ["/agents/runtime", "Runtime"],
  ["/agents/activity", "Activity"],
  ["/settings", "Settings"],
] as const;

function NavIcon({ label }: { label: string }) {
  const common = "h-5 w-5 text-current";
  if (label === "Graph") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M6 6h.01M18 6h.01M6 18h.01M18 18h.01M7 6h10M6 7v10M18 7v10M7 18h10" /></svg>;
  if (label === "Agents") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M16 11a4 4 0 1 0-4-4 4 4 0 0 0 4 4ZM8 13a3 3 0 1 0-3-3 3 3 0 0 0 3 3Zm8 1c-3.3 0-6 1.6-6 3.5V20h12v-2.5c0-1.9-2.7-3.5-6-3.5ZM8 14c-2.8 0-5 1.2-5 2.8V19h5" /></svg>;
  if (label === "Explore") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="8"/><path d="m15 9-2 5-5 2 2-5 5-2Z"/></svg>;
  if (label === "Insights") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 19V8m5 11V5m5 14v-8m6 8H3"/></svg>;
  if (label === "Governance") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="m12 3 7 3v5c0 4.2-2.7 7.3-7 9-4.3-1.7-7-4.8-7-9V6l7-3Z"/></svg>;
  if (label === "Schedules") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M7 3v4m10-4v4M5 7h14M5 7v13h14V7M8 11h3m2 0h3m-8 4h3m2 0h3" /></svg>;
  if (label === "Triggers") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="m13 2-8 12h6l-1 8 9-13h-6l1-7Z" /></svg>;
  if (label === "Runtime") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M12 2v4m0 12v4M4.9 4.9l2.8 2.8m8.6 8.6 2.8 2.8M2 12h4m12 0h4M4.9 19.1l2.8-2.8m8.6-8.6 2.8-2.8" /><circle cx="12" cy="12" r="4" /></svg>;
  if (label === "Activity") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 12h4l2-6 4 12 2-6h4" /></svg>;
  return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="3.5"/><path d="m19 12 2-1-1-3-2-.3-.7-1.8 1.2-1.7-2.3-2.3-1.7 1.2-1.8-.7L12 1 9 2l-.3 2-1.8.7-1.7-1.2L2.9 5.8l1.2 1.7L3.4 9.3 1.5 9.6v3l1.9.3.7 1.8-1.2 1.7 2.3 2.3 1.7-1.2 1.8.7.3 2h3l.3-2 1.8-.7 1.7 1.2 2.3-2.3-1.2-1.7.7-1.8 2-.3Z"/></svg>;
}

function isRouteHotkeyTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return !target.closest(
    'input, textarea, select, button, a, [contenteditable="true"], [contenteditable=""], [role="button"], [role="link"], [role="textbox"], [role="combobox"]',
  );
}

function StudioShell() {
  const connectionStatus = useBrainStore((s) => s.connectionStatus);
  const location = useLocation();
  const navigate = useNavigate();
  const isGraphRoute = location.pathname === "/graph";
  const isAgentsRoute = location.pathname.startsWith("/agents");
  const isExploreRoute = location.pathname.startsWith("/explore");
  const isGovernanceRoute = location.pathname === "/governance";
  const isInsightsRoute = location.pathname === "/insights";
  const isSettingsRoute = location.pathname.startsWith("/settings");
  const hasCompactHeader = isGovernanceRoute || isInsightsRoute;
  const shellNavItems = isAgentsRoute ? agentNavItems : navItems;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        const input = document.querySelector<HTMLInputElement>('input[type="search"], input[placeholder*="Search" i]');
        if (input) {
          event.preventDefault();
          input.focus();
        }
      }
      if (event.defaultPrevented || !isRouteHotkeyTarget(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "g") navigate("/graph");
      if (key === "a") navigate("/agents");
      if (key === "e") navigate("/explore");
      if (key === "i") navigate("/insights");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate]);

  return (
    <div className="studio-root h-screen w-screen overflow-hidden text-[#dce8ff]">
      <aside className="studio-rail fixed inset-y-0 left-0 z-30 w-[228px] border-r border-[#162a45]">
        <div className="h-[90px] border-b border-[#162a45] px-4 py-5">
          <div className="flex items-center gap-3">
            <div className="text-[34px] leading-none text-[#00bfff]">⌬</div>
            <div>
              <div className="text-[29px] leading-none tracking-[0.13em] text-[#f3f7ff]">AXIOM</div>
              <div className="mt-1 text-[13px] text-[#9aaac0]">Company Brain</div>
            </div>
          </div>
        </div>
        <nav className="px-2 py-5">
          {shellNavItems.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/agents" || to === "/graph"}
              className={({ isActive }) =>
                `mb-1 flex h-[52px] items-center gap-4 rounded-lg px-4 text-[18px] transition ${isActive ? "border border-[#1f5db0] bg-[#10266a]/70 text-[#eef5ff] shadow-[inset_3px_0_0_#2389ff]" : "text-[#aab5c7] hover:bg-[#0b1930]"}`
              }
            >
              <NavIcon label={label} />
              {label}
            </NavLink>
          ))}
        </nav>
        {isAgentsRoute ? (
          <div className="absolute bottom-2 left-0 right-0 border-t border-[#162a45] px-3 py-4">
            <div className="mb-3 rounded-lg border border-[#213c5e] bg-[#071225]/90 p-4">
              <div className="text-[13px] text-[#eef6ff]">AXIOM Company Brain</div>
              <div className="axiom-grid-preview my-4 h-[94px] rounded-lg" />
              <div className={`mx-auto flex h-[28px] w-[104px] items-center justify-center gap-2 rounded-md text-[12px] ${connectionStatus === "live" ? "bg-[#05271f] text-[#2af8a9]" : "bg-[#1c2636] text-[#9fb0c8]"}`}>
                <span className={`h-2 w-2 rounded-full ${connectionStatus === "live" ? "bg-[#20e99b]" : "bg-[#7d8ba0]"}`} />
                {connectionStatus === "live" ? "Connected" : connectionStatus === "syncing" ? "Syncing" : "Offline"}
              </div>
            </div>
            <div className="rounded-lg border border-[#213c5e] bg-[#071225]/90 p-3">
              <div className="text-[13px] text-[#eef6ff]">Axiom Corp.</div>
              <div className="text-[12px] text-[#8ba8cb]">Enterprise Plan</div>
            </div>
          </div>
        ) : (
          <div className="absolute bottom-2 left-0 right-0 border-t border-[#162a45] px-4 py-4">
            <div className="rounded-lg border border-[#213c5e] bg-[#071225]/90 p-3">
              <div className="text-[13px] text-[#eef6ff]">Axiom Operator</div>
              <div className="text-[12px] text-[#8ba8cb]">Platform Admin</div>
            </div>
          </div>
        )}
      </aside>

      {!isExploreRoute && !isAgentsRoute ? (
        <header className={`fixed left-[228px] right-0 top-0 z-30 flex items-start justify-between border-b border-[#132339] px-8 ${hasCompactHeader ? "h-[60px] pt-4" : "h-[112px] pt-7"}`}>
          {hasCompactHeader ? (
            <div className="absolute left-1/2 top-5 -translate-x-1/2 text-[15px] text-[#b9c1cf]">
              {isInsightsRoute ? "Unified intelligence. Informed decisions. Reduced risk." : "Unified governance. Verifiable trust. Continuous compliance."}
            </div>
          ) : (
            <div>
              <div className="text-[28px] leading-none tracking-[0.22em] text-[#eef5ff]">{isSettingsRoute ? "SETTINGS" : "STUDIO"}</div>
              <div className="mt-2 text-[12px] text-[#7fa2c8]">Think in graph. Act with agents.</div>
            </div>
          )}
          <div className="ml-auto mt-[-4px] flex h-[38px] items-center gap-2 rounded-lg border border-[#1d3452] bg-[#071328] px-4 text-[16px] text-[#14e0a7]">
            <span className={`h-2.5 w-2.5 rounded-full ${connectionStatus === "live" ? "bg-[#16f0a9]" : "bg-[#5f728f]"}`} />
            LIVE
          </div>
        </header>
      ) : null}

      <main
        className={
          isGraphRoute
            ? "fixed inset-y-0 right-0 left-[228px] z-0 overflow-hidden"
            : isAgentsRoute
              ? "fixed inset-0 left-[228px] z-0 overflow-y-auto"
            : isExploreRoute
              ? "fixed inset-0 left-[228px] z-0 overflow-y-auto"
            : hasCompactHeader
              ? "fixed inset-0 left-[228px] top-[60px] z-0 overflow-y-auto"
            : "fixed inset-0 left-[228px] top-[112px] z-0 overflow-y-auto"
        }
      >
        <Outlet />
      </main>
    </div>
  );
}

function GraphPage() {
  return (
    <>
      <BrainHealthCard />
      <div className="absolute inset-0">
        <Brain />
      </div>
      <QueryBar />
      <EdgeLegend />
      <EntityInspector />
      <StatusFooter />
      <CommandPalette />
    </>
  );
}

function WsStatusBridge() {
  const setConnectionStatus = useBrainStore((s) => s.setConnectionStatus);
  const applyEvent = useBrainStore((s) => s.applyEvent);

  useEffect(() => {
    const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${wsScheme}://${window.location.hostname}:8000/ws/brain`;
    const socket = new BrainSocket(url);
    socket.onStatus(setConnectionStatus);
    const off = socket.on((event) => {
      applyEvent(event);
      window.dispatchEvent(new CustomEvent("axiom:brain-event", { detail: event }));
    });
    socket.start();
    return () => {
      off();
      socket.close();
    };
  }, [applyEvent, setConnectionStatus]);

  return null;
}

export function App() {
  return (
    <BrowserRouter>
      <WsStatusBridge />
      <Routes>
        <Route element={<StudioShell />}>
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/passports" element={<PassportsPage />} />
          <Route path="/agents/*" element={<AgentsPage />} />
          <Route path="/explore/*" element={<ExplorePage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/governance" element={<GovernancePage />} />
          <Route path="*" element={<Navigate to="/graph" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
