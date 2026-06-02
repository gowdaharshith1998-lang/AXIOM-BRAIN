import { useEffect, useState, type FormEvent } from "react";

import { hasApiToken, setApiToken } from "@/lib/auth";
import { AUTH_REQUIRED_EVENT } from "@/lib/http";

// Auth gate overlay (P1-15).
//
// Stays invisible until a request comes back 401/403 (the backend signals auth
// is required). In dev mode the backend returns 200s without a token, the
// `axiom:auth-required` event never fires, and this overlay never renders.
//
// On "Connect" the token is stored in memory (sessionStorage only when the user
// opts into "remember for this tab"); the next request carries it and, on
// success, no further auth-required events fire so the gate closes.

export function TokenGate() {
  // Only ever shown in reaction to an auth-required signal — never on mount.
  const [visible, setVisible] = useState(false);
  const [token, setToken] = useState("");
  const [remember, setRemember] = useState(false);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    function onAuthRequired() {
      // If we already have a token yet still got a 401/403, the token was
      // wrong/expired — clear the field and re-prompt.
      setRetrying(false);
      setVisible(true);
    }
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, []);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = token.trim();
    if (!trimmed) return;
    setApiToken(trimmed, remember);
    setToken("");
    setVisible(false);
    // Nudge the app to re-fetch with the new token. Listeners (or a reload)
    // pick this up; if the token is still rejected, a fresh auth-required
    // event re-opens the gate.
    setRetrying(true);
    window.dispatchEvent(new CustomEvent("axiom:auth-token-set"));
  }

  if (!visible) return null;

  const alreadyHadToken = hasApiToken();

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/78 backdrop-blur-sm px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="token-gate-title"
        className="w-full max-w-md rounded-xl border border-[#1a3550]/80 bg-[#06101b]/95 p-6 shadow-[0_0_60px_rgba(0,0,0,0.55)]"
      >
        <div className="flex items-center gap-3">
          <div className="text-[28px] leading-none text-[#00E5D8]">⌬</div>
          <h3 id="token-gate-title" className="font-mono text-lg font-semibold text-[#E8F0FF]">
            Connect to AXIOM
          </h3>
        </div>
        <p className="mt-2 text-[13px] leading-snug text-[#9aa8c4]">
          {alreadyHadToken
            ? "That token was rejected. Enter a valid API token to continue."
            : "This deployment requires an API token. Paste yours to access the company brain."}
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label
              htmlFor="axiom-api-token"
              className="block font-mono text-[11px] uppercase tracking-wider text-[#8d9bbb]"
            >
              API Token
            </label>
            <input
              id="axiom-api-token"
              name="api-token"
              type="password"
              autoComplete="off"
              autoFocus
              value={token}
              onChange={(ev) => setToken(ev.target.value)}
              placeholder="Bearer token"
              className="mt-1.5 w-full rounded-lg border border-[#1a3550]/80 bg-[#020711]/90 px-3 py-2 font-mono text-[13px] text-[#E8F0FF] outline-none ring-[#00E5D8]/25 placeholder:text-[#5f6f90] focus:border-[#00E5D8]/55 focus:ring-2"
            />
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-[12px] text-[#9aa8c4]">
            <input
              type="checkbox"
              className="accent-[#00E5D8]"
              checked={remember}
              onChange={(ev) => setRemember(ev.target.checked)}
            />
            Remember for this tab
          </label>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="submit"
              disabled={!token.trim() || retrying}
              className="inline-flex items-center gap-2 rounded-lg bg-[#00E5D8]/18 px-4 py-2 font-mono text-[13px] font-semibold text-[#00E5D8] shadow-[0_0_22px_rgba(0,229,216,0.22)] transition hover:bg-[#00E5D8]/26 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Connect
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
