import { describe, expect, it } from "vitest";
import { LANDMARK, calibrationFromLandmarks, calibrationOfBestSide, framesOf, pickRecordedSide, wristSample, normalizedY, pickSide, toPoseFrame, wristOf, type Landmark } from "../../vendor/ground-truth/demo/src/pose/landmarks";

/** A full 33-landmark pose, all at (0.5, 0.5) and fully visible, with overrides by index. */
function pose(overrides: Record<number, Partial<Landmark>> = {}): Landmark[] {
  return Array.from({ length: 33 }, (_, i) => ({ x: 0.5, y: 0.5, visibility: 1, ...overrides[i] }));
}

describe("landmark indices", () => {
  it("are the pose model's, symmetric left and right", () => {
    expect(LANDMARK).toEqual({ LEFT_EYE: 2, RIGHT_EYE: 5, LEFT_WRIST: 15, RIGHT_WRIST: 16, LEFT_ANKLE: 27, RIGHT_ANKLE: 28 });
  });
});

describe("toPoseFrame", () => {
  const landmarks = pose({ 15: { y: 0.31, visibility: 0.9 }, 16: { y: 0.62, visibility: 0.4 } });

  it("reads the left wrist for LEFT and the right wrist for RIGHT, with the time given", () => {
    expect(toPoseFrame(1.25, landmarks, "LEFT")).toEqual({ tS: 1.25, wristY: 0.31, visibility: 0.9 });
    expect(toPoseFrame(1.25, landmarks, "RIGHT")).toEqual({ tS: 1.25, wristY: 0.62, visibility: 0.4 });
  });

  it("passes y through unchanged: the capture package owns the orientation", () => {
    // y is normalised and points down; 0.31 stays 0.31, and values outside 0..1 are not clamped here.
    expect(toPoseFrame(0, pose({ 15: { y: 1.2 } }), "LEFT").wristY).toBe(1.2);
    expect(toPoseFrame(0, pose({ 15: { y: -0.05 } }), "LEFT").wristY).toBe(-0.05);
  });

  it("no detection is visibility 0, not the last position", () => {
    expect(toPoseFrame(2, undefined, "LEFT")).toEqual({ tS: 2, wristY: 0, visibility: 0 });
    expect(toPoseFrame(2, [], "RIGHT")).toEqual({ tS: 2, wristY: 0, visibility: 0 });
  });

  it("a pose that stops before the wrist is a missing landmark", () => {
    expect(toPoseFrame(3, pose().slice(0, 12), "LEFT")).toEqual({ tS: 3, wristY: 0, visibility: 0 });
  });

  it("a wrist with no usable y or no visibility is not trusted", () => {
    expect(toPoseFrame(4, pose({ 15: { y: Number.NaN } }), "LEFT")).toEqual({ tS: 4, wristY: 0, visibility: 0 });
    const noVisibility = pose();
    noVisibility[15] = { x: 0.5, y: 0.4 };
    expect(toPoseFrame(4, noVisibility, "LEFT")).toEqual({ tS: 4, wristY: 0.4, visibility: 0 });
    expect(toPoseFrame(4, pose({ 15: { visibility: Number.NaN } }), "LEFT").visibility).toBe(0);
  });
});

describe("pickSide", () => {
  it("chooses the wrist with the higher mean visibility", () => {
    const samples = [
      pose({ 15: { visibility: 0.9 }, 16: { visibility: 0.2 } }),
      pose({ 15: { visibility: 0.8 }, 16: { visibility: 0.5 } }),
    ];
    expect(pickSide(samples)).toBe("LEFT");
    const flipped = [
      pose({ 15: { visibility: 0.1 }, 16: { visibility: 0.95 } }),
      pose({ 15: { visibility: 0.7 }, 16: { visibility: 0.9 } }),
    ];
    expect(pickSide(flipped)).toBe("RIGHT");
  });

  it("the mean, not a single frame: one very visible frame does not outweigh a hidden wrist", () => {
    const samples = [
      pose({ 15: { visibility: 1 }, 16: { visibility: 0.6 } }),
      pose({ 15: { visibility: 0 }, 16: { visibility: 0.6 } }),
      pose({ 15: { visibility: 0 }, 16: { visibility: 0.6 } }),
    ];
    expect(pickSide(samples)).toBe("RIGHT"); // left mean 0.33, right mean 0.6
  });

  it("a frame with no detection counts as invisible for both", () => {
    // left (0 + 0.6) / 2 = 0.3, right (0 + 0.7) / 2 = 0.35
    expect(pickSide([[], pose({ 16: { visibility: 0.7 }, 15: { visibility: 0.6 } })])).toBe("RIGHT");
  });

  it("with nothing to compare it says LEFT", () => {
    expect(pickSide([])).toBe("LEFT");
  });
});

describe("calibrationFromLandmarks", () => {
  it("returns the eye and ankle heights of the side asked for", () => {
    const l = pose({ 2: { y: 0.12 }, 27: { y: 0.93 }, 5: { y: 0.14 }, 28: { y: 0.95 } });
    expect(calibrationFromLandmarks(l, "LEFT")).toEqual({ eyeY: 0.12, ankleY: 0.93 });
    expect(calibrationFromLandmarks(l, "RIGHT")).toEqual({ eyeY: 0.14, ankleY: 0.95 });
  });

  it("is null when the ankle is hidden", () => {
    expect(calibrationFromLandmarks(pose({ 27: { visibility: 0.3 } }), "LEFT")).toBeNull();
  });

  it("is null when the eye is hidden, and visibility 0.5 is enough", () => {
    expect(calibrationFromLandmarks(pose({ 2: { visibility: 0.49 } }), "LEFT")).toBeNull();
    expect(calibrationFromLandmarks(pose({ 2: { visibility: 0.5 } }), "LEFT")).not.toBeNull();
  });

  it("is null for a pose that is too short, or a landmark with no visibility", () => {
    expect(calibrationFromLandmarks(pose().slice(0, 20), "LEFT")).toBeNull();
    const l = pose();
    l[27] = { x: 0.5, y: 0.9 };
    expect(calibrationFromLandmarks(l, "LEFT")).toBeNull();
  });
});

describe("wristOf", () => {
  it("is the wrist of the side asked for, and undefined when there is none", () => {
    const l = pose({ 15: { x: 0.2 }, 16: { x: 0.8 } });
    expect(wristOf(l, "LEFT")?.x).toBe(0.2);
    expect(wristOf(l, "RIGHT")?.x).toBe(0.8);
    expect(wristOf(undefined, "LEFT")).toBeUndefined();
    expect(wristOf(pose().slice(0, 10), "RIGHT")).toBeUndefined();
  });
});

describe("normalizedY", () => {
  it("is the fraction of the element's height from its top, clamped", () => {
    expect(normalizedY(150, 100, 200)).toBe(0.25);
    expect(normalizedY(100, 100, 200)).toBe(0);
    expect(normalizedY(300, 100, 200)).toBe(1);
    expect(normalizedY(50, 100, 200)).toBe(0);
    expect(normalizedY(500, 100, 200)).toBe(1);
  });
  it("an element with no height gives 0, not NaN", () => {
    expect(normalizedY(10, 0, 0)).toBe(0);
  });
});

describe("the side is chosen over the recorded frames", () => {
  // Preview might have seen the left wrist; the recording has the right one visible. The recorded frames decide.
  const frame = (tS: number, left: Partial<Landmark>, right: Partial<Landmark>) => wristSample(tS, pose({ 15: left, 16: right }));

  it("wristSample keeps both wrists of one frame, each as the capture package wants it", () => {
    const s = wristSample(0.5, pose({ 15: { y: 0.3, visibility: 0.9 }, 16: { y: 0.6, visibility: 0.2 } }));
    expect(s).toEqual({ tS: 0.5, LEFT: { tS: 0.5, wristY: 0.3, visibility: 0.9 }, RIGHT: { tS: 0.5, wristY: 0.6, visibility: 0.2 } });
    expect(wristSample(1, undefined)).toEqual({ tS: 1, LEFT: { tS: 1, wristY: 0, visibility: 0 }, RIGHT: { tS: 1, wristY: 0, visibility: 0 } });
  });

  it("chooses the wrist with the higher mean visibility over the whole recording", () => {
    const samples = [
      frame(0, { visibility: 0.9 }, { visibility: 0.1 }), // a stray frame where the left was seen
      frame(1, { visibility: 0.1 }, { visibility: 0.95 }),
      frame(2, { visibility: 0.1 }, { visibility: 0.95 }),
      frame(3, { visibility: 0.1 }, { visibility: 0.95 }),
    ];
    expect(pickRecordedSide(samples)).toBe("RIGHT");
  });

  it("the frames analysed are that side's, constant for the whole recording", () => {
    const samples = [
      frame(0, { y: 0.1, visibility: 0.2 }, { y: 0.7, visibility: 0.9 }),
      frame(1, { y: 0.2, visibility: 0.9 }, { y: 0.6, visibility: 0.9 }),
    ];
    const side = pickRecordedSide(samples);
    expect(side).toBe("RIGHT"); // right mean 0.9, left mean 0.55
    expect(framesOf(samples, side).map((f) => f.wristY)).toEqual([0.7, 0.6]);
  });

  it("a tie, or nothing recorded, is LEFT", () => {
    expect(pickRecordedSide([])).toBe("LEFT");
    expect(pickRecordedSide([frame(0, { visibility: 0.5 }, { visibility: 0.5 })])).toBe("LEFT");
  });
});

describe("calibrationOfBestSide", () => {
  it("reads eye and ankle of the side whose eye and ankle are more visible, and says which", () => {
    const l = pose({ 2: { y: 0.1, visibility: 0.3 }, 27: { y: 0.9, visibility: 0.3 }, 5: { y: 0.12, visibility: 0.9 }, 28: { y: 0.94, visibility: 0.9 } });
    expect(calibrationOfBestSide(l)).toEqual({ side: "RIGHT", eyeY: 0.12, ankleY: 0.94 });
  });
  it("falls to the other side when the better one is not usable, and to null when neither is", () => {
    const l = pose({ 2: { y: 0.1, visibility: 0.9 }, 27: { y: 0.9, visibility: 0.9 }, 5: { visibility: 0.8 }, 28: { visibility: 0.2 } });
    expect(calibrationOfBestSide(l)?.side).toBe("LEFT");
    expect(calibrationOfBestSide(pose({ 27: { visibility: 0.1 }, 28: { visibility: 0.1 } }))).toBeNull();
    expect(calibrationOfBestSide(undefined)).toBeNull();
  });
});
