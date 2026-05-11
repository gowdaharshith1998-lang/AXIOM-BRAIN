import { useEffect, useState } from "react";

import { listSkills, type Skill } from "@/lib/skillsClient";
import { AgentsSubPageShell, EmptyState } from "@/pages/agents/shared";

function eventName(config: Record<string, unknown>): string {
  const event = config.event ?? config.event_type;
  return typeof event === "string" && event.trim() ? event : "Not recorded";
}

export function TriggersPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSkills({ triggerType: "event" })
      .then(setSkills)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Unable to load triggers"));
  }, []);

  return (
    <AgentsSubPageShell title="Triggers" subtitle="Event-triggered skills from the live skills registry.">
      {error ? <EmptyState>Unable to load event-triggered skills: {error}</EmptyState> : null}
      <section className="agents-panel">
        <div className="agents-panel-head">
          <h2>Event Triggers <span>{skills.length}</span></h2>
        </div>
        <div className="agents-table">
          <div className="agents-table-head">
            <span>Name</span>
            <span>Event</span>
            <span>Intent</span>
            <span>Status</span>
          </div>
          {skills.length ? skills.map((skill) => (
            <div className="agents-table-row" key={skill.id}>
              <span>{skill.name}</span>
              <span>{eventName(skill.trigger_config)}</span>
              <span>{skill.intent}</span>
              <span>{skill.status}</span>
            </div>
          )) : <EmptyState>No event-triggered skills yet.</EmptyState>}
        </div>
      </section>
    </AgentsSubPageShell>
  );
}
