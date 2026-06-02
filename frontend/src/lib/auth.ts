// In-memory API token store for the SPA (P1-15).
//
// The token lives in a module-level variable by default — NOT localStorage —
// so it is never persisted to disk and is cleared on a full page reload. Cookie-
// based deployments (HttpOnly session cookie behind a reverse proxy) need no
// token at all; this store stays empty and `request()` still sends credentials.
//
// Opt-in `sessionStorage` persistence ("remember for this tab") survives a
// reload within the same tab only — it never leaks to other tabs or to disk.

const SESSION_STORAGE_KEY = "axiom.api-token";

let apiToken: string | null = null;
const listeners = new Set<() => void>();

function safeSessionStorage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.sessionStorage;
  } catch {
    // sessionStorage can throw in private-mode / sandboxed contexts.
    return null;
  }
}

function readPersisted(): string | null {
  const store = safeSessionStorage();
  if (!store) return null;
  try {
    const value = store.getItem(SESSION_STORAGE_KEY);
    return value && value.trim() ? value : null;
  } catch {
    return null;
  }
}

// Hydrate from sessionStorage on module load (only when "remember" was used).
apiToken = readPersisted();

function notify(): void {
  for (const listener of listeners) listener();
}

/**
 * Set the active API token.
 *
 * @param token   The bearer token. An empty/blank value clears the token.
 * @param remember When true, persist to sessionStorage so it survives a reload
 *                 within this tab. Defaults to in-memory only.
 */
export function setApiToken(token: string, remember = false): void {
  const trimmed = token.trim();
  if (!trimmed) {
    clearApiToken();
    return;
  }
  apiToken = trimmed;
  const store = safeSessionStorage();
  if (store) {
    try {
      if (remember) store.setItem(SESSION_STORAGE_KEY, trimmed);
      else store.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // Persistence is best-effort; the in-memory token still works.
    }
  }
  notify();
}

export function getApiToken(): string | null {
  return apiToken;
}

export function clearApiToken(): void {
  apiToken = null;
  const store = safeSessionStorage();
  if (store) {
    try {
      store.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // ignore
    }
  }
  notify();
}

export function hasApiToken(): boolean {
  return apiToken !== null;
}

/**
 * Subscribe to auth-state changes (set / clear). Returns an unsubscribe fn.
 */
export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
