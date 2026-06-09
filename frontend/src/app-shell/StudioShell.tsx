import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { AxiomGlyph } from "@/components/AxiomGlyph";
import { ConnectorLoadingIndicator } from "@/components/ConnectorLoadingIndicator";
import { OPERATOR_NAME, OPERATOR_ROLE, PRODUCT_CATEGORY, PRODUCT_NAME, PRODUCT_SHORT_NAME } from "@/lib/product";
import { useBrainStore } from "@/state/brain.store";

import { agentNavItems, navItems, NavIcon } from "./nav";

function isRouteHotkeyTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return !target.closest(
    'input, textarea, select, button, a, [contenteditable="true"], [contenteditable=""], [role="button"], [role="link"], [role="textbox"], [role="combobox"]',
  );
}

export function StudioShell() {
  const connectionStatus = useBrainStore((s) => s.connectionStatus);
  const location = useLocation();
  const navigate = useNavigate();
  const isGraphRoute = location.pathname === "/graph";
  const isAgentsRoute = location.pathname.startsWith("/agents");
  const isSkillsRoute = location.pathname.startsWith("/skills");
  const isExploreRoute = location.pathname.startsWith("/explore");
  const isInsightsRoute = location.pathname === "/insights";
  const isSettingsRoute = location.pathname.startsWith("/settings");
  const hasCompactHeader = isInsightsRoute;
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
            <AxiomGlyph className="h-9 w-9 text-[#00bfff]" />
            <div>
              <div className="text-[24px] leading-none tracking-[0.1em] text-[#f3f7ff]">{PRODUCT_SHORT_NAME}</div>
              <div className="mt-1 text-[13px] text-[#9aaac0]">{PRODUCT_NAME}</div>
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
              <div className="text-[13px] text-[#eef6ff]">{PRODUCT_NAME}</div>
              <div className="axiom-grid-preview my-4 h-[94px] rounded-lg" />
              <div className={`mx-auto flex h-[28px] w-[104px] items-center justify-center gap-2 rounded-md text-[12px] ${connectionStatus === "live" ? "bg-[#05271f] text-[#2af8a9]" : "bg-[#1c2636] text-[#9fb0c8]"}`}>
                <span className={`h-2 w-2 rounded-full ${connectionStatus === "live" ? "bg-[#20e99b]" : "bg-[#7d8ba0]"}`} />
                {connectionStatus === "live" ? "Connected" : connectionStatus === "syncing" ? "Syncing" : "Offline"}
              </div>
            </div>
            <div className="rounded-lg border border-[#213c5e] bg-[#071225]/90 p-3">
              <div className="text-[13px] text-[#eef6ff]">{PRODUCT_CATEGORY}</div>
            </div>
          </div>
        ) : (
          <div className="absolute bottom-2 left-0 right-0 border-t border-[#162a45] px-4 py-4">
            <div className="rounded-lg border border-[#213c5e] bg-[#071225]/90 p-3">
              <div className="text-[13px] text-[#eef6ff]">{OPERATOR_NAME}</div>
              <div className="text-[12px] text-[#8ba8cb]">{OPERATOR_ROLE}</div>
            </div>
          </div>
        )}
      </aside>

      {!isExploreRoute && !isAgentsRoute && !isSkillsRoute && !isGraphRoute ? (
        <header className={`fixed left-[228px] right-0 top-0 z-30 flex items-start justify-between border-b border-[#132339] px-8 ${hasCompactHeader ? "h-[60px] pt-4" : "h-[112px] pt-7"}`}>
          {hasCompactHeader ? (
            <div className="absolute left-1/2 top-5 -translate-x-1/2 text-[15px] text-[#b9c1cf]">
              {"Unified intelligence. Informed decisions. Reduced risk."}
            </div>
          ) : (
            <div>
              <div className="text-[28px] leading-none tracking-[0.22em] text-[#eef5ff]">{isSettingsRoute ? "SETTINGS" : "STUDIO"}</div>
              <div className="mt-2 text-[12px] text-[#7fa2c8]">Think in graph. Act with agents.</div>
            </div>
          )}
          <div className="ml-auto mt-[-4px] flex items-center gap-2">
            <ConnectorLoadingIndicator />
            <div className="flex h-[38px] items-center gap-2 rounded-lg border border-[#1d3452] bg-[#071328] px-4 text-[16px] text-[#14e0a7]">
              <span className={`h-2.5 w-2.5 rounded-full ${connectionStatus === "live" ? "bg-[#16f0a9]" : "bg-[#5f728f]"}`} />
              LIVE
            </div>
          </div>
        </header>
      ) : null}

      <main
        className={
          isGraphRoute
            ? "fixed inset-y-0 right-0 left-[228px] z-0 overflow-hidden"
            : isAgentsRoute || isSkillsRoute
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
