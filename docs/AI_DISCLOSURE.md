# AI disclosure

> DRAFT for review by the hardware member and the operator (task S15). Facts marked [confirm] need a human check before submission. The commit count is refreshed at the pre-submit check.

The team made the idea and every design decision: what to monitor, which sources to trust, what the crew is told, the hardware, and what to cut. AI assistants helped us write and check the work. Nothing was accepted without review.

## Tools

- Claude Code (Anthropic), using Claude models, run in the team's own development environment. [confirm exact model names against the commit trailers]
- No AI image, video or voice generator was used so far [confirm at the pre-submit check].

## What each tool did

- Planning and research: drafts of the plan and the spec, and a fact-check of the NASA numbers, endpoints and sensor options, which the team read and amended.
- Code: most of the hub, tests, console, simulator and analysis code was written by Claude agents working on separate branches from the team's written plan, each task test-first.
- Drafts: threshold tables with citations (document, requirement ID, page, URL), guidance texts, validation protocol, safety checklist, data-source notes and submission text were drafted by an agent.
- Every NASA number was re-read in the primary PDF by the agent and cited with page and requirement ID in `docs/thresholds-review.md`. Clinical bands are labelled "not NASA-published".

## Human review

- The operator approved each threshold table before it was encoded into `data/thresholds.json`, and the approved decisions are recorded in `docs/thresholds-review.md`.
- Team members run every hardware step, bench measurement and validation session, and sign the safety checklist (`docs/safety-checklist.md`).
- Team members write nothing into the validation results except what the hub recorded, and results are reported against targets declared in advance.
- Team members read the project page, the README and this file before submission.

## Generated media

No AI-generated images, video or voice are used [confirm]. Any added later will carry a visible "AI-generated" watermark and will show no NASA logo or mission identifier.

## Commit trailers

Every commit made with AI assistance ends with a trailer naming the assistant, for example `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. At the time of writing, all commits on `main` carry it (67 of 67 on 2026-11-14 at about 11:00; refresh at S19). The trailers can be listed with `git log --format=%B | grep Co-Authored-By`.

## Short version for the form ("Use of Super Intelligence (SI)")

We used Claude Code (Anthropic) to plan, research, write code and tests, and draft documents. The team defined the idea and all design decisions, approved every threshold and wording choice, ran all hardware work and validation sessions, and reviewed the outputs. All AI-assisted commits carry a Co-Authored-By trailer. No AI-generated images, video or voice are used. Details: `docs/AI_DISCLOSURE.md`.
