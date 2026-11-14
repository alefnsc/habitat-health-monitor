// Keeps the calibration between sets: the second set starts without a new calibration step.
export function createSetState() {
  let scale: number | null = null;
  return {
    setScale(metersPerUnit: number): void {
      scale = metersPerUnit;
    },
    nextSet(): { needsCalibration: boolean; metersPerUnit: number | null } {
      return { needsCalibration: scale === null, metersPerUnit: scale };
    },
  };
}
