# S13 draft: project page summary and description

Final text for S18, updated 2026-11-15 to the D40 bench that the video shows. The operator submits; nothing is posted from here. Sensor validation was not run, so no validation number appears, and the text says so. Text is plain English with no company, product brand or shop name; devices are named by class. The page must not contain the third-party push host name of ISS Live (ISS Live is not built and is not mentioned).

## High-Level Project Summary

We built a crew health monitor for a habitat that keeps working when Earth cannot answer. On a real bench, a small board reads cabin temperature and humidity and sounds an alarm on command, a sealed tilt switch on the exercise weight checks the timing of each rep, and a camera turns every lift into work in joules at Earth, Moon or Mars gravity. Heart rate, SpO2 and sleep come from a crew member's own smart ring through a delayed cloud import. The crew types in the readings that need a certified device: blood pressure, blood sugar, body temperature and mood.

Each reading is judged against a stated source: NASA-STD-3001 for the cabin and radiation, and named clinical references, labelled "not NASA-published", for vital signs. The crew is told what to do now and whom to tell, from themselves to the crew medical officer to the flight surgeon. NASA DONKI space-weather events drive the radiation alert, and a simulated Mars link carries the data to a public ground page with light-time delay and blackouts.

It matters because one-way light time between Earth and Mars runs from about 4 to 22 minutes, so a crew must judge a health problem on its own first.

## Detailed Project Description

### What exactly does it do?

It reads sensors and typed-in measurements, assesses every value against a band, and shows the result on a crew console that works with no internet. Each status (ok, watch, act) comes with the source, the requirement ID, what to do now and whom to tell. Radiation, cabin air and food intake are tracked next to the six vital signs. A ground page shows what Earth would see after the link delay.

### How does it work?

An Arduino Uno with a temperature and humidity sensor and a buzzer talks to the hub over USB serial. A Wi-Fi board (ESP8266) with a sealed mercury tilt switch publishes over MQTT to Mosquitto on the hub. The hub, a laptop or a Raspberry Pi 3, stores every reading and assesses it, and keeps working with no link to Earth. The camera page runs pose tracking on the device and sends each rep's work to the hub; no video leaves the device. A link simulator adds light-time delay and blackouts before the data reach the public ground page. Rules live in a reviewed table; each row cites a document, page and requirement ID. The whole bench circuit can also be run in a public Wokwi simulation, where a custom chip stands in for the hub on the Uno's serial link.

### Which measurements can be done in space, and why

| Indicator | Measured how | Feasible in space because | Why measured | What prevents escalation | Source class | Band source | Needs crew or flight-surgeon attention when |
|---|---|---|---|---|---|---|---|
| Heart rate | Smart ring, imported by a delayed cloud sync | feasible in space because a ring is small, battery-powered and needs no consumables | Cardiovascular adaptation to weightlessness (HRP risk 179) | Rest and re-measure at once | Clinical reference | NEWS2 (RCP 2017), not NASA-published | Above 130 or below 41 beats per minute: tell the CMO |
| Blood pressure | Certified cuff, typed in | feasible in space because a cuff is small and runs on board | Fluids shift toward the head (HRP risk 179) | Sit, re-measure twice | Clinical reference | AHA/ACC 2025, team choice; single reading is a screening prompt | Above 180 systolic or 120 diastolic |
| Blood sugar | Glucometer, typed in | feasible in space because a glucometer is a handheld device | Food supply is constrained (HRP risk 176) | Note food and time, re-measure | Clinical reference | ADA 2026; screening prompt, not a diagnosis; timing unknown | Below 54 or at or above 200 |
| Body temperature | Clinical thermometer, typed in | feasible in space because thermometers are small and need no power | In-mission medical conditions (HRP risk 95) | Rest, re-measure | Clinical reference | NEWS2 (RCP 2017) | At or below 35.0 degrees C |
| Daily sleep hours | Self-report | feasible in space because it needs no hardware | Sleep loss lowers performance (HRP risk 100) | Protect the sleep period | Clinical reference | Watson et al. 2015 | A weekly average under 7 hours |
| Mood | Self-report, 1 to 5 | feasible in space because it needs no hardware | Isolation and confinement (HRP risk 99) | Talk with a crewmate | Team convention | Team convention, not clinical | A weekly average below 2.5 |

Cabin temperature and humidity are sensed on the bench. Heart rate, SpO2 and sleep are imported from the ring, labelled with their age. Blood pressure, blood sugar, body temperature and mood are typed in. The radiation alert uses recorded NASA DONKI events when the live feed is not available and says so on screen.

### Hazards and environments

The five NASA hazards of human spaceflight each map to indicators on the console:

- [Space radiation](https://www.nasa.gov/hrp/hazard-space-radiation/): space weather and the dose estimate.
- [Isolation and confinement](https://www.nasa.gov/hrp/hazard-isolation-and-confinement/): mood and sleep.
- [Distance from Earth](https://www.nasa.gov/hrp/hazard-distance-from-earth/): the link and every vital sign.
- [Altered gravity fields](https://www.nasa.gov/hrp/hazard-gravity-fields/): the exercise session's gravity setting.
- [Hostile, closed environments](https://www.nasa.gov/hrp/hazard-hostile-closed-environments/): CO2, temperature, humidity, light and fluid intake.

Nutrition is a supporting domain under the hostile closed environment hazard: food values are database values for generic foods, not measurements, and NASA reference values describe a population, not a personal target.

### What benefits does it have?

A crew sees, in one place, whether each reading is inside its band, why, and who to tell. The same screen works without any link, and Earth sees the same data later with the delay made visible.

### Scientific validity

Cabin and radiation limits show their NASA-STD-3001 requirement IDs (Vol 2 Rev F and Vol 1 Rev C). The CO2 line comes from the OCHMO technical brief TB-004. Vital-sign bands come from named clinical documents and are not NASA-published. The career dose gauge is an estimate (mission day times 0.5 mSv/day, an upper ISS rate from a NASA draft paper) and never converts measured absorbed dose. Sensor validation was not run, so no bias or agreement number is quoted. Hobby-sensor values are labelled estimates. The camera's work per rep is not validated against a load cell; it is an estimate from pose tracking and the entered mass.

### NASA data at the core

NASA-STD-3001, OCHMO-TB-004, NASA DONKI space-weather events, the OSDR Environmental Data Application (ISS cabin readings and absorbed dose from mission RR-6), the Human Research Roadmap risk pages and the JSC-67378 nutrition requirements are the basis of every band, alert and explanation.

### What tools, coding languages, hardware, or software did you use?

Python 3.12 (FastAPI), TypeScript, Arduino C++. An Arduino Uno with a temperature and humidity sensor and a passive buzzer; an ESP8266 board with a sealed mercury tilt switch; a laptop or Raspberry Pi 3 as the hub; a smart-ring import; a camera with an on-device pose model; Mosquitto for messaging; Wokwi for the simulated circuit. AI assistants and AI media tools were used and are disclosed in the repository (`docs/AI_DISCLOSURE.md`).

### Impact, creativity, relevance and presentation

Impact: a crew that cannot wait minutes for Earth gets a clear next step. Creativity: one rule table drives console, alerts and the ground page, and the link delay is simulated end to end. Relevance: it answers the challenge directly, with the indicators that have data and the guide's questions. Presentation: a public ground page with recorded data, a public Wokwi simulation of the bench, a 30-second video and three images (listed below).

### Limits

It is an educational prototype, not a medical device. It never diagnoses and gives no treatment doses. Hobby sensors are estimates. Rovers are not modelled. The link is simulated.

## Images

Three images: one real screenshot and two AI-generated illustrations, each marked as such on the image. Every number on them is cited in `docs/img/image-facts.md`.

1. `docs/img/console-status.png`
   - Caption: Crew console status board replaying a recorded synthetic session: heart rate and cabin sensors, each with its source and reference. Real screenshot; educational prototype, not a medical device.
   - Alt text: Dark console page titled Status board, with banners "Educational prototype, not a medical device" and "Replay of a recorded session, not live data".
     - Values shown: heart rate 61 bpm, skin temperature 33.5 °C, cabin CO2 1.01 mmHg (1,324 ppm), temperature 22.2 °C, humidity 45 %, pressure 1013.0 hPa and light 400 lx.
     - Blood pressure, glucose, body temperature, sleep, mood and SpO2 read "No reading yet".
2. `docs/img/habitat-illustration.png`
   - Caption: One habitat on the simplified circuit: an offline hub, one I/O board for cabin temperature and humidity, a camera that measures exercise work, and a sealed tilt witness. A ring supplies heart rate, SpO2 and sleep by a delayed import (built after this image was drawn; the image still says "planned"). AI-generated illustration.
   - Alt text: Flat cartoon cutaway of a cylindrical surface habitat with bunks, a galley, an exercise room and a desk corner, with no people.
     - Callouts read "Hub: logs and judges every reading, works offline", "I/O board on USB: cabin temperature and humidity, alarm", "Camera (computer vision): reps and work in joules", "Tilt node (sealed mercury switch, Wi-Fi board, AA cells): checks rep timing" and "Smart ring (team owner's own): heart rate, SpO2, sleep; import planned, not built yet".
     - Footnotes say "The hub works offline; the planned ring import would need the internet." and "Educational prototype, not a medical device. Hobby-sensor values are estimates."
     - A label reads "AI-generated illustration".
3. `docs/img/same-sensors-three-places.png`
   - Caption: Same sensors, three places: the cabin limits stay the same while gravity, distance to Earth and radiation change. AI-generated concept art; the console has no ISS, Moon or Mars mode.
   - Alt text: Comparison card titled "Same sensors, three places", with cartoon art of a space station, a Moon base and a Mars base side by side.
     - A box gives the shared cabin limits: CO2 at most 3 mmHg (1-hour mean) and 18-27 °C, both checked by the prototype, and 34.5-103 kPa total pressure as a NASA reference only.
     - Rows compare gravity, link or light time to Earth, radiation dose rate and outside air for each place.
     - A label reads "AI-generated art · concept only".
