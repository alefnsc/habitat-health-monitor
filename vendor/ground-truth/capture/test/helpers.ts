import type { PoseFrame } from "../src/index";

/**
 * Deterministic uniform generator in [−1, 1): a 32-bit linear congruential generator
 * (Numerical Recipes constants). Test noise comes from here and never from Math.random,
 * so every failure is reproducible from its seed.
 */
export function lcg(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 2 ** 31 - 1;
  };
}

/** Minimum-jerk profile: 0 at τ = 0, 1 at τ = 1, zero velocity and acceleration at both ends. */
export function minJerk(tau: number): number {
  return 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5;
}

export interface SyntheticSessionOptions {
  reps: number;
  heightM: number;
  upS: number;
  downS: number;
  restS: number;
  rateHz: number;
  /** Half-width of the uniform position noise in metres (±noiseM). 0 for none. */
  noiseM: number;
  seed: number;
  metersPerUnit: number;
}

/** Wrist height in the image when the arm is at rest at the bottom of the movement (y down). */
const BOTTOM_WRIST_Y = 0.7;

/**
 * Wrist positions of `reps` repetitions as a pose model would report them: normalised
 * image coordinates with y pointing down, visibility 1. The timeline is
 * rest, (up, down, rest) × reps, so there are rests before, between and after the reps.
 * Each lift follows minJerk(t/upS) and each lowering its mirror image. Position noise is
 * uniform ±noiseM metres, converted to image units with the same scale.
 */
export function syntheticSession(o: SyntheticSessionOptions): PoseFrame[] {
  const totalS = o.restS + o.reps * (o.upS + o.downS + o.restS);
  const n = Math.round(totalS * o.rateHz) + 1;
  const noise = lcg(o.seed);
  const frames: PoseFrame[] = [];
  for (let i = 0; i < n; i++) {
    const tS = i / o.rateHz;
    let local = tS - o.restS;
    let yM = 0;
    for (let r = 0; r < o.reps && local >= 0; r++) {
      if (local < o.upS) {
        yM = o.heightM * minJerk(local / o.upS);
        break;
      }
      local -= o.upS;
      if (local < o.downS) {
        yM = o.heightM * (1 - minJerk(local / o.downS));
        break;
      }
      local -= o.downS + o.restS;
    }
    yM += o.noiseM * noise();
    frames.push({ tS, wristY: BOTTOM_WRIST_Y - yM / o.metersPerUnit, visibility: 1 });
  }
  return frames;
}

/** One leg of a hand-drawn movement: take `durationS` to reach `toM`, with a minimum-jerk profile (a pause is a leg to the same height). */
export type Leg = [durationS: number, toM: number];

export interface LegSessionOptions {
  legs: readonly Leg[];
  /** Height at the start, metres. Default 0. */
  startM?: number;
  rateHz?: number; // default 60
  noiseM?: number; // default 0
  seed?: number; // default 1
  metersPerUnit?: number; // default 2.5
  /** Added to every timestamp, so a recording whose clock does not start at 0 can be built. Default 0. */
  clockOffsetS?: number;
}

/** Total duration of a list of legs. */
export const totalDurationS = (legs: readonly Leg[]): number => legs.reduce((sum, leg) => sum + leg[0], 0);

/** Height at time `tS` of the movement drawn by `legs` (it stays at the last height after the end). */
export function legPosition(legs: readonly Leg[], tS: number, startM = 0): number {
  let from = startM;
  let local = tS;
  for (const [durationS, toM] of legs) {
    if (local < durationS) return from + (toM - from) * minJerk(local / durationS);
    local -= durationS;
    from = toM;
  }
  return from;
}

/**
 * Wrist frames for an arbitrary movement drawn as legs (pick-ups, pauses, partial
 * movements, anything the rest-lift-lower-rest `syntheticSession` cannot draw).
 * Same image convention and noise as `syntheticSession`: y down, uniform ±noiseM metres.
 */
export function legSession(o: LegSessionOptions): PoseFrame[] {
  const rateHz = o.rateHz ?? 60;
  const metersPerUnit = o.metersPerUnit ?? 2.5;
  const noise = lcg(o.seed ?? 1);
  const n = Math.round(totalDurationS(o.legs) * rateHz) + 1;
  const frames: PoseFrame[] = [];
  for (let i = 0; i < n; i++) {
    const tS = i / rateHz;
    const yM = legPosition(o.legs, tS, o.startM ?? 0) + (o.noiseM ?? 0) * noise();
    frames.push({ tS: tS + (o.clockOffsetS ?? 0), wristY: BOTTOM_WRIST_Y - yM / metersPerUnit, visibility: 1 });
  }
  return frames;
}

/** `reps` lifts of `heightM` (up, then down) with `restS` of stillness before, between and after, as legs. */
export function repLegs(reps: number, heightM: number, upS: number, downS: number, restS: number): Leg[] {
  const legs: Leg[] = [[restS, 0]];
  for (let r = 0; r < reps; r++) legs.push([upS, heightM], [downS, 0], [restS, 0]);
  return legs;
}
