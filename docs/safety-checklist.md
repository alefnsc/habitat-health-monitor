# Electrical and mechanical safety checklist (F3 draft)

Status: DRAFT by the S agent for the operator and Andréia to review and sign on the bench. Print it, tape it to the table, tick boxes 1 to 6 with a meter on the real hardware, and write the measured values in the blanks. **Not ticked until measured.** Sign-off of checks 1 to 6 is needed before the first finger test (F11) and before any validation session (D27: Sat 16:00).

This is an educational prototype, not a medical device. IEC 60601-1 compliance is **not** claimed. Adults only (rule R8).

## Rules

1. **Battery only on the body.** The radio link (Wi-Fi/BLE) is the isolation barrier.
2. **Nothing body-worn is cabled to anything mains-powered:** no laptop on its charger, no Pi, no monitor, no Ethernet, no bench supply. No electrodes on anyone while a mains-powered device is connected.
3. The Pi and the exercise rig's USB host never touch a person's sensors.
4. **ECG only if built (AD8232):** series resistance on every electrode (at least 180 kOhm on inputs, at least 360 kOhm on the right-leg-drive line, the plan's values for the datasheet's under-10 uA fault target; verify against the AD8232 datasheet before use). Never connect electrodes to MCU pins directly. Mains hum on the trace means something is grounded: stop.
5. One powered device per person. Intact skin only. Nobody with a pacemaker or implanted device volunteers. Single-use gel pads. Alcohol wipe on optical and thermal sensors between people. Adults only.
6. Protected USB power bank, never a bare LiPo on a wrist. The tilt-1 node is not body-worn and runs on 2 × AA or AAA cells on its 3V3 and GND pins (D40): never VIN, never more than 3.6 V on 3V3, no CR2032 coin cell, and the cells come out before USB goes in to flash.
7. 3.3 V parts (ESP GPIO, MFRC522, bare BME280, the MLX90614 GY-906 and MAX30102 and MPU6050 boards on the vitals I2C bus, MLX90614 B/D variants) never see 5 V; level-shift or do not connect. Some MAX30102 boards pull SDA and SCL up to 1.8 V: move the jumper to 3.3 V before first power-on.
8. **Servo on its own 5 V supply** (only if a servo is fitted; the D40 board has none), grounds joined with the Uno GND; never from the Uno 5 V pin.
9. **Exercise rig mechanics:** clamp the load cell, hook and band so nothing can fly free if the band snaps; keep the HX711 board enclosed or taped; no bare conductor within reach of the handle; stay clear of the swing path. Never pull to the cell's rated capacity to test a flag (F15 uses a temporary low capacity constant).
10. Every screen, the README and the project page say "educational prototype, not a medical device".
11. If anything smells hot or a regulator burns a finger: unplug first, then think.
12. **Mercury tilt switch (KY-017, tilt-1 node):** the capsule holds liquid mercury in glass. It stays in its sealed pod (heat-shrink plus a closed box) and is never opened; only adult team members handle it. If the glass breaks: clear the room and ventilate; no vacuum cleaner and no broom; gloves on, collect the beads with stiff card or an eyedropper; seal everything in a zip bag and take it to a hazardous-waste drop-off, never household trash. Anyone under 18 stays out of the cleanup.
13. **Neodymium magnets** (they hold the tilt pod on the steel weight) snap together hard and can pinch skin: slide them apart, keep fingers clear, keep them away from cards and phones.

## Bench checks (tick only after measuring)

| # | Check | How | Pass criterion | Measured / result | Tick |
|---|---|---|---|---|---|
| 1 | Body node on battery | Inspect the vitals node's USB port while strapped to a person | Only the power bank is connected (no laptop, Pi, charger or monitor). For a serial debug session the laptop runs on battery with its charger unplugged and nothing else plugged in. | | [ ] |
| 2 | No 5 V on 3.3 V pins | Power on; meter every signal pin to GND on each ESP node, MFRC522, BME280, MAX30102, MPU6050 and MLX90614 board, and the vitals SDA and SCL lines (3.3 V, not 1.8 V) | No pin exceeds 3.6 V (MFRC522: limiting value 4.0 V, recommended 2.5 to 3.6 V) | Highest per board: ____ V | [ ] |
| 3 | Servo supply (n/a in D40 unless a servo is fitted) | Trace the servo 5 V line on the exercise rig | Own 5 V supply, GND joined to Uno GND, not the Uno 5 V pin | Supply: ____ | [ ] |
| 4 | Load-cell isolation (n/a in D40 unless a load cell is fitted) | Disconnect the cell from the HX711; measure resistance between the metal body and each of its four leads | Every reading above 1 MOhm | Lead 1 __ 2 __ 3 __ 4 __ MOhm | [ ] |
| 5 | AD8232 resistors (only if built) | Measure the series resistance on each input lead and on the RLD (third electrode) line | Inputs at least 180 kOhm; RLD at least 360 kOhm | Inputs __ / __ kOhm; RLD __ kOhm | [ ] n/a [ ] |
| 6 | Mechanical (n/a in D40 unless the rig is fitted) | Load the rig with the heaviest test mass; pull the handle to full range | Cell, hook and band clamped, nothing can fly free if the band snaps, no bare conductor near the handle | Heaviest mass: ____ kg | [ ] |
| 7 | Cells hold the tilt node | Run tilt-1 on its two cells for 10 minutes | A `tilt` heartbeat arrives every 10 s without a gap; 3V3 to GND reads 2.7 V or more | Cells and voltage: ____ | [ ] |
| 8 | Labels present | Look at the console, README and page | "educational prototype, not a medical device" is visible | | [ ] |

## Per-session sign-off

One line per session; sign before any sensor touches a person.

| Date | Session (validation S7/S8a/S8b, exercise S10, demo filming, judging) | Checks 1 to 8 still true? | Subjects (pseudonyms only) | Checked by / time |
|---|---|---|---|---|
| 2026-11-14 | | | | |
| 2026-11-14 | | | | |
| 2026-11-15 | | | | |

Bench sign-off: operator ____________  Andréia ____________  Time ____
