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

- **Board:** NodeMCU Amica (ESP8266). D37 had assigned it to the vitals node; the vitals node moves to a Wemos D1 mini running the same sketch and pin map (§7).
- **Wiring:** KY-017 signal to **D5 (GPIO14)**, VCC to 3V3, GND to GND. Pin order differs between module batches, so read the silkscreen and confirm the switch with a meter before power. D1 and D2 stay free for a later MPU6050 on I2C. D3, D4 and D8 (boot pins) stay free.
- **Mounting:** the capsule sits under heat-shrink inside a small closed box. The neodymium magnet is glued to the outside of the box, and the box sticks to the steel weight for the desk demonstration.
- **Power:** USB from the Pi. The node is never worn on the body, so the battery-only rule does not apply.

## 4. Firmware: `firmware/tilt-esp8266`

- Reads D5 with a 30 ms software debounce. The debounce is a pure function with host tests, following the `exercise-uno` pattern.
- Publishes contract-v1 readings over MQTT to the hub's broker: `{node: "tilt-1", ind: "tilt", unit: "state", val: 0 | 1, dev: "KY017", src: "hobby", age_ms, seq, boot}`. Value 1 means the switch is tripped.
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

From the same per-interval work terms the camera already computes, w = (m·g + F_device)·Δy + ½m(v_j² − v_i²):

- **Phase:** each interval's phase comes from the sign of the vertical wrist velocity. Intervals with |v| < 0.05 m/s keep the previous phase.
- **Concentric work:** the sum of w > 0. This equals today's `work_j`, which is unchanged.
- **Eccentric work:** the sum of |w| over w < 0, sent as `work_ecc_j`.
- **Times:** `t_con_ms` and `t_ecc_ms` are the summed interval durations of each phase. `t_turn_ms` is the time of the change from concentric to eccentric, at the top of the rep.
- **g:** the configured menu value, shown as "configured g".

### 5.3 Hub

- **One clock.** Each event is placed at hub time = receive time − `age_ms`. For a camera rep, the turnaround is at hub_t1 − (t1_ms − t_turn_ms), where hub_t1 = receive time − `age_ms` (the camera anchors `age_ms` on t1).
- **Join.** A `tilt` change is a `tilt-1` reading whose value differs from the previous one; heartbeats that repeat the value are not changes. The node is not session-aware, so the time window alone selects the changes. For each camera rep, take the change nearest the turnaround within the rep window ± 500 ms. Store:
  - `tilt_offset_ms` = tilt change time − camera turnaround time (signed);
  - `tilt_seen` = false when no change falls in the window (the weight never passed the trip angle).
- **Validation.** `hub/validation.py` adds a tilt-vs-camera summary next to the load-cell vs camera one: the share of reps with `tilt_seen`, and the median and 95th percentile of |offset|.
- **Console.** The rep row shows concentric J, eccentric J, the phase times and the offset.

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

The vitals node runs on a **Wemos D1 mini** (ESP8266, `esp8266:esp8266:d1_mini`), with the same sketch, the same I2C bus on D2/D1 and the same watch-outs. It goes on Saturday's shopping list. The NodeMCU Amica is `tilt-1`.

## 8. Testing

- **Contract:** the new node, dev and ind are accepted. A `tilt` reading with a wrong unit is rejected.
- **Camera (vitest):** on a synthetic up-and-down trajectory, concentric and eccentric work each come out ≈ m·g·h. The phase times and the turnaround match the synthetic profile, and `work_j` is unchanged.
- **Hub join:** synthetic times cover a change on time, a late change, a change outside the window (`tilt_seen` false) and two changes in one window (the nearest wins). The signed offset is computed correctly.
- **Firmware:** host tests for the debounce (bounce bursts under 30 ms collapse into one change).
- **Bench smoke:** five slow reps with the sealed pod on the desk weight. The console shows the split and the offsets, and the validation summary lists the five reps.

## 9. Out of scope

- A level check and a measured local g. They wait for an MPU6050: its gravity vector gives pitch, roll and |a|, and a pendulum timed by the camera is the credible check for local g.
- `tilt` on the public page.
- A Wokwi twin for `tilt-1`. Wokwi does not simulate the ESP8266; an ESP32 with a slide switch can stand in later if the team wants one.
