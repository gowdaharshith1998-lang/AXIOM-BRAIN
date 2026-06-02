import { useEffect, useState } from "react";

import { subscribe } from "@/lib/auth";

/**
 * Returns a counter that increments whenever the API auth token changes
 * (set or cleared).
 *
 * Every effect that opens a WebSocket (or any other long-lived authenticated
 * connection) must include this value in its dependency array so the
 * connection is re-created with fresh credentials after the user enters a
 * token in the TokenGate. Without it, a socket created before authentication
 * keeps retrying unauthenticated forever (it resolves its subprotocols only
 * at connect time).
 */
export function useAuthEpoch(): number {
  const [epoch, setEpoch] = useState(0);

  useEffect(() => {
    return subscribe(() => setEpoch((value) => value + 1));
  }, []);

  return epoch;
}
