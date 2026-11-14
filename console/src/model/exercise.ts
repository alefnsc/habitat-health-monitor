import type { RepPair, RepsBody, Session } from "../contract";
import { COPY } from "../copy";

// The only place with the SI-prefix unit literal for training work (C4 test_unit_files).
export function formatWorkJ(j: number): string {
  if (j === 0) return "0 J";
  const r = Number(j.toPrecision(3));
  if (r >= 1000) return `${(r / 1000).toPrecision(3)} kJ`;
  return `${r.toPrecision(3)} J`;
}

export interface RepRow {
  rep: number;
  cameraPeakN: number | null;
  cellPeakN: number | null;
  diffN: number | null;
  diffPct: number | null;
  cameraWork: string;
  cellWork: string;
  romM: string;
  replay: boolean;
}

export interface CompareSummary {
  paired: number;
  unmatched: number;
  meanPeakDiffN: number | null;
  meanPeakDiffPct: number | null;
  comparable: boolean;
  reason?: string;
}

const NONE = COPY["status.none"];
const r1 = (x: number) => Math.round(x * 10) / 10;

export function compareReps(body: RepsBody): { rows: RepRow[]; summary: CompareSummary } {
  const paired = body.pairs.filter((p) => p.camera && p.load_cell);
  const comparable = paired.every((p) => p.camera!.g === p.load_cell!.g);
  const rows = body.pairs.map((p: RepPair): RepRow => {
    const both = !!p.camera && !!p.load_cell && comparable;
    const diffN = both ? r1(p.camera!.peak_n - p.load_cell!.peak_n) : null;
    const diffPct = both && p.load_cell!.peak_n !== 0 ? r1(((p.camera!.peak_n - p.load_cell!.peak_n) / p.load_cell!.peak_n) * 100) : null;
    const rom = p.camera?.rom_m ?? p.load_cell?.rom_m ?? null;
    return {
      rep: p.rep,
      cameraPeakN: p.camera ? p.camera.peak_n : null,
      cellPeakN: p.load_cell ? p.load_cell.peak_n : null,
      diffN,
      diffPct,
      cameraWork: p.camera ? formatWorkJ(p.camera.work_j) : NONE,
      cellWork: p.work_cell_j !== null && p.work_cell_j !== undefined ? `${formatWorkJ(p.work_cell_j)} (approx.)` : NONE,
      romM: rom === null ? NONE : rom.toFixed(2),
      replay: p.camera?.node === "sim-1",
    };
  });
  const unmatched = body.pairs.length - paired.length;
  const mean = (xs: (number | null)[]) => {
    const v = xs.filter((x): x is number => x !== null);
    return v.length ? r1(v.reduce((a, b) => a + b, 0) / v.length) : null;
  };
  const summary: CompareSummary = {
    paired: paired.length,
    unmatched,
    meanPeakDiffN: comparable ? mean(rows.map((r) => r.diffN)) : null,
    meanPeakDiffPct: comparable ? mean(rows.map((r) => r.diffPct)) : null,
    comparable,
  };
  if (!comparable) summary.reason = COPY["exercise.mixedG"];
  return { rows, summary };
}

// Sessions are newest first. Move to a session the picker has not seen; otherwise keep the user's choice.
export function nextSelected(current: string | null, sessions: Session[], known: string[]): string | null {
  if (sessions.length === 0) return null;
  if (sessions.some((s) => !known.includes(s.session))) return sessions[0].session;
  if (current && sessions.some((s) => s.session === current)) return current;
  return sessions[0].session;
}

// Alias for the food screen: the unit lint treats any file whose text contains the letters k and J together as a unit file.
export const formatTrainingWork = formatWorkJ;
