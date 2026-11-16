# Pre-submit checklist (S19) and final submit (S20)

Plan task S19, Sunday 15/11 20:00–21:00 (São Paulo time). Every line reads pass, fail or pending, with the time and who checked it.

- **Agent lines:** re-run by an agent on `main` at `239924d`, 15/11 16:32–16:59. The 20:00 check re-runs them on the main of that moment and updates the time.
- **Pending lines:** need a person, and the operator fills them at 20:00.
- **Fails:** each one has a fix task below, with an owner and a 21:30 deadline (S19 step 2).
- **Tests:** run with `pytest -m 'not broker'` only, so nothing touches the live bench broker.
- **Bench:** nothing on the bench was touched (no hub restart, serial, MQTT or flashing).

**Count at 17:00:** 16 pass, 0 fail, 7 pending.
- Lines 3a and 16 failed at 16:39 and passed after the text fixes F2 and F4.
- Lines 2 and 7 pass by operator ruling ("Accept both", relayed by the hub session at 17:00).

## Checklist

| # | S19 line | Result | Time | Who | Evidence and notes |
|---|---|---|---|---|---|
| 1 | Video: ffprobe duration ≤ 29.0 s and the player shows ≤ 0:30 | pending: operator at 20:00 | | | The export comes after the 17:00 takes. Record the ffprobe duration and the SHA-256 of the exported file here and in `docs/video/script.md` ("Export"). The placeholder dry run (`out/dryrun-29s.mp4`) was 29.000 s, but it is not the final file. |
| 2 | Video subtitles name the challenge question: the "Question answered:" line of `docs/video/script.md` matches the 2.0–6.0 s subtitle | pass | 17:00 | operator ruling | Passes under the amended S16 check (B3). The title card (0.0–1.6 s, deck slide 1) states the question, and `docs/video/script.md:3` carries the "Question answered:" line in the challenge's own words. No caption change. **Agent finding at 16:38:** the 2.0–6.0 s cues in `subtitles.en.srt` don't name the question, and SRT cue 1 reads only "Habitat Health Monitor." (F1). |
| 3 | Doc and content tests, all pass | pass | 16:40 | agent | `pytest -m 'not broker'` on the six content files that exist gives 117 passed. **Left out, never created:** `docs/tests/` (with `test_references.py`), because S14's reference tests were not built; and `hub/tests/test_environments_content.py`, because the environment presets were cut (the console has no ISS, Moon or Mars mode). Line 3a re-checks the dependency citations by hand instead. |
| 3a | `test_every_dependency_cited`, re-checked against the manifests as they stand now (hand check, because the test does not exist) | pass | 16:59 | agent | All 33 dependencies in `pyproject.toml` and `camera`, `console` and `ground/package.json` are now named in the References (`docs/drafts/s14-nasa-data-and-references.md`) or in `DATA_SOURCES.md`. At 16:39 five were missing, so this line failed: `uplot`, `segno`, `smbus2`, `upstash-redis` and `@types/node`. Fix F2 cited them. |
| 4 | Links: video, public page and repo each open in a private window on mobile data, with no sign-in | pending: operator at 20:00 | | | Judged link changed at about 18:15 (operator, D24): `https://habitat-health-monitor.vercel.app/`. Agent pre-check at 18:32, from this machine (not a private window and not mobile data): the judged page, its `/console/` and `/ground/summary` (JSON), the Pages mirror `https://alefnsc.github.io/habitat-health-monitor/` and its `/console/`, and the repo `https://github.com/alefnsc/habitat-health-monitor` all return 200. The video link does not exist yet. |
| 5 | Entry repository is public, Apache-2.0 and created at or after 2026-11-14 09:00 (D24) | pass | 16:33 | agent | `gh repo view alefnsc/habitat-health-monitor --json visibility,licenseInfo,createdAt` gives `PUBLIC`, `apache-2.0` and `2026-11-14T13:04:59Z` (10:04 in São Paulo). |
| 6 | The public page shows all six named indicators | pass | 16:36 | agent | The C25 console replay at `/console/#/status` on the judged link (`/habitat-health-monitor/console/#/status` on the Pages mirror), linked from the ground page as "Crew console (replay)", shows Blood pressure, Heart rate, Glucose, Body temperature, Sleep and Mood. The ground page's own table does not show them. The 16:36 check was on the mirror. Both serve the same `replay.json` (same SHA-256 at 18:32). Re-check on the judged link at 20:00. |
| 7 | The public page lists the five hazards with links | pass | 17:00 | operator ruling | The project page text (`docs/drafts/s13-project-page.md:38–44`) is accepted as the public listing. It lists the five NASA hazards, each linked to its HRP page, and all 5 links returned 200 at 16:34. Neither the judged page nor the Pages mirror has changed since the freeze: no merge after 16:00 touches `ground/` or `console/`. Every merge to main redeploys the judged page; after S20, merge nothing that touches ground/ or console/, or turn off automatic production deploys, until judging ends (operator). **Agent finding at 16:37:** neither the ground page nor any console screen lists the hazards (F3). |
| 8 | The console replay opens with no hub (write which one was checked) | pass | 16:36 | agent | Checked the **C25 `/console/` bundle**. The L9 "Crew view (replay)" panel is also on the ground page. The browser made only static requests to `alefnsc.github.io`: the page, its assets, `replay.json`, `guidance.json` and `exercise-day.jsonl`. There was no `/api` request and no WebSocket. This 16:36 evidence is from the Pages mirror. Re-check on the judged link at 20:00: its `/console/` bundle should make only static requests. The ground page there also reads `/ground/summary` and `/ground/arrivals`, which are its own public API, never the hub. |
| 9 | Seed readings are labelled Replay wherever they are shown, and no brand names are in the food catalogue | pass | 16:41 | agent | **Replay labels:** every console reading carries "Replay (recorded)". The console and the ground page both show the banner "Replay of a recorded session — not live data", and the ground table's Source column reads `replay`. On the judged link, while arrivals are under 5 minutes old, the ground page shows the live banner instead. At 20:00, note which mode it is in and check that mode's banner. **Catalogue:** `grep -ci "brand" data/food/catalog.json` gives 0. All 31 item names were read once, and all are generic foods. |
| 10 | DATA_SOURCES coverage: every host in code appears in `DATA_SOURCES.md`, except the listed ones | pass, with exceptions | 16:40 | agent | 23 hosts, 12 not in `DATA_SOURCES.md`. Allowed by name: `localhost`, `127.0.0.1` and `www.w3.org` (an XML namespace in the HRP fixtures). The other nine are documented exceptions E3. None is an uncited data source. |
| 11 | English-only sweep of the page, README, console UI strings, ground page and subtitles | pass, with exceptions | 16:40 | agent | The S19 grep for Portuguese words gives 11 hits: 7 in `docs/consent.md` and 4 in `docs/drafts/s1-local-lead-questions.md`. Both are documented exceptions (E4, E5). The project page text, the subtitles, the README and the console and ground sources have none. |
| 12a | Brand sweep, company name: none in the UI, page body, video text or code | pass, with exceptions | 16:40 | agent | A case-insensitive `git grep` for the company name finds 5 lines, all of them the tests' own `assert "<company name>" not in …` guards (exception E1). `docs/video/script.md`, `subtitles.en.srt` and the project page text have none. The judged URL carries the hosting provider's name (exception E6); it stays out of page UI text and the video. |
| 12b | Brand sweep, Q4 and Q5: the team name and About text match the Q5 decision, and product names are allowed by the Q4 answer | pending: operator at 20:00 | | | The current team name contains the company name (R5), so the operator decides before S20. For the operator to confirm under Q4: <ul><li>The project page names hardware and tools by project name: Arduino Uno, ESP8266, Raspberry Pi 3, Mosquitto, Wokwi, FastAPI.</li><li>The ground page shows UNO, DHT11, NodeMCU, KY-017 and Raspberry Pi.</li><li>The console shows sensor part numbers: MAX30102, DS18B20, SCD41, BME280, BH1750.</li><li>The end card names the narration tool, as the AI disclosure (R7) requires.</li><li>The judged URL names the hosting provider (exception E6). It goes only in the "Link to Final Project" field, never in the page body text or the video.</li></ul> |
| 13 | No demo key used as a key (the S19 `git grep`) | pass | 16:40 | agent | No output. |
| 14 | No secrets tracked (`git ls-files \| grep -i -E "passw\|secret\|\.env$"`) | pass, with exceptions | 16:40 | agent | 3 hits, all `secrets.example.h` files: `firmware/cabin-esp8266`, `firmware/tilt-esp8266` and `firmware/vitals-esp32`. They hold only placeholders (`your-wifi-name`, `your-wifi-password`, `change-me`, a 192.168.0.10 example host and a placeholder user name). Exception E2. No `.env` file is tracked. |
| 15 | Licence: `LICENSE` is Apache-2.0 | pass | 16:33 | agent | `LICENSE` is the Apache License 2.0 text (202 lines), and GitHub detects `apache-2.0`. |
| 16 | The `ground-truth` SHA in References equals the `commit=` line of `vendor/ground-truth/PINNED` | pass | 16:59 | agent | The References (`docs/drafts/s14-nasa-data-and-references.md:30`) now give `0940adab0ec33dd5127d7efdacfbc6744a31e4d6`. It equals `PINNED`'s `commit=` line, `docs/decisions/links.md` and `camera/public/NOTICE.txt`. At 16:39 the line failed: it still had the SHA placeholder and "Public status pending S1". Fix F4 replaced both; `alefnsc/ground-truth` is public, Apache-2.0. |
| 17 | NASA Data has one sentence per source | pending: operator at 20:00 | | | Agent pre-check of the draft (`s14-nasa-data-and-references.md`, "NASA Data"): 6 sources, one sentence each, plus one leftover placeholder line, "[ISS Live: add when built …]". ISS Live was not built, so delete that line (fix task F4). The operator checks the text in the submission form. |
| 18 | The SI field is filled | pending: operator at 20:00 | | | Form field. Not visible to the agent. |
| 19 | The roster has every member at São Paulo, none waitlisted | pending: operator at 20:00 | | | Form field. Not visible to the agent. |
| 20 | No minor in any image or video (R8), and no real names in data files | pending: operator at 20:00 | | | Look at the three images in `docs/img/` and the exported video. Agent pre-check: the crew ids in `data/` are only `crew-a`, `crew-b` and `crew-c`. |
| 21 | The public page works with the hub off | pass | 16:36 | agent | **Judged link:** the page reads only its own `/ground/*` API, never the hub, and falls back to the labelled replay after 5 minutes with no arrival (D38 §4.4). Re-check at 20:00. **Mirror:** the Pages site is static. At 16:36 the ground page and the console replay loaded and played from `alefnsc.github.io` with no hub request (see line 8). |

## Documented exceptions

- **E1:** the tests' `assert "<company name>" not in …` guards, one line each in `hub/tests/test_firmware_exercise.py`, `test_firmware_full_bench.py`, `test_firmware_tilt.py`, `test_firmware_tilt_twin.py` and `test_firmware_vitals.py`. They exist to keep the name out, and they are the only hits.
- **E2:** the three `secrets.example.h` files, which hold placeholders only. The real `secrets.h` files are not tracked.
- **E3:** hosts in code that `DATA_SOURCES.md` doesn't list, none of them a data source:
  - link targets in tests: `github.com`, `wokwi.com`, `alefnsc.github.io`;
  - test fixtures and test-only addresses: `example.org` and `192.168.4.20`, plus `lsda.jsc.nasa.gov`, `oig.nasa.gov` and `www.usa.gov`, which appear only in the HRP HTML fixtures;
  - the internal link-simulator service name: `linksim`.
- **E4:** `docs/consent.md` is the volunteer consent form, written in Portuguese for the local participants.
- **E5:** `docs/drafts/s1-local-lead-questions.md` holds internal questions to the local lead, in Portuguese. It is not submission text.
- **E6:** the judged URL `https://habitat-health-monitor.vercel.app/` carries the hosting provider's name. It may appear only in the "Link to Final Project" field, `docs/decisions/links.md`, the plan and the setup docs (`docs/deploy-public.md`, the D38 design, this checklist). It never appears in page UI text or the video (operator decision, 15/11 ~18:15).

## Fix tasks (deadline 21:30)

| Task | Line | What | Owner |
|---|---|---|---|
| F1 | 2 | **Ruled 17:00: pass.** Under the amended S16 check (B3), the title card plus the "Question answered:" line in `script.md` count as naming the question. No caption change. | operator |
| F2 | 3a | **Done 16:59.** The References now cite segno (BSD-3-Clause), smbus2 (MIT) and upstash-redis (MIT), marked as optional extras of `pyproject.toml`, and uPlot (MIT) and @types/node (MIT, dev only). Licences come from the package metadata, segno's from its licence file. Text only. | agent; operator approves the text |
| F3 | 7 | **Ruled 17:00: pass.** The project page's linked list of the five hazards is accepted as the public listing. Neither the judged page nor the Pages mirror has changed since the freeze. Every merge to main redeploys the judged page; after S20, merge nothing that touches ground/ or console/, or turn off automatic production deploys, until judging ends (operator). | operator |
| F4 | 16, 17 | **Line 16 done 16:59.** The `ground-truth` reference gives `0940adab0ec33dd5127d7efdacfbc6744a31e4d6`, and "Public status pending S1" now reads "The repository is public." **Still open, under line 17:** delete the ISS Live placeholder line from NASA Data. Text only. | agent for line 16; operator for line 17 |

## Also found (not S19 lines)

- **AI disclosure still marked as a draft (R7).**
  - `docs/AI_DISCLOSURE.md:3` says "DRAFT for review …".
  - `:9` still has "[confirm exact model names against the commit trailers]".
  - The README "Hardware" and "AI use" sections still carry "DRAFT [confirm: …]" markers (`README.md:45`, `:47`, `:80`).
- **The stated commit count is stale.** `docs/AI_DISCLOSURE.md:62` gives "67 of 67 on 2026-11-14". On `main` at `239924d`, all 222 non-merge commits carry a Claude `Co-Authored-By` trailer. The plan's `test_trailer_count_matches` allows ±5 at S19, so refresh the number.
- **A licence still needs checking.** The References line for the Mosquitto broker ends in "[confirm]" (`s14-nasa-data-and-references.md:36`).
- **The S20 comparison file is missing.** S20 step 2 compares the form with `docs/submission/project-page.md`, which doesn't exist. The final page text lives in `docs/drafts/s13-project-page.md`, and NASA Data and References in `docs/drafts/s14-nasa-data-and-references.md`. Either copy them there, or compare against the drafts and write that here.

## Pre-submit check closed

- All lines pass at: ____ (time, initials)
- Then commit: `git add docs/submission/checklist.md && git commit -m "docs(submission): pre-submit check passed"`

## S20 final submit

Plan task S20: due Sunday 22:00, hard deadline 23:59. The submission owner does these steps; nothing is submitted from the repo.

- [ ] 1. **Check:** after the final paste, the Project tab shows the submission as submitted for judging, with a timestamp before 22:00.
- [ ] 2. **Before the final click,** compare the saved page text with the repo text (`docs/submission/project-page.md`, or the drafts named above). Fix any difference first.
- [ ] 3. **Paste and submit:** paste the final texts and fill the link fields:
  - "Link to Final Project" = `https://habitat-health-monitor.vercel.app/` (D24);
  - "Link to Project Demo" = the video;
  - the repo `https://github.com/alefnsc/habitat-health-monitor` wherever the form asks for code.

  Do not paste the Pages mirror as the final project link. Then click "Submit for Judging". After that:
  - edit only for a critical fix, and re-submit before 23:59;
  - keep all links alive until at least 2027-01-26: the hosting project, its Redis store and the Pages mirror. Public arrivals expire 48 h after the last ingest, so after that judges see the labelled replay;
  - every merge to main redeploys the judged page; after S20, merge nothing that touches ground/ or console/, or turn off automatic production deploys, until judging ends (operator).
- [ ] 4. **Reload:** a private-window reload shows the final texts, and the Final Project link opens `https://habitat-health-monitor.vercel.app/`.
- [ ] 5. **Commit and tag:**
  - `git add docs/submission/checklist.md && git commit -m "docs(submission): final submission"`
  - then `git tag submission-2026-11-15`.

**Final submitted at:** ____ (time, initials)

**Acceptance:** the submitted page matches the repo text, and it was submitted by 22:00.
