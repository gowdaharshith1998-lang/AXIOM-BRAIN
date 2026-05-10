export type PassportStatus = "active" | "revoked" | "expired" | "kill_switch";

export type Passport = {
  passport_id: string;
  agent_name: string;
  agent_class: string;
  owner_email: string;
  scope_clusters: string[];
  scope_intents: string[];
  scope_skills: string[];
  issued_at: string;
  expires_at: string;
  kill_switch: boolean;
  revoked_at: string | null;
  revocation_reason: string | null;
  status: PassportStatus;
};

export type IssuePassportBody = {
  agent_name: string;
  agent_class: string;
  owner_email: string;
  scope_clusters: string[];
  scope_intents: string[];
  scope_skills: string[];
  ttl_hours: number;
};

export type IssuedPassport = Passport & {
  bearer_token: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function listPassports(): Promise<Passport[]> {
  const data = await request<{ passports: Passport[] }>("/api/internal/passports?active_only=false");
  return data.passports;
}

export async function issuePassport(body: IssuePassportBody): Promise<IssuedPassport> {
  return request<IssuedPassport>("/api/internal/passports", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function revokePassport(passportId: string): Promise<Passport> {
  return request<Passport>(`/api/internal/passports/${encodeURIComponent(passportId)}`, {
    method: "DELETE",
  });
}

export async function setPassportKillSwitch(passportId: string, enabled: boolean): Promise<Passport> {
  return request<Passport>(
    `/api/internal/passports/${encodeURIComponent(passportId)}/kill-switch`,
    {
      method: "POST",
      body: JSON.stringify({ enabled }),
    },
  );
}
