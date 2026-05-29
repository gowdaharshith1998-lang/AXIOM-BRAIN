import { CONNECTOR_VENDORS } from "@/state/connectors.store";

export type SourceVendorId = (typeof CONNECTOR_VENDORS)[number]["id"];

export const SOURCE_VENDOR_LABELS: Record<SourceVendorId, string> = {
  github: "GitHub",
  notion: "Notion",
  linear: "Linear",
  slack: "Slack",
  gmail: "Gmail",
};

export const SOURCE_VENDOR_ORDER: SourceVendorId[] = ["github", "notion", "linear", "slack", "gmail"];

export const SOURCE_VENDOR_COLOURS: Record<SourceVendorId, string> = {
  github: "#E8F0FF",
  notion: "#E8F0FF",
  linear: "#8B9CFF",
  slack: "#E88FD4",
  gmail: "#F28B82",
};

export function vendorFromSourceId(sourceId: string | null | undefined): SourceVendorId | null {
  if (!sourceId) return null;
  const lower = sourceId.toLowerCase();
  for (const vendor of CONNECTOR_VENDORS) {
    if (lower === vendor.id || lower.startsWith(`${vendor.id}-`) || lower.startsWith(`${vendor.id}_`) || lower.endsWith(`-${vendor.id}`)) {
      return vendor.id;
    }
  }
  if (lower.includes("github")) return "github";
  if (lower.includes("notion")) return "notion";
  if (lower.includes("linear")) return "linear";
  if (lower.includes("slack")) return "slack";
  if (lower.includes("gmail") || lower.includes("google_mail")) return "gmail";
  return null;
}

export function integrationPath(vendor: SourceVendorId): string {
  return `/settings/integrations/${vendor}`;
}
