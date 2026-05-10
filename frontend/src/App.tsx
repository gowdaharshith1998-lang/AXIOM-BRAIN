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

function StudioShell() {
  const connectionStatus = useBrainStore((s) => s.connectionStatus);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        const input = document.querySelector<HTMLInputElement>('input[type="search"], input[placeholder*="Search" i]');
        if (input) {
          event.preventDefault();
          input.focus();
        }
      }
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
      <aside className="studio-rail fixed inset-y-0 left-0 w-[200px] border-r border-[#113457]">
        <div className="border-b border-[#113457] px-5 py-5">
          <div className="text-4xl leading-none text-[#17bfff]">⬡</div>
          <div className="mt-2 text-4xl tracking-[0.18em] text-[#edf7ff]">AXIOM</div>
          <div className="text-sm text-[#8ea8cb]">Company Brain</div>
        </div>
        <nav className="px-2 py-3">
          {navItems.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `mb-1 block rounded-xl px-4 py-3 text-[30px] transition ${isActive ? "border border-[#2257a8] bg-[#0f2e71]/55 text-[#e8f2ff]" : "text-[#abc1de] hover:bg-[#0d1f43]"}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="absolute bottom-3 left-3 right-3 rounded-xl border border-[#214367] bg-[#08152d] p-3">
          <div className="text-sm text-[#eef6ff]">Axiom Operator</div>
          <div className="text-xs text-[#8ba8cb]">Platform Admin</div>
        </div>
      </aside>

      <header className="fixed left-[200px] right-0 top-0 flex h-14 items-center justify-between border-b border-[#113457] px-8">
        <div>
          <div className="text-4xl tracking-[0.2em]">{location.pathname === "/settings" ? "SETTINGS" : "STUDIO"}</div>
          <div className="text-xs text-[#7fa2c8]">Think in graph. Act with agents.</div>
        </div>
        <div className="flex items-center gap-2 rounded-xl border border-[#214467] bg-[#071328] px-4 py-2 text-lg text-[#14e0a7]">
          <span className={`h-2.5 w-2.5 rounded-full ${connectionStatus === "live" ? "bg-[#16f0a9]" : "bg-[#5f728f]"}`} />
          LIVE
        </div>
      </header>

      <main className="fixed inset-0 left-[200px] top-14 overflow-y-auto">
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
