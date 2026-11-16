# AI disclosure

The team made the idea and every design decision: what to monitor, which sources to trust, what the crew is told, the hardware, and what to cut. AI assistants helped us write and check the work. Nothing was accepted without review.

## Tools

- Claude Code (Anthropic), run in the team's own development environment. The commit trailers name the models used: Claude Opus 5.5, Claude Sonnet 5.5, Claude Haiku 5.5 and, on one commit, Claude Fable 5.1.
- An image tool run by a team member, using a Gemini image model (Google), generated the background art for two presentation images (see "Generated media").
- ElevenLabs (text-to-speech, model `eleven_turbo_v2_5` for the final v3 cut; `eleven_multilingual_v2` for earlier cuts) read the team's own script to make the English narration of the 29-second video, using a stock library voice. One 1-second AI video clip is used: the team's AI illustration animated with a Gemini Veo model through an internal media tool, labelled "AI-generated video" on screen, with its audio removed.

## What each tool did

- Planning and research: drafts of the plan and the spec, and a fact-check of the NASA numbers, endpoints and sensor options, which the team read and amended.
- Code: most of the hub, tests, console, simulator and analysis code was written by Claude agents working on separate branches from the team's written plan, each task test-first.
- Drafts: threshold tables with citations (document, requirement ID, page, URL), guidance texts, validation protocol, safety checklist, data-source notes and submission text were drafted by an agent.
- Every NASA number was re-read in the primary PDF by the agent and cited with page and requirement ID in `docs/thresholds-review.md`. Clinical bands are labelled "not NASA-published".
- Images:
  - Claude agents wrote the image prompts.
  - They checked every number shown against NASA sources, listed in `docs/img/image-facts.md`.
  - They added the labels, panels and watermarks with a script.
  - A separate agent reviewed each image for people, logos and wrong numbers.
  - The operator chose which images to use.
- Narration: the team wrote the 29-second script, and ElevenLabs only turned it into speech. In the final cut the pauses were trimmed and the audio was sped up 34 % (pitch kept), and its loudness normalised in the edit. No real person's voice was cloned.

## Human review

- The operator approved each threshold table before it was encoded into `data/thresholds.json`, and the approved decisions are recorded in `docs/thresholds-review.md`.
- Team members run every hardware step, bench measurement and validation session, and sign the safety checklist (`docs/safety-checklist.md`).
- Team members write nothing into the validation results except what the hub recorded, and results are reported against targets declared in advance.
- Team members read the project page, the README and this file before submission.

## Generated media

Two presentation images are AI-generated illustrations.

- **How the art was made:**
  - It came from an image tool run by a team member, using a Gemini image model, prompted in a flat cartoon style with no people, no text, no logos and no NASA marks.
  - The art was generated without any lettering.
  - Every label, number and caption was added afterwards by script.
  - Every number is cited in `docs/img/image-facts.md`.
- **What they are:**
  - Concept art, not photographs. The habitat, station and bases shown are invented designs.
  - The console has no ISS, Moon or Mars mode; the comparison image only shows which limits stay the same and which conditions change.
  - Each carries a visible "AI-generated" watermark.

The images:

- `docs/img/habitat-illustration.png`
  - Generated: the art, a flat cartoon cutaway of a surface habitat module with bunks, a galley, an exercise room and a desk corner. The galley shelf holds a hub board, an I/O board, one sensor and a buzzer. The exercise room has a rig with a sealed pod, a small board and AA cells on the weights, and a wall camera. The desk corner has a ring on a charging puck. It has no people and no text.
  - Added by the team: the callouts, footnotes and watermark. The team also painted out a second sensor module that the model drew but the circuit does not have.
- `docs/img/same-sensors-three-places.png`
  - Generated: three pieces of art (an invented space station in orbit, a Moon base and a Mars base, each a flat cartoon with no people and no text).
  - Added by the team: the composite layout, the comparison text and numbers from cited NASA sources, and the watermark.
- `docs/img/console-status.png` is not AI. It is a real screenshot of the team's console replaying a recorded synthetic session, labelled "Real screenshot".

The 29-second video's narration is an AI-generated voice (ElevenLabs, a stock library voice) reading the team's script. No person's voice is cloned, and the video contains no microphone or room audio. One 1-second AI video clip (Gemini Veo, animated from the team's AI illustration, labelled "AI-generated video" on screen, audio removed) is used, at 22.3–23.3 s in the final cut. No image shows a person, a NASA logo or a mission identifier.

## Commit trailers

Every commit made with AI assistance ends with a trailer naming the assistant, for example `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. On 2026-11-16 at about 00:10 BRT, all 245 non-merge commits on `main` carry it; the other 58 commits are GitHub merge commits, which carry no trailer. The trailers can be listed with `git log --format=%B | grep Co-Authored-By`.

## Short version for the form ("Use of Super Intelligence (SI)")

We used Claude Code (Anthropic) to plan, research, write code and tests, and draft documents. The team defined the idea and all design decisions, approved every threshold and wording choice, ran all hardware work and validation sessions, and reviewed the outputs. All AI-assisted commits carry a Co-Authored-By trailer. Two presentation images are AI-generated illustrations, made with an image tool using a Gemini image model, and carry a visible "AI-generated" watermark; the 29-second video's narration is an AI-generated voice (ElevenLabs), and one 1-second clip is AI-generated video, labelled on screen. Details: `docs/AI_DISCLOSURE.md`.
