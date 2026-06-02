// Shared fetch wrapper that injects auth credentials (P1-15).
//
// Every API client routes through `request()` so auth is applied uniformly:
//   - `Authorization: Bearer <token>` when an in-memory token is set
//     (matches the backend's `Bearer ` parsing in studio/auth.py).
//   - `credentials: "include"` is always preserved so cookie-based
//     deployments (HttpOnly session cookie behind a reverse proxy) work too.
//
// On a 401/403 the wrapper fires a global `axiom:auth-required` CustomEvent so
// the TokenGate can prompt for credentials. When the backend never returns
// 401/403 (dev mode), the event never fires and no gate ever appears.

import { getApiToken } from "@/lib/auth";

export const AUTH_REQUIRED_EVENT = "axiom:auth-required";

export type AuthRequiredDetail = {
  status: number;
  url: string;
};

function dispatchAuthRequired(status: number, url: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<AuthRequiredDetail>(AUTH_REQUIRED_EVENT, {
      detail: { status, url },
    }),
  );
}

/**
 * Merge the Authorization header into an existing init, without clobbering a
 * caller-supplied Authorization header. Preserves `credentials: "include"`.
 */
export function withAuth(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers);
  const token = getApiToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return {
    credentials: "include",
    ...init,
    headers,
  };
}

/**
 * Auth-aware fetch. Behaves exactly like `fetch`, plus:
 *   - injects the bearer token + `credentials: "include"`, and
 *   - dispatches `axiom:auth-required` on a 401/403 response.
 *
 * Returns the raw Response so callers keep full control over body parsing and
 * non-OK handling (preserving each client's existing error semantics).
 */
export async function requestRaw(input: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, withAuth(init));
  if (response.status === 401 || response.status === 403) {
    dispatchAuthRequired(response.status, input);
  }
  return response;
}

/**
 * Convenience JSON wrapper: throws `HTTP <status>` on a non-OK response and
 * returns the parsed body otherwise. Auth-required dispatch already happened in
 * `requestRaw`.
 */
export async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await requestRaw(input, init);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}
