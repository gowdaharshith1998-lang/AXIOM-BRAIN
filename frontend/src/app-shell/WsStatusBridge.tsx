import { useEffect } from "react";

import { useAuthEpoch } from "@/hooks/useAuthEpoch";
import { BrainSocket } from "@/lib/websocket";
import { wsUrl } from "@/lib/wsUrl";
import { useBrainStore } from "@/state/brain.store";

export function WsStatusBridge() {
  const setConnectionStatus = useBrainStore((s) => s.setConnectionStatus);
  const applyEvent = useBrainStore((s) => s.applyEvent);
  const authEpoch = useAuthEpoch();

  useEffect(() => {
    const url = wsUrl("/ws/brain");
    const socket = new BrainSocket(url);
    socket.onStatus(setConnectionStatus);
    const off = socket.on((event) => {
      applyEvent(event);
      window.dispatchEvent(new CustomEvent("axiom:brain-event", { detail: event }));
    });
    socket.start();
    return () => {
      off();
      socket.close();
    };
  }, [applyEvent, setConnectionStatus, authEpoch]);

  return null;
}
