# S2 draft: NASA thresholds, effective-dose method, OSDR mission

Status: DRAFT for operator approval. Nothing here is encoded until the operator approves (D29). H4b encodes only approved rows.
Drafted by the S agent, 2026-11-14, 10:2x local. Every NASA number below was re-read in the primary PDF (downloaded 2026-11-14) and compared with `research/*.md`. "Page" is the PDF page, which equals the printed "Page N of 389" (Vol 2), "N of 87" (Vol 1).

Documents read:
- Vol 2 = NASA-STD-3001 Vol 2 Rev F, approved 2026-07-14. https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf
- Vol 1 = NASA-STD-3001 Vol 1 Rev C, approved 2023-09-15. https://standards.nasa.gov/sites/default/files/standards/NASA/C/nasa-std-3001-vol-1-rev-c-signature.pdf
- TB-004 = OCHMO-TB-004 Rev D, 10-Mar-26. https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf
- NTRS 20250006168 = Simonsen, Zawaski, Weeks, "Moon 2 Mars Space Radiation Protection 'Buying Down' Risks to Crew" (ASCEND draft 1). https://ntrs.nasa.gov/citations/20250006168 (PDF: https://ntrs.nasa.gov/api/citations/20250006168/downloads/ASCEND%20Simonsen%20draft%201.pdf)

## Decisions the operator must make first (S2)

1. **Figure 6.2-2 is a polygon, not a rectangle** (plan open point b, spec and research assumed a rectangle). Vertices read from Vol 2 p. 55: (18 °C, 75 % RH), (25.7 °C, 75 %), (27 °C, 25 %), (19.1 °C, 25 %). RH limits 25 to 75 % hold everywhere, but the temperature limits slide with humidity: 19.1 to 27 °C at 25 % RH, 18 to 25.7 °C at 75 % RH. The plan's rectangle (18 to 27 °C, 25 to 75 %) wrongly calls 18 °C at 25 % RH and 27 °C at 75 % RH "watch/ok". Options: (A) keep the rectangle rows as written and label them "display aid, bounding box" (plan default, S4 tests unchanged); (B) encode the largest rectangle that is inside the polygon everywhere, 19.1 to 25.7 °C and 25 to 75 % RH, which changes the S4 temperature boundaries (18.0 would be act, 25.1 to 25.7 would be ok/act as decided); (C) A now, polygon later. S agent recommends C: keep A for L0, and add the polygon as a separate later change. Either way the card note should say "bounding box of Figure 6.2-2".
2. **7-day CO2 line is not in Rev F.** Rev F [V2 6004] has only the 1-hour 3 mmHg limit. The 2.5 mmHg 7-day figure is in TB-004 Rev D p. 5. `co2_7d` source_ref is therefore TB-004, not Vol 2 (open point a settled). TB-004 says "below 2.5"; the plan encodes max 2.5 inclusive. A mean of exactly 2.500 mmHg is a measure-zero case; S4 values (2.49996 ok, 2.50071 watch) pass either way. Approve either reading.
3. **Lux hours 07:00 to 23:00 are a team convention.** [V2 8051] sets minimum levels per Table 8.7-1 and sets no hours; the table's other row is "Crew Sleep <=0.02 lux". Also 8051 applies to architectures "that do not include the presence of orbital sunlight". Keep the hours field, label it team convention.
4. **Radiation 50 %/90 % bands (300/540 mSv) and the space-weather levels are team conventions.** The only NASA number is 600 mSv ([V1 4030]). Confirmed: [V1 4031] (250 mSv per SPE) is a shielding design limit, so it is context only; the SPE alert source is [V2 6164]/[V2 6165] (open point c settled).
5. **NTRS 20250006168 is a conference draft** ("ASCEND ... draft 1"). It is the only document with the 0.2 to 0.5 mSv/day range. Acceptable as the cited range; label it "draft paper".
6. **OSDR mission: proposed RR-6** from the N probe table (all four series complete). Needs the operator's signature on the `Mission:` line. See "OSDR mission".

No other disagreement between the PDFs and `research/*.md`.

## NASA rules (S2 table)

Band notation as in plan section S: "none" = absent (null), "any" = empty band. Checked by: S agent, 2026-11-14 (PDF read in full at the cited page).

| id | ind | window | ok | watch | act | source_kind | Document / revision | Requirement ID | Page | URL | Quote (<=15 words) | Confidence | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `co2_1h` | cabin_ppco2 | mean_1h | max 3.0 | none | any | nasa_std | NASA-STD-3001 Vol 2 Rev F, 6.2.1.3 | [V2 6004] | 51 | Vol 2 URL | "one-hour CO2 partial pressure (ppCO2) in the habitable volume to no more than 3 mmHg" | High | Same page: off-nominal CO2 values are not in the standard, so no watch band. |
| `co2_7d` | cabin_ppco2 | mean_7d | max 2.5 | any | none | nasa_std | OCHMO-TB-004 Rev D (10-Mar-26), Background | related to [V2 6004] | 5 | TB-004 URL | "average 7-day CO2 needs to be maintained below 2.5 mmHg" | High (number), Medium (use as a status band) | Headache risk below 1 %. A technical brief "for reference only", not a requirement; label it so. Not in Vol 2 Rev F. |
| `cabin_health_box_temp` | cabin_temp | instant | min 18, max 27 | none | any | nasa_std | Vol 2 Rev F, 6.2.3.1, Figure 6.2-2 | [V2 6012] | 54 to 55 | Vol 2 URL | "anchored at 18°C and 75% humidity on the upper left corner" | High (anchors), see decision 1 (shape) | Figure is a polygon; band 18 to 27 is its bounding box. DHT11 is +/-2 C, show that on the card. |
| `cabin_health_box_rh` | cabin_rh | instant | min 25, max 75 | none | any | nasa_std | same | [V2 6012] | 54 to 55 | Vol 2 URL | "above this lower limit (25%) to ensure that the environment is not too dry" | High | RH 25 to 75 holds across the whole polygon. Below 25 % also a static/ignition concern (p. 54 rationale). |
| `cabin_performance_temp` | cabin_temp | instant | min 20, max 25 | any | none | nasa_std | Vol 2 Rev F, 6.2.3.2, Figure 6.2-3 | [V2 6013] | 55 to 56 | Vol 2 URL | "(20°C - 25°C and 30-60% humidity) to support human comfort and performance" | High | Performance zone, not a health limit. Figure 6.2-3 draws the zone (red) inside the health polygon; the rationale gives the numbers. |
| `cabin_performance_rh` | cabin_rh | instant | min 30, max 60 | any | none | nasa_std | same | [V2 6013] | 55 to 56 | Vol 2 URL | same quote | High | |
| `lux_general` | cabin_lux | instant | min 350 | any | none | nasa_std | Vol 2 Rev F, 8.7.1, Table 8.7-1 | [V2 8051] | 151 to 152 | Vol 2 URL | "General Horizontal Ambient Lighting >= 350" (table row, lux) | High (number), Medium (hours, decision 3) | Hours 07:00 to 23:00 are team convention. Table also lists translation >=108, vertical >=200, medical >=750, sleep <=0.02 lux; BH1750 cannot judge 0.02 lx. |
| `radiation_career` | rad_dose_cum | instant | max 299.9 | max 539.9 | any | nasa_std | NASA-STD-3001 Vol 1 Rev C, 4.8.2 | [V1 4030] | 40 of 87 | Vol 1 URL | "shall be less than 600 mSv. This limit is universal for all ages and sexes" | High (600), team convention (50 %/90 %) | Note must say: 600 mSv career limit [V1 4030]; 300 and 540 mSv are 50 % and 90 % team-convention fractions. Value is an effective-dose estimate (method below), never OSDR mGy. |
| `radiation_spe` | space_weather | instant | max 0 | min 1, max 1 | any | nasa_std | Vol 2 Rev F, 6.8.1.6 and 6.8.1.7 | [V2 6164], [V2 6165] | 109 | Vol 2 URL | "shall alert the crew and operations teams when radiation exposure rates exceed predefined thresholds" | High (IDs), trigger logic is the team's | Levels per D9/N3. [V1 4031] (p. 42 of 87, "less than an effective dose of 250 mSv") is a design limit: context only. NOAA R3 = X1 flare, G3 = Kp 7 cited in References. |

Line under the table (required): NASA publishes no numeric in-flight escalation thresholds for the six vital signs (OCHMO-STD-100.1A, NASA-STD-3001 Vol 1, OCHMO technical briefs). Not re-verified for OCHMO-STD-100.1A (not fetched); Vol 1 Rev C and TB-004 were searched and contain no vital-sign escalation bands.

### Figure 6.2-2 read (check `figure_read`)

Shape: polygon (quadrilateral) on a psychrometric chart, Vol 2 p. 55. Vertices in degrees C and % RH: (18, 75), (25.7, 75), (27, 25), (19.1, 25). The top and bottom edges follow the 75 % and 25 % RH curves; the left and right edges are straight lines on the figure's axes (dry-bulb temperature and humidity ratio). Figure 6.2-3 (p. 56) draws the performance zone as a smaller quadrilateral inside it; its stated numbers are 20 to 25 C and 30 to 60 %.

## Effective-dose method (open point f)

- Source: NTRS 20250006168, PDF p. 2. Quote: "effective doses accumulate at a rate of approximately 0.2 to 0.5 mSv/day" (12 words, verbatim "ISS, effective doses accumulate at a rate of approximately 0.2 to 0.5 mSv/day"). Same page: "averaging between ~40 and 90 mSv during a typical six-month mission"; 0.5 mSv/day over 180 days is 90 mSv, consistent.
- Rate adopted: 0.5 mSv/day (upper end, so the gauge never understates). Cited range: 0.2 to 0.5 mSv/day.
- Exact method string, to be copied verbatim as `method` in `data/nasa/dose_profile.json`:

`mission_day × 0.5 mSv/day (upper ISS effective-dose rate, NTRS 20250006168); estimate, not measured`

- OSDR absorbed dose (mGy) is shown separately and never converted.
- Confidence: High on the range (read in the PDF); Medium on source quality (draft conference paper). Context: Vol 1 Rev C p. 46 gives a free-space GCR design rate of 1.5 mSv/day (about 1.3 mSv/day shielded) for deep space; the 0.5 figure is ISS low Earth orbit only, so the profile for Moon/Mars environments must not reuse it silently (profile owner N7).

## OSDR mission (open point e)

Proposed for signature: **Mission: RR-6** (SpaceX-13 rodent mission, Dec 2017 to Feb 2018). Source: N agent's probe table `docs/drafts/osdr-probe.md` (read from origin/main at 10:2x), which I cross-checked on the one point I could repeat: the EDA `missions` list and a `telemetry_data` call (RR-9, RR-28) returned the same structure and the bare `/temperature/iss/` paths return 404, as the table says.
- Per the probe table, RR-6 returned all four series: temperature 21.7 to 25.6 C, humidity 25 to 61 %, CO2 500 to 4187 ppm, all complete, plus 49 daily radiation values (mean total 0.283 mGy/day, 2017-12-15 to 2018-02-01) on the same dates.
- Other missions with all four: RR-1, RR-3, RR-7 (half empty for humidity and CO2), RR-9 (radiation dates do not overlap telemetry), RR-12, RR-19, RR-23 (small gaps). RR-6 is the best complete pairing.
- Caveat for the page: units are not in the JSON; the probe took them from the EDA page scripts (degC, % RH, ppm, mGy/day). The CO2 comes in ppm, so it needs the 0.000750062 mmHg/ppm conversion (same factor as S4) before comparison with the 3 mmHg limit. Cabin RH of 25 % at the low edge is at the Rev F health limit.
- OSDR absorbed dose (mGy) is shown separately and never converted.
- Confidence: Medium-High (table not independently repeated for RR-6 radiation). If the operator approves, the `Mission:` line in the probe file is `Mission: RR-6`.

## Nutrition rules

Moved to `docs/drafts/m1-nutrition-values.md` (M1 draft).
