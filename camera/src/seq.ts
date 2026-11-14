export interface Sequencer {
  next(): number;
  boot: number;
}

// Same behaviour as the console sequencer: boot is the page-load time in Unix seconds, seq counts from 1.
export function createSequencer(bootEpochS: number): Sequencer {
  let n = 0;
  return { boot: bootEpochS, next: () => ++n };
}
