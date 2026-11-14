# @ground-truth/physics

Dependency-free TypeScript, pure functions, no I/O. It turns a recorded exercise
session into the two currencies of the [brief](../../docs/strategy.md):

- **Energy** — mechanical work in joules, and a labelled metabolic range.
- **Load** — peak force in newtons, and a skeletal load stimulus with its
  cumulative deficit against an Earth baseline.

Gravity (`gEnvMs2`) and applied device force are inputs to every calculation, so
the same code compares a session on Earth with one on the ISS. SI units; the
unit is in the name (`massKg`, `forceN`, `workJ`, `speedMs`, `gEnvMs2`). Invalid
input throws a `RangeError` naming the argument.

**This package does load accounting, not clinical inference.** It does
bookkeeping on loads that someone or something supplied; it does not measure
bone and does not predict bone loss.

```sh
npm test                                      # from the repo root
npm run typecheck -w @ground-truth/physics
```

## Usage

### Constants and session types (`constants`, `session`)

```ts
import { G_ENV_MS2, GENC_2010_PEAK_LOAD_DECREMENT, type Environment } from "@ground-truth/physics";

const env: Environment = {
  gEnvMs2: G_ENV_MS2.ISS, // 0
  body: "ISS",
  massKg: 78.4,
  massSource: "SLAMMD",
  massMeasuredAt: "2026-11-02T09:12:00Z",
};
GENC_2010_PEAK_LOAD_DECREMENT.squat; // 0.65
```

### Mechanics (`mechanics`)

Work and peak force from vertical position samples, for any gravity. The scheme
is the discrete work-energy theorem, so a mass that starts and ends at rest has
net work exactly `m · g_env · Δy`. No smoothing is applied.

```ts
import { trajectoryWork } from "@ground-truth/physics";

const r = trajectoryWork(samples, 10, 9.81); // samples: { tS, yM }[]
r.positiveWorkJ; r.negativeWorkJ; r.netWorkJ; r.peakForceN; r.displacementM; r.pathLengthM; r.impulseNs;

// A constant device force that resists upward motion (added weight, an ARED setting),
// e.g. a camera-tracked rep on the ISS under 1000 N. The mass is the LOAD's (the bar and plates
// the wrist tracks), not the body's: the wrist trajectory is not the body's centre of mass.
trajectoryWork(samples, 20, 0, { deviceForceN: 1000 });
forceSeries(samples, 20, 0, { deviceForceN: 1000 }); // { tS, forceN }[], interior samples only
```

The force model is `F = m·(g_env + a) + F_device`. The device force is constant and
always points against +y, so on the way down it does negative work, exactly as
weight does. `negativeWorkJ` is <= 0. `peakForceN` is the maximum of |F| over the
interior samples. `pathLengthM` is Σ|Δy| (0.5 for a 0.5 m lift, 1.0 for the lift
and the lowering, where `displacementM` is 0). `impulseNs` is the signed ∫F dt,
`(m·g_env + F_device)·Δt + m·(v_end − v_start)`, from the end velocities and not
from integrating the noisy force series. `forceSeries` is the signed force at each
interior sample. See [Noise sensitivity](#noise-sensitivity) before feeding any of
it camera positions.

### Devices and environment (`devices`)

```ts
import {
  ergometerActualPowerW, ergometerWorkJ, metabolicRange, totalForceN, deviceForceForEarthEquivalenceN,
  treadmillEffectiveForceN, aredRepWorkJ, aredPeakForceN, froudeTransitionSpeedMs,
} from "@ground-truth/physics";

// ergometerSamples: { tS, displayedPowerW }[] from the dynamometer display. The 0.20–0.25
// band is a cycling gross-efficiency figure, so it is applied to ergometer work as a
// cross-check, not to the work of a lift.

ergometerActualPowerW(75);                       // 61.7 W (0.98·P − 11.8)
metabolicRange(ergometerWorkJ(ergometerSamples)); // { lowJ, highJ, kind: "ESTIMATE", basis }
deviceForceForEarthEquivalenceN(1769.1, 78.4, 0); // 1769.1 N on the ISS
treadmillEffectiveForceN(78.4, 0, 0.7);           // 538.4 N
aredRepWorkJ(2669, 0.762);                        // { concentricJ: 2033.8, eccentricMagnitudeJ: 1830.4 } (a magnitude)
aredPeakForceN(2669, 0.762, 2);                   // 3562 N
froudeTransitionSpeedMs(1.62, 0.9);               // 0.854 m/s on the Moon
```

### Load stimulus (`load`)

```ts
import { dailyLoadStimulus, cyclesToMatch, cumulativeDeficit } from "@ground-truth/physics";

dailyLoadStimulus([{ cycles: 12, peakLoad: 2000 }]); // 3722.4  ( (Σ n σ⁴)^(1/4) )
cyclesToMatch(0.25);                                  // 256
cumulativeDeficit([{ day: 0, achieved: 25 }, { day: 180, achieved: 25 }], 100); // 13500
```

## Measured versus estimated

Three groups, from most to least assumed.

**Computed from the inputs, no model parameters.** The result follows from the
data you pass in and the arithmetic stated in the doc comment:
`trajectoryWork` (work and peak force), `totalForceN`,
`deviceForceForEarthEquivalenceN`, `cumulativeDeficit` (only as good as the
baseline and the achieved series you pass in) and the integration inside
`ergometerWorkJ`.

**A published model with stated parameters.** Correct if the model applies to your
case; the parameter is in the source and the doc comment:

- `ergometerActualPowerW`: the CEVIS dynamometer correction `0.98·P − 11.8`. CEVIS
  was replaced by FERGO in October 2023 and this package does not claim the same
  correction for FERGO.
- `treadmillEffectiveForceN`: a static model, `m·g_env + supportFraction·m·1 g`. It
  is not a measured ground reaction force.
- `froudeTransitionSpeedMs`: Fr = 0.5. On the T2 treadmill the relevant gravity is the
  harness-supplied one (`supportFraction × 9.81`), not 0.
- `dailyLoadStimulus` and `cyclesToMatch`: exponent `m = 4`, the standard
  Carter/Whalen/Beaupré value, not a fitted one.
- `aredRepWorkJ`: a constant pneumatic force over a rest-to-rest stroke with a
  lossless flywheel, and a default eccentric ratio of 0.9, the brief's upper bound.

**Calibrated or estimated, and labelled as such.**

- `aredPeakForceN` rests on `ARED_FLYWHEEL_EFFECTIVE_MASS_KG`, **CALIBRATED** to one
  anchor in the brief (+893 N at 2669 N, 0.762 m, 2 s), not published. Three
  assumptions stand behind it: (1) the effective flywheel mass is independent of
  the load setting, because the brief states its anchor only "at the 600 lbf
  setting"; (2) the brief says "up to +91 kgf", so the anchor is an upper bound,
  which this model treats as the value for a sinusoidal stroke; (3) the work claim
  assumes a lossless flywheel and a constant pneumatic force (the brief says
  "nearly constant"). The brief also calls the term "velocity-dependent" while writing
  `F_flywheel(ẍ)` and describing a peak at the bottom of the stroke; this model
  follows the formula and the timing sentence, so the term is proportional to
  acceleration.
- `metabolicRange` is a range (gross efficiency 0.20–0.25), tagged `"ESTIMATE"`.
  Kilocalories are never derived from mechanics as a single figure.
- `aredRepWorkJ` returns `eccentricMagnitudeJ`, a positive magnitude; the signed
  counterpart in `trajectoryWork` is `negativeWorkJ`, which is <= 0.

## Noise sensitivity

`trajectoryWork` applies **no smoothing**. `positiveWorkJ` and `peakForceN` are
**not usable on raw camera positions**: they come from first and second
differences of the position, which amplify noise. Filter the positions first.

Measured in review on synthetic trajectories, not on real video: 10 kg, 0.5 m,
a 1 s lift followed by a 1 s lowering, 60 Hz, Earth, a minimum-jerk profile with
±2 mm uniform position noise. The noise-free truth is 49.05 J and 126.9 N. Filter:
zero-phase 2nd-order Butterworth low-pass.

| Filter | `positiveWorkJ` | `peakForceN` |
|---|---|---|
| none | 55.48 J | 363 N |
| 10 Hz | 51.39 J | 152.9 N |
| 6 Hz | 50.38 J | 139.9 N |
| 4 Hz | 49.82 J | 131.7 N |
| 3 Hz | 49.77 J | 128.8 N |

`netWorkJ` stayed within 0.5 J of the truth throughout, because it depends only on
the end samples. That is why it must not be used as evidence that the input is
clean. A higher sample rate makes raw input worse, not better: differencing divides
the noise by the sample interval, and by its square for acceleration. Guidance: low-pass at 3–4 Hz for peak force;
6 Hz is enough for work. The filter is not part of this package.

## Consuming this package

`main` and `types` point at the TypeScript source, and the source imports are
extensionless. Consume it through a bundler or a TypeScript-aware toolchain: an npm
workspace, or a git dependency pinned to a commit SHA. It is not published to a
registry and does not run under plain Node without a build. There is no build step.

## Known gaps

What is still missing:

- Loading rate (a third derivative of position; revisit with real video).

Closed for the capture pipeline: an optional device force in the trajectory integral,
path length, a per-sample force series, and impulse.

## Two places where the numbers differ from the brief's prose

Recorded so nobody "fixes" the tests to match the prose.

1. **Ergometer error.** The brief says an 11.8 W offset on a 75 W prescription
   "is a 16 % error". That counts the offset alone (11.8 / 75 = 15.7 %). The full
   correction `0.98 × 75 − 11.8` gives 61.7 W, which is 17.7 % below the display.
   The tests assert 61.7 W.
2. **Load stimulus gap.** The brief says achieved peak load is about a quarter of
   Earth-equivalent "and with m = 4 that is a very large gap in S". `S` is
   homogeneous of degree 1 in peak load, so a quarter of the load gives exactly a
   quarter of `S`. What is very large is the number of cycles needed to
   compensate: `(1/0.25)^4 = 256` times as many. The package exposes that number
   as `cyclesToMatch`.
