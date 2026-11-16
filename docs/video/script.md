# 29-second demo video: script (S16)

Question answered: "a visual tool that helps astronauts assess their own health during space missions and provides guidance on treatments and health improvements" (the challenge statement, published 2026-10-28).

The title card (0.0–1.6 s) states it: deck slide 1, "Habitat Health Monitor. Helps astronauts assess their own health during space missions."

## Audio and AI use

- **Narration:** an AI-generated voice (ElevenLabs, `eleven_turbo_v2_5`, the stock library voice "Ryan – American Documentary Narrator") reads the team's own script (version B, v3 cut). Pauses were trimmed and the audio was sped up 1.343× (+34 %, pitch kept) so each line fits under its own shot; loudness was normalised in the edit. It is the only audio track: there is no microphone or room audio (R8). The end card says "Narration: AI-generated voice (ElevenLabs)." The file's `comment` and `description` metadata say the same.
- **AI images:** the title slide's illustration carries an "AI-generated illustration" badge.
- **AI video:** shot 8a is a 1-second clip animated from the team's AI illustration with a Gemini Veo model. It is labelled "AI-generated video" on screen (a top-right badge in v3) and has no audio.
- **Captions:** English captions are burnt in and repeat the narration. `subtitles.en.srt` has the same cues.
- Full disclosure: `docs/AI_DISCLOSURE.md`.

## Shots (final cut v3, 29.0 s)

Synthetic data: no camera set was recorded on the live hub on 15/11, so the lift, work and food/mass cards in v3 come from a scratch hub seeded with one simulated set (crew A, 5 kg, 8 reps), 3 meals and 7 weigh-ins. Every frame that shows them carries a "Simulated set" badge.

| Time (s) | Shot | Picture | Caption (= narration) | Lower third / badge |
|---|---|---|---|---|
| 0.00–1.47 | 1 | Deck slide 1 (title) | Habitat Health Monitor. | AI-generated illustration |
| 1.47–3.50 | 2 | Split: a real lift on the bench tray (hand and forearm, no face), and the panel's Lift card (8 reps, 137 J) | A camera tracks every lift on the bench | Simulated set |
| 3.50–6.03 | 3 | Panel card "Same lift, four places": work per rep at Earth, Moon, Mars and station gravity | and converts each rep into work, in joules. | Simulated set |
| 6.03–9.17 | 4a | Desk View of the bench: the UNO with the DHT11 and the buzzer | An Arduino UNO senses cabin air and sounds the alarm; | UNO → USB serial → hub · tilt-1 (NodeMCU) → Wi-Fi → MQTT → hub |
| 9.17–11.13 | 4b | Crop of the Desk View on the weight and the tilt node | a NodeMCU reports the weight's tilt. | (same) |
| 11.13–15.43 | 5 | Crop of the Desk View on the Raspberry Pi | A Raspberry Pi hub checks every reading against NASA limits, with no link to Earth. | Hub: Mosquitto, NASA-STD-3001 rules, crew console. Runs on a Raspberry Pi 3 or a Mac. |
| 15.43–18.97 | 6 | Panel: food energy and training work side by side (not converted), body mass trend | The crew panel adds food energy, training work and body mass. | Simulated set, meals and weigh-ins |
| 18.97–22.27 | 7 | Panel: cabin temperature and humidity (real bench data) against the NASA limits | Cabin temperature and humidity are scored on NASA's own bands. | — |
| 22.27–23.27 | 8a | AI video clip: the habitat on Mars | Mission control sees it all twelve minutes later, over a simulated Mars link. | AI-generated video |
| 23.27–26.33 | 8b | Public ground page: the 12-minute one-way delay | (same caption) | — |
| 26.33–29.00 | 9 | End card: repo and public page links, "Educational prototype, not a medical device.", AI disclosure lines | An educational prototype, not a medical device. | Also AI-generated: one 1-second video clip (Veo), labelled on screen. |

## Indicators that have data, with frame times

S16's `six_indicators_shown` check was amended on 15/11 (operator decision B3).

- **Work per rep in joules (camera, simulated set):** 3.50–6.03 s. A real lift is at 1.47–3.50 s.
- **Cabin temperature and relative humidity** (live bench sensor, judged against NASA-STD-3001): 18.97–22.27 s. The sensor appears on the bench at 6.03–9.17 s.
- **Food energy, training work and body mass (simulated meals and weigh-ins):** 15.43–18.97 s.
- **Link delay to Earth:** 22.27–26.33 s.
- **Not shown:**
  - Blood pressure, blood sugar, body temperature and mood are typed-in readings, and the bench has none.
  - Heart rate, SpO2 and sleep come from the team owner's ring and are kept off camera: the panel is recorded as Crew A (decision B1).

## Export

- **Size limit:** the exported `docs/video/final.mp4` stays out of git if it is over 10 MB.
- **Final export v3 (15/11, 22:49), replaces v2 at the same address:**
  - **File:** `video-2026-11-15/out/final-29s-v3.mp4`, hosted with the public pages as `ground/public/video/habitat-health-monitor-29s.mp4`. 1920x1080, 30 fps, H.264 High yuv420p with one AAC track (the narration). 9,327,054 bytes.
  - **SHA-256:** `a1973183ee01e0ae8e1f01cf9b335e3c9dd766b2b1703617e41fd543d7d91e62`.
  - **ffprobe duration:** 29.000000 s, within the 29.0 s limit.
  - **What changed from v2:** narration version B (names the UNO, the NodeMCU and the Raspberry Pi); the lift, work and food/mass cards show a labelled simulated set instead of empty cards; close-ups of the tilt node and the Pi replace the Wokwi shot; AI badges on the title illustration and the Veo clip.
  - **Still true:** no set was counted on camera on 15/11; the joules lines are illustrated by the simulated set, and say so on screen.
- **Previous export v2 (15/11, about 22:05):** SHA-256 `897ae381647cbd910b4359d32d27037a8378b1207c3729c2a539c6008ed4cfd3`, 6,040,942 bytes.
- **Rules:**
  - R5: no company name or logo in any shot or the audio.
  - R7: AI images and the AI clip carry visible labels.
  - R8: no minor's face, hands or voice.
