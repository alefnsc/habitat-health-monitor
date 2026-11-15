import type { Alert, LinkState, StatusEntry } from "./contract";
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

// Hub push events the panel draws: alert frames and link-state frames from the one app WebSocket.
type AlertListener = (a: Alert) => void;
type LinkListener = (l: LinkState) => void;
const alertListeners = new Set<AlertListener>();
const linkListeners = new Set<LinkListener>();

export const hubEvents = {
  alert(a: Alert): void {
    alertListeners.forEach((l) => l(a));
  },
  link(s: LinkState): void {
    linkListeners.forEach((l) => l(s));
  },
  onAlert(l: AlertListener): () => void {
    alertListeners.add(l);
    return () => alertListeners.delete(l);
  },
  onLink(l: LinkListener): () => void {
    linkListeners.add(l);
    return () => linkListeners.delete(l);
  },
};
