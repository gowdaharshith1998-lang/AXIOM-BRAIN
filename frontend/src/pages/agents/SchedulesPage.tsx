import { useEffect, useState } from "react";

import { listSkills, type Skill } from "@/lib/skillsClient";
import { AgentsSubPageShell, EmptyState, formatTime } from "@/pages/agents/shared";

function textConfig(config: Record<string, unknown>, key: string): string | null {
  const value = config[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function SchedulesPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSkills({ triggerType: "schedule" })
      .then(setSkills)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Unable to load schedules"));
  }, []);

  return (
    <AgentsSubPageShell title="Schedules" subtitle="Scheduled skill runs from the live skills registry.">
      {error ? <EmptyState>Unable to load scheduled skills: {error}</EmptyState> : null}
      <section className="agents-panel">
        <div className="agents-panel-head">
          <h2>Scheduled Skills <span>{skills.length}</span></h2>
        </div>
        <div className="agents-table">
          <div className="agents-table-head">
            <span>Name</span>
            <span>Cron</span>
            <span>Next Run</span>
            <span>Status</span>
          </div>
          {skills.length ? skills.map((skill) => (
            <div className="agents-table-row" key={skill.id}>
              <span>{skill.name}</span>
              <span>{textConfig(skill.trigger_config, "cron") ?? "Not recorded"}</span>
              <span>{formatTime(textConfig(skill.trigger_config, "next_run_at"))}</span>
              <span>{skill.status}</span>
            </div>
          )) : <EmptyState>No scheduled skills yet.</EmptyState>}
        </div>
      </section>
    </AgentsSubPageShell>
  );
}
