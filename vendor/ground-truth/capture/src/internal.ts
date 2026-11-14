/** Shared by the modules of this package; not part of its public surface (index.ts does not export it). */

export function requireFinite(name: string, value: number): void {
  if (!Number.isFinite(value)) throw new RangeError(`${name} must be a finite number, got ${value}`);
}
