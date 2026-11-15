# 29-second demo video: script (S16)

Question answered: "a visual tool that helps astronauts assess their own health during space missions and provides guidance on treatments and health improvements" (the challenge statement, published 2026-10-28).

The title card (0.0–1.6 s) states it: deck slide 1, "Habitat Health Monitor. Helps astronauts assess their own health during space missions."

## Audio and AI use

- **Narration:** an AI-generated voice (ElevenLabs, `eleven_multilingual_v2`, the stock library voice "Ryan – American Documentary Narrator") reads the team's own script. It was sped up 1.08× and loudness-normalised in the edit. It is the only audio track: there is no microphone or room audio (R8). The end card says "Narration: AI-generated voice (ElevenLabs)."
- **AI video:** shot 8a is a 1-second clip animated from the team's AI illustration with a Gemini Veo model. It is labelled "AI-generated video" on screen and has no audio.
- **Captions:** English captions are burnt in and repeat the narration. `subtitles.en.srt` has the same cues.
- Full disclosure: `docs/AI_DISCLOSURE.md`.

## Shots (final cut, 29.0 s)

| Time (s) | Shot | Picture | Caption (= narration) | Lower third |
|---|---|---|---|---|
| 0.0–1.6 | 1 | Deck slide 1 (title) | Habitat Health Monitor. | — |
| 1.6–4.3 | 2 | Split: the lift with the sealed tilt pod on the weight, and the camera page following the right wrist | A camera tracks each lift on the bench, | — |
| 4.3–7.7 | 3 | Camera page result table: work per rep in joules | and turns every rep into work, in joules. | Gravity configured: Earth, Moon or Mars |
| 7.7–11.3 | 4 | Desk View of the bench: the Uno with the temperature and humidity sensor and the buzzer, and the tilt node | Sensors reach the hub over USB and Wi-Fi. | Uno → USB serial → hub · tilt node → Wi-Fi → MQTT → hub |
| 11.3–14.6 | 5 | The full bench circuit in Wokwi, with the hub chip | One hub judges every reading, offline. | Hub: Mosquitto, NASA-STD-3001 rules, console |
| 14.6–18.4 | 6 | Panel: food energy and training work side by side (not converted), body mass trend | The panel shows food energy, training work and mass. | — |
| 18.4–21.6 | 7 | Panel: cabin temperature and humidity, live, against the NASA limits | Cabin readings are judged against NASA's own limits. | — |
| 21.6–22.6 | 8a | AI video clip (labelled): the habitat and the Mars–Earth link | Earth sees it later, over a simulated Mars link. | — |
| 22.6–25.5 | 8b | Public ground page: the delay to Earth | (same caption) | — |
| 25.5–29.0 | 9 | End card: repo and public page links, "Educational prototype, not a medical device.", AI disclosure lines | An educational prototype, not a medical device. | — |

## Indicators that have data, with frame times

S16's `six_indicators_shown` check was amended on 15/11 (operator decision B3).

- **Work per rep in joules (camera):** 4.3–7.7 s. The lift itself is at 1.6–4.3 s.
- **Cabin temperature and relative humidity** (live bench sensor, judged against NASA-STD-3001): 18.4–21.6 s. The sensor appears on the bench at 7.7–11.3 s.
- **Food energy, training work and body mass:** 14.6–18.4 s. The card shows what was logged before the take, and says so when nothing was.
- **Link delay to Earth:** 21.6–25.5 s.
- **Not shown:**
  - Blood pressure, blood sugar, body temperature and mood are typed-in readings, and the bench has none.
  - Heart rate, SpO2 and sleep come from the team owner's ring and are kept off camera: the panel is recorded as Crew A (decision B1).

## Export

- **Size limit:** the exported `docs/video/final.mp4` stays out of git if it is over 10 MB.
- **Recorded after the 17:00 export:** its SHA-256 and its ffprobe duration, which must be ≤ 29.0 s, go here.
- **Rules:**
  - R5: no company name or logo in any shot or the audio.
  - R7: AI images and the AI clip carry visible labels.
  - R8: no minor's face, hands or voice.
