# Habitat panel — design (D43)

Status: approved by the team owner, 2026-11-15 ~12:37 (UTC−03:00). The approval covered the three premises, the
reduced energy-and-mass block, and the layout below. Deadline day: build by 15:30, PR by 16:00, video from 17:00.

## 1. Goal

The crew console gets one screen, the **habitat panel** (`#/panel`), and it becomes the default screen. It shows the
whole habitat in one frame that a judge can read in seconds in a 30-second video, with no live pitch. Its reading
order follows the frozen video flow:

lift → work per rep → energy and mass → cabin and vitals against NASA limits → Mars-to-Earth link delay.

The other screens stay in the navigation as the detail behind each card.

## 2. Premises (confirmed by the team owner)

- **Colours.** The team owner chose the colour values, and they are declared here under neutral habitat names
  (section 6). Only plain colour values are used. No logo, font, component code or other material from elsewhere.
- **Health data** means the hub's own data:
  - the ring import (D41: `hr`, `spo2`, `sleep_h`, a delayed sync shown with its true age);
  - manual entries (`body_mass` and the rest);
  - the food log (USDA FoodData Central values);
  - camera reps (`work_j`, `exercise`).
- **NASA data** is what the hub already serves:
  - DONKI space weather;
  - OSDR snapshot and effective-dose estimate;
  - ISS Live cabin telemetry;
  - NASA-STD-3001 limits in `data/thresholds.json`.

  The panel connects to these feeds and does not rebuild them.
- **Challenge.** "Create Health Monitoring Software for Astronauts on Space Missions". Judging is asynchronous, from
  a 30 s video and the public repo, and design weighs more than raw code.

## 3. Layout

The panel is designed for 1920×1080. It needs no scrolling on a desktop and stacks into one column below 900 px.

**Top bar.** It has the title and the banner "Educational prototype, not a medical device." It also holds four chips:
cabin sensors (live, with age), last camera set (with age), space weather (DONKI) and the link (one-way light time
and state). A 24-hour UTC clock sits at the end.

**Row 1, three cards:**

1. **Lift.** The latest camera set: exercise, load mass, rep count and one bar per rep for its work in joules. It is
   labelled "Camera estimate". With no set yet, it says to start a set on the camera page.
2. **Same lift, four places.** The latest rep's work is recomputed for each place's gravity, as
   `work_j × g_place / g_rep`, which is the same estimate scaled:
   - Earth uses 9.81 m/s²;
   - the Moon uses 1.62 m/s² (NASA NSSDC Moon Fact Sheet);
   - Mars uses 3.73 m/s² (NASA NSSDC Mars Fact Sheet);
   - the space station is in free fall, about 0 g. Its row says a free weight does almost no work there, so the
     crew trains on a resistance device.
3. **Food, training and body mass.** This is the reduced energy-and-mass block (section 5).

**Row 2, two cards:**

4. **Cabin and vitals against NASA limits.** These are compact lanes over the last 6 hours, reusing the Lanes
   model and its bands:
   - each lane shows its value, status word and short source;
   - an amber or red value gets one sentence naming both NASA bands, for example "Above the 20–25 °C comfort zone,
     inside the 18–27 °C health limit";
   - cabin temperature carries an "ISS now" chip from ISS Live when that value is fresh;
   - a small career-dose bar and the space-weather line come from the existing NASA models;
   - lanes with no data are not drawn. One line instead names what would fill them ("Not on this bench: heart
     rate, SpO2, sleep (ring import); …").
5. **Mars → Earth link.** An SVG strip runs from Mars to Earth, with the one-way light time, the demo time scale,
   the link state and the queue length:
   - each alert from the hub's WebSocket sends a packet along the line, taking the demo hold time
     (`light_time_s / time_scale`, 12 s with the default config);
   - the caption says the flight surgeon hears about an alert that much later and the crew acts first, on board;
   - when the link simulator is not running, the strip says so and uses the light time from the config file, as
     the guidance popup already does.

The panel has **no tilt visual.** tilt-1 is API-only by D39, and the bench node is intermittent.

## 4. Data flow

No hub change. The panel uses only existing GET endpoints and the existing WebSocket:

- `/api/status` and WebSocket frames for the board, nodes and alerts;
- `/api/sessions` and `/api/reps` for the lift and four-places cards;
- `/api/readings` for the lanes (6 h) and for `body_mass` (30 days);
- `/api/food/day` and `/api/exercise/day` for the energy-and-mass card;
- `/api/nasa/space-weather`, `/api/nasa/iss-cabin` and `/api/nasa/iss-reference` for the NASA feeds;
- `/api/link` and `link` frames for the link card.

Each card loads on its own and refreshes every 10 s, except the WebSocket-driven parts. A card that fails shows
"No data" and leaves the others alone. The panel never writes to the hub.

## 5. Energy and mass, reduced (honesty rules hold)

Section 1 of the earlier energy-and-mass design included an "intake − needs = balance" waterfall. That waterfall is
**left out**. It would need the words that `console/tests/honesty.ts` forbids, a J-to-food-energy conversion, and a
single estimated energy-need figure. The card keeps:

- **Weigh-ins.** Logged `body_mass` readings from the last 30 days, as dots:
  - with 3 or more weigh-ins on 3 or more different days, it draws the least-squares trend line;
  - the trend is extended 30 days as a dashed line, labelled "Logged trend extended, arithmetic only, not a
    prediction";
  - with fewer weigh-ins, the dots stay and a note says what the trend needs;
  - no limit band is drawn, because no NASA limit applies here.
- **Side by side, not converted.** The card shows "Food energy logged" next to "Training work, last 24 hours". It
  reuses the existing food-screen copy and formatters, so the unit and wording lint holds unchanged.
- **Today's exercises.** A checklist of the camera exercises done in the last 24 h: dumbbell curl, overhead press,
  row.

## 6. Palette (neutral names)

Values are declared once in `console/src/styles.css`. Colour never stands alone: every status shows its word next
to the colour.

| Variable | Value | Use |
|---|---|---|
| `--bg` | `#111113` | page |
| `--panel` | `#18181b` | cards |
| `--raised` | `#242428` | chips, inner boxes |
| `--line` | `#404045` | borders, grid |
| `--text` | `#fafafa` | main text |
| `--text-2` | `#c9c9cf` | secondary text |
| `--muted` | `#9f9fa8` | labels, footnotes |
| `--ok` | `#22c55e` | within the limit |
| `--watch` | `#fb923c` | watch |
| `--act` | `#f87171` | outside the limit |
| `--unknown` | `#a3a3a3` | no rule or no reading |
| `--accent` | `#a78bfa` | active navigation, focus |
| `--series` | `#60a5fa` | chart lines |
| `--watch-bg` | `#7c2d12` | banner, watch chips |
| `--act-bg` | `#7f1d1d` | flag chips |
| `--ok-bg` | `#064e3b` | ok chips |

On `--panel`, every text colour above is at least 6:1. The lowest is `--act` at 6.4:1, which passes WCAG AA. Hard-coded
colours in the lanes, NASA and banner code switch to these variables.

## 7. Fixes folded in from the 2026-11-15 bench validation

- **Status chip source.** It printed "NASA-STD-3001" twice. It now shows the source reference once.
- **Lanes time axis.** It is now a 24-hour clock marked "UTC", spanning the chosen window instead of the data
  extent.
- **"Watch" readable at a glance.** This is the two-band sentence of section 3, card 4.
- **Empty tiles.** The panel draws only what has data and names the missing sources in one line.

## 8. Code

- `console/src/screens.ts`: `panel` first. `screenFromHash` takes a fallback, which is `panel` in the console and
  `status` in the replay build, so the public replay still opens on its board.
- `console/src/views/panel.ts` lays out the frame. Each card lives in `console/src/views/panel/*.ts`.
- `console/src/model/panel/*.ts` holds pure functions with vitest tests: gravity rescaling, weigh-in trend,
  packet positions, the two-band sentence and the "not on this bench" line.
- `console/vite.config.ts` reads `HUB_URL` (default `http://127.0.0.1:8000`), so a demo hub on another port can
  be previewed.

## 9. Testing

- vitest, test-first for every model function. `npm run build` runs before the dist tests, and the copy lint runs
  on all new text (English only, sources named, the disclaimer unchanged).
- A palette test checks the contrast of the text and status colours on `--panel`, and checks that the console holds
  no company name.
- `pytest -q` is not needed, because the hub does not change.
- A screenshot comes from the live bench, read-only (GET only). Demo reps and weigh-ins go to a separate hub on port
  8010 with its own database. Nothing synthetic is posted to the live hub.

## 10. Cut order if time runs short

1. The packet animation becomes a static strip with the light time.
2. The 30-day extension is dropped, and dots and the trend line stay.
3. The four-places bars become a table.

## 11. Adjustments made while building (2026-11-15, for the team owner's review in the PR)

- **Radiation card.** The career-dose bar and the space-weather line moved out of card 4 into a small unnumbered
  "Radiation" card under the link card. Card 4 alone was taller than a 1080 px frame.
- **Screen title.** The heading "Habitat panel" is hidden on the panel, because the active navigation button already
  names it. That height lets the disclaimer footnote fit in the frame.
- **Guidance popup.** On the panel, a watch or act alert no longer opens the guidance popup by itself. The panel
  already shows the alert in place: an amber or red lane with its sentence, and a packet on the link. On every other
  screen the popup opens as before. This needs the team owner's yes.
- **Cabin chip age.** The cabin chip's age comes from the newest cabin reading. A node's `last_seen` is its
  connection time, which made the chip read "1 h ago" while readings arrived every 5 s.
- **Lane sources.** Lane sources on the panel are compact, with the kind label once plus every requirement ID, for
  example "NASA-STD-3001 [V2 6012] [V2 6013]". The full references stay on the Lanes screen.
