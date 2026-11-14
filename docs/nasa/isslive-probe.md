# ISS Live item ids (probe record)

Source: the community telemetry sheet `ISS_Public_Telemetry.xlsx` (ISS Mimic project), read on 2026-11-14. The sheet is not copied into this repository.

| Item id | Name | Label unit (sheet) | Assumed unit |
|---|---|---|---|
| `USLAB000058` | `cabin_pressure` | PSI | mmHg by magnitude (values read 740 to 780) |
| `USLAB000059` | `cabin_temperature` | CNT | degrees Celsius (values read about 23) |
| `USLAB000055` | `lab_ppco2` | PSIA | mmHg (values read about 2.4) |
| `NODE3000003` | `node3_ppco2` | PSIA | mmHg (values read about 2.9) |

Unit assumption: the feed labels cabin pressure PSI, but the values are mmHg by magnitude. A PSI reading of 14.7 would be sea level; the feed shows about 759.

Never subscribe to `TIME_000001`: it pushes about 20 updates per second.

TimeStamp formula: TimeStamp = day-of-year x 24 + UTC hours, where day 1 is 1 January of the current year. Use the previous year if the result is more than 1 day ahead of now.

Client: `lightstreamer-client-lib` 2.2.3 (PyPI), server `https://push.lightstreamer.com`, adapter set `ISSLIVE`, mode MERGE, fields `TimeStamp`, `Value`, `Status.Class`. Dependencies: aiohttp, jsonpatch.

Licence: Apache-2.0 (OSI: yes)
