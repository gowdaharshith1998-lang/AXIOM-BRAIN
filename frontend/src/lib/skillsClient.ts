export type Skill = {
  id: string;
  name: string;
  description: string;
  intent: string;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  prompt_template: string;
  llm_provider: string;
  llm_model: string;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  total_runs: number;
  scope_clusters?: string[];
};

export type SkillRun = {
  id: string;
  skill_id: string;
  run_at: string;
  status: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown> | null;
  receipt_id: string | null;
  error_message: string | null;
  duration_ms: number | null;
  agent_name: string;
};

export type RegisterSkillBody = {
  name: string;
  description: string;
  intent: string;
  prompt_template: string;
  llm_provider: string;
  llm_model: string;
  trigger_config?: Record<string, unknown>;
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

export async function listSkills(options: { triggerType?: string } = {}): Promise<Skill[]> {
  const params = new URLSearchParams();
  if (options.triggerType) params.set("trigger_type", options.triggerType);
  const query = params.toString();
  const data = await request<{ skills: Skill[] }>(`/api/internal/skills${query ? `?${query}` : ""}`);
  return data.skills;
}

export async function registerSkill(body: RegisterSkillBody): Promise<Skill> {
  return request<Skill>("/api/internal/skills", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function archiveSkill(skillId: string): Promise<Skill> {
  return request<Skill>(`/api/internal/skills/${encodeURIComponent(skillId)}/archive`, {
    method: "POST",
  });
}

export async function listSkillRuns(skillId: string): Promise<SkillRun[]> {
  const data = await request<{ runs: SkillRun[] }>(
    `/api/internal/skills/${encodeURIComponent(skillId)}/runs`,
  );
  return data.runs;
}
