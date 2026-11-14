# Tilt node and per-phase work — design (D39)

Status: approved by the team owner, 2026-11-14, section by section.

## 1. Goal

Each exercise rep reports its concentric work, its eccentric work and the time spent in each phase. The camera measures both phases from one wrist trajectory. A tilt switch on the weight gives an independent witness of when the movement turns around, so the team can show how well the two agree.

## 2. Constraints

| ID | Constraint | Consequence |
|---|---|---|
| Safety | The KY-017 module holds liquid mercury in a glass capsule | It is used only as a sealed desk demonstration. Only adult team members handle it. The safety checklist gains a mercury section (§6) |
| R8 | No likeness of anyone under 18 | Unchanged: the desk demonstration shows only the team owner's hands and bench |
| Prior work | `vendor/ground-truth` is declared prior work, pinned at a commit | The phase split is new code in `camera/src`. The vendored library is not edited |
| Compatibility | `work_j` already means positive (concentric) work | `work_j` keeps that meaning. The new values are new optional fields |
| Honesty about g | The bench is on Earth | Work uses the configured g from the camera menu (Earth, Moon, Mars, ISS), labelled "configured". This design measures no g |
| Public page (D38) | Only consented or cabin data goes public | `tilt` is not added to any public set, so the consent filter keeps it local |

## 3. Hardware: node `tilt-1`

> **Amended by D40** (`2026-11-14-fewer-mcus-design.md`): the node runs on a cell pack instead of USB from the hub, so the
> pod on the weight has no cable. The pack is 4 × Ni-MH AA on VIN (chosen), or 2 × alkaline AA/AAA on 3V3; see D40 §6. Its Wokwi twin is `firmware/wokwi/tilt-esp32`.
> D40 also retires the vitals node: the D1 mini below is not used (§7).

- **Board:** NodeMCU Amica (ESP8266). D37 had assigned it to the vitals node; the vitals node moves to a Wemos D1 mini running the same sketch and pin map (§7).
- **Wiring:** KY-017 signal to **D5 (GPIO14)**, VCC to 3V3, GND to GND. Pin order differs between module batches, so read the silkscreen and confirm the switch with a meter before power. D1 and D2 stay free for a later MPU6050 on I2C. D3, D4 and D8 (boot pins) stay free.
- **Mounting:** the capsule sits under heat-shrink inside a small closed box. The neodymium magnet is glued to the outside of the box, and the box sticks to the steel weight for the desk demonstration.
- **Power:** USB from the Pi. The node is never worn on the body, so the battery-only rule does not apply.

## 4. Firmware: `firmware/tilt-esp8266`

- Reads D5 with a 200 ms software debounce (raised from 30 ms on 14/11: on the bench the mercury bounced for up to about 150 ms per edge). The debounce is a pure function with host tests, following the `exercise-uno` pattern.
- Publishes contract-v1 readings over MQTT to the hub's broker: `{node: "tilt-1", ind: "tilt", unit: "state", val: 0 | 1, dev: "KY017", src: "hobby", age_ms, seq, boot}`. Value 1 means the switch is tripped. The firmware reports the raw state; the pod is mounted so that it reads 0 with the weight at rest, and the bench check confirms this before a set with `GET /api/readings?ind=tilt&limit=5` (or the node's serial `# pub tilt` lines).
- Sends one reading on every debounced change, plus a heartbeat with the current state every 10 s.

## 5. Data flow

### 5.1 Contract (`hub/contract.py` and its mirrors)

- `NODES` += `tilt-1`, `DEVICES` += `KY017`, `INDICATORS` += `tilt: "state"`.
- `tilt` is not in `BODY_INDS` or `CABIN_INDS`.
- Mirrors: the firmware `Dev` enum (`firmware/libraries/HabitatNode/src/ReadingFormat.h`) and the console contract (`console/src/contract.ts` and its unit lists).
- Rep message, new optional fields (all null-safe for older senders):
  - `work_ecc_j` (J, ≥ 0): energy absorbed in the eccentric phase;
  - `t_con_ms`, `t_ecc_ms` (ms): time in each phase;
  - `t_turn_ms` (ms, same timebase as `t0_ms` and `t1_ms`): the turnaround time.

### 5.2 Camera (`camera/src`)

No new trajectory code. The vendored capture library already returns, for each rep, `positiveWorkJ` and `negativeWorkJ` (the sums of the per-interval work w = (m·g + F_device)·Δy + ½m(v_j² − v_i²) over w > 0 and w < 0) and `liftDurationS` (movement onset to the first sample at the top level). The camera only maps them into the rep message:

- **Concentric work:** `work_j` = `positiveWorkJ`, unchanged.
- **Eccentric work:** `work_ecc_j` = −`negativeWorkJ` (≥ 0).
- **Turnaround:** `t_turn_ms` = round((`startS` + `liftDurationS`) × 1000), on the same timebase as `t0_ms` and `t1_ms`.
- **Times:** `t_con_ms` = `t_turn_ms` − `t0_ms`; `t_ecc_ms` = `t1_ms` − `t_turn_ms`. The eccentric time includes any pause at the top.
- **g:** the configured menu value, shown as "configured g".
- **Display:** the camera's result table after a set shows concentric J, eccentric J and both phase times. (The console has no per-rep view; it shows only daily exercise totals.)

### 5.3 Hub

- **One clock.** The store already keeps `measured_at` = receive time − `age_ms` for every reading and rep. The camera anchors `age_ms` on t1, so a camera rep's t1 is at its `measured_at`, its t0 is at `measured_at` − (t1_ms − t0_ms), and its turnaround is at `measured_at` − (t1_ms − t_turn_ms).
- **What the switch shows.** The switch trips when the weight tilts past its trip angle and releases when it comes back. In a rep it therefore *rises* (0 → 1) during the concentric phase and *falls* (1 → 0) during the eccentric phase. It does not flip at the top.
- **Changes.** A `tilt` change is a `tilt-1` reading whose value differs from the previous one. Heartbeats that repeat the value are not changes. The node is not session-aware, so the time window alone selects the changes.
- **Witness per camera rep.** Look for rise → fall pairs with both changes inside [t0 − 500 ms, t1 + 500 ms] in hub time. When there are several, take the pair whose midpoint is nearest the camera turnaround. Report:
  - `seen`: a pair was found (false means the weight never passed the trip angle in that rep);
  - `turn_inside`: the camera turnaround lies between the rise and the fall;
  - `offset_ms`: midpoint(rise, fall) − turnaround (signed);
  - `rise_at` and `fall_at`: the change times.
- **Computed on read.** The witness is computed when `GET /api/reps` is served (in `pairs_for`), as `pair["tilt"]` for every pair with a camera rep. It is not stored, because a tilt change can arrive after the rep message and the values derive from rows already stored. Only the four camera fields of §5.1 become new rep columns.
- **Quiet indicator.** `tilt` joins the assessor's ungated set (as `motion` and `load_raw` are), so its readings are stored without an "unknown" assessment each.
- **Validation.** `hub/validation.py` adds three rows next to the load-cell vs camera ones: the share of camera reps with a tilt witness, the share whose turnaround falls inside the tilt interval, and the median and 95th percentile of |offset|.

## 6. Safety checklist additions (`docs/safety-checklist.md`)

- The mercury pod stays sealed. It is never opened, and only adult team members handle it.
- If the glass breaks:
  - clear the room and ventilate;
  - no vacuum cleaner or broom;
  - wear gloves and collect the beads with card or an eyedropper;
  - seal everything in a zip bag and take it to a hazardous-waste drop-off;
  - anyone under 18 stays out of the cleanup.
- The neodymium magnet stack is a pinch hazard. Keep fingers clear when it snaps onto steel.

## 7. Amendment to D37

> **Superseded by D40:** there is no vitals board, so no D1 mini. Wearable vitals come from a ring import.

The vitals node runs on a **Wemos D1 mini** (ESP8266, `esp8266:esp8266:d1_mini`), with the same sketch, the same I2C bus on D2/D1 and the same watch-outs. It goes on Saturday's shopping list. The NodeMCU Amica is `tilt-1`.

## 8. Testing

- **Contract:** the new node, dev and ind are accepted. A `tilt` reading with a wrong unit is rejected.
- **Camera (vitest):** from a synthetic rep result, the message carries `work_ecc_j` = −`negativeWorkJ`, the turnaround from `startS` + `liftDurationS`, and phase times that add up to t1 − t0. `work_j` is unchanged.
- **Hub witness:** synthetic changes cover a rise and fall around the turnaround, a pair late by 300 ms (still seen, offset positive), a pair outside the window (not seen), a rise with no fall (not seen), heartbeats (ignored), and two pairs in one window (the one nearest the turnaround wins).
- **Store:** the four new rep columns round-trip, and an old database without them is migrated in place.
- **Firmware:** host tests for the debounce (bounce bursts under 200 ms collapse into one change).
- **Bench smoke:** five slow reps with the sealed pod on the desk weight. The camera result table shows the split, `GET /api/reps` and `python -m hub.validation reps` show the offsets, and the validation summary lists the five reps. The tilt state check is the same one as in the tilt node README.

## 9. Out of scope

- A level check and a measured local g. They wait for an MPU6050: its gravity vector gives pitch, roll and |a|, and a pendulum timed by the camera is the credible check for local g.
- `tilt` on the public page.
- A Wokwi twin for `tilt-1`. Wokwi does not simulate the ESP8266; an ESP32 with a slide switch can stand in later if the team wants one.
