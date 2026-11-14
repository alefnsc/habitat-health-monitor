/**
 * Repetition segmentation on a smoothed, uniformly sampled vertical position.
 */

/** Judgement call: smaller reversals are treated as jitter. */
export const MIN_PHASE_DISPLACEMENT_M = 0.1;

/** Sample indices of one repetition: lift start, turnaround, lowering end. */
export interface Rep {
  startIndex: number;
  topIndex: number;
  endIndex: number;
}

interface Extremum {
  index: number;
  kind: "MIN" | "MAX";
}

/**
 * Turning points of the position, by displacement hysteresis (a zig-zag filter): a local
 * extremum is confirmed only once the position has moved back by at least
 * `minPhaseDisplacementM` from it. Raw velocity sign changes are never used, so noise
 * and small wobbles cannot make a turning point. Consequently every leg between two
 * confirmed turning points spans at least the threshold. An extremum at the very end
 * of the trace is kept: the leg that leads to it has already passed the threshold.
 * Ties go to the earliest sample.
 */
function turningPoints(y: readonly number[], minPhaseDisplacementM: number): Extremum[] {
  const at = (i: number): number => y[i] as number;
  const found: Extremum[] = [];
  let mode: "UNKNOWN" | "UP" | "DOWN" = "UNKNOWN";
  let hi = 0; // index of the highest sample since the last confirmed turning point
  let lo = 0; // index of the lowest
  for (let i = 1; i < y.length; i++) {
    if (mode === "UNKNOWN") {
      if (at(i) > at(hi)) hi = i;
      if (at(i) < at(lo)) lo = i;
      if (at(i) - at(lo) >= minPhaseDisplacementM) {
        found.push({ index: lo, kind: "MIN" });
        mode = "UP";
        hi = i;
      } else if (at(hi) - at(i) >= minPhaseDisplacementM) {
        found.push({ index: hi, kind: "MAX" });
        mode = "DOWN";
        lo = i;
      }
    } else if (mode === "UP") {
      if (at(i) > at(hi)) hi = i;
      else if (at(hi) - at(i) >= minPhaseDisplacementM) {
        found.push({ index: hi, kind: "MAX" });
        mode = "DOWN";
        lo = i;
      }
    } else {
      if (at(i) < at(lo)) lo = i;
      else if (at(i) - at(lo) >= minPhaseDisplacementM) {
        found.push({ index: lo, kind: "MIN" });
        mode = "UP";
        hi = i;
      }
    }
  }
  if (mode === "UP") found.push({ index: hi, kind: "MAX" });
  else if (mode === "DOWN") found.push({ index: lo, kind: "MIN" });
  return found;
}

/**
 * A rep is an upward phase of at least the minimum displacement followed by a downward
 * phase of at least the minimum displacement: a MIN, a MAX and the next MIN among the
 * turning points. A lift with no lowering is not a rep, and a movement that begins
 * mid-lowering is ignored until the first minimum. Adjacent reps share the minimum
 * between them (the rest between two reps is split at its lowest sample), so
 * `endIndex` of one rep is `startIndex` of the next.
 *
 * Input: smoothed, uniformly sampled vertical position in metres (up positive).
 */
export function segmentReps(yM: readonly number[], minPhaseDisplacementM: number = MIN_PHASE_DISPLACEMENT_M): Rep[] {
  if (!Number.isFinite(minPhaseDisplacementM) || minPhaseDisplacementM <= 0) {
    throw new RangeError(`minPhaseDisplacementM must be a finite number > 0, got ${minPhaseDisplacementM}`);
  }
  yM.forEach((v, i) => {
    if (!Number.isFinite(v)) throw new RangeError(`yM[${i}] must be a finite number, got ${v}`);
  });

  const points = turningPoints(yM, minPhaseDisplacementM);
  const reps: Rep[] = [];
  for (let k = 0; k + 2 < points.length; k++) {
    const [start, top, end] = [points[k] as Extremum, points[k + 1] as Extremum, points[k + 2] as Extremum];
    if (start.kind === "MIN" && top.kind === "MAX" && end.kind === "MIN") {
      reps.push({ startIndex: start.index, topIndex: top.index, endIndex: end.index });
    }
  }
  return reps;
}
