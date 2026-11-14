# Guidance review (S12)

Status: DRAFT for the operator's review. `data/guidance.json` is copied from this file character for character (`hub/tests/test_guidance_content.py::test_matches_review`). Food-rule rows are added by M10.

Wording rules: no diagnosis, no treatment doses, no named drugs. Escalation chain self, CMO, flight surgeon; food rules never reach the flight surgeon (D25). Where a threshold carries an operator-approved label it is repeated in the text: glucose rows "screening prompt, not a diagnosis; timing unknown" (the guidance texts say "screening prompt only; timing unknown", because the content tests forbid the word diagnosis in card text; the full label stays in the threshold note); blood pressure rows "single reading is a screening prompt" (team choice); cabin box rows refer to the bounding box of Figure 6.2-2. When `escalate_to` is `flight_surgeon` the console appends the current one-way light time from `GET /api/link`.

Risk links: HRP risk pages were opened on 2026-11-14 and checked against the statements in the "why" lines (179 headward fluid shift alters blood pressure; 176 constrained food supply; 99 isolation and confinement; 100 sleep loss lowers performance; 95 in-mission medical conditions; 96 radiation carcinogenesis). The "why" lines for heart rate, glucose, body temperature and sleep were softened to what those pages state.

## Entries

| id | do_now | tell | escalate_to | risk |
|---|---|---|---|---|
| default.ok | Within the reference band. No action needed. | — | self | — |
| default.unknown | This reading was not assessed (see the sensor flag). Check contact and measure again. | — | self | — |
| baseline_2sd.watch | This value is unusual for you: more than 2 SD from your own 30-day average. Measure again at rest. | Tell the CMO if repeat readings stay unusual. | self | — |
| hr_rest_high.watch | Sit and rest 5 minutes, then measure again. If you exercised in the last 10 minutes, rest first. | Tell the CMO if it stays above 90 bpm at rest, or with chest discomfort, dizziness or breathlessness. | self | Cardiovascular (HRP risk 179) |
| hr_rest_high.act | Stop activity, sit or lie down, and measure again with the chest strap or certified oximeter. | Tell the CMO now. The CMO decides whether to contact the flight surgeon. | cmo | Cardiovascular (HRP risk 179) |
| hr_rest_low.watch | Measure again at rest with a certified device. A low resting rate can be normal for trained crew. | Tell the CMO if you feel faint, dizzy or unusually tired. | self | Cardiovascular (HRP risk 179) |
| hr_rest_low.act | Sit or lie down and measure again with a certified device. | Tell the CMO now. | cmo | Cardiovascular (HRP risk 179) |
| spo2_low.watch | Warm your hand, keep still and re-measure with the certified oximeter. The sensor value is an estimate. | If the certified reading is 95 % or lower, tell the CMO and check the cabin pressure display. | self | In-mission medical conditions (HRP risk 95) |
| spo2_low.act | Keep still, stop activity if short of breath, and confirm with the certified oximeter now. | If confirmed, tell the CMO now; the CMO contacts the flight surgeon. | cmo | In-mission medical conditions (HRP risk 95) |
| body_temp_low.watch | Re-measure with the clinical thermometer. Add a layer and check the cabin temperature. | Tell the CMO if it stays below 36.1 °C or you are shivering. | self | In-mission medical conditions (HRP risk 95) |
| body_temp_low.act | Warm up now: add layers and move to a warmer module. Re-measure in 15 minutes. | Tell the CMO now. | cmo | In-mission medical conditions (HRP risk 95) |
| body_temp_high.watch | Rest away from exercise and heat, and re-measure with the clinical thermometer in 15 minutes. | Tell the CMO and answer the symptom check. | cmo | In-mission medical conditions (HRP risk 95) |
| bp_sys_high.watch | Sit quietly 5 minutes, arm supported at heart level, then take two readings 1 minute apart and enter both. Single reading is a screening prompt. | Tell the CMO at the next check-in if readings stay at 130/80 or above on two different days. | self | Cardiovascular (HRP risk 179) |
| bp_dia_high.watch | Sit quietly 5 minutes, arm supported at heart level, then take two readings 1 minute apart and enter both. Single reading is a screening prompt. | Tell the CMO at the next check-in if readings stay at 130/80 or above on two different days. | self | Cardiovascular (HRP risk 179) |
| bp_sys_high.act | Sit quietly and measure again after 5 minutes. Single reading is a screening prompt. | If still above 180/120, tell the CMO now; the CMO contacts the flight surgeon. | cmo | Cardiovascular (HRP risk 179) |
| bp_dia_high.act | Sit quietly and measure again after 5 minutes. Single reading is a screening prompt. | If still above 180/120, tell the CMO now; the CMO contacts the flight surgeon. | cmo | Cardiovascular (HRP risk 179) |
| bp_sys_low.watch | Sit or lie down and measure again. Stand up slowly. | Tell the CMO if you feel light-headed or faint. | self | Cardiovascular (HRP risk 179) |
| bp_sys_low.act | Lie down with your legs raised and measure again. | Tell the CMO now. | cmo | Cardiovascular (HRP risk 179) |
| glucose_low.watch | Follow the low-glucose step in the crew medical checklist and re-measure in 15 minutes. Screening prompt only. | Tell the CMO if it stays below 70 mg/dL. | self | Nutrition (HRP risk 176) |
| glucose_low.act | Stop activity, follow the low-glucose step in the crew medical checklist now, and do not exercise alone. | Tell the CMO now. | cmo | Nutrition (HRP risk 176) |
| glucose_high.watch | Note what and when you last ate, and measure again before your next meal. Screening prompt only; timing unknown. | Tell the CMO at the next check-in if repeat readings stay at 140 mg/dL or above. | self | Nutrition (HRP risk 176) |
| glucose_high.act | Wash and dry your hands and re-measure with a fresh strip. Screening prompt only. | If still 200 mg/dL or above, tell the CMO now. | cmo | Nutrition (HRP risk 176) |
| sleep_night.watch | Plan a sleep period of at least 7 hours tonight and dim the module lights before it. | Tell the CMO if short nights continue; they reduce alertness on critical tasks. | self | Sleep (HRP risk 100) |
| sleep_week.watch | Your 7-day average is under 7 hours. Protect the sleep period in tomorrow's schedule. | Review the schedule with the CMO. | cmo | Sleep (HRP risk 100) |
| mood_self.watch | Take a short break and talk with a crewmate you trust. | If low mood continues or affects your work, tell the CMO; private time with ground support can be requested. | self | Behavioral health (HRP risk 99) |
| mood_7d.watch | Mood has been low for a week. Talk with a crewmate or request private time with ground support. | Tell the CMO at the next check-in. | cmo | Behavioral health (HRP risk 99) |
| co2_1h.act | Check the CO2 scrubber status and the fans, and move to a module with better airflow. | Tell the CMO and answer the headache check. | cmo | OCHMO-TB-004 Carbon Dioxide |
| co2_7d.watch | The 7-day CO2 average is above 2.5 mmHg, where headache reports rise. Check ventilation. | Tell the CMO at the next check-in; report headaches in the symptom check. | self | OCHMO-TB-004 Carbon Dioxide |
| cabin_health_box_temp.act | The cabin temperature is outside the bounding box of NASA's crew health limits. Check the thermal control setpoint and fans. | Tell the CMO. | cmo | NASA-STD-3001 Vol 2 Rev F |
| cabin_health_box_rh.act | The cabin humidity is outside NASA's crew health limits. Check the humidity control and fans. | Tell the CMO. | cmo | NASA-STD-3001 Vol 2 Rev F |
| cabin_performance_temp.watch | The temperature is outside the zone where crew perform best. Adjust the setpoint and check the fans. | — | self | NASA-STD-3001 Vol 2 Rev F |
| cabin_performance_rh.watch | The humidity is outside the zone where crew perform best. Check the humidity control. | — | self | NASA-STD-3001 Vol 2 Rev F |
| lux_general.watch | Work-surface light is below 350 lx. Turn up the work lights while awake. | — | self | NASA-STD-3001 Vol 2 Rev F |
| radiation_career.watch | Half of the career dose limit is used. No immediate action. | Review planned EVAs with the CMO at the next check-in. | self | Radiation carcinogenesis (HRP risk 96) |
| radiation_career.act | You are near the career dose limit. Avoid optional EVAs until reviewed. | Tell the CMO; the flight surgeon reviews remaining exposure. | flight_surgeon | Radiation carcinogenesis (HRP risk 96) |
| radiation_spe.watch | Space weather is elevated: a strong flare or geomagnetic storm in the last 24 hours. Check that the shelter route is clear. | Tell the CMO at the next check-in. | self | Radiation carcinogenesis (HRP risk 96) |
| radiation_spe.act | Solar particle event alert. Go to the designated shelter area and stay until the all-clear. | Acknowledge with your badge or the console button; the CMO informs the flight surgeon. | flight_surgeon | Radiation carcinogenesis (HRP risk 96) |
| default.hr | — | — | self | Cardiovascular (HRP risk 179) |
| default.bp_sys | — | — | self | Cardiovascular (HRP risk 179) |
| default.bp_dia | — | — | self | Cardiovascular (HRP risk 179) |
| default.glucose | — | — | self | Nutrition (HRP risk 176) |
| default.body_temp | — | — | self | In-mission medical conditions (HRP risk 95) |
| default.sleep_h | — | — | self | Sleep (HRP risk 100) |
| default.mood | — | — | self | Behavioral health (HRP risk 99) |

## Why this measurement (status info)

| id | why |
|---|---|
| default.hr | Heart rate at rest is a basic sign of how the heart is coping. Spaceflight changes the cardiovascular system, so a trend helps the CMO spot a problem early. |
| default.bp_sys | Fluids shift toward the head in space, which can change blood pressure. A regular reading shows a trend early, so the CMO can act first. |
| default.bp_dia | Fluids shift toward the head in space, which can change blood pressure. A regular reading shows a trend early, so the CMO can act first. |
| default.glucose | Glucose reflects how the body gets and uses fuel. Food supply in flight is constrained, so a trend can flag a nutrition problem early. |
| default.body_temp | Body temperature is a basic sign that something may be wrong. A steady rise or fall tells the CMO when to look closer. |
| default.sleep_h | Crews often sleep less in flight, and sleep loss lowers alertness and performance. Logging it lets the crew change the schedule early. |
| default.mood | Mood is an early sign of how the crew copes with isolation and confinement. A low trend is a prompt to talk and ask for support. |
