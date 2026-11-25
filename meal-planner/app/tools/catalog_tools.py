"""Deterministic product catalogue and store inventory lookup tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db.database import DEFAULT_STORE_ID, get_connection

# Common synonym normalization so slight LLM wording differences resolve cleanly
INGREDIENT_ALIASES: dict[str, str] = {
    "chicken": "chicken_breast",
    "chicken_breasts": "chicken_breast",
    "boneless_skinless_chicken_breast": "chicken_breast",
    "chicken_thighs": "chicken_thigh",
    "turkey": "ground_turkey",
    "beef": "beef_sirloin",
    "steak": "beef_sirloin",
    "salmon": "salmon_fillet",
    "prawns": "shrimp",
    "garbanzo_beans": "chickpeas",
    "red_bell_pepper": "bell_pepper",
    "bell_peppers": "bell_pepper",
    "sweet_bell_pepper": "bell_pepper",
    "tomatoes": "tomato",
    "roma_tomatoes": "tomato",
    "onion": "yellow_onion",
    "scallions": "green_onion",
    "scallion": "green_onion",
    "spring_onion": "green_onion",
    "green_onions": "green_onion",
    "garlic_cloves": "garlic",
    "fresh_garlic": "garlic",
    "fresh_ginger": "ginger",
    "lemon_juice": "lemon",
    "lime_juice": "lime",
    "baby_spinach": "spinach",
    "carrots": "carrot",
    "mushroom": "mushrooms",
    "fresh_parsley": "parsley",
    "fresh_cilantro": "cilantro",
    "fresh_dill": "dill",
    "fresh_basil": "basil",
    "olives": "kalamata_olives",
    "unsalted_butter": "butter",
    "yogurt": "greek_yogurt",
    "feta": "feta_cheese",
    "parmesan": "parmesan_cheese",
    "egg": "eggs",
    "rice": "jasmine_rice",
    "white_rice": "jasmine_rice",
    "penne": "pasta",
    "penne_pasta": "pasta",
    "pita": "pita_bread",
    "tortillas": "corn_tortillas",
    "all_purpose_flour": "flour",
    "tamari": "soy_sauce",
    "gluten_free_soy_sauce": "soy_sauce",
    "extra_virgin_olive_oil": "olive_oil",
    "evoo": "olive_oil",
    "vegetable_oil": "avocado_oil",
    "cooking_oil": "avocado_oil",
    "broth": "chicken_broth",
    "cumin": "cumin_powder",
    "ground_cumin": "cumin_powder",
    "oregano": "dried_oregano",
    "smoked_paprika": "paprika",
    "chili_flakes": "red_chili_flakes",
    "red_pepper_flakes": "red_chili_flakes",
    "pepper": "black_pepper",
    "sea_salt": "salt",
    "kosher_salt": "salt",
    "ground_turmeric": "turmeric",
    "ground_coriander": "coriander",
    "roasted_peanuts": "peanuts",
    "unsalted_peanuts": "peanuts",
}

# Safe deterministic fallback map when a canonical ingredient is out of stock or blocked
SAFE_INGREDIENT_SUBSTITUTES: dict[str, list[str]] = {
    "pine_nuts": ["cashews", "peanuts"],
    "peanuts": ["cashews"],
    "soy_sauce": ["coconut_aminos"],
    "chicken_broth": ["vegetable_broth"],
    "pita_bread": ["corn_tortillas", "quinoa", "jasmine_rice"],
    "flour": ["cornstarch"],
    "butter": ["olive_oil", "avocado_oil"],
    "feta_cheese": ["kalamata_olives"],
    "red_chili_flakes": ["paprika"],
    "sichuan_peppercorns": ["black_pepper"],
}

NON_VEGETARIAN_CATEGORIES = {"meat_poultry", "seafood"}
NON_VEGETARIAN_INGREDIENTS = {"chicken_broth"}


def normalize_ingredient_key(name: str) -> str:
    """Normalize an ingredient string to a canonical database key."""
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    return INGREDIENT_ALIASES.get(key, key)


def _row_to_product_dict(row: Any) -> dict[str, Any]:
    return {
        "sku": row["sku"],
        "name": row["name"],
        "canonical_ingredient": row["canonical_ingredient"],
        "category": row["category"],
        "brand": row["brand"],
        "package_qty": row["package_qty"],
        "package_unit": row["package_unit"],
        "base_unit": row["base_unit"],
        "grams_or_ml_per_package": row["grams_or_ml_per_package"],
        "unit_price_usd": row["unit_price_usd"],
        "allergen_tags": json.loads(row["allergen_tags_json"]),
        "dietary_tags": json.loads(row["dietary_tags_json"]),
        "is_pantry_staple": bool(row["is_pantry_staple"]),
        "available_qty": row["available_qty"],
        "aisle_location": row["aisle_location"],
    }


def _violates_hard_blocks(
    product: dict[str, Any],
    blocked_allergens: set[str],
    is_vegetarian: bool,
    is_vegan: bool,
) -> bool:
    allergens = {a.lower() for a in product["allergen_tags"]}
    if allergens & blocked_allergens:
        return True
    if is_vegetarian and (
        product["category"] in NON_VEGETARIAN_CATEGORIES
        or product["canonical_ingredient"] in NON_VEGETARIAN_INGREDIENTS
    ):
        return True
    if is_vegan and (
        product["category"] in NON_VEGETARIAN_CATEGORIES
        or product["canonical_ingredient"] in NON_VEGETARIAN_INGREDIENTS
        or "dairy" in allergens
        or "eggs" in allergens
        or product["canonical_ingredient"] == "honey"
    ):
        return True
    return False


def list_available_ingredients(
    store_id: str = DEFAULT_STORE_ID,
    db_path: str | Path | None = None,
) -> list[str]:
    """Return sorted list of canonical_ingredient keys currently in stock."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT p.canonical_ingredient
            FROM products p
            JOIN v_available_inventory i ON p.sku = i.sku
            WHERE p.is_active = 1 AND i.store_id = ? AND i.available_qty > 0
            ORDER BY p.canonical_ingredient
            """,
            (store_id,),
        ).fetchall()
    return [r["canonical_ingredient"] for r in rows]


def search_products(
    query: str,
    exclude_allergens: list[str],
    required_dietary_tags: list[str],
    in_stock_only: bool,
) -> dict[str, Any]:
    """Deterministically search the grocery store product catalogue and inventory.

    Args:
        query: Search term matching product name, canonical ingredient, or category.
        exclude_allergens: Allergens to strictly exclude (e.g., ['gluten', 'peanuts']).
        required_dietary_tags: Dietary tags products must carry (e.g., ['gluten_free', 'low_sodium']).
        in_stock_only: When True, only return items with available_qty > 0.

    Returns:
        Dictionary with matching SKUs, prices, stock quantities, and dietary/allergen metadata.
    """
    q = f"%{query.strip().lower()}%"
    blocked = {a.strip().lower() for a in exclude_allergens if a.strip()}
    req_tags = {t.strip().lower() for t in required_dietary_tags if t.strip()}
    is_veg = "vegetarian" in req_tags
    is_vegan = "vegan" in req_tags

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*, i.available_qty, i.aisle_location
            FROM products p
            JOIN v_available_inventory i ON p.sku = i.sku
            WHERE p.is_active = 1
              AND i.store_id = ?
              AND (
                LOWER(p.name) LIKE ?
                OR LOWER(p.canonical_ingredient) LIKE ?
                OR LOWER(p.category) LIKE ?
              )
            ORDER BY p.unit_price_usd ASC
            """,
            (DEFAULT_STORE_ID, q, q, q),
        ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        prod = _row_to_product_dict(row)
        if in_stock_only and prod["available_qty"] <= 0:
            continue
        if _violates_hard_blocks(prod, blocked, is_veg, is_vegan):
            continue
        prod_tags = {t.lower() for t in prod["dietary_tags"]}
        if req_tags and not req_tags.issubset(prod_tags):
            continue
        results.append(prod)

    return {"status": "success", "count": len(results), "products": results}


def find_best_sku_for_ingredient(
    canonical_ingredient: str,
    blocked_allergens: set[str],
    prefer_low_sodium: bool = False,
    is_vegetarian: bool = False,
    is_vegan: bool = False,
    store_id: str = DEFAULT_STORE_ID,
    db_path: str | Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Deterministically pick the best safe, in-stock SKU for a canonical ingredient.

    If the primary ingredient has no safe in-stock SKU, checks SAFE_INGREDIENT_SUBSTITUTES.

    Returns:
        (product_dict_or_None, substitution_note_or_None)
    """
    norm_key = normalize_ingredient_key(canonical_ingredient)

    def _query_candidates(key: str) -> list[dict[str, Any]]:
        with get_connection(db_path) as conn:
            rows = conn.execute(
                """
                SELECT p.*, i.available_qty, i.aisle_location, n.sodium_mg_per_100
                FROM products p
                JOIN v_available_inventory i ON p.sku = i.sku
                JOIN nutritional_facts n ON p.sku = n.sku
                WHERE p.is_active = 1
                  AND i.store_id = ?
                  AND p.canonical_ingredient = ?
                """,
                (store_id, key),
            ).fetchall()
        candidates = []
        for row in rows:
            prod = _row_to_product_dict(row)
            prod["sodium_mg_per_100"] = row["sodium_mg_per_100"]
            if prod["available_qty"] <= 0:
                continue
            if _violates_hard_blocks(prod, blocked_allergens, is_vegetarian, is_vegan):
                continue
            candidates.append(prod)

        def _rank(p: dict[str, Any]) -> tuple[Any, ...]:
            tags = set(p["dietary_tags"])
            low_sod_penalty = 0 if (not prefer_low_sodium or "low_sodium" in tags) else 1
            sod_val = p["sodium_mg_per_100"] if prefer_low_sodium else 0.0
            return (low_sod_penalty, sod_val, p["unit_price_usd"], p["sku"])

        candidates.sort(key=_rank)
        return candidates

    primary = _query_candidates(norm_key)
    if primary:
        chosen = primary[0]
        # Note if we deterministically picked a dietary-safe variant over a standard one
        sub_note = None
        if norm_key == "soy_sauce" and chosen["sku"] == "SKU-TAMARI-GF-LS-10OZ":
            sub_note = "Selected certified gluten-free reduced-sodium tamari to match dietary constraints."
        elif norm_key == "pasta" and chosen["sku"] == "SKU-PASTA-GF-12OZ":
            sub_note = "Selected certified gluten-free brown rice penne for gluten-free compliance."
        return chosen, sub_note

    # Try deterministic safe substitutes
    for alt_key in SAFE_INGREDIENT_SUBSTITUTES.get(norm_key, []):
        alts = _query_candidates(alt_key)
        if alts:
            chosen = alts[0]
            return (
                chosen,
                f"Substituted '{chosen['name']}' for '{canonical_ingredient}' (out of stock or dietary restriction).",
            )

    return None, None
