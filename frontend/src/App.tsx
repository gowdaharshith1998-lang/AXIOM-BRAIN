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
import { SettingsPage } from "@/pages/SettingsPage";
import { useBrainStore } from "@/state/brain.store";

const navItems = [
  ["/graph", "Graph"],
  ["/agents", "Agents"],
  ["/explore", "Explore"],
  ["/insights", "Insights"],
  ["/governance", "Governance"],
  ["/settings", "Settings"],
] as const;

function NavIcon({ label }: { label: string }) {
  const common = "h-5 w-5 text-current";
  if (label === "Graph") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M6 6h.01M18 6h.01M6 18h.01M18 18h.01M7 6h10M6 7v10M18 7v10M7 18h10" /></svg>;
  if (label === "Agents") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M16 11a4 4 0 1 0-4-4 4 4 0 0 0 4 4ZM8 13a3 3 0 1 0-3-3 3 3 0 0 0 3 3Zm8 1c-3.3 0-6 1.6-6 3.5V20h12v-2.5c0-1.9-2.7-3.5-6-3.5ZM8 14c-2.8 0-5 1.2-5 2.8V19h5" /></svg>;
  if (label === "Explore") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="8"/><path d="m15 9-2 5-5 2 2-5 5-2Z"/></svg>;
  if (label === "Insights") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 19V8m5 11V5m5 14v-8m6 8H3"/></svg>;
  if (label === "Governance") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="m12 3 7 3v5c0 4.2-2.7 7.3-7 9-4.3-1.7-7-4.8-7-9V6l7-3Z"/></svg>;
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
          {navItems.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `mb-1 flex h-[52px] items-center gap-4 rounded-lg px-4 text-[18px] transition ${isActive ? "border border-[#1f5db0] bg-[#10266a]/70 text-[#eef5ff] shadow-[inset_3px_0_0_#2389ff]" : "text-[#aab5c7] hover:bg-[#0b1930]"}`
              }
            >
              <NavIcon label={label} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="absolute bottom-2 left-0 right-0 border-t border-[#162a45] px-4 py-4">
          <div className="rounded-lg border border-[#213c5e] bg-[#071225]/90 p-3">
            <div className="text-[13px] text-[#eef6ff]">Axiom Operator</div>
            <div className="text-[12px] text-[#8ba8cb]">Platform Admin</div>
          </div>
        </div>
      </aside>

      <header className="fixed left-[228px] right-0 top-0 z-30 flex h-[112px] items-start justify-between border-b border-[#132339] px-8 pt-7">
        <div>
          <div className="text-[28px] leading-none tracking-[0.22em] text-[#eef5ff]">{location.pathname === "/settings" ? "SETTINGS" : "STUDIO"}</div>
          <div className="mt-2 text-[12px] text-[#7fa2c8]">Think in graph. Act with agents.</div>
        </div>
        <div className="mt-[-4px] flex h-[38px] items-center gap-2 rounded-lg border border-[#1d3452] bg-[#071328] px-4 text-[16px] text-[#14e0a7]">
          <span className={`h-2.5 w-2.5 rounded-full ${connectionStatus === "live" ? "bg-[#16f0a9]" : "bg-[#5f728f]"}`} />
          LIVE
        </div>
      </header>

      <main
        className={
          isGraphRoute
            ? "fixed inset-y-0 right-0 left-[228px] z-0 overflow-hidden"
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

function StubPage({ title, phase }: { title: string; phase: string }) {
  return (
    <div className="flex min-h-full items-center justify-center p-10">
      <div className="w-full max-w-2xl rounded-2xl border border-[#1a4b87] bg-[#06152d]/90 p-10 text-center">
        <h1 className="text-3xl tracking-wide">{title}</h1>
        <p className="mt-3 text-[#9ab4d3]">Coming in Phase 13 — full studio shell.</p>
        <p className="mt-1 text-sm text-[#6f90b7]">Backend: Phase {phase}</p>
      </div>
    </div>
  );
}

function WsStatusBridge() {
  const setConnectionStatus = useBrainStore((s) => s.setConnectionStatus);

  useEffect(() => {
    const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${wsScheme}://${window.location.hostname}:8000/ws/brain`;
    const socket = new BrainSocket(url);
    socket.onStatus(setConnectionStatus);
    socket.start();
    return () => socket.close();
  }, [setConnectionStatus]);

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
          <Route path="/agents" element={<StubPage title="Agents" phase="8" />} />
          <Route path="/explore" element={<StubPage title="Explore" phase="7" />} />
          <Route path="/insights" element={<StubPage title="Insights" phase="7" />} />
          <Route path="/governance" element={<StubPage title="Governance" phase="9/10" />} />
          <Route path="*" element={<Navigate to="/graph" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
