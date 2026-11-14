# M2 draft: shelf-stable item list for the food catalogue

Status: DRAFT for operator review. Source of the ids: USDA FoodData Central bulk download, SR Legacy (April 2018) CSV, https://fdc.nal.usda.gov/download-datasets/ (public domain, CC0 1.0). Machine-readable version: `data/food/items.csv` (the input of M5).

Scope statement (for `docs/food-items.md` later): Generic foods in the style of long-shelf-life space food. These are not NASA menu items, and NASA publishes no nutrient table for individual flown items (none was found).

## Method and checks

- 31 items, all from the SR Legacy dataset (`sr_legacy`). No Branded records. The FDC Foundation CSV bundle that was downloaded did not include the food and nutrient tables, so Foundation was not used; every id below was read from SR Legacy.
- Every item is a generic food kept without refrigeration (dry, canned, dried or shelf-stable). The reason is in the `note` column of the CSV.
- Names are generic wording. The published FDC description is shown below as given, so M5 can copy it; none of the chosen records carries a brand name.
- Drinks and the milk powder carry a fluid volume (1 cup = 240 mL, tea 8 fl oz = 237 mL, team-chosen conventions). Solid foods carry 0 with "solid food, drinking fluid not counted".
- Vitamin D is null in the catalogue where FDC does not report it; the numbers below are FDC values per 100 g, "null" meaning not reported.

Mix check (M2 `mix`): drinks or powders with fluid above 0: 5 (milk powder, orange juice, apple juice, almond milk, instant tea). Sodium below 100 mg per 100 g: 19 items. Iron below 2 mg per 100 g: 17 items. `item_count` 31 is inside 28 to 32.

Open points for the operator:
1. Dry milk powder and instant tea are listed as the mixed drink, with nutrients per serving of the mixed drink (tea) or per powder weight (milk). The milk serving is 30 g of powder, and its fluid is the 240 mL it is mixed to.
2. Popcorn, tortilla and crispbread are the most "ordinary pantry" items. Drop them if you want the list closer to a flown menu.
3. Unsalted nuts and low-sodium beans are chosen on purpose so a seed day can stay inside the sodium references.

## Items (FDC values per 100 g)

| id | FDC id | data type | FDC description (as published, shortened) | category | serving | kcal | sodium mg | iron mg | vitamin D µg | fluid mL/serving |
|---|---|---|---|---|---|---|---|---|---|---|
| `white-rice-dry` | 169756 | sr_legacy | Rice, white, long-grain, regular, raw, unenriched | grain | 45 g dry (about 1/4 cup) | 365 | 5 | 0.8 | 0 | 0 |
| `rolled-oats-dry` | 173904 | sr_legacy | Cereals, oats, regular and quick, not fortified, dry | grain | 1/3 cup dry | 379 | 6 | 4.25 | 0 | 0 |
| `pasta-dry` | 168927 | sr_legacy | Pasta, dry, unenriched | grain | 2 oz dry | 371 | 6 | 1.3 | 0 | 0 |
| `saltine-crackers` | 172746 | sr_legacy | Crackers, saltines (includes oyster, soda, soup) | grain | 5 crackers | 418 | 941 | 5.57 | 0 | 0 |
| `rye-crispbread` | 172739 | sr_legacy | Crackers, crispbread, rye | grain | 1 triple wafer | 366 | 410 | 2.43 | 0 | 0 |
| `popcorn-air-popped` | 167959 | sr_legacy | Snacks, popcorn, air-popped | grain | 1 oz | 387 | 8 | 3.19 | 0 | 0 |
| `flour-tortilla-shelf-stable` | 167535 | sr_legacy | Tortillas, ready-to-bake or -fry, flour, shelf stable | grain | 1 tortilla | 297 | 742 | 3.32 | 0 | 0 |
| `almonds-raw` | 170567 | sr_legacy | Nuts, almonds | nuts_seeds | 1 oz (23 kernels) | 579 | 1 | 3.71 | 0 | 0 |
| `walnuts-english` | 170187 | sr_legacy | Nuts, walnuts, english | nuts_seeds | 1 oz (14 halves) | 654 | 2 | 2.91 | 0 | 0 |
| `peanuts-dry-roasted-unsalted` | 173806 | sr_legacy | Peanuts, all types, dry-roasted, without salt | nuts_seeds | 1 oz | 587 | 6 | 1.58 | 0 | 0 |
| `cashews-dry-roasted-unsalted` | 170571 | sr_legacy | Nuts, cashew nuts, dry roasted, without salt added | nuts_seeds | 1 oz | 574 | 16 | 6 | 0 | 0 |
| `peanut-butter-smooth` | 174294 | sr_legacy | Peanut Butter, smooth (Includes foods for USDA's Food Distri | nuts_seeds | 2 tbsp | 588 | 476 | 2.16 | 0 | 0 |
| `raisins-dark` | 168165 | sr_legacy | Raisins, dark, seedless (Includes foods for USDA's Food Dist | dried_fruit | 1 small box (1.5 oz) | 299 | 26 | 1.79 | 0 | 0 |
| `apricots-dried` | 173941 | sr_legacy | Apricots, dried, sulfured, uncooked | dried_fruit | 40 g (about 11 halves) | 241 | 10 | 2.66 | 0 | 0 |
| `dates-medjool` | 168191 | sr_legacy | Dates, medjool | dried_fruit | 2 pitted dates | 277 | 1 | 0.9 | 0 | 0 |
| `prunes-dried` | 168162 | sr_legacy | Plums, dried (prunes), uncooked | dried_fruit | 4 pitted prunes | 240 | 2 | 0.93 | 0 | 0 |
| `cranberries-dried-sweetened` | 171723 | sr_legacy | Cranberries, dried, sweetened (Includes foods for USDA's Foo | dried_fruit | 1/4 cup | 308 | 5 | 0.39 | 0 | 0 |
| `tuna-light-canned-water` | 173709 | sr_legacy | Fish, tuna, light, canned in water, drained solids (Includes | canned_protein | 3 oz drained | 86 | 247 | 1.63 | 1.2 | 0 |
| `salmon-pink-canned` | 175175 | sr_legacy | Fish, salmon, pink, canned, drained solids | canned_protein | 3 oz drained | 138 | 381 | 0.77 | 14.5 | 0 |
| `sardines-canned-oil` | 175139 | sr_legacy | Fish, sardine, Atlantic, canned in oil, drained solids with  | canned_protein | 1 can (3.75 oz) | 208 | 307 | 2.92 | 4.8 | 0 |
| `chicken-canned` | 171110 | sr_legacy | Chicken, canned, no broth | canned_protein | 3 oz | 185 | 482 | 1.3 | 0.1 | 0 |
| `black-beans-canned-low-sodium` | 175238 | sr_legacy | Beans, black, mature seeds, canned, low sodium | legume | 1/2 cup | 91 | 138 | 1.9 | 0 | 0 |
| `chickpeas-canned` | 175206 | sr_legacy | Chickpeas (garbanzo beans, bengal gram), mature seeds, canne | legume | 1/2 cup | 88 | 278 | 1.23 | 0 | 0 |
| `lentils-dry` | 172420 | sr_legacy | Lentils, raw | legume | 1/4 cup dry | 352 | 6 | 6.51 | 0 | 0 |
| `granola-bar-hard-plain` | 167542 | sr_legacy | Snacks, granola bars, hard, plain | bar_snack | 1 bar | 471 | 294 | 2.95 | 0 | 0 |
| `fruit-bar-nonfat` | 168861 | sr_legacy | Snacks, granola bar, fruit-filled, nonfat | bar_snack | 1 bar | 342 | 16 | 4 | 0 | 0 |
| `milk-powder-nonfat-d` | 172195 | sr_legacy | Milk, dry, nonfat, regular, with added vitamin A and vitamin | shelf_dairy | 1/4 cup powder, mixed to 240 mL | 362 | 535 | 0.32 | 11 | 240 |
| `orange-juice-canned` | 169099 | sr_legacy | Orange juice, canned, unsweetened | beverage | 1 cup (240 mL) | 47 | 4 | 0.1 | 0 | 240 |
| `apple-juice-canned` | 173933 | sr_legacy | Apple juice, canned or bottled, unsweetened, without added a | beverage | 1 cup (240 mL) | 46 | 4 | 0.12 | 0 | 240 |
| `almond-milk-shelf-stable` | 174832 | sr_legacy | Beverages, almond milk, unsweetened, shelf stable | beverage | 1 cup (240 mL) | 15 | 72 | 0.28 | 1 | 240 |
| `instant-tea-prepared` | 174873 | sr_legacy | Beverages, tea, instant, unsweetened, prepared with water | beverage | 8 fl oz (237 mL) | 1 | 4 | 0.01 | 0 | 237 |
