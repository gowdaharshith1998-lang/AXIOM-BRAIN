// Auth-aware WebSocket factory (P1-15).
//
// Browsers cannot set arbitrary headers on a WebSocket handshake, so the token
// rides on the Sec-WebSocket-Protocol list instead. The backend
// (studio/auth.py) scans the offered subprotocols for the marker
// `axiom.auth` and reads the *next* entry as `axiom-token.<base64url(token)>`.
//
// Cookie-based deployments need no token: the same-origin HttpOnly cookie is
// sent automatically on the handshake (which relies on the P1-14 wsUrl fix
// deriving host/scheme from window.location).

import { getApiToken } from "@/lib/auth";
import { wsUrl } from "@/lib/wsUrl";

export const WS_AUTH_SUBPROTOCOL = "axiom.auth";
export const WS_AUTH_TOKEN_PREFIX = "axiom-token.";

// Base64url-encode a UTF-8 string without padding (matches the backend decoder,
// which strips `=` padding and uses the URL-safe alphabet).
function base64UrlEncode(value: string): string {
  const utf8 = typeof TextEncoder !== "undefined"
    ? new TextEncoder().encode(value)
    : null;
  let binary = "";
  if (utf8) {
    for (const byte of utf8) binary += String.fromCharCode(byte);
  } else {
    binary = unescape(encodeURIComponent(value));
  }
  const base64 = btoa(binary);
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * Build the subprotocol list for an auth handshake, or undefined when no token
 * is set (cookie-based / dev deployments).
 */
export function authSubprotocols(): string[] | undefined {
  const token = getApiToken();
  if (!token) return undefined;
  return [WS_AUTH_SUBPROTOCOL, `${WS_AUTH_TOKEN_PREFIX}${base64UrlEncode(token)}`];
}

/**
 * Open a WebSocket to a backend path, deriving a proxy-safe URL from the
 * current origin and attaching the auth subprotocol when a token is set.
 */
export function wsConnect(path: string): WebSocket {
  const url = wsUrl(path);
  const protocols = authSubprotocols();
  return protocols ? new WebSocket(url, protocols) : new WebSocket(url);
}
