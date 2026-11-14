import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { connectWs } from "../src/ws";

class FakeSocket {
  static instances: FakeSocket[] = [];
  static times: number[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
    FakeSocket.times.push(Date.now());
  }
  close() {
    this.closed = true;
  }
  emit(data: unknown) {
    this.onmessage?.({ data: typeof data === "string" ? data : JSON.stringify(data) });
  }
}

const deps = () => ({ WebSocketImpl: FakeSocket as unknown as typeof WebSocket, backoffMs: [1000, 2000, 5000] });

beforeEach(() => {
  FakeSocket.instances = [];
  FakeSocket.times = [];
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe("ws", () => {
  test("test_ws_dispatch", () => {
    const got: unknown[] = [];
    connectWs("ws://x/ws", (m) => got.push(m), deps());
    const s = FakeSocket.instances[0];
    s.onopen?.();
    for (const type of ["snapshot", "assessment", "alert", "prompt", "link"]) s.emit({ type, data: { a: 1 } });
    expect(got).toHaveLength(5);
    s.emit({ type: "reading", data: { a: 1 } });
    s.emit("not json");
    expect(got).toHaveLength(5);
  });

  test("test_ws_reconnect_backoff", () => {
    connectWs("ws://x/ws", () => {}, deps());
    const t0 = FakeSocket.times[0];
    const expected = [1000, 2000, 5000, 5000];
    let elapsed = 0;
    for (const wait of expected) {
      const n = FakeSocket.instances.length;
      FakeSocket.instances[n - 1].onclose?.();
      vi.advanceTimersByTime(wait - 1);
      expect(FakeSocket.instances).toHaveLength(n);
      vi.advanceTimersByTime(1);
      expect(FakeSocket.instances).toHaveLength(n + 1);
      elapsed += wait;
      expect(FakeSocket.times[n] - t0).toBe(elapsed);
    }
  });

  test("test_ws_close_stops", () => {
    const h = connectWs("ws://x/ws", () => {}, deps());
    h.close();
    FakeSocket.instances[0].onclose?.();
    vi.advanceTimersByTime(60000);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(h.state()).toBe("closed");
  });
});
