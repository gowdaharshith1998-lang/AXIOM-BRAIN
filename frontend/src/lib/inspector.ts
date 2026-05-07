export function stripEmptyMetadata(value: unknown): unknown {
  if (value === null || value === undefined || value === "") return undefined;
  if (Array.isArray(value)) {
    const items = value.map(stripEmptyMetadata).filter((item) => item !== undefined);
    return items.length > 0 ? items : undefined;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => [key, stripEmptyMetadata(item)] as const)
      .filter(([, item]) => item !== undefined);
    return entries.length > 0 ? Object.fromEntries(entries) : undefined;
  }
  return value;
}

export function prettyMetadata(value: unknown): string | null {
  const stripped = stripEmptyMetadata(value);
  return stripped === undefined ? null : JSON.stringify(stripped, null, 2);
}
