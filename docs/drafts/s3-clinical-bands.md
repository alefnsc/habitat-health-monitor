# S3 draft: clinical references and bands for the vital signs

Status: DRAFT for operator approval. Nothing is encoded until the operator approves (D29).
Drafted by the S agent, 2026-11-14. **All rows below are clinical or team-convention bands and are not NASA-published.** Every card must show the label "not NASA-published" (or "Team convention, not clinical" for mood). source_kind is `clinical_ref` except `mood_self` and `mood_7d` (`team_convention`, D13).

Verification status by source (what I could actually open on 2026-11-14):
- NEWS2 Chart 1: primary PDF downloaded and read. Every number below for hr, spo2, body_temp, bp_sys_low matches the chart. Verified.
- Watson et al. 2015: primary AASM PDF read. Verified.
- AHA/ACC 2025 and ADA 2026: only secondary summaries and search results were reachable (journal full text was not retrieved). The numbers match the 2017 AHA/ACC categories and the ADA hypoglycaemia classification as summarised, but no primary quote is available; confidence is marked accordingly and no quote is invented.

## Decisions the operator must make first (S3)

1. **`glucose_high` watch band 140 to 199 is the weakest row.** The plan source is ADA "diagnosis section: <140 normal 2-h value". The ADA 2-hour value of 140 to 199 mg/dL is the impaired-glucose-tolerance range of a timed OGTT. A glucometer reading of unknown timing (fasting, random, post-meal) is not comparable, and a post-meal 160 would show "watch". Options: (A) keep as planned and label "screening prompt, not a diagnosis, timing unknown"; (B) drop the watch band (ok up to 199, act from 200, the "random >=200 with symptoms" line); (C) drop `glucose_high` entirely and keep `glucose_low`. S agent recommends A with the label, or B if the operator wants the card to stay quiet after meals. The S4 boundary test (139 ok, 140 watch, 199 watch, 200 act) assumes A.
2. **`bp_sys_high`/`bp_dia_high` use AHA/ACC, not NEWS2.** NEWS2 systolic scores 0 for 111 to 219 and 3 only at 220 or more, so NEWS2 would never flag 150. AHA/ACC categories (normal <120/<80, elevated 120 to 129, stage 1 130 to 139 or 80 to 89, stage 2 >=140 or >=90, severe >180 or >120) classify an average of two or more readings on two or more occasions, so one reading is a screening prompt only. Note the plan treats the AHA "elevated" band (120 to 129) as ok: this is a team choice, say so on the card. Approve or tighten.
3. **Confidence on 2025/2026 editions.** AHA/ACC 2025 is Hypertension 2025;82(10):e212 to e316 and keeps the 2017 categories (per two secondary sources). ADA Standards of Care 2026 Section 6 is Diabetes Care 2026;49(Suppl 1):S132 to S149 (doi 10.2337/dc26-S006). Operator may prefer to cite the 2017 AHA/ACC (Whelton et al., Hypertension 2018;71:e13 to e115) and ADA 2025, which I can name but also did not read in full text.
4. **Unverified claim in the plan:** "the OCHMO sleep brief: about 6 h observed in flight against a 7 to 9 h need" (`sleep_week` context) was not checked. Do not put it on a card until someone reads the brief.

## Clinical rules (S3 table)

Checked by: S agent, 2026-11-14. "Chart 1" = RCP NEWS2 Chart 1 "The NEWS scoring system" (one page), (c) Royal College of Physicians 2017. URL: https://www.rcp.ac.uk/media/alxev00t/news2-chart-1_the-news-scoring-system_0_0.pdf (landing page https://www.rcp.ac.uk/resources/national-early-warning-score-news-2/).

NEWS2 mapping used: score 0 is ok, 1 to 2 is watch, 3 is act (single-parameter use only). NEWS2 is for acutely ill adults in hospital.

| id | ind | window | ok | watch | act | source_kind | Document and edition | Section or table | URL | Quote (<=15 words) | Confidence | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `hr_rest_low` | hr | instant | min 51 | min 41 | any | clinical_ref | RCP, NEWS2 (2017) | Chart 1, row "Pulse (per minute)" | Chart 1 URL | "Pulse (per minute) <=40 | 41-50 | 51-90" (chart row: 3, 1, 0) | High | Resting readings only. |
| `hr_rest_high` | hr | instant | max 90 | max 130 | any | clinical_ref | same | same | same | "91-110 | 111-130 | >=131" (chart row: 1, 2, 3) | High | Resting readings only. |
| `spo2_low` | spo2 | instant | min 96 | min 92 | any | clinical_ref | same | Chart 1, row "SpO2 Scale 1 (%)" | same | "SpO2 Scale 1 (%) <=91 | 92-93 | 94-95 | >=96" (3, 2, 1, 0) | High | MAX30102 SpO2 is an uncalibrated estimate; guidance asks for a certified re-measure before escalation. |
| `body_temp_low` | body_temp | instant | min 36.1 | min 35.1 | any | clinical_ref | same | Chart 1, row "Temperature (C)" | same | "Temperature (C) <=35.0 | 35.1-36.0 | 36.1-38.0" (3, 1, 0) | High | `skin_temp` has no rule and is never judged as `body_temp`. |
| `body_temp_high` | body_temp | instant | max 38.0 | any | none | clinical_ref | same | same | same | "36.1-38.0 | 38.1-39.0 | >=39.1" (0, 1, 2) | High | Chart has no score 3 on the high side, so no act band. |
| `bp_sys_low` | bp_sys | instant | min 111 | min 91 | any | clinical_ref | same | Chart 1, row "Systolic blood pressure (mmHg)" | same | "<=90 | 91-100 | 101-110 | 111-219" (3, 2, 1, 0) | High | Chart has act for >=220; not used, see `bp_sys_high`. |
| `bp_sys_high` | bp_sys | instant | max 129 | max 180 | any | clinical_ref | AHA/ACC adult high blood pressure guideline 2025, Hypertension 2025;82(10):e212-e316 (categories unchanged from 2017, Hypertension 2018;71:e13-e115) | BP classification table | https://www.ahajournals.org/doi/10.1161/HYP.0000000000000249 | not retrieved (no primary quote) | Medium | Screening prompt, one reading. "Elevated" 120 to 129 treated as ok by team choice (decision 2). Severe = above 180. |
| `bp_dia_high` | bp_dia | instant | max 79 | max 120 | any | clinical_ref | same | same | same | not retrieved | Medium | Normal <80; stage 1 80 to 89; stage 2 >=90; severe >120. |
| `glucose_low` | glucose | instant | min 70 | min 54 | any | clinical_ref | ADA Standards of Care in Diabetes 2026, Diabetes Care 2026;49(Suppl 1):S132-S149 | Section 6, hypoglycaemia classification (level 1 <70, level 2 <54 mg/dL) | https://doi.org/10.2337/dc26-S006 | not retrieved (secondary: "Glucose <70 mg/dL and >=54 mg/dL") | Medium-High | Level 1 is below 70 and at or above 54; level 2 is below 54. Glucometer readings are screening prompts, not a diagnosis. |
| `glucose_high` | glucose | instant | max 139 | max 199 | any | clinical_ref | ADA Standards of Care 2026, Section 2 (diagnosis) | 2-h plasma glucose 140 to 199 (IGT range), >=200 | https://doi.org/10.2337/dc26-S002 (DOI pattern, not opened) | not retrieved | Low-Medium | See decision 1: OGTT values applied to untimed glucometer readings. |
| `sleep_night` | sleep_h | instant | min 7 | any | none | clinical_ref | Watson et al., AASM/SRS joint consensus, Sleep 2015;38(6):843-844 | Recommendation | https://www.aasm.org/resources/pdf/adultsleepdurationconsensus.pdf | "Adults should sleep 7 or more hours per night on a regular basis" | High | Applies to adults 18 to 60. No act band. |
| `sleep_week` | sleep_h | mean_7d | min 7 | any | none | clinical_ref | same | same | same | same | High (number), Medium (7-day mean use) | The consensus is about regular sleep; a 7-day mean is the team's way to apply it. |
| `mood_self` | mood | instant | min 3 | any | none | team_convention | none (no clinical cut-off exists for a single 1 to 5 item) | n/a | n/a | n/a | n/a | Label "Team convention, not clinical". |
| `mood_7d` | mood | mean_7d | min 2.5 | any | none | team_convention | none; context only: NASA HRP Behavioral Medical Conditions risk | n/a | n/a | n/a | n/a | 7-day mean of the 1 to 5 report below 2.5. Non-clinical. Needs 24 h coverage (H7a). Supporting signal for the isolation and confinement hazard. |

Required notes (to appear in each rule's `note` or the card):
- NEWS2 is for acutely ill adults in hospital; used here for single-parameter bands only.
- `hr` rules apply to resting readings.
- `spo2` from the MAX30102 is an uncalibrated estimate.
- Glucometer readings are screening prompts, not a diagnosis. No treatment doses anywhere.
- `skin_temp` has no rule (status `unknown`).
- No act band on `body_temp_high`, the `sleep_*` rules, `mood_self` or `mood_7d`.
- Optional NASA context for the glucose note (only if Proposed addition 7 is accepted): Inspiration4 crew lab reference range 65 to 99 mg/dL (OSDR OSD-575). Per research this was confirmed, but OSD-575 also contains implausibly low glucose values (36 to 44 mg/dL at R+45), so do not use it as a band.

Count check: 14 vital and mood rows here plus 9 NASA rows in S2 = 23 ids (`co2_1h`, `co2_7d`, `cabin_health_box_temp`, `cabin_health_box_rh`, `cabin_performance_temp`, `cabin_performance_rh`, `lux_general`, `radiation_career`, `radiation_spe`, `hr_rest_low`, `hr_rest_high`, `spo2_low`, `body_temp_low`, `body_temp_high`, `bp_sys_low`, `bp_sys_high`, `bp_dia_high`, `glucose_low`, `glucose_high`, `sleep_night`, `sleep_week`, `mood_self`, `mood_7d`).
