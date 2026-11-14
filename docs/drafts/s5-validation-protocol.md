# S5 draft: pre-declared validation protocol and targets

Status: DRAFT for operator approval. Intended destination: `docs/validation.md` (sections "Protocol" and "Pre-declared targets") and `data/validation/README.md` (text at the end). The commit that publishes this protocol must be earlier than the first validation reading in the hub database (S5 acceptance); with the D27 shift the first session starts Sat 16:00, so publish before 16:00.
Drafted by the S agent, 2026-11-14 from plan Task S5, D11, D21, D27. Depends on S1 Q6 (may adult team members' own consented, pseudonymised readings appear in published validation data): if the Local Lead says no, publish only the aggregate table and keep the CSVs local.

## Protocol

### Comparisons and schedule (D27: plan times +1 h)

| # | Comparison | Session | Time (D27) | Condition |
|---|---|---|---|---|
| 1 | MAX30102 `hr` vs fingertip oximeter HR | S7 | Sat 16:00 to 17:20 | HR live (F11) |
| 2 | MAX30102 `spo2` vs fingertip oximeter SpO2 | S7 | same sitting | |
| 3 | DS18B20 `skin_temp` (axilla, arm closed) vs clinical thermometer `body_temp`, site recorded | S8a | Sat 17:20 to 18:40 | F12 built |
| 4 | MLX90614 `skin_temp` (forehead, 1 to 2 cm) vs the same thermometer | S8b | Sat after 19:00 | only if F18 is built |
| 5 | Camera `peak_n` and `work_j` vs load cell, per rep | S10 | Sun 09:00 to 10:30 (unchanged) | rig calibrated |

D28: no hardware has been on the bench yet. Sessions 1 to 4 start only when the operator and the hardware lane meet; if they have not met by the Sat 23:00 check, the cut order applies (the plan then reports "not run"). Nothing is validated on simulator data and the page never claims otherwise.

### Reference readings and crew attribution
- Reference readings are typed on the manual form with src `certified`, dev `manual` and `crew` set. During the session, manual `hr` and `spo2` come only from the oximeter.
- Crew attribution (D11): before each subject's first pair, the operator sets the console crew selector for the sensor node (`vitals-1`, or `cabin-1` for the MLX90614). This calls `POST /api/crew {node, crew}`, so the hub fills `crew` on that node's body readings. The log records each switch time.

### Pairing
- t = `measured_at` of the reference reading. No test reading further than 60 s from t is used (D11 cap).
- `hr` and `spo2`: median of `ok` test readings in [t - 10 s, t].
- `skin_temp`: median of `ok` test readings in [t - 30 s, t].
- Crew must match when both sides have one. A test reading with a null crew is accepted on time alone.
- Flagged readings (q other than `ok`) are never used; they are listed as failures with the reason.

### Sample size and procedure
- At least 20 pairs per sensor across at least 2 adult subjects, with at least 30 s between the pairs of one subject.
- Include post-exertion pairs (1 minute of stair steps) to widen the HR range.
- Calibration: if a one-point DS18B20 offset is used, it comes from a stirred water bath near 37 C before the session. Those readings are not reused as validation pairs.
- Exercise sessions run with the camera session g at 9.81, because the bench load cell is on Earth. Each set starts with the load hanging still for 2 s before the first rep, so the hub can read F0 from the first second (D21).

### Statistics
- bias = mean(test - ref).
- SD = sample standard deviation (n - 1).
- LoA = bias +/- 1.96 x SD.
- For SpO2 also Arms = root mean square of the differences.
- Report the attempted, valid and failed counts and every failure with its reason. Rounding only when the table is written.

### Subjects, consent and safety
- Adults on the team only. Consent is recorded verbally in the log. Pseudonymous ids are `crew-a`, `crew-b`, `crew-c`; no names appear in data files.
- Electrode or contact circuits on a person run on the power bank only (battery only, no mains-powered device connected).
- Nutrition has no paired-measurement validation. Nutrient values are database values for generic foods, so M12 documents the limits and the spot-check instead.
- Reported with every result: this is a small, uncontrolled comparison of hobby sensors on team members, not a clinical validation, and no sensor is represented as a medical device.

## Pre-declared targets (stated before any data exist)

These are the team's own targets (not NASA's, not regulatory). If a target is missed, the result is reported as missed.

| Comparison | Target |
|---|---|
| 1. HR (MAX30102 vs oximeter) | Limits of agreement within +/-5 bpm. |
| 2. SpO2 (MAX30102 vs oximeter) | Arms <= 3.5 %. FDA's reflectance-oximeter accuracy figure is a yardstick only, because our reference is another oximeter, not co-oximetry. |
| 3. DS18B20 axillary vs clinical thermometer | abs(bias) <= 0.5 C. |
| 4. MLX90614 forehead vs the same thermometer | Report only. A negative bias is expected (forehead skin is cooler than core). |
| 5a. Exercise peak force (camera vs load cell, per rep) | abs(bias) <= 10 % of the static load m x g, and at least 90 % of reps detected by both paths. |
| 5b. Exercise work | Report only. `work_cell_j` is an approximation: static load F0 (median of `load_raw` in the first second, else mass x 9.81) times the camera `rom_m` (D21). Camera `work_j` for a lift from rest is about (m x g + F_device) x ROM and counts lifting only, so a small positive camera-over-cell bias is not by itself a failure. |

Training work is reported in joules, never as calories. Hobby-sensor numbers are labelled estimates.

## Open points for the operator
1. Publication time: this protocol commit must precede the first reading. Suggest committing at the Sat 15:30 target.
2. S1 Q6 answer decides whether CSVs are published.
3. The 5 targets are copied from the plan; the HR LoA of +/-5 bpm is tight for a hobby optical sensor, but pre-declaring a loose target would hide that. Operator may loosen before the data exist, not after.
4. Not verified by me: the FDA reflectance-oximetry accuracy figure the SpO2 target cites (Arms 3.5 %); I did not open the FDA guidance. Keep the wording "yardstick only" or drop the FDA mention.

## Text for `data/validation/README.md`

> Validation data for the Habitat Health Monitor. Files are pseudonymous: subjects are `crew-a`, `crew-b` and `crew-c`; no names or contact data appear. Subjects are adult team members who gave verbal consent, recorded in the session log. Real health data of anyone outside the team are never stored here.
>
> File naming: `pairs-<date>.csv` (one row per valid pair: subject, comparison, t, test_val, ref_val, unit), `failures-<date>.csv` (one row per failed pair: comparison, t, reason), and for exercise `reps-<session>.csv`. Dates are UTC `YYYY-MM-DD`. Charts are in `docs/img/`. Targets were declared in `docs/validation.md` before any data were collected. Results labelled estimates; not a clinical validation.

(The exact CSV column lists are fixed by S6a/S6b when they are built; update this README to match them.)
