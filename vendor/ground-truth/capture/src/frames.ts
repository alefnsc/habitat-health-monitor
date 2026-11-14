/**
 * One frame of pose-model output, reduced to what the pipeline needs. Image
 * coordinates are normalised (0–1) with y pointing DOWN, as pose models report them.
 */
export interface PoseFrame {
  tS: number; // capture timestamp, seconds
  wristY: number; // normalised image coordinate, y down
  visibility: number; // 0..1 as reported by the pose model
}
