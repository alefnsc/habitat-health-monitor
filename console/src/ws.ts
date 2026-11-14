import type { WsMessage } from "./contract";

const TYPES = new Set(["snapshot", "assessment", "alert", "prompt", "link"]);

export interface WsDeps {
  WebSocketImpl: typeof WebSocket;
  backoffMs: number[];
}

export interface WsHandle {
  close(): void;
  state(): "open" | "connecting" | "closed";
  lastOpenAt(): number | null;
}

export function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws`;
}

export function parseFrame(raw: unknown): WsMessage | null {
  if (typeof raw !== "string") return null;
  try {
    const m = JSON.parse(raw);
    if (m && typeof m === "object" && TYPES.has(m.type) && m.data && typeof m.data === "object") {
      return m as WsMessage;
    }
  } catch {
    /* not JSON */
  }
  return null;
}

export function connectWs(url: string, onMessage: (m: WsMessage) => void, deps?: Partial<WsDeps>): WsHandle {
  const Impl = deps?.WebSocketImpl ?? WebSocket;
  const backoff = deps?.backoffMs ?? [1000, 2000, 5000];
  let stopped = false;
  let sock: WebSocket | null = null;
  let current: "open" | "connecting" | "closed" = "closed";
  let failures = 0;
  let openAt: number | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    current = "connecting";
    const s = new Impl(url);
    sock = s;
    s.onopen = () => {
      current = "open";
      failures = 0;
      openAt = Date.now();
    };
    s.onmessage = (ev: MessageEvent) => {
      const m = parseFrame(ev.data);
      if (m) onMessage(m);
    };
    s.onclose = () => {
      current = "closed";
      if (stopped) return;
      const wait = backoff[Math.min(failures, backoff.length - 1)];
      failures += 1;
      timer = setTimeout(open, wait);
    };
  };
  open();

  return {
    close() {
      stopped = true;
      clearTimeout(timer);
      try {
        sock?.close();
      } catch {
        /* already closed */
      }
      current = "closed";
    },
    state: () => current,
    lastOpenAt: () => openAt,
  };
}
