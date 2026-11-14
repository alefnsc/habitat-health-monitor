# Nutrition: what is and is not validated

(Section text for `docs/validation.md`, held here until S creates that file.)

- Nutrient values are database values for generic foods (USDA FoodData Central), not measurements of the served item.
- Portions are the catalogue's serving sizes, not weighed amounts.
- There is no paired-measurement validation for intake.
- The only checks are: arithmetic tests of the meal sums and 24 h totals; a script (`tools/food/check_against_bulk.py`) that diffs the catalogue against the FDC bulk files; and a hand spot-check against the FDC website (`docs/food-spot-check.md`, pending).
- Alerts fire only when a meal is logged. A floor breached later in the day shows in the console preview but raises no alert until the next logged meal.
- Floors are judged only after 20 h of logging.
- The NASA values are population references, not personal targets. The seven food rules were reviewed against the NASA documents (M1) and approved by the operator; sodium, iron, fluid and calcium cite JSC-67378 (a program document, source kind `nasa_doc`), vitamin D cites NASA-STD-3001. The sodium watch band is a historical operating band, and iron has no act band.
- The nutrition feature is not clinically validated and is not medical advice or a diet tool.
