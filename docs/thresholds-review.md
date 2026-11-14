# Thresholds review (approved)

The reviewed, citable source for `data/thresholds.json`. Approved by the operator 2026-11-14 about 10:22 for the NASA rules (S2) and the clinical rules (S3). Drafts with the working notes: `docs/drafts/s2-nasa-thresholds.md` and `docs/drafts/s3-clinical-bands.md`. Rows were re-read in the primary documents on 2026-11-14 by the S agent ("checked by / at" in each section); the operator approved the decisions below.

Honesty rules: vital-sign bands are **not NASA-published**; cabin and radiation limits show their NASA-STD-3001 requirement ID; mood rows are "Team convention, not clinical".

## Approved decisions
- Cabin box: rectangle now, polygon later. Label on the card: "bounding box of Figure 6.2-2".
- `co2_7d`: cited to OCHMO-TB-004 Rev D (a technical brief, reference only), max 2.5 inclusive.
- `lux_general` hours 07:00 to 23:00, the radiation 50 %/90 % bands (300 and 540 mSv) and the space-weather levels are `team_convention`; only the 600 mSv career limit is NASA [V1 4030].
- NTRS 20250006168 is labelled "draft paper".
- `glucose_high`: "screening prompt, not a diagnosis; timing unknown".
- Blood pressure rows: "team choice; single reading is a screening prompt".
- Citations: AHA/ACC 2025 (Hypertension 2025;82(10):e212-e316) and ADA Standards of Care 2026 (Diabetes Care 2026;49(Suppl 1)). No primary quote was retrievable for these two; rows say so.
- The OCHMO sleep claim ("about 6 h in flight") appears on no card.
- Cabin shape detail: Figure 6.2-2 vertices are (18 C, 75 %), (25.7 C, 75 %), (27 C, 25 %), (19.1 C, 25 %) (Vol 2 p. 55).

## Also approved (operator, about 10:35: D33/D34)
- **M1 nutrition rules approved as drafted** (`docs/drafts/m1-nutrition-values.md`). New `source_kind` `nasa_doc`, label "NASA program document, not NASA-STD-3001", for the JSC-67378 food rules (sodium, iron, fluid, calcium). Vitamin D stays `nasa_std` (Vol 2 Rev F Table 7.1-2). Sodium 2300 to 3500 is read as watch ("historical operating band"); iron has no act band; vitamin D and calcium floors have no extra bands.
- **OSDR mission: RR-6 signed.** All four series (temperature, humidity, CO2, radiation) are complete for RR-6 in the EDA API.

## Documents

- Vol 2 = NASA-STD-3001 Vol 2 Rev F, approved 2026-07-14. https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf
- Vol 1 = NASA-STD-3001 Vol 1 Rev C, approved 2023-09-15. https://standards.nasa.gov/sites/default/files/standards/NASA/C/nasa-std-3001-vol-1-rev-c-signature.pdf
- TB-004 = OCHMO-TB-004 Rev D, 10-Mar-26. https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf
- NTRS 20250006168 = Simonsen, Zawaski, Weeks, "Moon 2 Mars Space Radiation Protection 'Buying Down' Risks to Crew" (ASCEND draft 1). https://ntrs.nasa.gov/citations/20250006168 (PDF: https://ntrs.nasa.gov/api/citations/20250006168/downloads/ASCEND%20Simonsen%20draft%201.pdf)


## NASA rules

Band notation as in plan section S: "none" = absent (null), "any" = empty band. Checked by: S agent, 2026-11-14 (PDF read in full at the cited page).

| id | ind | window | ok | watch | act | source_kind | Document / revision | Requirement ID | Page | URL | Quote (<=15 words) | Confidence | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `co2_1h` | cabin_ppco2 | mean_1h | max 3.0 | none | any | nasa_std | NASA-STD-3001 Vol 2 Rev F, 6.2.1.3 | [V2 6004] | 51 | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | "one-hour CO2 partial pressure (ppCO2) in the habitable volume to no more than 3 mmHg" | High | Same page: off-nominal CO2 values are not in the standard, so no watch band. |
| `co2_7d` | cabin_ppco2 | mean_7d | max 2.5 | any | none | nasa_std | OCHMO-TB-004 Rev D (10-Mar-26), Background | related to [V2 6004] | 5 | https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf | "average 7-day CO2 needs to be maintained below 2.5 mmHg" | High (number), Medium (use as a status band) | Headache risk below 1 %. A technical brief "for reference only", not a requirement; label it so. Not in Vol 2 Rev F. |
| `cabin_health_box_temp` | cabin_temp | instant | min 18, max 27 | none | any | nasa_std | Vol 2 Rev F, 6.2.3.1, Figure 6.2-2 | [V2 6012] | 54 to 55 | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | "anchored at 18°C and 75% humidity on the upper left corner" | High (anchors); shape per approved decision | Card label: "bounding box of Figure 6.2-2"; the figure is a polygon (polygon later). DHT11 is +/-2 C, show that on the card. |
| `cabin_health_box_rh` | cabin_rh | instant | min 25, max 75 | none | any | nasa_std | same | [V2 6012] | 54 to 55 | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | "above this lower limit (25%) to ensure that the environment is not too dry" | High | RH 25 to 75 holds across the whole polygon. Below 25 % also a static/ignition concern (p. 54 rationale). |
| `cabin_performance_temp` | cabin_temp | instant | min 20, max 25 | any | none | nasa_std | Vol 2 Rev F, 6.2.3.2, Figure 6.2-3 | [V2 6013] | 55 to 56 | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | "(20°C - 25°C and 30-60% humidity) to support human comfort and performance" | High | Performance zone, not a health limit. Figure 6.2-3 draws the zone (red) inside the health polygon; the rationale gives the numbers. |
| `cabin_performance_rh` | cabin_rh | instant | min 30, max 60 | any | none | nasa_std | same | [V2 6013] | 55 to 56 | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | same quote | High | |
| `lux_general` | cabin_lux | instant | min 350 | any | none | nasa_std | Vol 2 Rev F, 8.7.1, Table 8.7-1 | [V2 8051] | 151 to 152 | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | "General Horizontal Ambient Lighting >= 350" (table row, lux) | High (number), Medium (hours are team convention) | Hours 07:00 to 23:00 are `team_convention`. Table also lists translation >=108, vertical >=200, medical >=750, sleep <=0.02 lux; BH1750 cannot judge 0.02 lx. |
| `radiation_career` | rad_dose_cum | instant | max 299.9 | max 539.9 | any | nasa_std | NASA-STD-3001 Vol 1 Rev C, 4.8.2 | [V1 4030] | 40 of 87 | https://standards.nasa.gov/sites/default/files/standards/NASA/C/nasa-std-3001-vol-1-rev-c-signature.pdf | "shall be less than 600 mSv. This limit is universal for all ages and sexes" | High (600), team convention (50 %/90 %) | Note must say: 600 mSv career limit [V1 4030]; 300 and 540 mSv are 50 % and 90 % team-convention fractions. Value is an effective-dose estimate (method below), never OSDR mGy. |
| `radiation_spe` | space_weather | instant | max 0 | min 1, max 1 | any | nasa_std | Vol 2 Rev F, 6.8.1.6 and 6.8.1.7 | [V2 6164], [V2 6165] | 109 | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | "shall alert the crew and operations teams when radiation exposure rates exceed predefined thresholds" | High (IDs), trigger logic is the team's | Levels per D9/N3. [V1 4031] (p. 42 of 87, "less than an effective dose of 250 mSv") is a design limit: context only. NOAA R3 = X1 flare, G3 = Kp 7 cited in References. |

Line under the table (required): NASA publishes no numeric in-flight escalation thresholds for the six vital signs (OCHMO-STD-100.1A, NASA-STD-3001 Vol 1, OCHMO technical briefs). Not re-verified for OCHMO-STD-100.1A (not fetched); Vol 1 Rev C and TB-004 were searched and contain no vital-sign escalation bands.

### Figure 6.2-2 read (check `figure_read`)

Shape: polygon (quadrilateral) on a psychrometric chart, Vol 2 p. 55. Vertices in degrees C and % RH: (18, 75), (25.7, 75), (27, 25), (19.1, 25). The top and bottom edges follow the 75 % and 25 % RH curves; the left and right edges are straight lines on the figure's axes (dry-bulb temperature and humidity ratio). Figure 6.2-3 (p. 56) draws the performance zone as a smaller quadrilateral inside it; its stated numbers are 20 to 25 C and 30 to 60 %.

## Effective-dose method (open point f)

- Source: NTRS 20250006168, PDF p. 2. Quote: "effective doses accumulate at a rate of approximately 0.2 to 0.5 mSv/day" (12 words, verbatim "ISS, effective doses accumulate at a rate of approximately 0.2 to 0.5 mSv/day"). Same page: "averaging between ~40 and 90 mSv during a typical six-month mission"; 0.5 mSv/day over 180 days is 90 mSv, consistent.
- Rate adopted: 0.5 mSv/day (upper end, so the gauge never understates). Cited range: 0.2 to 0.5 mSv/day.
- Exact method string, to be copied verbatim as `method` in `data/nasa/dose_profile.json`:

`mission_day × 0.5 mSv/day (upper ISS effective-dose rate, NTRS 20250006168); estimate, not measured`

- OSDR absorbed dose (mGy) is shown separately and never converted.
- Confidence: High on the range (read in the PDF); draft paper. Context: Vol 1 Rev C p. 46 gives a free-space GCR design rate of 1.5 mSv/day (about 1.3 mSv/day shielded) for deep space; the 0.5 figure is ISS low Earth orbit only, so the profile for Moon/Mars environments must not reuse it silently (profile owner N7).


## Clinical rules

Checked by: S agent, 2026-11-14. "Chart 1" = RCP NEWS2 Chart 1 "The NEWS scoring system" (one page), (c) Royal College of Physicians 2017. URL: https://www.rcp.ac.uk/media/alxev00t/news2-chart-1_the-news-scoring-system_0_0.pdf (landing page https://www.rcp.ac.uk/resources/national-early-warning-score-news-2/).

NEWS2 mapping used: score 0 is ok, 1 to 2 is watch, 3 is act (single-parameter use only). NEWS2 is for acutely ill adults in hospital.

| id | ind | window | ok | watch | act | source_kind | Document and edition | Section or table | URL | Quote (<=15 words) | Confidence | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `hr_rest_low` | hr | instant | min 51 | min 41 | any | clinical_ref | RCP, NEWS2 (2017) | Chart 1, row "Pulse (per minute)" | https://www.rcp.ac.uk/media/alxev00t/news2-chart-1_the-news-scoring-system_0_0.pdf | "Pulse (per minute) <=40 | 41-50 | 51-90" (chart row: 3, 1, 0) | High | Resting readings only. |
| `hr_rest_high` | hr | instant | max 90 | max 130 | any | clinical_ref | same | same | same | "91-110 | 111-130 | >=131" (chart row: 1, 2, 3) | High | Resting readings only. |
| `spo2_low` | spo2 | instant | min 96 | min 92 | any | clinical_ref | same | Chart 1, row "SpO2 Scale 1 (%)" | same | "SpO2 Scale 1 (%) <=91 | 92-93 | 94-95 | >=96" (3, 2, 1, 0) | High | MAX30102 SpO2 is an uncalibrated estimate; guidance asks for a certified re-measure before escalation. |
| `body_temp_low` | body_temp | instant | min 36.1 | min 35.1 | any | clinical_ref | same | Chart 1, row "Temperature (C)" | same | "Temperature (C) <=35.0 | 35.1-36.0 | 36.1-38.0" (3, 1, 0) | High | `skin_temp` has no rule and is never judged as `body_temp`. |
| `body_temp_high` | body_temp | instant | max 38.0 | any | none | clinical_ref | same | same | same | "36.1-38.0 | 38.1-39.0 | >=39.1" (0, 1, 2) | High | Chart has no score 3 on the high side, so no act band. |
| `bp_sys_low` | bp_sys | instant | min 111 | min 91 | any | clinical_ref | same | Chart 1, row "Systolic blood pressure (mmHg)" | same | "<=90 | 91-100 | 101-110 | 111-219" (3, 2, 1, 0) | High | Chart has act for >=220; not used, see `bp_sys_high`. |
| `bp_sys_high` | bp_sys | instant | max 129 | max 180 | any | clinical_ref | AHA/ACC adult high blood pressure guideline 2025, Hypertension 2025;82(10):e212-e316 (categories unchanged from 2017, Hypertension 2018;71:e13-e115) | BP classification table | https://www.ahajournals.org/doi/10.1161/HYP.0000000000000249 | not retrieved (no primary quote) | Medium | Screening prompt, one reading. "Elevated" 120 to 129 treated as ok by team choice Card label: "team choice; single reading is a screening prompt". Severe = above 180. |
| `bp_dia_high` | bp_dia | instant | max 79 | max 120 | any | clinical_ref | same | same | same | not retrieved | Medium | Normal <80; stage 1 80 to 89; stage 2 >=90; severe >120. |
| `glucose_low` | glucose | instant | min 70 | min 54 | any | clinical_ref | ADA Standards of Care in Diabetes 2026, Diabetes Care 2026;49(Suppl 1):S132-S149 | Section 6, hypoglycaemia classification (level 1 <70, level 2 <54 mg/dL) | https://doi.org/10.2337/dc26-S006 | not retrieved (secondary: "Glucose <70 mg/dL and >=54 mg/dL") | Medium-High | Level 1 is below 70 and at or above 54; level 2 is below 54. Glucometer readings are screening prompts, not a diagnosis. |
| `glucose_high` | glucose | instant | max 139 | max 199 | any | clinical_ref | ADA Standards of Care 2026, Section 2 (diagnosis) | 2-h plasma glucose 140 to 199 (IGT range), >=200 | https://doi.org/10.2337/dc26-S002 (DOI pattern, not opened) | not retrieved | Low-Medium | Card label: "screening prompt, not a diagnosis; timing unknown" (OGTT range applied to untimed readings). |
| `sleep_night` | sleep_h | instant | min 7 | any | none | clinical_ref | Watson et al., AASM/SRS joint consensus, Sleep 2015;38(6):843-844 | Recommendation | https://www.aasm.org/resources/pdf/adultsleepdurationconsensus.pdf | "Adults should sleep 7 or more hours per night on a regular basis" | High | Applies to adults 18 to 60. No act band. |
| `sleep_week` | sleep_h | mean_7d | min 7 | any | none | clinical_ref | same | same | same | same | High (number), Medium (7-day mean use) | The consensus is about regular sleep; a 7-day mean is the team's way to apply it. |
| `mood_self` | mood | instant | min 3 | any | none | team_convention | none (no clinical cut-off exists for a single 1 to 5 item); cite the team review file | n/a | https://github.com/alefnsc/habitat-health-monitor/blob/main/docs/thresholds-review.md | n/a | n/a | Label "Team convention, not clinical". The URL is the repo review file, because S4 requires every rule to carry an https URL. |
| `mood_7d` | mood | mean_7d | min 2.5 | any | none | team_convention | none; context only: NASA HRP Behavioral Medical Conditions risk | n/a | https://github.com/alefnsc/habitat-health-monitor/blob/main/docs/thresholds-review.md | n/a | n/a | 7-day mean of the 1 to 5 report below 2.5. Non-clinical. Needs 24 h coverage (H7a). Supporting signal for the isolation and confinement hazard. |

Required notes (to appear in each rule's `note` or the card):
- NEWS2 is for acutely ill adults in hospital; used here for single-parameter bands only.
- `hr` rules apply to resting readings.
- `spo2` from the MAX30102 is an uncalibrated estimate.
- Glucometer readings are screening prompts, not a diagnosis. No treatment doses anywhere.
- `skin_temp` has no rule (status `unknown`).
- No act band on `body_temp_high`, the `sleep_*` rules, `mood_self` or `mood_7d`.
- Optional NASA context for the glucose note (only if Proposed addition 7 is accepted): Inspiration4 crew lab reference range 65 to 99 mg/dL (OSDR OSD-575). Per research this was confirmed, but OSD-575 also contains implausibly low glucose values (36 to 44 mg/dL at R+45), so do not use it as a band.

Count check: 14 vital and mood rows here plus 9 NASA rows in S2 = 23 ids (`co2_1h`, `co2_7d`, `cabin_health_box_temp`, `cabin_health_box_rh`, `cabin_performance_temp`, `cabin_performance_rh`, `lux_general`, `radiation_career`, `radiation_spe`, `hr_rest_low`, `hr_rest_high`, `spo2_low`, `body_temp_low`, `body_temp_high`, `bp_sys_low`, `bp_sys_high`, `bp_dia_high`, `glucose_low`, `glucose_high`, `sleep_night`, `sleep_week`, `mood_self`, `mood_7d`).
