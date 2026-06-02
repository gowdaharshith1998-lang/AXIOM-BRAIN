import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  issuePassport,
  listPassports,
  revokePassport,
  setPassportKillSwitch,
  type IssuePassportBody,
  type Passport,
} from "@/lib/passportsClient";
import { wsConnect } from "@/lib/ws";
import { useAuthEpoch } from "@/hooks/useAuthEpoch";

type FormState = Record<keyof IssuePassportBody, string>;

const initialForm: FormState = {
  agent_name: "",
  agent_class: "",
  owner_email: "",
  scope_clusters: "*",
  scope_intents: "*",
  scope_skills: "*",
  ttl_hours: "24",
};

function csv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function upsert(rows: Passport[], next: Passport): Passport[] {
  const without = rows.filter((row) => row.passport_id !== next.passport_id);
  return [next, ...without].sort((a, b) => Date.parse(b.issued_at) - Date.parse(a.issued_at));
}

function statusClass(status: string): string {
  if (status === "active") return "border-[#00E5D8]/55 bg-[#00E5D8]/10 text-[#00E5D8]";
  if (status === "kill_switch") return "border-amber-500/55 bg-amber-500/10 text-amber-200";
  return "border-red-500/55 bg-red-500/10 text-red-300";
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function PassportsPage() {
  const [rows, setRows] = useState<Passport[]>([]);
  const authEpoch = useAuthEpoch();
  const [issueOpen, setIssueOpen] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(initialForm);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void listPassports().then(setRows).catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    const ws = wsConnect("/ws/brain");
    ws.onmessage = (message) => {
      try {
        const event = JSON.parse(String(message.data)) as { type?: string; payload?: Passport };
        if (
          event.type === "passport_issued" ||
          event.type === "passport_revoked" ||
          event.type === "passport_kill_switch_toggled"
        ) {
          setRows((current) => event.payload ? upsert(current, event.payload) : current);
        }
      } catch {
        // ignore malformed websocket events
      }
    };
    return () => ws.close();
    // authEpoch: reconnect with fresh credentials after TokenGate auth.
  }, [authEpoch]);

  const canIssue = useMemo(
    () => form.agent_name.trim() && form.agent_class.trim() && form.owner_email.trim() && Number(form.ttl_hours) > 0,
    [form],
  );

  async function submitIssue(event: FormEvent) {
    event.preventDefault();
    if (!canIssue) return;
    setBusy(true);
    setError(null);
    try {
      const issued = await issuePassport({
        agent_name: form.agent_name.trim(),
        agent_class: form.agent_class.trim(),
        owner_email: form.owner_email.trim(),
        scope_clusters: csv(form.scope_clusters),
        scope_intents: csv(form.scope_intents),
        scope_skills: csv(form.scope_skills),
        ttl_hours: Number(form.ttl_hours),
      });
      setRows((current) => upsert(current, issued));
      setToken(issued.bearer_token);
      setIssueOpen(false);
      setForm(initialForm);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    const next = await revokePassport(id);
    setRows((current) => upsert(current, next));
  }

  async function toggleKillSwitch(row: Passport) {
    const next = await setPassportKillSwitch(row.passport_id, !row.kill_switch);
    setRows((current) => upsert(current, next));
  }

  return (
    <div className="settings-stage">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-[22px] tracking-[0.16em] text-[#eef5ff]">PASSPORTS</h2>
          <p className="mt-1 text-sm text-[#8aa5c4]">Agent bearer passports and revocation controls.</p>
        </div>
        <button className="settings-tab-active h-[38px] px-4" type="button" onClick={() => setIssueOpen(true)}>
          Issue Passport
        </button>
      </div>

      {error ? <div className="mb-3 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-red-100">{error}</div> : null}

      <div className="overflow-hidden rounded-md border border-[#1d446f] bg-[#071327]">
        <div className="grid grid-cols-[1.2fr_1.4fr_1.4fr_0.8fr_1.1fr] border-b border-[#1d446f] px-3 py-2 text-[12px] text-[#83a6cb]">
          <span>Agent</span>
          <span>Scope</span>
          <span>Issued / Expires</span>
          <span>Status</span>
          <span>Actions</span>
        </div>
        {rows.map((row) => (
          <div key={row.passport_id} className="grid grid-cols-[1.2fr_1.4fr_1.4fr_0.8fr_1.1fr] items-center border-b border-[#12365d]/60 px-3 py-3 text-[13px]">
            <span>
              <b className="block text-[#e8f2ff]">{row.agent_name}</b>
              <span className="text-[#83a6cb]">{row.agent_class} · {row.owner_email}</span>
            </span>
            <span className="text-[#c7d8ee]">
              {row.scope_clusters.join(", ")} / {row.scope_intents.join(", ")} / {row.scope_skills.join(", ")}
            </span>
            <span className="text-[#c7d8ee]">{formatDate(row.issued_at)}<br />{formatDate(row.expires_at)}</span>
            <span><span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusClass(row.status)}`}>{row.status}</span></span>
            <span className="flex gap-2">
              <button className="rounded-md border border-[#2b558a] px-2 py-1 text-[#c9d4ea]" type="button" onClick={() => void revoke(row.passport_id)}>
                Revoke
              </button>
              <button className="rounded-md border border-amber-500/40 px-2 py-1 text-amber-100" type="button" onClick={() => void toggleKillSwitch(row)}>
                {row.kill_switch ? "Disable kill-switch" : "Kill-switch"}
              </button>
            </span>
          </div>
        ))}
        {rows.length === 0 ? <div className="p-8 text-center text-[#83a6cb]">No passports issued.</div> : null}
      </div>

      {issueOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/72 px-4 backdrop-blur-sm">
          <form onSubmit={(event) => void submitIssue(event)} role="dialog" aria-modal="true" aria-label="Issue passport" className="w-full max-w-xl rounded-xl border border-[#1a3550]/80 bg-[#06101b]/95 p-6">
            <h3 className="font-mono text-lg font-semibold text-[#E8F0FF]">Issue Passport</h3>
            <div className="mt-5 grid grid-cols-2 gap-3">
              {Object.keys(initialForm).map((key) => (
                <label key={key} className={key.startsWith("scope_") ? "col-span-2" : ""}>
                  <span className="mb-1 block text-[12px] text-[#9fb5d0]">{key}</span>
                  <input
                    className="h-[38px] w-full rounded-md border border-[#223b5c] bg-[#071225] px-3 text-[#e6f0ff] outline-none"
                    value={form[key as keyof FormState]}
                    aria-label={key}
                    type={key === "ttl_hours" ? "number" : "text"}
                    onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
                  />
                </label>
              ))}
            </div>
            <div className="mt-5 flex justify-end gap-3">
              <button className="settings-tab" type="button" disabled={busy} onClick={() => setIssueOpen(false)}>Cancel</button>
              <button className="settings-tab-active" type="submit" disabled={!canIssue || busy}>{busy ? "Issuing..." : "Issue"}</button>
            </div>
          </form>
        </div>
      ) : null}

      {token ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/72 px-4 backdrop-blur-sm">
          <div role="dialog" aria-modal="true" aria-label="Bearer token" className="w-full max-w-lg rounded-xl border border-[#1a3550]/80 bg-[#06101b]/95 p-6">
            <h3 className="font-mono text-lg font-semibold text-[#E8F0FF]">Bearer Token</h3>
            <textarea readOnly value={token} className="mt-4 h-32 w-full rounded-md border border-[#223b5c] bg-[#071225] p-3 text-xs text-[#e6f0ff]" />
            <div className="mt-4 flex justify-end gap-3">
              <button className="settings-tab" type="button" onClick={() => void navigator.clipboard?.writeText(token)}>Copy</button>
              <button className="settings-tab-active" type="button" onClick={() => setToken(null)}>I saved it</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
