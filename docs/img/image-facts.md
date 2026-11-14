# Verified facts behind the presentation images

Read during this run on 2026-11-14. All sources fetched and read; PDFs read as extracted text. Only verified=true rows may be drawn. Hobby-sensor values are estimates; not a medical device. The console has no ISS, Moon or Mars mode.

## Cabin limits (same in every place)

| Metric | Value | Source | URL | Locator | Prototype checks today | Note |
|---|---|---|---|---|---|---|
| CO2 (1-hour mean) | <= 3 mmHg | NASA-STD-3001 Vol 2 Rev F | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | 6.2.1.3 [V2 6004], PDF p. 51 | yes | Checked today (rule co2_1h). NASA reference. |
| Temperature | 18-27 °C | NASA-STD-3001 Vol 2 Rev F | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | 6.2.3.1 [V2 6012] and Figure 6.2-2, PDF pp. 54-55 | yes | Rationale anchors the box at 18 C and 27 C; the figure is a polygon, so 18-27 C is its bounding range. Checked today (rule cabin_health_box_temp). |
| Total pressure | 34.5-103 kPa | NASA-STD-3001 Vol 2 Rev F | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | 6.2.2.1 [V2 6006], PDF p. 52 | NO (No rule) | Exact text: 34.5 kPa < pressure <= 103 kPa. NASA reference only: data/thresholds.json has no pressure rule, the console shows 'No rule'. |
| Humidity | 25-75 % RH | NASA-STD-3001 Vol 2 Rev F | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | 6.2.3.1 [V2 6012] and Figure 6.2-2, PDF pp. 54-55 | yes | Extra row, not on the card. Anchors 75 % at 18 C and 25 % at 27 C. Checked today (rule cabin_health_box_rh). |
| Career radiation dose | < 600 mSv | NASA-STD-3001 Vol 1 Rev C | https://standards.nasa.gov/sites/default/files/standards/NASA/C/nasa-std-3001-vol-1-rev-c-signature.pdf | 4.8.2 [V1 4030], PDF p. 40 | yes | Extra row, not on the card. The prototype's 300/540 mSv watch bands are team convention, not NASA. |

Humidity and career dose are extra rows (on_card=false); the card needs only the first three. Rule check from data/thresholds.json: rules exist for cabin_ppco2, cabin_temp, cabin_rh, cabin_lux, rad_dose_cum; none for cabin pressure.

## Low Earth orbit (space station) (iss)

| Metric | Value | Verified | Source | URL | Locator | Note |
|---|---|---|---|---|---|---|
| Gravity | about 0 g (free fall) | yes | NASA Glenn, Physical Sciences Program | https://www.nasa.gov/glenn/glenn-expertise-space-exploration/physical-sciences-program/ | text: station 'circles and falls around Earth, and the continuous free fall simulates the absence of gravity' | Microgravity, not zero gravity; the station is in continuous free fall. |
| Link to Earth | under 1 s delay (radio relay) | yes | NASA, Data Rate Increase on the ISS | https://www.nasa.gov/missions/station/data-rate-increase-on-the-international-space-station-supports-future-exploration/ | text: 'less than a one-second delay in communication' | This is a relay link delay through satellites, not Earth-Moon style light time. Corroborated by NASA Space Network page (no noticeable delay). |
| Radiation dose rate | 0.2-0.5 mSv/day | yes | NTRS 20250006168, Moon 2 Mars Space Radiation Protection (NASA draft conference paper) | https://ntrs.nasa.gov/citations/20250006168 | Section III, p. 2 of 11 | Effective dose, approximate. NASA-authored conference paper, labelled draft. |
| Outside air | near-vacuum (very thin air) | yes | NASA Space Place, Thermosphere | https://spaceplace.nasa.gov/thermosphere/en/ | text: ISS orbits in the thermosphere; too few gas molecules for sound to travel | NASA says 'not enough gas molecules', not 'vacuum'; wording kept honest. |

## Moon base (moon_base)

| Metric | Value | Verified | Source | URL | Locator | Note |
|---|---|---|---|---|---|---|
| Gravity | 1.62 m/s² (0.17 g) | yes | NASA NSSDC Moon Fact Sheet | https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html | Bulk parameters: surface gravity 1.62 m/s2; ratio to Earth 0.165 | NASA Science Moon Facts also says one-sixth of Earth's gravity (https://science.nasa.gov/moon/facts/). |
| One-way light time to Earth | about 1.3 s | yes | NASA Science, Voyager 1: What Is a Light-Day | https://science.nasa.gov/mission/voyager/voyager-1/voyager-1-what-is-a-light-day/ | text: light traverses the Earth-Moon distance in 1.3 seconds | Light time only. NASA TM-20250003885 (p. 2) estimates 3-14 s one-way latency for lunar links once systems are included; Apollo telemetry 1.3 s. |
| Radiation dose rate | no Earth magnetic shield | yes | NTRS 20250006168 (NASA draft conference paper) | https://ntrs.nasa.gov/citations/20250006168 | Section I, p. 2 of 11 | Plain-words only. No per-day number was verified for the lunar surface. |
| Outside air | essentially none | yes | NASA NSSDC Moon Fact Sheet | https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html | Lunar Atmosphere: surface pressure (night) 3 x 10^-15 bar | Tenuous exosphere, about 2 x 10^5 particles per cm3. |
| Lunar dust | cabin limit 0.3 mg/m³ | yes | NASA-STD-3001 Vol 2 Rev F | https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf | 6.4.4.2 [V2 6053], PDF p. 63 | Particles under 10 um, time-weighted average. A limit on dust inside the cabin, not a measurement. |

## Mars base (mars_base)

| Metric | Value | Verified | Source | URL | Locator | Note |
|---|---|---|---|---|---|---|
| Gravity | 3.73 m/s² (0.38 g) | yes | NASA NSSDC Mars Fact Sheet | https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html | Bulk parameters: surface gravity (mean) 3.73 m/s2, ratio 0.380 | Equatorial value 3.69 m/s2. The spec's 3.71 is not on this page, so 3.73 (mean) is used. |
| One-way light time to Earth | about 3-22 min | yes | NASA NSSDC Mars Fact Sheet + NASA ASCEND paper | https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html | Distance from Earth min 54.6e6 km, max 401.4e6 km; divided by c = 3.0 min and 22.3 min (my arithmetic). Corroborated: NTRS 20220013418 (p. 1, 9-10) max about 22 min | The prototype demo uses 12 min; that is a demo choice inside the range, not a NASA figure. NTRS record: https://ntrs.nasa.gov/citations/20220013418 |
| Radiation dose rate | about 0.5 mSv/day (estimate) | yes | NASA-STD-3001 Vol 1 Rev C | https://standards.nasa.gov/sites/default/files/standards/NASA/C/nasa-std-3001-vol-1-rev-c-signature.pdf | rationale after [V1 4032], PDF p. 44 | NASA design analysis for a surface mission (Mars mission analysis cited there), not a measured value. Same standard sets a design ceiling of 0.9 mSv/day on surfaces [V1 4033]. |
| Outside air | about 0.6 kPa, 95 % CO2 | yes | NASA NSSDC Mars Fact Sheet | https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html | Martian Atmosphere: surface pressure 6.36 mb (4.0-8.7 seasonal); CO2 95.1 % | 6.36 mb = 0.636 kPa. |

## Dropped or changed figures

| Figure | Reason |
|---|---|
| Mars gravity 3.71 m/s2 | Not found on the NASA NSSDC Mars fact sheet, which lists 3.73 mean and 3.69 equatorial. 3.73 used instead. |
| ISS light time about 1 s | No NASA source gives a light time for the ISS. NASA says the relay link has under 1 s delay, so the row says that instead. |
| ISS outside: vacuum | No NASA page read states 'vacuum' for the ISS. NASA Space Place says the thermosphere has too few molecules for sound; row says near-vacuum (very thin air). |
| Moon surface radiation dose rate (number) | No source read gives a trustworthy per-day number. NTRS 20250006168 Table 1 labels its GCR values mSv/yr, which is inconsistent with its own 'two to three times ISS' comparison, so none of its table values are used. |
| Mars surface dose from NTRS 20250006168 Table 1 (0.35/0.65) | Same unit problem in the draft table (mSv/yr). V1 Rev C 0.5 mSv/day estimate used instead. |
| Mars light time 12 min as a NASA figure | No NASA source gives 12 min. It is the prototype demo value; shown only as a note. |
| Moon light time 1.3 s as total link delay | 1.3 s is light time only. NASA TM-20250003885 estimates 3-14 s one-way for lunar links including systems; do not call it the link delay. |
| Any claim of an ISS/Moon/Mars mode in the console | data/environments.json was never built; no mode exists. |
