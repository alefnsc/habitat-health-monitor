import type { LinkState, StatusBody } from "../contract";
import { COPY } from "../copy";
import { linkAt, statusAt, type ReplayFile } from "./adapt";

const LOOP_GAP_MS = 3000;
const TICK_MS = 500;

type Frame = { positionMs: number; status: StatusBody; link: LinkState | null };

export function createReplayPlayer(file: ReplayFile, clock: () => number, onFrame: (f: Frame) => void) {
  const duration = file.arrivals.length ? file.arrivals[file.arrivals.length - 1].at_ms : 0;
  const period = duration + LOOP_GAP_MS;
  let playing = false;
  let startedAt = clock();
  let frozen = 0;
  let timer: ReturnType<typeof setInterval> | undefined;

  const position = () => (playing ? (clock() - startedAt) % period : frozen);
  const emit = () => {
    const p = position();
    onFrame({ positionMs: p, status: statusAt(file, p, null), link: linkAt(file, p) });
  };
  return {
    play() {
      if (playing) return;
      startedAt = clock() - frozen;
      playing = true;
      timer = setInterval(emit, TICK_MS);
      emit();
    },
    pause() {
      if (!playing) return;
      frozen = position();
      playing = false;
      clearInterval(timer);
    },
    restart() {
      frozen = 0;
      startedAt = clock();
      emit();
    },
    positionMs: position,
    durationMs: () => duration,
  };
}

const mmss = (ms: number) => {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

export function replayBanner(label: string, positionMs: number, durationMs: number): string {
  return `${COPY["replay.banner"]} ${label} · ${mmss(positionMs)} / ${mmss(durationMs)}`;
}
