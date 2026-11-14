# Pose model notice

`pose_landmarker_lite.task` is the MediaPipe Pose Landmarker "lite" model (float16, version 1), served by this page from
its own files.

| | |
|---|---|
| Source | https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task |
| Retrieved | 2026-10-09 |
| Size | 5,777,746 bytes |
| SHA-256 | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` (recorded in `pose_landmarker_lite.task.sha256`; `scripts/verify-model.mjs` checks it before every `dev` and `build`) |
| MD5 | `04a75ddf7c811ac7a1a4523266dd7d88`, equal to the ETag the server returned |
| Contents | a zip bundle with two entries: `pose_detector.tflite` (2,959,078 bytes) and `pose_landmarks_detector.tflite` (2,818,390 bytes) |

## Licence

The model card for BlazePose GHUM 3D (card date April 16, 2021;
https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf) states that the model is
"Licensed under Apache License, Version 2.0". The Pose Landmarker guide page states licences only for the page's content
(CC BY 4.0) and its code samples (Apache 2.0); the statement for the model comes from the model card.

## What the model card says about use

- Intended uses include fitness and repetition counting.
- Out of scope: multiple people in an image; people too far from the camera (further than 14 feet / 4 meters); the head
  not visible; applications requiring metric accurate depth; any form of surveillance or identity recognition.
- Ethical considerations: the model is not intended for human life-critical decisions, and its primary intended
  application is entertainment.
- When light, noise, motion or face overlapping degrade the input, expect lower quality and more "jittering".

## How this project uses it

One person, side-on to the camera, and only the 2D vertical position of one wrist. Depth is never used. The positions
feed load accounting (mechanical work and peak force of a lifting set), which is not a clinical measurement and not a
decision about anyone's health. Nothing about the result has been validated on real video.
