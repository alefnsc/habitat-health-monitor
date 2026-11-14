# M1 draft: NASA nutrition values for the 7 food rules (rules part)

Status: DRAFT for operator approval. Rules part only (NU8, open point g); `references.json` (NU9) comes later. M7 encodes NU8 first; any difference found here is a one-line fix in `data/food/thresholds_food.json`.
Drafted by the S agent, 2026-11-14. Every number was re-read in the primary PDF downloaded 2026-11-14. Checked by: S agent, 2026-11-14.

Documents:
- JSC-67378 = "Nutritional Requirements for Exploration Missions up to 365 days", JSC-67378 Rev 1, April 20 2020 (NTRS 20205008306). https://ntrs.nasa.gov/api/citations/20205008306/downloads/JSC67378%20Expl%20Nutr%20Reqs%20042020.pdf . Page numbers are the printed "JSC-67378 N" footers.
- TN71711 = "Nutrition Requirements, Standards, and Operating Bands for Exploration Missions", Initial Release (rev 1), December 2005 (NTRS 20200001703, JSC-E-DAA-TN71711). https://ntrs.nasa.gov/api/citations/20200001703/downloads/20200001703.pdf . Printed page numbers (PDF page = printed + 1). Superseded document: its bands are labelled "historical operating band".
- Vol 2 = NASA-STD-3001 Vol 2 Rev F (2026-07-14). https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf

## Decisions the operator must make first (M1)

1. **Only vitamin D is in NASA-STD-3001.** Vol 2 Rev F [V2 7100] (p. 116) points to the NIH Dietary Reference Intakes "with the exception of those adjusted for spaceflight as noted in Table 7.1-2", and Table 7.1-2 (p. 117) has a single row: vitamin D 25 µg. Sodium, iron, fluid and calcium numbers come from JSC-67378 (a NASA program document, not the standard). NU8 sets `source_kind` = `nasa_std` for every food rule; S agent recommends `nasa_std` only for `intake_vitd_floor` and a new honest label (for example "NASA JSC-67378") for the rest, or the card text must name JSC-67378, not NASA-STD-3001. This touches the D13 source_kind list, so it is the operator's call.
2. **Sodium watch band 2300 to 3500 is an interpretation.** The 2005 table has green 1500 to 2300, yellow "3500", red ">3500"; the interval 2300 to 3500 is not labelled. NU8 treats it as watch (ok max 2300, watch max 3500, act above). Accept, with the "historical operating band" label.
3. **Iron: no act band.** See row; recommended: keep NU8 (act none).
4. **Vitamin D and calcium floors could have a watch/act band from the 2005 table** but NU8 does not use them; recommended: keep NU8 (single floor, no further bands), because the 2005 requirements are superseded (calcium 2005 was 1200 to 2000 mg, now 1000 to 1200 mg).
5. **Fluid: the Vol 2 water number is supply, not intake.** [V2 6109] Table 6.3-1 (Vol 2 p. 69) requires the vehicle to provide at least 2.5 L potable water per crewmember per day for hydration. That is a supply requirement; the intake floor of 2100 mL comes from JSC-67378. Keep 2100 (the lower, women's value; crew sex is not recorded). Men's value is 2500 mL.

## Nutrition rules (7 ids)

Band notation as in S2. Quote limit 15 words (plan allows 25).

| id | ind | window | ok | watch | act | Document / revision | Requirement or table | Page | URL | Quote | Confidence | Deviation from NU8 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `intake_sodium_max` | intake_sodium_mg | dose_24h | max 2300 | max 3500 | any | JSC-67378 Rev 1 (ok); JSC-E-DAA-TN71711 (2005) Req. 23 (watch, act) | Mineral section; Table 1; 2005 Req. 23 | JSC p. 6 and Table 1 p. 9; TN71711 p. 34 | JSC-67378 URL; TN71711 URL | JSC: "Intake of sodium shall be 1500-2300 mg/d." 2005: ">3500 mg/d red; 3500 mg/d yellow; 1500-2300 mg/d green" | High (2300, 1500), Medium (3500 reading) | None. 2300 to 3500 gap read as watch (decision 2). |
| `intake_sodium_floor` | intake_sodium_mg | sum_24h_floor | min 1500 | min 500 | any | same | same | same | same | 2005: "500-1500 mg/d yellow; <500 mg/d red" | High | None. |
| `intake_iron_max` | intake_iron_mg | dose_24h | max 8 | any | none | JSC-67378 Rev 1; TN71711 (2005) Req. 25 | Mineral section "Iron"; Table 1 | JSC p. 6 and Table 1 p. 9; TN71711 p. 89 | same | JSC: "Iron intake shall not exceed 8 mg/d for men and women." | High | None. **iron_decision: no act band.** The 2005 table reads "35 mg/d red; 15-35 mg/d yellow; 8 mg/d green; 5-8 mg/d yellow; 3-5 mg/d red", but it leaves 8 to 15 mg unlabelled, its requirement was 8 to 10 mg/day (superseded by the 8 mg cap), and its red is at 35. It does not read unambiguously, so no act band. |
| `intake_water_floor` | intake_water_ml | sum_24h_floor | min 2100 | min 2000 | any | JSC-67378 Rev 1; TN71711 (2005) Req. 6 | "Fluid"; Table 1; 2005 Req. 6 | JSC p. 3 and Table 1 p. 8; TN71711 p. 30; Vol 2 p. 69 (supply) | same, plus Vol 2 URL | JSC: "no less than 2500 ml/d for men, no less than 2100 ml/d for women." 2005: "2 L/d yellow; <2 L/d red" | High | None. Value 2100 is the women's floor (decision 5). 2005 minimum intake of 2000 mL gives the watch edge. |
| `intake_vitd_floor` | intake_vitd_ug | sum_24h_floor | min 25 | any | none | NASA-STD-3001 Vol 2 Rev F, Table 7.1-2; JSC-67378 Rev 1 | [V2 7100], Table 7.1-2 | Vol 2 pp. 116 to 117; JSC p. 4 and Table 1 p. 8 | Vol 2 URL; JSC URL | Vol 2 Table 7.1-2: "Vitamin D 25 µg (micrograms)" | High | None. 2005 table (p. 45) would add watch 10 to 25 and act below 10 µg/d, and a yellow above 50; not adopted (decision 4). |
| `intake_calcium_floor` | intake_calcium_mg | sum_24h_floor | min 1000 | any | none | JSC-67378 Rev 1 | Mineral section "Calcium"; Table 1 | JSC p. 6 and Table 1 p. 8 | JSC URL | JSC: "Calcium intake shall be 1000-1200 mg/d for men and women" | High | None. 2005 (p. 78) said 1200 to 2000 with yellow 1000 to 1200: superseded. Floor 1000 is the lower edge of the current range. |
| `intake_calcium_max` | intake_calcium_mg | dose_24h | max 2500 | any | none | JSC-67378 Rev 1 | same | JSC p. 6 | JSC URL | JSC: "Calcium intake shall not exceed 2500 mg/d." | High | None. 2005 (p. 78): ">2500 mg/d red; 2000-2500 mg/d yellow". |

Count: 7 ids, as required (`intake_sodium_max`, `intake_sodium_floor`, `intake_iron_max`, `intake_water_floor`, `intake_vitd_floor`, `intake_calcium_floor`, `intake_calcium_max`). Checked-by lines: 7.

## Other checks required by M1

- **revision_checked:** JSC-67378 Rev 1 (20 Apr 2020) is the only revision on NTRS (search of NTRS 2026-11-14 returned only record 20205008306 for the title; the 2005 document is 20200001703). Not found newer. The 2005 operating bands come from a superseded document and are labelled "historical operating band".
- **EER typo:** JSC-67378 Rev 1 p. 2 prints the men's equation with the constant 622; NASA-STD-3001 Vol 2 Rev F Table 7.1-1 (p. 116) prints 662. Noted and unused (no energy rule). Rev F also gives the crew average 3,035 kcal/day [V2 7003] and +200 kcal per EVA hour [V2 7004], and AF 1.25 versus JSC's 1.11 "low active".
- **Iron for some women:** JSC-67378 p. 6 adds "for women under 50 ... iron intake shall be at least 18 mg/d"; no rule is written because sex is not collected.
- JSC-67378 p. 1 designs the requirements for a 70 kg person; fluid is "32 ml/kg body mass, and no less than ..." (p. 3); only the floor is encoded.
- NASA reference values describe a population, not a personal target (notes line for `references.json`).
