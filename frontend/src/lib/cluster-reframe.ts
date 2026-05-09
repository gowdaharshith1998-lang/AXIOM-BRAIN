import type { Entity } from "@/state/brain.store";

export const SUPER_CLUSTER_IDS = [
  "company_knowledge",
  "execution_context",
  "customers",
  "policies",
  "receipts",
  "agents",
  "governance",
  "people_teams",
  "billing",
] as const;

export type SuperClusterId = (typeof SUPER_CLUSTER_IDS)[number];

export function isSuperClusterId(value: unknown): value is SuperClusterId {
  return typeof value === "string" && (SUPER_CLUSTER_IDS as readonly string[]).includes(value);
}

export function superClusterIdForBackendCluster(clusterId?: string | null): SuperClusterId | null {
  switch (clusterId) {
    case "decisions_policy":
    case "customer_support":
    case "growth_product":
      return "company_knowledge";
    case "engineering_code":
    case "incidents_ops":
      return "execution_context";
    case "people_teams":
      return "people_teams";
    case "billing_payments":
      return "billing";
    default:
      return null;
  }
}

export function superClusterIdForEntity(entity: Entity | undefined): SuperClusterId | null {
  if (!entity) return null;

  if (entity.cluster_id === "customer_support" && entity.type === "customer") return "customers";
  if (entity.cluster_id === "decisions_policy" && entity.type === "policy") return "policies";

  return superClusterIdForBackendCluster(entity.cluster_id);
}

