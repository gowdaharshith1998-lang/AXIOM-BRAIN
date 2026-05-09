import type {
  BrainActivityRow,
  BrainQueryRow,
  BrainSkillRow,
  CompanyBrainCluster,
  CompanyBrainSourceState,
  CompanyBrainViewModel,
} from "@/components/company-brain/companyBrainTypes";

type ClusterSeed = Omit<CompanyBrainCluster, "count"> & { count: number; matchers: string[] };

// TODO: Replace these target-category fallbacks with a backend /api/brain/graph
// projection once AXIOM stores Company Brain categories directly.
const FALLBACK_COMPANY_BRAIN_CLUSTERS: ClusterSeed[] = [
  {
    id: "people",
    label: "People",
    count: 1248,
    icon: "person",
    color: "#2788ff",
    x: 26,
    y: 21,
    satellites: 12,
    filter: "People",
    status: "healthy",
    description: "Employees, contributors, owners, and frequently referenced humans across company sources.",
    owner: "People Systems",
    team: "People Ops",
    criticality: "Medium",
    confidence: 91,
    connections: ["Leadership", "Teams", "Meetings", "Tickets"],
    matchers: ["people", "person", "employee", "user", "author", "people_teams"],
  },
  {
    id: "leadership",
    label: "Leadership",
    count: 28,
    countLabel: "28 people",
    icon: "group",
    color: "#c15cff",
    x: 39,
    y: 16,
    satellites: 10,
    filter: "People",
    status: "healthy",
    description: "Executives and decision owners with authority over policy, budget, and operational direction.",
    owner: "CEO Staff",
    team: "Executive Ops",
    criticality: "High",
    confidence: 95,
    connections: ["Decisions", "Policies", "Projects", "Teams"],
    matchers: ["leadership", "exec", "founder", "director", "vp"],
  },
  {
    id: "meetings",
    label: "Meetings",
    count: 1932,
    icon: "calendar",
    color: "#24d9ff",
    x: 51,
    y: 24,
    satellites: 9,
    filter: "Meetings",
    status: "healthy",
    description: "Calendar events, transcripts, agenda items, and meeting-derived commitments.",
    owner: "Knowledge Ops",
    team: "Operations",
    criticality: "Medium",
    confidence: 88,
    connections: ["Decisions", "People", "Documents", "Projects"],
    matchers: ["meeting", "calendar", "transcript", "agenda"],
  },
  {
    id: "decisions",
    label: "Decisions",
    count: 763,
    icon: "check",
    color: "#ff6bd5",
    x: 64,
    y: 20,
    satellites: 13,
    filter: "Decisions",
    status: "healthy",
    description: "Approved decisions, unresolved tradeoffs, and durable operating context.",
    owner: "Strategy Ops",
    team: "Leadership",
    criticality: "High",
    confidence: 94,
    connections: ["Policies", "Meetings", "Projects", "Systems"],
    matchers: ["decision", "decisions_policy", "approved", "proposal"],
  },
  {
    id: "code",
    label: "Code (GitHub)",
    count: 512,
    countLabel: "512 repos",
    icon: "code",
    color: "#2f8dff",
    x: 61,
    y: 39,
    satellites: 12,
    filter: "Code / Repos",
    status: "healthy",
    description: "Repositories, pull requests, services, ownership metadata, and release context.",
    owner: "Engineering Systems",
    team: "Engineering",
    criticality: "High",
    confidence: 92,
    connections: ["Systems", "Tickets", "Incidents", "Documents"],
    matchers: ["code", "github", "repo", "pull", "engineering_code"],
  },
  {
    id: "projects",
    label: "Projects",
    count: 132,
    icon: "target",
    color: "#ff9416",
    x: 74,
    y: 34,
    satellites: 11,
    filter: "Projects",
    status: "watch",
    description: "Initiatives, milestones, owners, status, and links to source-backed execution data.",
    owner: "PMO",
    team: "Product Operations",
    criticality: "Medium",
    confidence: 89,
    connections: ["Tickets", "Decisions", "Teams", "Customers"],
    matchers: ["project", "growth_product", "roadmap", "initiative"],
  },
  {
    id: "tickets",
    label: "Tickets (Linear)",
    count: 2341,
    icon: "ticket",
    color: "#ffb21c",
    x: 75,
    y: 52,
    satellites: 13,
    filter: "Tickets",
    status: "watch",
    description: "Linear issues, support escalations, linked pull requests, and execution state.",
    owner: "Delivery Ops",
    team: "Engineering",
    criticality: "Medium",
    confidence: 90,
    connections: ["Projects", "Code (GitHub)", "Incidents", "Customers"],
    matchers: ["ticket", "linear", "issue", "bug", "task"],
  },
  {
    id: "incidents",
    label: "Incidents",
    count: 59,
    icon: "alert",
    color: "#ff5a5f",
    x: 70,
    y: 68,
    satellites: 10,
    filter: "Incidents",
    status: "critical",
    description: "Open and historical production incidents with impacted systems, owners, and receipts.",
    owner: "Reliability",
    team: "Platform Engineering",
    criticality: "High",
    confidence: 93,
    connections: ["Systems", "Code (GitHub)", "Tickets", "Policies"],
    matchers: ["incident", "outage", "alert", "incidents_ops"],
  },
  {
    id: "systems",
    label: "Systems",
    count: 184,
    icon: "cube",
    color: "#65e78f",
    x: 55,
    y: 72,
    satellites: 13,
    filter: "Systems",
    status: "healthy",
    description: "Production services, data assets, APIs, dependencies, and critical operational systems.",
    owner: "Platform Team",
    team: "Platform Engineering",
    criticality: "High",
    confidence: 94,
    connections: ["Stripe Billing API", "Billing Team", "Invoice Paid Decision", "Billing DB (Postgres)", "PAY-1234: Refund flow bug"],
    matchers: ["system", "service", "api", "database", "billing_payments"],
  },
  {
    id: "vendors",
    label: "Vendors",
    count: 87,
    icon: "briefcase",
    color: "#5b70ff",
    x: 43,
    y: 71,
    satellites: 9,
    filter: "Vendors",
    status: "watch",
    description: "External vendors, contracts, ownership, risk posture, and integration points.",
    owner: "Procurement",
    team: "Finance Ops",
    criticality: "Medium",
    confidence: 86,
    connections: ["Systems", "Policies", "Customers", "Documents"],
    matchers: ["vendor", "supplier", "contract", "stripe"],
  },
  {
    id: "customers",
    label: "Customers",
    count: 318,
    icon: "building",
    color: "#00e5d4",
    x: 30,
    y: 68,
    satellites: 11,
    filter: "Customers",
    status: "healthy",
    description: "Accounts, support context, customer commitments, and revenue-impacting dependencies.",
    owner: "Customer Ops",
    team: "Customer Success",
    criticality: "High",
    confidence: 91,
    connections: ["Tickets", "Projects", "Systems", "Documents"],
    matchers: ["customer", "account", "support", "customer_support"],
  },
  {
    id: "policies",
    label: "Policies",
    count: 64,
    icon: "shield",
    color: "#bd68ff",
    x: 24,
    y: 53,
    satellites: 12,
    filter: "Policies",
    status: "healthy",
    description: "Governance policies, retention rules, approvals, receipts, and audit evidence.",
    owner: "Governance",
    team: "Legal & Security",
    criticality: "High",
    confidence: 96,
    connections: ["Decisions", "Incidents", "Documents", "Systems"],
    matchers: ["policy", "governance", "compliance", "security"],
  },
  {
    id: "documents",
    label: "Documents",
    count: 6128,
    icon: "file",
    color: "#3a83ff",
    x: 34,
    y: 43,
    satellites: 14,
    filter: "Documents",
    status: "healthy",
    description: "Notion pages, specs, RFCs, docs, transcripts, and source-backed company memory.",
    owner: "Knowledge Ops",
    team: "Operations",
    criticality: "Medium",
    confidence: 87,
    connections: ["Meetings", "Policies", "Code (GitHub)", "Projects"],
    matchers: ["document", "doc", "notion", "spec", "rfc"],
  },
  {
    id: "teams",
    label: "Teams",
    count: 142,
    icon: "team",
    color: "#00d7df",
    x: 22,
    y: 34,
    satellites: 10,
    filter: "Teams",
    status: "healthy",
    description: "Org units, team ownership, on-call groups, Slack channels, and escalation paths.",
    owner: "People Systems",
    team: "People Ops",
    criticality: "Medium",
    confidence: 90,
    connections: ["People", "Projects", "Systems", "Tickets"],
    matchers: ["team", "group", "org", "channel", "people_teams"],
  },
];

export const QUICK_QUERIES = [
  "What decisions affect billing?",
  "Who owns payroll integration?",
  "Show open security incidents",
  "Which team manages Stripe?",
  "List high-risk vendors",
];

export const FILTERS = [
  "People",
  "Teams",
  "Systems",
  "Policies",
  "Code / Repos",
  "Documents",
  "Vendors",
  "Incidents",
  "Tickets",
  "Meetings",
];

export const FALLBACK_ACTIVITY: BrainActivityRow[] = [
  { label: "Slack thread ingested", detail: "#payments-alerts", time: "10:31:42", tone: "blue" },
  { label: "Linear ticket linked", detail: "PAY-1234", time: "10:31:35", tone: "violet" },
  { label: "Decision approved", detail: "Invoice policy v2", time: "10:31:28", tone: "red" },
  { label: "Policy checked", detail: "Data Retention Policy", time: "10:31:21", tone: "amber" },
  { label: "Receipt signed", detail: "Payments Service", time: "10:31:12", tone: "green" },
  { label: "Graph updated", detail: "42 changes", time: "10:31:09", tone: "cyan" },
];

export const FALLBACK_QUERIES: BrainQueryRow[] = [
  { text: "What decisions affect billing?", actor: "human", time: "10:30 AM" },
  { text: "Who owns payroll integration?", actor: "human", time: "10:29 AM" },
  { text: "Show open security incidents", actor: "agent", time: "10:28 AM" },
  { text: "Which team manages Stripe?", actor: "human", time: "10:27 AM" },
  { text: "List systems with high risk vendors", actor: "agent", time: "10:25 AM" },
];

export const FALLBACK_SKILLS: BrainSkillRow[] = [
  { skill: "skills_query_company", status: "Success", time: "10:31:40" },
  { skill: "skills_traverse_path", status: "Success", time: "10:31:38" },
  { skill: "skills_search_entities", status: "Success", time: "10:31:37" },
  { skill: "skills_get_entity", status: "Success", time: "10:31:36" },
  { skill: "skills_verify_receipt", status: "Success", time: "10:31:35" },
];

function countMatches(entities: Iterable<{ type: string; cluster_id?: string | null; data: Record<string, unknown> }>, matchers: string[]): number {
  let count = 0;
  for (const entity of entities) {
    const haystack = `${entity.type} ${entity.cluster_id ?? ""} ${JSON.stringify(entity.data ?? {})}`.toLowerCase();
    if (matchers.some((matcher) => haystack.includes(matcher))) count += 1;
  }
  return count;
}

function timeLabel(value: string | undefined): string {
  if (!value) return "live";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.round(minutes / 60)}h ago`;
}

export function buildCompanyBrainViewModel(state: CompanyBrainSourceState): CompanyBrainViewModel {
  const entities = Array.from(state.entities.values());
  const entityCount = entities.length;
  const realClusterCounts = FALLBACK_COMPANY_BRAIN_CLUSTERS.map((cluster) => countMatches(entities, cluster.matchers));
  const hasAnyMappedRealData = realClusterCounts.some((count) => count > 0);
  const clusters = FALLBACK_COMPANY_BRAIN_CLUSTERS.map(({ matchers: _matchers, ...cluster }, index) => ({
    ...cluster,
    count: realClusterCounts[index] > 0 ? realClusterCounts[index] : cluster.count,
  }));

  const actionRows: BrainSkillRow[] = state.agentActions.slice(0, 5).map((action) => ({
    skill: action.skill_called,
    status: action.decision === "deny" ? "Blocked" : "Success",
    time: timeLabel(action.timestamp),
  }));

  const receiptRows: BrainActivityRow[] = state.receipts.slice(0, 2).map((receipt) => ({
    label: "Receipt signed",
    detail: receipt.agent_name || receipt.action_id,
    time: timeLabel(receipt.timestamp),
    tone: receipt.decision === "deny" ? "red" : "green",
  }));

  return {
    summary: {
      entities: entityCount > 0 ? entityCount : 14892,
      relationships: state.edges.size > 0 ? state.edges.size : 58731,
      eventsPerMinute: Object.values(state.clusterHealth).reduce((sum, item) => sum + (item.ingest_rate_per_min || 0), 0) || 247,
      confidenceAvg: hasAnyMappedRealData ? 91.8 : 92.4,
      health: 98,
      dataMode: entityCount > 0 ? "mixed" : "fallback",
    },
    clusters,
    activity: [...receiptRows, ...FALLBACK_ACTIVITY].slice(0, 6),
    queries: FALLBACK_QUERIES,
    skills: actionRows.length > 0 ? actionRows : FALLBACK_SKILLS,
  };
}
