import type { Entity } from "@/state/brain.store";

export const SUPER_CLUSTER_IDS = [
  "company_knowledge",
  "execution_context",
  "customers",
  "policies",
  "receipts",
  "agents",
  "incidents",
  "governance",
  "people_teams",
  "billing",
] as const;

export type SuperClusterId = (typeof SUPER_CLUSTER_IDS)[number];

export function isSuperClusterId(value: unknown): value is SuperClusterId {
  return typeof value === "string" && (SUPER_CLUSTER_IDS as readonly string[]).includes(value);
}

export function superClusterIdForBackendCluster(
  clusterId?: string | null,
): SuperClusterId | null {
  if (!clusterId) return null;
  switch (clusterId) {
    // Knowledge sources
    case "knowledge":
    case "decisions_policy":
    case "growth_product":
      return "policies"; // labelled "Knowledge" in CLUSTER_LABELS
    // Comms + general company knowledge
    case "comms":
    case "customer_support":
      return "company_knowledge";
    // Engineering / ops
    case "engineering_code":
    case "incidents_ops":
      return "execution_context";
    // People
    case "people":
    case "people_teams":
      return "people_teams";
    // Customers (slack sales/customer channels)
    case "customers":
      return "customers";
    case "billing_payments":
      return "billing";
    default:
      return null;
  }
}

export function superClusterIdForEntity(entity: Entity | undefined): SuperClusterId | null {
  if (!entity) return null;

  if (entity.type === "customer") return "customers";
  if (entity.type === "policy") return "policies";
  if (entity.type === "incident") return "incidents";
  if (entity.type === "agent") return "agents";
  if (entity.type === "receipt") return "receipts";
  if (entity.type === "governance" || entity.type === "merkle_proof") return "governance";

  const fallback = superClusterIdForBackendCluster(entity.cluster_id);
  if (fallback) return fallback;
  // Final fallback: any unclassified entity bucketed as company knowledge
  // so it stays visible in the inspector instead of vanishing.
  return "company_knowledge";
}
