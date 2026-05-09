import type { AgentActionLog, ClusterHealthSnapshot, ConnectionStatus, Edge, Entity, LedgerReceipt } from "@/state/brain.store";

export type CompanyBrainClusterId =
  | "people"
  | "leadership"
  | "meetings"
  | "decisions"
  | "code"
  | "projects"
  | "tickets"
  | "incidents"
  | "systems"
  | "vendors"
  | "customers"
  | "policies"
  | "documents"
  | "teams";

export type CompanyBrainCluster = {
  id: CompanyBrainClusterId;
  label: string;
  count: number;
  countLabel?: string;
  icon: string;
  color: string;
  x: number;
  y: number;
  satellites: number;
  filter: string;
  status: "healthy" | "watch" | "critical";
  description: string;
  owner: string;
  team: string;
  criticality: "Low" | "Medium" | "High";
  confidence: number;
  connections: string[];
};

export type BrainSummary = {
  entities: number;
  relationships: number;
  eventsPerMinute: number;
  confidenceAvg: number;
  health: number;
  dataMode: "real" | "fallback" | "mixed";
};

export type BrainActivityRow = {
  label: string;
  detail: string;
  time: string;
  tone: "blue" | "violet" | "green" | "amber" | "red" | "cyan";
};

export type BrainQueryRow = {
  text: string;
  actor: "human" | "agent";
  time: string;
  response?: string;
};

export type BrainSkillRow = {
  skill: string;
  status: "Success" | "Running" | "Blocked";
  time: string;
};

export type CompanyBrainViewModel = {
  summary: BrainSummary;
  clusters: CompanyBrainCluster[];
  activity: BrainActivityRow[];
  queries: BrainQueryRow[];
  skills: BrainSkillRow[];
};

export type CompanyBrainSourceState = {
  entities: Map<string, Entity>;
  edges: Map<string, Edge>;
  clusterHealth: Record<string, ClusterHealthSnapshot>;
  agentActions: AgentActionLog[];
  receipts: LedgerReceipt[];
  connectionStatus: ConnectionStatus;
};
