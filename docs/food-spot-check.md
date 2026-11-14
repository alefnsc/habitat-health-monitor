# Food catalogue spot-check against the FDC website (M12)

STATUS: TO BE DONE BY HAND. The catalogue column is filled by the generator. The "FDC website" column must be read by a person on https://fdc.nal.usda.gov/ (search the FDC id, open Nutrients, per 100 g) and then marked "equal" or given the difference. No value below has been compared yet, so none is claimed as equal.

The script `tools/food/check_against_bulk.py` already confirms the catalogue equals the bulk CSV files ("all equal (31 items)"); this page checks the bulk files against the website a person sees.


## white-rice-dry (FDC 169756, sr_legacy; Rice, white, long-grain, regular, raw, unenriched)

| nutrient (per 100 g) | catalogue | FDC website | result |
|---|---|---|---|
| kcal | 365.0 |  |  |
| protein_g | 7.13 |  |  |
| carb_g | 79.95 |  |  |
| fat_g | 0.66 |  |  |
| sodium_mg | 5.0 |  |  |
| potassium_mg | 115.0 |  |  |
| calcium_mg | 28.0 |  |  |
| iron_mg | 0.8 |  |  |
| vitd_ug | 0.0 |  |  |

## salmon-pink-canned (FDC 175175, sr_legacy; Fish, salmon, pink, canned, drained solids)

| nutrient (per 100 g) | catalogue | FDC website | result |
|---|---|---|---|
| kcal | 138.0 |  |  |
| protein_g | 23.1 |  |  |
| carb_g | 0.0 |  |  |
| fat_g | 5.02 |  |  |
| sodium_mg | 381.0 |  |  |
| potassium_mg | 333.0 |  |  |
| calcium_mg | 283.0 |  |  |
| iron_mg | 0.77 |  |  |
| vitd_ug | 14.5 |  |  |

## orange-juice-canned (FDC 169099, sr_legacy; Orange juice, canned, unsweetened)

| nutrient (per 100 g) | catalogue | FDC website | result |
|---|---|---|---|
| kcal | 47.0 |  |  |
| protein_g | 0.68 |  |  |
| carb_g | 11.01 |  |  |
| fat_g | 0.15 |  |  |
| sodium_mg | 4.0 |  |  |
| potassium_mg | 184.0 |  |  |
| calcium_mg | 10.0 |  |  |
| iron_mg | 0.1 |  |  |
| vitd_ug | 0.0 |  |  |
