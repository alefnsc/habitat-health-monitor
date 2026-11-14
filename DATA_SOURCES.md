# Data sources

Every outside data source the Habitat Health Monitor touches, with access date (UTC), auth, terms, committed files, what the hub does with it, and what breaks without it. Access dates are 2026-11-14 unless stated. No key or credential is stored in this repository: a personal NASA key, if used, is read from the environment variable `NASA_API_KEY`, and the shared demonstration key is never used.

Last updated by the Science lane (N11a). The BLE, wearable-baseline, OAuth, ground-replay and final nutrition entries are added by the final pass (S14). ISS Live is not listed yet because its task has not landed.

## NASA DONKI (space weather)

- Name: NASA CCMC DONKI (Space Weather Database Of Notifications, Knowledge, Information).
- Endpoints: `https://ccmc.gsfc.nasa.gov/DONKI-API/get/{FLR,SEP,GST,notifications}?startDate=&endDate=` (keyless, direct host, used by default). Keyed route: `https://api.nasa.gov/DONKI/{kind}?api_key=<NASA_API_KEY>` with a personal key (never the shared demonstration key).
- Access date: 2026-11-14.
- Auth: none on the direct host; a personal key on `api.nasa.gov`, read from the environment.
- Terms: public NASA data; no separate licence file was found for these endpoints. Cite as NASA CCMC DONKI.
- Window and polling: a query window of at most 60 days (probed 2026-11-14: 60 days answers 200, 61 days answers 400); the hub polls every 10 minutes and keeps a runtime cache under `var/`, which is not committed.
- Committed file: `data/nasa/donki_replay_2025-11.json`, a recorded payload (source `https://ccmc.gsfc.nasa.gov/DONKI-API/get/{FLR,SEP,GST}?startDate=2025-11-01&endDate=2025-11-30`) replayed for the demo and labelled "not live data".
- Use: the team's own trigger logic turns events in the last 24 hours into `space_weather` level 0, 1 or 2: a solar energetic particle (SEP) alert gives level 2; an X-class flare or Kp 7 or higher (NOAA G3) gives level 1. The hub then assesses it with rule `radiation_spe`.
- Disclaimer: DONKI is a research-grade archive, not an operational warning service. Operational space-weather forecasts and warnings come from NOAA SWPC. The trigger levels are the team's, not a NASA or NOAA product.
- Without it: the space-weather card shows grey ("unknown or stale"); the replay file keeps the demo working.

## NASA OSDR Environmental Data Application (EDA) and RadLab

- Name: NASA Open Science Data Repository, Environmental Data Application, and the RadLab dose API.
- Endpoints that answered in the 2026-11-14 probe (`docs/nasa/osdr-probe.md`): `https://visualization.osdr.nasa.gov/eda/api/missions/`, and for mission RR-6: `/missions/RR-6/temperature/iss/`, `/missions/RR-6/humidity/iss/`, `/missions/RR-6/co2/iss/`, `/missions/RR-6/radiation_data/`, all under `https://visualization.osdr.nasa.gov/eda/api`. The bare paths without a mission segment return 404. Fallback dose source: `https://visualization.osdr.nasa.gov/radlab/api/` (DosTel instruments), not used because its unit could not be confirmed.
- Access date: 2026-11-14. Auth: none. Terms: public NASA data; no separate licence file was found.
- Mission: RR-6 (SpaceX-13, Dec 2017 to Feb 2018), chosen because temperature, humidity, CO2 and radiation are all complete for it.
- Committed file: `data/nasa/osdr_eda_snapshot.json` (fetched 2026-11-14).
- Units as observed: the JSON carries no units; they come from the EDA page scripts: degC, % RH, CO2 in ppm (converted to mmHg for comparison with the 3 mmHg limit), radiation "Dose [mGy/day]". The RadLab unit is not confirmed (the portal documentation returned HTTP 500); values are consistent with uGy/h, which is an inference.
- Dose: the radiation series is absorbed dose in mGy (one value per day, summed over the mission). OSDR absorbed dose (mGy) is shown separately and never converted to mSv.
- Use: ISS reference panel for the cabin and a mission absorbed-dose figure.
- Without it: the reference panel is empty; the committed snapshot keeps it working.

## Mission dose estimate (effective dose)

- Method (Science lane, S2): `mission_day × 0.5 mSv/day (upper ISS effective-dose rate, NTRS 20250006168); estimate, not measured`.
- Source of the rate: Simonsen, Zawaski, Weeks, "Moon 2 Mars Space Radiation Protection 'Buying Down' Risks to Crew" (draft paper), NTRS 20250006168, https://ntrs.nasa.gov/citations/20250006168: effective doses accumulate at about 0.2 to 0.5 mSv/day on the ISS.
- Career limit: NASA-STD-3001 Vol 1 Rev C [V1 4030], 600 mSv (https://standards.nasa.gov/sites/default/files/standards/NASA/C/nasa-std-3001-vol-1-rev-c-signature.pdf). The 50 % and 90 % watch and act points are a team convention.
- It is an estimate, never computed from OSDR mGy. Committed file: `data/nasa/dose_profile.json` (added with the dose-estimate task; this entry covers it).
- Without it: the career gauge is not shown.

## NASA Human Research Program risk pages

- Name: NASA HRP Human Research Roadmap, risk pages.
- Endpoint: `https://humanresearchroadmap.nasa.gov/Risks/?i=NN` (list at `https://humanresearchroadmap.nasa.gov/Risks/`).
- Access date: scraped 2026-11-14 (13:22 UTC, per the file). Auth: none. Terms: public NASA pages.
- Committed file: `data/nasa/hrp_risks.json` (21 risks as scraped). Ratings are NASA Human System Risk Board programme-level likelihood × consequence values for crew populations, not personal probabilities.
- Use: risk links and "why this measurement" lines in the guidance texts; the nutrition indicators map to risk 176.
- Without it: the risk labels are missing; the links still work.

## NASA standards and technical documents (threshold sources)

Read in full on 2026-11-14; page and requirement ID for each number are in `docs/thresholds-review.md`.
- NASA-STD-3001 Volume 2 Rev F (approved 2026-07-14): https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf
- NASA-STD-3001 Volume 1 Rev C (approved 2023-09-15): https://standards.nasa.gov/sites/default/files/standards/NASA/C/nasa-std-3001-vol-1-rev-c-signature.pdf
- OCHMO-TB-004 Rev D, carbon dioxide (10-Mar-26): https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf
- Auth: none. Terms: public NASA documents; cited, not redistributed.
- Use: cabin and radiation limits, each shown with its requirement ID. Vital-sign bands are clinical references and are not NASA-published (`docs/thresholds-review.md`).

## NASA nutrition documents

- JSC-67378 Rev 1, "Nutritional Requirements for Exploration Missions up to 365 days" (20 Apr 2020), NTRS 20205008306: https://ntrs.nasa.gov/api/citations/20205008306/downloads/JSC67378%20Expl%20Nutr%20Reqs%20042020.pdf (NASA program document, not NASA-STD-3001).
- JSC-E-DAA-TN71711, "Nutrition Requirements, Standards, and Operating Bands for Exploration Missions" (Dec 2005, superseded; bands are labelled "historical operating band"), NTRS 20200001703: https://ntrs.nasa.gov/api/citations/20200001703/downloads/20200001703.pdf
- NASA-STD-3001 Vol 2 Rev F Table 7.1-2 (vitamin D 25 µg) and [V2 7100]; URL above.
- Access date: 2026-11-14. Auth: none.
- Use: the seven food rules (`data/food/thresholds_food.json`) and the reference values. NASA reference values describe a population, not a personal target.
- Without it: the food rules cannot be explained.

## USDA FoodData Central (SR Legacy)

- Name: USDA FoodData Central, SR Legacy, release 04/2018.
- Source: https://fdc.nal.usda.gov/ (bulk download of the SR Legacy dataset).
- Licence: CC0 1.0; credit USDA FoodData Central.
- Committed file: `data/food/catalog.json` (generic foods only, built by `tools/food/build_catalog.py` from `data/food/items.csv`). The file is labelled synthetic: database values for generic foods, not NASA menu items and not measurements of the item eaten.
- Access date: 2026-11-14 (catalogue generated 2026-11-14). Auth: none for the bulk download.
- Use: nutrient values for the food log.
- Without it: no catalogue, no food screen.
