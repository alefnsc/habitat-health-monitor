# OSDR probe results (task N6, Part A)

Probed live on 2026-11-14 (about 10:20 local) from the hub dev machine, no key, no auth. This draft is copied to `docs/nasa/osdr-probe.md` for the repo record (same content); the Science lane edits the decision lines below.

## What changed against the plan's URL list

The plan and spec list the telemetry paths without a mission segment (`/temperature/iss/`). Those bare paths return HTTP 404. Every series path lives under `/missions/{name}/`. The query parameters `start` and `end` (ISO 8601, `YYYY-MM-DDTHH:MM:SSZ`) filter by date; without them the whole mission is returned (up to about 2 MB for `telemetry_data`).

Units are not in the JSON. They come from the EDA page's own plotting scripts (`/eda/static/js/telemetry_plots.js` and `radiation_plots.js`): temperature `Degrees [C]`, humidity `RH [%]`, CO2 `CO2 [ppm]`, radiation `Dose [mGy/day]` (one value per day, so a mission total is the sum of the days). The API reference page (`/eda/api_reference`) names the series but gives no units.

## Probe table

Base URL: `https://visualization.osdr.nasa.gov/eda/api`. Probed with mission RR-6 (fixtures) and with all 24 missions (coverage table below). Fixtures are windowed to 6 hours (`start=2017-12-16T00:00:00Z&end=2017-12-16T06:00:00Z`) to keep them small; `radiation_data` and `missions` are whole responses.

| Path | HTTP | Value keys | Unit as observed | Fixture |
|---|---|---|---|---|
| `/missions/` | 200 | `name`, `title`, `description`, `link` (24 missions) | n/a | `eda/missions.json` |
| `/missions/{name}/telemetry_data/` | 200 | `time`, `temperature_iss`, `temperature_ground`, `humidity_iss`, `humidity_ground`, `co2_iss`, `co2_ground`, `milestones` | degC, % RH, ppm (EDA page scripts) | `eda/telemetry_data_RR-6.json` |
| `/missions/{name}/temperature/iss/` | 200 | `time`, `temperature_iss` | degC | `eda/temperature_iss_RR-6.json` |
| `/missions/{name}/humidity/iss/` | 200 | `time`, `humidity_iss` | % RH | `eda/humidity_iss_RR-6.json` |
| `/missions/{name}/co2/iss/` | 200 | `time`, `co2_iss` | ppm | `eda/co2_iss_RR-6.json` |
| `/missions/{name}/temperature/ground/` | 200 | `time`, `temperature_ground` | degC | `eda/temperature_ground_RR-6.json` |
| `/missions/{name}/humidity/ground/` | 200 | `time`, `humidity_ground` | % RH | `eda/humidity_ground_RR-6.json` |
| `/missions/{name}/co2/ground/` | 200 | `time`, `co2_ground` | ppm | `eda/co2_ground_RR-6.json` |
| `/missions/{name}/radiation_data/` | 200 | `time`, `gcr`, `saa`, `total`, `milestones` | mGy/day (EDA page script, "Dose [mGy/day]") | `eda/radiation_data_RR-6.json` |
| `/temperature/iss/` (no mission segment, as listed in the plan) | 404 | none | n/a | none |
| RadLab `https://visualization.osdr.nasa.gov/radlab/api/?instrument_id=DosTel1&timestamp>2024-05-10T00:00&timestamp<2024-05-10T03:00&absorbed_dose_rate&format=json` | 200 | `columns` (`timestamp`, `instrument_id`, `absorbed_dose_rate`), `index`, `data` | uGy/h per the OSDR docs example; not stated in the response | `radlab/dostel1.json` |

`/missions/{name}/` (single mission) also answers 200 with `name`, `title`, `description`, `link` (fixture `eda/mission_RR-6.json`). Extra radiation routes `/missions/{name}/{gcr|saa|total}/` are documented, not probed.

RadLab notes: an empty window returns 200 with `data: []` (for example Dec 2020 for DosTel1). The RadLab GUI and docs pages returned HTTP 500 on 2026-11-14, so the unit could not be confirmed from the portal. Sample values 4.3 to 5.9 are consistent with uGy/h but that is an inference.

## Mission coverage (full responses, all series for ISS and ground are the same length per mission)

Missions with temperature, humidity, CO2 (ISS) and radiation all present: RR-1, RR-3, RR-6, RR-7, RR-9, RR-12, RR-19, RR-23. No telemetry at all: RR-4, RR-8, RR-17, VEG-01B, RR-22. No radiation rows: RR-5, RR-18, APEX-03-1, APEX-03-2, APEX-04, VEG-01A, VEG-01C, RR-10, RR-20, RR-25, RR-28, VEG-01B, RR-22.

| Mission | Telemetry rows | Temp ISS (degC) | RH ISS (%) | CO2 ISS (ppm) | Radiation days | Mean total (mGy/day) |
|---|---|---|---|---|---|---|
| RR-1 | 12087 | 18.5-26.8, complete | 31-76, complete | 1862-4667, complete | 39 | 0.204 |
| RR-3 | 14385 | 18.5-24.8, complete | 32-66, complete | 250-6977, complete | 43 | 0.230 |
| **RR-6** | 17572 | 21.7-25.6, complete | 25-61, complete | 500-4187, complete | 49 | 0.283 |
| RR-7 | 43898 | 20.0-30.0, 97% | 28-79, 50% | 200-9000, 50% | 76 | 0.287 |
| RR-9 | 10079 | 20.8-30.0, complete | 33-67, complete | 400-4051, complete | 32 | 0.319 |
| RR-12 | 11785 | 17.6-27.9, complete | 12-62, complete | 500-3668, complete | 37 | 0.361 |
| RR-19 | 10193 | 14.3-26.0, complete | 27-56, complete | 128-3581, complete | 35 | 0.362 |
| RR-23 | 52599 | 19.5-25.3, 92% | 35-62, 92% | 1226-3159, 83% | 39 | 0.355 |

RR-9 caveat: its radiation dates (Aug to Sep 2017) do not overlap its telemetry dates (Aug to Sep 2018), so the two series cannot be paired by date.

## Decisions

Proposed by the N agent from the table above. The Science lane confirms or replaces the first line (S2 open point e).

Mission: RR-6
Radiation source: eda
RadLab unit confirmed: no

Reasoning, for the Science lane: RR-6 (SpaceX-13 rodent mission, 2017-12-06 to 2018-02-06) has gap-free temperature, humidity and CO2 for the whole mission and 49 daily radiation values on the same dates (2017-12-15 to 2018-02-01), the longest complete set after RR-7 (which is half empty for humidity and CO2). Radiation comes from EDA because its unit (mGy/day) is printed on the EDA page itself, while the RadLab unit stays unconfirmed (the portal docs returned HTTP 500). EDA radiation is absorbed dose in mGy, not effective dose in mSv.
