"""Deterministic seed data generator for the Grocery Store SQLite database.

Populates:
- ~80 realistic grocery SKUs spanning produce, poultry, seafood, meats, plant proteins,
  dairy/eggs, grains/pasta (including certified GF), sauces/pantry (standard & GF/low-sodium),
  oils, nuts/seeds, and spices/herbs.
- 1:1 USDA-style nutritional_facts (per 100g/100ml) for every SKU.
- Store inventory (STORE-001) with aisle locations (including an out-of-stock SKU to test
  deterministic fallback/substitution).
- Fixture customer profiles including Malcom Munson (celiac disease, hypertension,
  Mediterranean preference, chicken > fish, dislikes eggplant).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Allow running directly as `uv run python data/seed.py`
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.db.database import DEFAULT_STORE_ID, get_connection, init_db  # noqa: E402

NOW_ISO = datetime.now(UTC).isoformat()

# Tuple layout for concise, readable catalog definition:
# (sku, name, canonical_ingredient, category, brand,
#  package_qty, package_unit, base_unit, grams_or_ml_per_package, unit_price_usd,
#  allergens, dietary_tags, is_pantry_staple,
#  serving_desc, serving_g, kcal, protein, carbs, fat, sat_fat, fiber, sugar, sodium_mg,
#  qty_on_hand, aisle)
CATALOG_ENTRIES: list[tuple[Any, ...]] = [
    # --- MEAT & POULTRY ---
    (
        "SKU-CHK-BRST-16OZ", "Organic Boneless Skinless Chicken Breast", "chicken_breast",
        "meat_poultry", "FreshValley", 1.0, "lb", "g", 453.59, 6.99,
        [], ["gluten_free", "low_sodium", "high_protein", "dairy_free"], 0,
        "4 oz (112g)", 112.0, 120, 22.5, 0.0, 2.6, 0.6, 0.0, 0.0, 45,
        32, "Meat Counter",
    ),
    (
        "SKU-CHK-THGH-16OZ", "Boneless Skinless Chicken Thighs", "chicken_thigh",
        "meat_poultry", "FreshValley", 1.0, "lb", "g", 453.59, 5.49,
        [], ["gluten_free", "low_sodium", "high_protein", "dairy_free"], 0,
        "4 oz (112g)", 112.0, 143, 19.7, 0.0, 6.7, 1.8, 0.0, 0.0, 68,
        24, "Meat Counter",
    ),
    (
        "SKU-TRKY-GRND-16OZ", "93% Lean Ground Turkey", "ground_turkey",
        "meat_poultry", "MeadowFarms", 1.0, "lb", "g", 453.59, 5.99,
        [], ["gluten_free", "low_sodium", "high_protein", "dairy_free"], 0,
        "4 oz (112g)", 112.0, 150, 19.6, 0.0, 7.6, 2.1, 0.0, 0.0, 65,
        18, "Meat Counter",
    ),
    (
        "SKU-BEEF-SRLN-16OZ", "Grass-Fed Beef Sirloin Strips", "beef_sirloin",
        "meat_poultry", "RanchReserve", 1.0, "lb", "g", 453.59, 9.99,
        [], ["gluten_free", "low_sodium", "high_protein", "dairy_free"], 0,
        "4 oz (112g)", 112.0, 162, 22.3, 0.0, 7.5, 2.9, 0.0, 0.0, 55,
        14, "Meat Counter",
    ),
    # --- SEAFOOD ---
    (
        "SKU-SLMN-FIL-12OZ", "Wild Alaskan Salmon Fillet", "salmon_fillet",
        "seafood", "PacificCatch", 12.0, "oz", "g", 340.19, 10.49,
        ["fish"], ["gluten_free", "low_sodium", "high_protein", "dairy_free", "pescatarian"], 0,
        "4 oz (113g)", 113.0, 182, 20.4, 0.0, 10.8, 1.9, 0.0, 0.0, 44,
        16, "Seafood Counter",
    ),
    (
        "SKU-SHMP-RAW-16OZ", "Wild Gulf Peeled Raw Shrimp", "shrimp",
        "seafood", "PacificCatch", 1.0, "lb", "g", 453.59, 11.99,
        ["shellfish"], ["gluten_free", "high_protein", "dairy_free", "pescatarian"], 0,
        "3 oz (85g)", 85.0, 85, 20.1, 0.2, 0.5, 0.1, 0.0, 0.0, 119,
        15, "Seafood Counter",
    ),
    # --- PLANT PROTEINS & LEGUMES ---
    (
        "SKU-TOFU-XFRM-14OZ", "Organic Extra-Firm Tofu", "tofu",
        "plant_protein", "SoyCraft", 14.0, "oz", "g", 396.89, 2.79,
        ["soy"], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "3 oz (85g)", 85.0, 94, 10.0, 2.3, 5.3, 0.8, 1.2, 0.5, 14,
        28, "Produce - Refrigerated",
    ),
    (
        "SKU-CHKP-LSOD-15OZ", "Organic No-Salt-Added Chickpeas", "chickpeas",
        "pantry", "GreenHarvest", 15.0, "oz", "g", 425.0, 1.69,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/2 cup (130g)", 130.0, 119, 6.2, 20.0, 1.9, 0.2, 5.4, 2.0, 12,
        40, "Aisle 3 - Canned Goods",
    ),
    (
        "SKU-BLKBN-LSOD-15OZ", "Organic No-Salt-Added Black Beans", "black_beans",
        "pantry", "GreenHarvest", 15.0, "oz", "g", 425.0, 1.59,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/2 cup (130g)", 130.0, 114, 7.6, 20.4, 0.5, 0.1, 7.5, 0.3, 15,
        36, "Aisle 3 - Canned Goods",
    ),
    (
        "SKU-LNTL-RED-16OZ", "Organic Red Split Lentils", "red_lentils",
        "grains_pasta", "EarthGrain", 16.0, "oz", "g", 453.59, 3.29,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/4 cup dry (45g)", 45.0, 352, 24.6, 63.4, 1.1, 0.2, 10.7, 2.0, 6,
        25, "Aisle 5 - Grains & Legumes",
    ),
    # --- PRODUCE ---
    (
        "SKU-PEP-BELL-RED-1CT", "Red Bell Pepper", "bell_pepper",
        "produce", "LocalGrowers", 1.0, "count", "g", 150.0, 1.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 medium pepper (150g)", 150.0, 31, 1.0, 6.0, 0.3, 0.1, 2.1, 4.2, 4,
        55, "Produce",
    ),
    (
        "SKU-PEP-BELL-GRN-1CT", "Green Bell Pepper", "green_bell_pepper",
        "produce", "LocalGrowers", 1.0, "count", "g", 140.0, 1.19,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 medium pepper (140g)", 140.0, 20, 0.9, 4.6, 0.2, 0.0, 1.7, 2.4, 3,
        42, "Produce",
    ),
    (
        "SKU-ZUCH-1CT", "Organic Green Zucchini", "zucchini",
        "produce", "LocalGrowers", 1.0, "count", "g", 200.0, 1.29,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 medium (200g)", 200.0, 17, 1.2, 3.1, 0.3, 0.1, 1.0, 2.5, 8,
        38, "Produce",
    ),
    (
        "SKU-EGGP-1CT", "Fresh Globe Eggplant", "eggplant",
        "produce", "LocalGrowers", 1.0, "count", "g", 450.0, 2.29,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 cup cubed (82g)", 82.0, 25, 1.0, 5.9, 0.2, 0.0, 3.0, 3.5, 2,
        20, "Produce",
    ),
    (
        "SKU-CUCM-ENG-1CT", "English Seedless Cucumber", "cucumber",
        "produce", "LocalGrowers", 1.0, "count", "g", 300.0, 1.79,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/2 cucumber (150g)", 150.0, 15, 0.7, 3.6, 0.1, 0.0, 0.5, 1.7, 2,
        44, "Produce",
    ),
    (
        "SKU-TOM-CHRY-10OZ", "Sweet Cherry Tomatoes", "cherry_tomatoes",
        "produce", "SunRipe", 10.0, "oz", "g", 283.5, 3.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 cup (149g)", 149.0, 18, 0.9, 3.9, 0.2, 0.0, 1.2, 2.6, 5,
        35, "Produce",
    ),
    (
        "SKU-TOM-ROMA-16OZ", "Fresh Roma Tomatoes", "tomato",
        "produce", "SunRipe", 1.0, "lb", "g", 453.59, 2.19,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 medium (62g)", 62.0, 18, 0.9, 3.9, 0.2, 0.0, 1.2, 2.6, 5,
        40, "Produce",
    ),
    (
        "SKU-ONION-RED-1CT", "Red Onion", "red_onion",
        "produce", "LocalGrowers", 1.0, "count", "g", 170.0, 0.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/2 medium (85g)", 85.0, 40, 1.1, 9.3, 0.1, 0.0, 1.7, 4.2, 4,
        60, "Produce",
    ),
    (
        "SKU-ONION-YEL-1CT", "Yellow Onion", "yellow_onion",
        "produce", "LocalGrowers", 1.0, "count", "g", 170.0, 0.89,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/2 medium (85g)", 85.0, 40, 1.1, 9.3, 0.1, 0.0, 1.7, 4.2, 4,
        65, "Produce",
    ),
    (
        "SKU-ONION-GRN-1BN", "Fresh Green Onions (Scallions)", "green_onion",
        "produce", "LocalGrowers", 1.0, "bunch", "g", 100.0, 1.29,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "2 stalks (30g)", 30.0, 32, 1.8, 7.3, 0.2, 0.0, 2.6, 2.3, 16,
        35, "Produce",
    ),
    (
        "SKU-GARLIC-1CT", "Fresh Garlic Bulb", "garlic",
        "produce", "LocalGrowers", 1.0, "count", "g", 55.0, 0.79,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 clove (3g)", 3.0, 149, 6.4, 33.1, 0.5, 0.1, 2.1, 1.0, 17,
        75, "Produce",
    ),
    (
        "SKU-GINGER-4OZ", "Fresh Ginger Root", "ginger",
        "produce", "LocalGrowers", 4.0, "oz", "g", 113.4, 1.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 tbsp grated (6g)", 6.0, 80, 1.8, 17.8, 0.8, 0.2, 2.0, 1.7, 13,
        30, "Produce",
    ),
    (
        "SKU-LEMON-1CT", "Fresh Lemon", "lemon",
        "produce", "CitrusGrove", 1.0, "count", "g", 85.0, 0.69,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 lemon (85g)", 85.0, 29, 1.1, 9.3, 0.3, 0.0, 2.8, 2.5, 2,
        80, "Produce",
    ),
    (
        "SKU-LIME-1CT", "Fresh Lime", "lime",
        "produce", "CitrusGrove", 1.0, "count", "g", 67.0, 0.59,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 lime (67g)", 67.0, 30, 0.7, 10.5, 0.2, 0.0, 2.8, 1.7, 2,
        65, "Produce",
    ),
    (
        "SKU-SPIN-BABY-5OZ", "Organic Baby Spinach", "spinach",
        "produce", "GreenLeaf", 5.0, "oz", "g", 141.75, 3.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "2 cups (60g)", 60.0, 23, 2.9, 3.6, 0.4, 0.1, 2.2, 0.4, 79,
        28, "Produce - Packaged Greens",
    ),
    (
        "SKU-BROC-CRWN-12OZ", "Fresh Broccoli Crowns", "broccoli",
        "produce", "LocalGrowers", 12.0, "oz", "g", 340.19, 2.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 cup florets (91g)", 91.0, 34, 2.8, 6.6, 0.4, 0.0, 2.6, 1.7, 33,
        34, "Produce",
    ),
    (
        "SKU-CARR-16OZ", "Organic Whole Carrots", "carrot",
        "produce", "LocalGrowers", 1.0, "lb", "g", 453.59, 1.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 medium (61g)", 61.0, 41, 0.9, 9.6, 0.2, 0.0, 2.8, 4.7, 69,
        45, "Produce",
    ),
    (
        "SKU-MUSH-CREM-8OZ", "Sliced Cremini Mushrooms", "mushrooms",
        "produce", "ValleyFungi", 8.0, "oz", "g", 226.8, 2.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 cup (70g)", 70.0, 22, 3.1, 3.3, 0.3, 0.0, 1.0, 2.0, 5,
        24, "Produce",
    ),
    (
        "SKU-AVOC-1CT", "Hass Avocado", "avocado",
        "produce", "LocalGrowers", 1.0, "count", "g", 150.0, 1.59,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/3 medium (50g)", 50.0, 160, 2.0, 8.5, 14.7, 2.1, 6.7, 0.7, 7,
        40, "Produce",
    ),
    (
        "SKU-HERB-PARS-1BN", "Fresh Flat-Leaf Parsley", "parsley",
        "produce", "HerbGarden", 1.0, "bunch", "g", 60.0, 1.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "2 tbsp chopped (8g)", 8.0, 36, 3.0, 6.3, 0.8, 0.1, 3.3, 0.9, 56,
        30, "Produce - Fresh Herbs",
    ),
    (
        "SKU-HERB-CIL-1BN", "Fresh Cilantro Bunch", "cilantro",
        "produce", "HerbGarden", 1.0, "bunch", "g", 60.0, 1.29,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "2 tbsp chopped (8g)", 8.0, 23, 2.1, 3.7, 0.5, 0.0, 2.8, 0.9, 46,
        32, "Produce - Fresh Herbs",
    ),
    (
        "SKU-HERB-DILL-1OZ", "Fresh Dill Sprigs", "dill",
        "produce", "HerbGarden", 1.0, "oz", "g", 28.35, 2.19,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 tbsp chopped (3g)", 3.0, 43, 3.5, 7.0, 1.1, 0.1, 2.1, 0.0, 61,
        22, "Produce - Fresh Herbs",
    ),
    (
        "SKU-HERB-BASIL-1OZ", "Fresh Sweet Basil", "basil",
        "produce", "HerbGarden", 1.0, "oz", "g", 28.35, 2.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "2 tbsp chopped (5g)", 5.0, 23, 3.2, 2.7, 0.6, 0.0, 1.6, 0.3, 4,
        26, "Produce - Fresh Herbs",
    ),
    (
        "SKU-OLIVE-KAL-6OZ", "Pitted Kalamata Olives (Reduced Sodium)", "kalamata_olives",
        "pantry", "AegeanSelect", 6.0, "oz", "g", 170.1, 4.49,
        [], ["gluten_free", "vegetarian", "vegan", "dairy_free"], 0,
        "5 olives (15g)", 15.0, 145, 1.0, 3.8, 15.3, 2.0, 3.3, 0.0, 620,
        22, "Aisle 2 - Mediterranean & Olives",
    ),
    # --- DAIRY & EGGS ---
    (
        "SKU-BUTR-UNSLT-8OZ", "Unsalted Sweet Cream Butter", "butter",
        "dairy", "CloverCreamery", 8.0, "oz", "g", 226.8, 3.99,
        ["dairy"], ["gluten_free", "low_sodium", "vegetarian"], 1,
        "1 tbsp (14g)", 14.0, 717, 0.9, 0.1, 81.1, 51.4, 0.0, 0.1, 11,
        35, "Dairy",
    ),
    (
        "SKU-YOG-GRK-16OZ", "Plain 2% Greek Yogurt", "greek_yogurt",
        "dairy", "OlympusDairy", 16.0, "oz", "g", 453.59, 4.29,
        ["dairy"], ["gluten_free", "low_sodium", "vegetarian", "high_protein"], 0,
        "3/4 cup (170g)", 170.0, 73, 9.9, 3.9, 1.9, 1.2, 0.0, 3.6, 36,
        26, "Dairy",
    ),
    (
        "SKU-FETA-LSOD-6OZ", "Reduced-Sodium Crumbled Feta Cheese", "feta_cheese",
        "dairy", "OlympusDairy", 6.0, "oz", "g", 170.1, 4.79,
        ["dairy"], ["gluten_free", "vegetarian"], 0,
        "1 oz (28g)", 28.0, 264, 14.2, 4.1, 21.3, 14.9, 0.0, 4.1, 580,
        18, "Dairy - Specialty Cheese",
    ),
    (
        "SKU-PARM-GRTD-5OZ", "Aged Parmigiano-Reggiano", "parmesan_cheese",
        "dairy", "BellaItalia", 5.0, "oz", "g", 141.75, 5.99,
        ["dairy"], ["gluten_free", "vegetarian"], 0,
        "2 tbsp (10g)", 10.0, 431, 38.5, 4.1, 28.6, 17.3, 0.0, 0.9, 1529,
        20, "Dairy - Specialty Cheese",
    ),
    (
        "SKU-EGG-LRG-12CT", "Pasture-Raised Large Eggs (12 ct)", "eggs",
        "dairy", "MeadowFarms", 12.0, "count", "count", 12.0, 5.49,
        ["eggs"], ["gluten_free", "low_sodium", "vegetarian", "dairy_free"], 0,
        "1 large egg (50g)", 50.0, 143, 12.6, 0.7, 9.5, 3.1, 0.0, 0.4, 142,
        30, "Dairy",
    ),
    # --- GRAINS, RICE & PASTA ---
    (
        "SKU-RICE-JASM-32OZ", "Organic White Jasmine Rice", "jasmine_rice",
        "grains_pasta", "EarthGrain", 32.0, "oz", "g", 907.18, 4.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1/4 cup dry (45g)", 45.0, 365, 7.1, 80.0, 0.7, 0.2, 1.3, 0.1, 5,
        40, "Aisle 5 - Grains & Rice",
    ),
    (
        "SKU-RICE-BRWN-32OZ", "Long-Grain Brown Rice", "brown_rice",
        "grains_pasta", "EarthGrain", 32.0, "oz", "g", 907.18, 3.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1/4 cup dry (45g)", 45.0, 362, 7.5, 76.2, 2.7, 0.5, 3.4, 0.7, 4,
        35, "Aisle 5 - Grains & Rice",
    ),
    (
        "SKU-QUIN-WHT-16OZ", "Organic White Quinoa", "quinoa",
        "grains_pasta", "AndeanHarvest", 16.0, "oz", "g", 453.59, 4.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/4 cup dry (45g)", 45.0, 368, 14.1, 64.2, 6.1, 0.7, 7.0, 0.0, 5,
        28, "Aisle 5 - Grains & Rice",
    ),
    (
        "SKU-PASTA-WH-16OZ", "Traditional Durum Wheat Penne Pasta", "pasta",
        "grains_pasta", "BellaItalia", 16.0, "oz", "g", 453.59, 2.29,
        ["gluten"], ["low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "2 oz dry (56g)", 56.0, 371, 13.0, 74.7, 1.5, 0.3, 3.2, 2.7, 6,
        50, "Aisle 5 - Pasta",
    ),
    (
        "SKU-PASTA-GF-12OZ", "Certified Gluten-Free Brown Rice Penne", "pasta",
        "grains_pasta", "PureGrainGF", 12.0, "oz", "g", 340.19, 3.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "2 oz dry (56g)", 56.0, 357, 7.1, 76.8, 2.7, 0.4, 3.6, 0.0, 0,
        25, "Aisle 5 - Gluten-Free Pasta",
    ),
    (
        "SKU-PITA-WH-12OZ", "Whole Wheat Pita Bread (6 ct)", "pita_bread",
        "bakery", "HearthBake", 6.0, "count", "g", 340.0, 3.79,
        ["gluten"], ["vegetarian", "vegan", "dairy_free"], 0,
        "1 pita (57g)", 57.0, 262, 9.8, 55.0, 2.6, 0.4, 7.4, 1.0, 420,
        22, "Bakery",
    ),
    (
        "SKU-TORT-CORN-12CT", "Organic White Corn Tortillas (12 ct)", "corn_tortillas",
        "bakery", "MesaVerde", 12.0, "count", "g", 312.0, 2.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "2 tortillas (52g)", 52.0, 218, 5.7, 44.6, 2.9, 0.4, 6.3, 0.9, 45,
        30, "Bakery",
    ),
    (
        "SKU-FLOUR-AP-32OZ", "Unbleached All-Purpose Wheat Flour", "flour",
        "pantry", "GoldMill", 32.0, "oz", "g", 907.18, 3.49,
        ["gluten"], ["low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1/4 cup (30g)", 30.0, 364, 10.3, 76.3, 1.0, 0.2, 2.7, 0.3, 2,
        40, "Aisle 6 - Baking",
    ),
    (
        "SKU-CORNST-16OZ", "Pure Organic Cornstarch", "cornstarch",
        "pantry", "GoldMill", 16.0, "oz", "g", 453.59, 2.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tbsp (8g)", 8.0, 381, 0.3, 91.3, 0.1, 0.0, 0.9, 0.0, 9,
        32, "Aisle 6 - Baking",
    ),
    # --- SAUCES, OILS, BROTHS & CONDIMENTS (INCLUDING GF / LOW-SODIUM VARIANTS) ---
    (
        "SKU-SOY-STD-15OZ", "Brewed Soy Sauce (Contains Wheat)", "soy_sauce",
        "pantry", "DragonWok", 15.0, "fl oz", "ml", 443.6, 3.49,
        ["gluten", "soy"], ["vegetarian", "vegan", "dairy_free"], 1,
        "1 tbsp (15ml)", 15.0, 53, 8.1, 4.9, 0.1, 0.0, 0.8, 0.4, 5493,
        40, "Aisle 2 - Asian Pantry",
    ),
    (
        "SKU-TAMARI-GF-LS-10OZ", "Certified Gluten-Free Reduced-Sodium Tamari", "soy_sauce",
        "pantry", "PureBrew", 10.0, "fl oz", "ml", 295.7, 5.49,
        ["soy"], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tbsp (15ml)", 15.0, 60, 10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 2900,
        24, "Aisle 2 - Asian Pantry",
    ),
    (
        "SKU-COCO-AMINO-8OZ", "Organic Coconut Aminos (Soy-Free & GF)", "coconut_aminos",
        "pantry", "IslandPure", 8.0, "fl oz", "ml", 236.6, 5.99,
        [], ["gluten_free", "low_sodium", "soy_free", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tbsp (15ml)", 15.0, 100, 0.0, 20.0, 0.0, 0.0, 0.0, 13.3, 1800,
        18, "Aisle 2 - Asian Pantry",
    ),
    (
        "SKU-VIN-RICE-12OZ", "Unseasoned Rice Vinegar", "rice_vinegar",
        "pantry", "DragonWok", 12.0, "fl oz", "ml", 354.9, 3.29,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tbsp (15ml)", 15.0, 18, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2,
        26, "Aisle 2 - Asian Pantry",
    ),
    (
        "SKU-VIN-REDW-12OZ", "Organic Red Wine Vinegar", "red_wine_vinegar",
        "pantry", "AegeanSelect", 12.0, "fl oz", "ml", 354.9, 3.79,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tbsp (15ml)", 15.0, 19, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 8,
        24, "Aisle 2 - Oils & Vinegars",
    ),
    (
        "SKU-OIL-OLV-16OZ", "Extra Virgin Olive Oil", "olive_oil",
        "pantry", "AegeanSelect", 16.9, "fl oz", "ml", 500.0, 9.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tbsp (15ml)", 15.0, 884, 0.0, 0.0, 100.0, 13.8, 0.0, 0.0, 2,
        45, "Aisle 2 - Oils & Vinegars",
    ),
    (
        "SKU-OIL-SES-8OZ", "Toasted Sesame Oil", "sesame_oil",
        "pantry", "DragonWok", 8.0, "fl oz", "ml", 236.6, 5.49,
        ["sesame"], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tbsp (15ml)", 15.0, 884, 0.0, 0.0, 100.0, 14.2, 0.0, 0.0, 0,
        28, "Aisle 2 - Asian Pantry",
    ),
    (
        "SKU-OIL-AVOC-16OZ", "Refined Avocado Oil", "avocado_oil",
        "pantry", "SunPress", 16.9, "fl oz", "ml", 500.0, 10.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tbsp (15ml)", 15.0, 884, 0.0, 0.0, 100.0, 11.6, 0.0, 0.0, 0,
        30, "Aisle 2 - Oils & Vinegars",
    ),
    (
        "SKU-BROTH-CHK-LS-32OZ", "Organic Low-Sodium Chicken Broth", "chicken_broth",
        "pantry", "KettleKitchen", 32.0, "fl oz", "ml", 946.4, 3.49,
        [], ["gluten_free", "low_sodium", "dairy_free"], 0,
        "1 cup (240ml)", 240.0, 6, 0.8, 0.4, 0.0, 0.0, 0.0, 0.0, 58,
        32, "Aisle 3 - Soups & Broths",
    ),
    (
        "SKU-BROTH-VEG-LS-32OZ", "Organic Low-Sodium Vegetable Broth", "vegetable_broth",
        "pantry", "KettleKitchen", 32.0, "fl oz", "ml", 946.4, 3.29,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 cup (240ml)", 240.0, 8, 0.4, 1.2, 0.0, 0.0, 0.0, 0.8, 55,
        28, "Aisle 3 - Soups & Broths",
    ),
    (
        "SKU-TOM-CRSH-LS-28OZ", "No-Salt-Added Crushed Tomatoes", "crushed_tomatoes",
        "pantry", "BellaItalia", 28.0, "oz", "g", 793.8, 2.79,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/2 cup (121g)", 121.0, 32, 1.6, 7.3, 0.3, 0.0, 1.9, 4.4, 15,
        34, "Aisle 3 - Canned Goods",
    ),
    (
        "SKU-COCM-LT-13OZ", "Organic Light Coconut Milk", "coconut_milk",
        "pantry", "IslandPure", 13.5, "fl oz", "ml", 400.0, 2.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1/3 cup (80ml)", 80.0, 75, 0.6, 2.5, 6.9, 6.2, 0.0, 1.2, 15,
        26, "Aisle 2 - Asian Pantry",
    ),
    (
        "SKU-HONEY-RAW-12OZ", "Raw Wildflower Honey", "honey",
        "pantry", "MeadowBees", 12.0, "oz", "g", 340.19, 6.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "dairy_free"], 1,
        "1 tbsp (21g)", 21.0, 304, 0.3, 82.4, 0.0, 0.0, 0.2, 82.1, 4,
        28, "Aisle 6 - Baking & Sweeteners",
    ),
    (
        "SKU-TAHINI-10OZ", "Roasted Sesame Tahini", "tahini",
        "pantry", "AegeanSelect", 10.0, "oz", "g", 283.5, 6.99,
        ["sesame"], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "2 tbsp (30g)", 30.0, 595, 17.0, 21.2, 53.8, 7.5, 9.3, 0.5, 115,
        16, "Aisle 2 - Mediterranean & Olives",
    ),
    # --- NUTS & SEEDS ---
    (
        "SKU-PNUT-UNSLT-12OZ", "Unsalted Dry Roasted Peanuts", "peanuts",
        "nuts_seeds", "NutHouse", 12.0, "oz", "g", 340.19, 4.29,
        ["peanuts"], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 oz (28g)", 28.0, 587, 24.4, 21.3, 49.7, 7.7, 8.4, 4.9, 6,
        30, "Aisle 7 - Nuts & Snacks",
    ),
    (
        "SKU-CASH-UNSLT-10OZ", "Unsalted Roasted Cashews", "cashews",
        "nuts_seeds", "NutHouse", 10.0, "oz", "g", 283.5, 6.99,
        ["tree_nuts"], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 oz (28g)", 28.0, 574, 15.3, 32.7, 46.4, 9.2, 3.0, 5.0, 16,
        24, "Aisle 7 - Nuts & Snacks",
    ),
    (
        "SKU-PINE-NUT-4OZ", "Mediterranean Pine Nuts", "pine_nuts",
        "nuts_seeds", "AegeanSelect", 4.0, "oz", "g", 113.4, 7.99,
        ["tree_nuts"], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 0,
        "1 oz (28g)", 28.0, 673, 13.7, 13.1, 68.4, 4.9, 3.7, 3.6, 2,
        0, "Aisle 7 - Nuts & Snacks",  # Intentionally OUT OF STOCK to test substitution!
    ),
    # --- SPICES & SEASONINGS ---
    (
        "SKU-SPC-CUMIN-2OZ", "Organic Ground Cumin Powder", "cumin_powder",
        "spices", "SpiceRoute", 2.0, "oz", "g", 56.7, 3.79,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tsp (2g)", 2.0, 375, 17.8, 44.2, 22.3, 1.5, 10.5, 2.3, 168,
        45, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-OREG-1OZ", "Dried Greek Oregano", "dried_oregano",
        "spices", "SpiceRoute", 1.0, "oz", "g", 28.35, 3.29,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tsp (1g)", 1.0, 265, 9.0, 68.9, 4.3, 1.6, 42.5, 4.1, 25,
        40, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-PAPR-2OZ", "Smoked Sweet Paprika", "paprika",
        "spices", "SpiceRoute", 2.0, "oz", "g", 56.7, 3.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tsp (2g)", 2.0, 282, 14.1, 53.9, 12.9, 2.1, 34.9, 10.3, 68,
        36, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-GARLP-3OZ", "Granulated Garlic Powder", "garlic_powder",
        "spices", "SpiceRoute", 3.0, "oz", "g", 85.0, 3.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tsp (3g)", 3.0, 331, 16.6, 72.7, 0.7, 0.2, 9.0, 2.4, 60,
        42, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-CHILI-2OZ", "Crushed Red Chili Flakes", "red_chili_flakes",
        "spices", "SpiceRoute", 2.0, "oz", "g", 56.7, 3.19,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free", "spicy"], 1,
        "1/2 tsp (1g)", 1.0, 318, 12.0, 56.6, 17.3, 3.3, 27.2, 10.3, 30,
        38, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-PEPPR-2OZ", "Cracked Black Peppercorns", "black_pepper",
        "spices", "SpiceRoute", 2.0, "oz", "g", 56.7, 4.29,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1/4 tsp (0.6g)", 0.6, 251, 10.4, 64.0, 3.3, 1.4, 25.3, 0.6, 20,
        50, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-SALT-16OZ", "Fine Sea Salt", "salt",
        "spices", "OceanPure", 16.0, "oz", "g", 453.59, 2.49,
        [], ["gluten_free", "vegetarian", "vegan", "dairy_free"], 1,
        "1/4 tsp (1.5g)", 1.5, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 38758,
        60, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-TURM-2OZ", "Organic Ground Turmeric", "turmeric",
        "spices", "SpiceRoute", 2.0, "oz", "g", 56.7, 3.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tsp (3g)", 3.0, 312, 9.7, 67.1, 3.3, 1.8, 22.7, 3.2, 27,
        34, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-GARAM-2OZ", "Garam Masala Spice Blend", "garam_masala",
        "spices", "SpiceRoute", 2.0, "oz", "g", 56.7, 4.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tsp (2g)", 2.0, 379, 15.0, 50.0, 15.0, 1.5, 25.0, 2.0, 60,
        28, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-CORI-2OZ", "Organic Ground Coriander", "coriander",
        "spices", "SpiceRoute", 2.0, "oz", "g", 56.7, 3.49,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free"], 1,
        "1 tsp (2g)", 2.0, 298, 12.4, 55.0, 17.8, 1.0, 41.9, 0.0, 35,
        30, "Aisle 4 - Spices",
    ),
    (
        "SKU-SPC-SICH-1OZ", "Whole Sichuan Peppercorns", "sichuan_peppercorns",
        "spices", "DragonWok", 1.0, "oz", "g", 28.35, 4.99,
        [], ["gluten_free", "low_sodium", "vegetarian", "vegan", "dairy_free", "spicy"], 1,
        "1 tsp (2g)", 2.0, 251, 10.4, 64.0, 3.3, 1.4, 25.3, 0.6, 20,
        20, "Aisle 2 - Asian Pantry",
    ),
]

FIXTURE_USERS: list[dict[str, Any]] = [
    {
        "user_id": "cust_malcom_munson",
        "full_name": "Malcom Munson",
        "phone_number": "+1-555-0101",
        "cooking_skill_level": "intermediate",
        "default_servings": 2,
        "daily_calorie_target": 2000,
        "daily_sodium_limit_mg": 1500,
        "constraints": [
            ("medical_condition", "celiac_disease", "hard_block", "Strict gluten-free required."),
            ("allergen", "gluten", "hard_block", "Derived from celiac disease."),
            ("medical_condition", "hypertension", "warn_threshold", "High blood pressure; prefer low sodium."),
            ("diet_regime", "low_sodium", "warn_threshold", "Target <= 600mg sodium per serving."),
        ],
        "preferences": [
            ("cuisine", "mediterranean", "like", 2.0),
            ("protein", "chicken", "prefer", 1.8),
            ("protein", "fish", "dislike", 1.2),
            ("ingredient", "eggplant", "dislike", 2.0),
        ],
    },
    {
        "user_id": "cust_priya_patel",
        "full_name": "Priya Patel",
        "phone_number": "+1-555-0102",
        "cooking_skill_level": "advanced",
        "default_servings": 4,
        "daily_calorie_target": 1900,
        "daily_sodium_limit_mg": 2300,
        "constraints": [
            ("diet_regime", "vegetarian", "hard_block", "No meat, poultry, or seafood."),
            ("allergen", "peanuts", "hard_block", "Severe peanut allergy."),
        ],
        "preferences": [
            ("cuisine", "indian", "like", 2.0),
            ("cuisine", "mexican", "like", 1.5),
            ("ingredient", "mushrooms", "dislike", 1.8),
        ],
    },
    {
        "user_id": "cust_alex_rivera",
        "full_name": "Alex Rivera",
        "phone_number": "+1-555-0103",
        "cooking_skill_level": "beginner",
        "default_servings": 2,
        "daily_calorie_target": None,
        "daily_sodium_limit_mg": None,
        "constraints": [],
        "preferences": [
            ("flavor_profile", "spicy", "dislike", 1.5),
        ],
    },
    {
        "user_id": "cust_guest",
        "full_name": "Guest Shopper",
        "phone_number": None,
        "cooking_skill_level": "intermediate",
        "default_servings": 2,
        "daily_calorie_target": None,
        "daily_sodium_limit_mg": None,
        "constraints": [],
        "preferences": [],
    },
]


def seed_database(db_path: str | Path | None = None) -> dict[str, int]:
    """Initialize schema and idempotently seed products, nutrition, inventory, and users."""
    resolved = init_db(db_path)
    with get_connection(resolved) as conn:
        for entry in CATALOG_ENTRIES:
            (
                sku, name, canonical, category, brand,
                pkg_qty, pkg_unit, base_unit, g_per_pkg, price,
                allergens, dietary_tags, is_staple,
                serving_desc, serving_g, kcal, protein, carbs, fat, sat_fat, fiber, sugar, sodium,
                qty_on_hand, aisle,
            ) = entry

            conn.execute(
                """
                INSERT OR REPLACE INTO products (
                    sku, name, canonical_ingredient, category, brand,
                    package_qty, package_unit, base_unit, grams_or_ml_per_package,
                    unit_price_usd, allergen_tags_json, dietary_tags_json,
                    is_pantry_staple, is_active, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    sku, name, canonical, category, brand,
                    pkg_qty, pkg_unit, base_unit, g_per_pkg,
                    price, json.dumps(allergens), json.dumps(dietary_tags),
                    is_staple, NOW_ISO,
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO nutritional_facts (
                    sku, serving_size_desc, serving_size_g_or_ml,
                    calories_per_100, protein_g_per_100, carbs_g_per_100,
                    fat_g_per_100, saturated_fat_g_per_100, fiber_g_per_100,
                    sugar_g_per_100, sodium_mg_per_100, data_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USDA_FDC_SEED')
                """,
                (
                    sku, serving_desc, serving_g,
                    kcal, protein, carbs, fat, sat_fat, fiber, sugar, sodium,
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO inventory (
                    store_id, sku, qty_on_hand, qty_reserved,
                    aisle_location, restock_eta, last_counted_at
                ) VALUES (?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    DEFAULT_STORE_ID,
                    sku,
                    qty_on_hand,
                    aisle,
                    "2026-12-01" if qty_on_hand == 0 else None,
                    NOW_ISO,
                ),
            )

        for user in FIXTURE_USERS:
            conn.execute(
                """
                INSERT OR REPLACE INTO users (
                    user_id, full_name, phone_number, cooking_skill_level,
                    default_servings, daily_calorie_target, daily_sodium_limit_mg,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["user_id"], user["full_name"], user["phone_number"],
                    user["cooking_skill_level"], user["default_servings"],
                    user["daily_calorie_target"], user["daily_sodium_limit_mg"],
                    NOW_ISO, NOW_ISO,
                ),
            )
            for c_type, code, severity, notes in user["constraints"]:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO user_dietary_constraints (
                        user_id, constraint_type, code, severity, notes
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (user["user_id"], c_type, code, severity, notes),
                )
            for category, value, sentiment, weight in user["preferences"]:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO user_preferences (
                        user_id, category, value, sentiment, weight,
                        source_session_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'seed_fixture', ?)
                    """,
                    (user["user_id"], category, value, sentiment, weight, NOW_ISO),
                )

    return {
        "products": len(CATALOG_ENTRIES),
        "nutritional_facts": len(CATALOG_ENTRIES),
        "inventory": len(CATALOG_ENTRIES),
        "users": len(FIXTURE_USERS),
    }


if __name__ == "__main__":
    counts = seed_database()
    print(f"Seeded SQLite database successfully: {counts}")
