import type { StatusEntry } from "./contract";
import { applyAssessment } from "./model/status";

// Shared board state: the latest StatusEntry per indicator, fed by snapshot and assessment frames and by POST results.
type Listener = () => void;

let entries: StatusEntry[] = [];
const listeners = new Set<Listener>();
const notify = () => listeners.forEach((l) => l());

export const board = {
  get entries(): StatusEntry[] {
    return entries;
  },
  replace(next: StatusEntry[]): void {
    entries = next;
    notify();
  },
  apply(results: StatusEntry[]): void {
    entries = results.reduce(applyAssessment, entries);
    notify();
  },
  subscribe(l: Listener): () => void {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};
