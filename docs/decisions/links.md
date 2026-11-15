# Public links (D24)

Every task reads these URLs from this file instead of using placeholders.

- Entry repository: https://github.com/alefnsc/habitat-health-monitor
- Pages site (judged public link): https://alefnsc.github.io/habitat-health-monitor/
- Prior-work library (declared, Apache-2.0): https://github.com/alefnsc/ground-truth pinned at commit 0940adab0ec33dd5127d7efdacfbc6744a31e4d6 (merge of its PR #4)
- Wokwi twin of the UNO I/O board (D40; Arduino Uno, same sketch as `firmware/exercise-uno` plus `wokwi_twin.h`; DHT22 stand-in for the DHT11, buzzer; simulated parts labelled): https://wokwi.com/projects/480675272836723713
- Wokwi twin of the tilt-1 node (D40; ESP32 stand-in for the NodeMCU, same sketch as `firmware/tilt-esp8266` in serial-only mode; slide switch stand-in for the KY-017). This link held the vitals node twin until D40: https://wokwi.com/projects/480680478751478785
- Both twins were saved in place on 2026-11-14 (D40). Both were re-saved as bench wiring maps. The UNO twin's files match commit ffd1a0c, the tilt twin's match e1983a2 (200 ms debounce), and the projects are titled "UNO I/O board twin" and "tilt-1 node twin".
- Wokwi project of the whole bench circuit (D40; UNO block runs `firmware/exercise-uno`, tilt-1 node and Raspberry Pi 3 hub drawn; `firmware/wokwi/full-bench/`), saved 2026-11-15: https://wokwi.com/projects/480768002795017217
