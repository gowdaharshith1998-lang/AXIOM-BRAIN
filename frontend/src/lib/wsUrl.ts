// Build a proxy-safe WebSocket URL from the current page origin.
//
// Avoids hardcoding host/port (e.g. ":8000") so the app works behind a
// reverse proxy / TLS terminator: it derives scheme + host from
// window.location, matching whatever origin served the page.
export function wsUrl(path: string): string {
  const isHttps =
    typeof window !== "undefined" && window.location.protocol === "https:";
  const scheme = isHttps ? "wss:" : "ws:";
  const host = typeof window !== "undefined" ? window.location.host : "";
  // Ensure exactly one leading slash on the path.
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${scheme}//${host}${normalizedPath}`;
}
