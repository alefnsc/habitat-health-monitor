# Validation

## Offline check

Dry run, Sat 2026-11-14 (C agent). The uplink was not physically unplugged and no camera was attached, so the
hotspot and camera-set parts of the acceptance still have to be done by a person.

- Static scan: the built `console/dist` and `camera/dist` contain no host outside the fixed lists in
  `console/tests/offline.test.ts` and `camera/tests/offline.test.ts`. No web font, no external script or stylesheet.
  A planted external script tag made the camera test fail, then it was removed.
- Bench check 1 (dry run): hub on localhost:8000 serving `/` and `/camera/`. Every console screen opened
  (status, entry, history, exercise, food, nasa, prompts, body). The browser's resource list held one origin only,
  `http://localhost:8000`, for the console and for the camera page. Exercise showed "HTTP 404" (sessions routes not on the
  hub yet) and NASA showed "NASA data not available on this hub".
- Bench check 2 (dry run): hub stopped for about 10 s. The "Hub connection lost" banner appeared within 8 s. After the hub
  restarted the banner cleared and the board refilled without a reload.
- Not yet done: camera preview and a camera set with the uplink off; re-check at the 16:00 freeze.
