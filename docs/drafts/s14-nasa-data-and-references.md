# S14 draft: NASA Data field and References

FIRST DRAFT by the S agent. The operator submits. Not final: the ISS Live line, the dependency list after 14:00 (S19 re-runs the check), the `ground-truth` commit SHA (from `vendor/ground-truth/PINNED`, C10, not yet on main) and M12's wording are open. Libraries are cited by exact project name (Q4 answer pending, S1). Licences for Python packages were read from installed package metadata on 2026-11-14; JavaScript licences are from the package names and must be confirmed from `package.json` metadata before S19.

## NASA Data

- We use NASA-STD-3001 Volume 2 Rev F (https://standards.nasa.gov/system/files/tmp/NASA-STD-3001%20Vol%202%20Rev%20F.pdf), Volume 1 Rev C and OCHMO-TB-004 Rev D to set every cabin and radiation threshold with its requirement ID; without it the status colours would have no basis.
- We use NTRS 20250006168, a NASA draft paper (https://ntrs.nasa.gov/citations/20250006168), for the upper ISS effective-dose rate of 0.5 mSv/day behind the career dose estimate; without it the career gauge would have no cited rate.
- We use NASA CCMC DONKI (https://ccmc.gsfc.nasa.gov/DONKI-API/) solar flare, particle and geomagnetic storm events to drive the radiation banner and alert; without it there is no space-weather alert.
- We use the NASA OSDR Environmental Data Application (https://visualization.osdr.nasa.gov/eda/) for ISS cabin temperature, humidity, CO2 and absorbed dose from mission RR-6 as a reference panel; without it the console has no real ISS cabin reference.
- [ISS Live: add when built, linking NASA's own page, not the push host.]
- We use the NASA Human Research Roadmap risk pages (https://humanresearchroadmap.nasa.gov/Risks/) to explain why each indicator matters; without it the guidance texts would have no NASA risk link.
- We use JSC-67378 Rev 1 (NTRS 20205008306, https://ntrs.nasa.gov/citations/20205008306) with NASA-STD-3001 Table 7.1-2 for the food and fluid reference values and rules; without it the food screen would have no reference values or rule sources to judge against.

## References

Clinical and standards documents
- NASA-STD-3001 Vol 2 Rev F (2026-07-14); Vol 1 Rev C (2023-09-15); OCHMO-TB-004 Rev D (2026-03-10); JSC-67378 Rev 1 (2020-04-20); JSC-E-DAA-TN71711 (2005, superseded, used only as "historical operating band"); NTRS 20250006168 (draft paper); NTRS 20220013418, "Communication Delays, Disruptions, and Blackouts for Crewed Mars Missions" (light-time range). NASA documents are public.
- Royal College of Physicians, National Early Warning Score (NEWS) 2, Chart 1 (2017), https://www.rcp.ac.uk/resources/national-early-warning-score-news-2/
- 2025 AHA/ACC high blood pressure guideline, Hypertension 2025;82(10):e212-e316, doi 10.1161/HYP.0000000000000249
- American Diabetes Association, Standards of Care in Diabetes-2026, Diabetes Care 2026;49(Suppl 1), doi 10.2337/dc26-S006 (Section 6)
- Watson NF et al., Recommended Amount of Sleep for a Healthy Adult: AASM and SRS consensus, Sleep 2015;38(6):843-844
- NOAA Space Weather Prediction Center scales (R3 = X1 flare, G3 = Kp 7), used for the team's trigger levels

Data
- USDA FoodData Central, SR Legacy release 04/2018, CC0 1.0, credit requested to USDA FoodData Central (https://fdc.nal.usda.gov/)
- NASA DONKI, OSDR EDA, HRP: see NASA Data and `DATA_SOURCES.md`

Prior work (declared)
- ground-truth, https://github.com/alefnsc/ground-truth, declared prior work written 2026-09-23 to 2026-10-11, Apache-2.0, used at commit [40-hex SHA from `vendor/ground-truth/PINNED`]. Public status pending S1.

Software (Python, licence from package metadata)
- FastAPI (MIT), Uvicorn (BSD-3-Clause), aiomqtt (BSD), paho-mqtt (EPL-2.0 or BSD-3-Clause), pyserial (BSD), httpx (BSD-3-Clause), Beautiful Soup 4 (MIT), pytest (MIT), ruff (MIT), respx (BSD-3-Clause), pytest-asyncio (Apache-2.0), matplotlib (Matplotlib licence, PSF-based), NumPy (BSD-3-Clause)
- JavaScript (confirm): Vite, Vitest, jsdom, TypeScript; console and camera manifests to be read at 14:00
- MediaPipe Pose Landmarker lite (Apache-2.0), if the camera page ships
- Mosquitto broker (EPL-2.0/EDL-1.0) [confirm]
- Firmware libraries: from `firmware/README.md` library table (F1)

Images and media: none yet. AI use: `docs/AI_DISCLOSURE.md`.
