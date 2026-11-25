"""Deterministic unit conversion and nutritional calculation tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.database import DEFAULT_STORE_ID, get_connection
from app.schemas import IngredientSpec, NutrientTotals, NutritionSummary
from app.tools.catalog_tools import find_best_sku_for_ingredient

# Exact conversion factors to grams (mass) or milliliters (volume)
MASS_TO_GRAMS: dict[str, float] = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
}

VOLUME_TO_ML: dict[str, float] = {
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "fl_oz": 29.5735,
    "fl oz": 29.5735,
    "tsp": 4.92892,
    "teaspoon": 4.92892,
    "teaspoons": 4.92892,
    "tbsp": 14.7868,
    "tablespoon": 14.7868,
    "tablespoons": 14.7868,
    "cup": 236.588,
    "cups": 236.588,
}

# Approximate culinary volume->gram density for dry solids measured in spoons/cups
DRY_VOLUME_TO_GRAMS: dict[str, float] = {
    "tsp": 3.0,
    "teaspoon": 3.0,
    "teaspoons": 3.0,
    "tbsp": 9.0,
    "tablespoon": 9.0,
    "tablespoons": 9.0,
    "cup": 150.0,
    "cups": 150.0,
}

DISCRETE_UNITS = {"count", "ct", "piece", "pieces", "whole", "medium", "large", "small", "bunch", "bunches", "clove", "cloves", "stalk", "stalks", "head", "bulb"}


def convert_units_to_base(
    quantity: float,
    unit: str,
    product: dict[str, Any],
) -> tuple[float, float]:
    """Convert an ingredient recipe quantity to the SKU's base_unit and gram/ml mass.

    Returns:
        (qty_in_base_unit, grams_or_ml_for_nutrition)
    """
    u = unit.strip().lower()
    base_unit = product["base_unit"]
    g_per_pkg = float(product["grams_or_ml_per_package"])
    pkg_qty = float(product["package_qty"])
    canonical = product["canonical_ingredient"]

    # Special culinary discrete units
    if u in {"clove", "cloves"} and canonical == "garlic":
        g = quantity * 4.0
        return (g, g)
    if u in {"stalk", "stalks"} and canonical == "green_onion":
        g = quantity * 15.0
        return (g, g)

    if base_unit == "count":
        # e.g., eggs: 1 egg ~= 50g
        if u in DISCRETE_UNITS:
            return (quantity, quantity * 50.0)
        if u in MASS_TO_GRAMS:
            g = quantity * MASS_TO_GRAMS[u]
            return (max(1.0, g / 50.0), g)
        return (quantity, quantity * 50.0)

    if base_unit == "g":
        if u in MASS_TO_GRAMS:
            g = quantity * MASS_TO_GRAMS[u]
            return (g, g)
        if u in DRY_VOLUME_TO_GRAMS:
            # Liquids or dense grains override
            if canonical in {"jasmine_rice", "brown_rice", "quinoa", "red_lentils"} and u in {"cup", "cups"}:
                g = quantity * 185.0
            elif canonical in {"greek_yogurt", "crushed_tomatoes", "chickpeas", "black_beans"} and u in {"cup", "cups"}:
                g = quantity * 240.0
            elif canonical in {"butter", "honey", "tahini"} and u in {"tbsp", "tablespoon", "tablespoons"}:
                g = quantity * 15.0
            elif canonical in {"butter", "honey", "tahini"} and u in {"tsp", "teaspoon", "teaspoons"}:
                g = quantity * 5.0
            else:
                g = quantity * DRY_VOLUME_TO_GRAMS[u]
            return (g, g)
        if u in DISCRETE_UNITS:
            # 1 count/bunch = grams_or_ml_per_package / package_qty
            per_item_g = g_per_pkg / max(pkg_qty, 1.0)
            g = quantity * per_item_g
            return (g, g)
        # Fallback to grams directly
        return (quantity, quantity)

    # base_unit == "ml"
    if u in VOLUME_TO_ML:
        ml = quantity * VOLUME_TO_ML[u]
        return (ml, ml)
    if u in MASS_TO_GRAMS:
        # Approximate 1g ~= 1ml for water-like liquids
        ml = quantity * MASS_TO_GRAMS[u]
        return (ml, ml)
    if u in DISCRETE_UNITS:
        per_item_ml = g_per_pkg / max(pkg_qty, 1.0)
        ml = quantity * per_item_ml
        return (ml, ml)
    return (quantity, quantity)


def get_sku_nutrition(
    sku: str,
    quantity_g_or_ml: float,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Deterministically compute exact calories, macros, and sodium for a SKU quantity.

    Args:
        sku: Primary key of the product in products / nutritional_facts.
        quantity_g_or_ml: Ingredient weight in grams or volume in milliliters.

    Returns:
        Dictionary with exact rounded nutritional metrics for the specified quantity.
    """
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT p.sku, p.name, n.*
            FROM products p
            JOIN nutritional_facts n ON p.sku = n.sku
            WHERE p.sku = ?
            """,
            (sku,),
        ).fetchone()

    if row is None:
        return {"status": "error", "message": f"SKU '{sku}' not found in nutritional_facts."}

    factor = max(0.0, float(quantity_g_or_ml)) / 100.0
    totals = NutrientTotals(
        calories=round(row["calories_per_100"] * factor, 1),
        protein_g=round(row["protein_g_per_100"] * factor, 1),
        carbs_g=round(row["carbs_g_per_100"] * factor, 1),
        fat_g=round(row["fat_g_per_100"] * factor, 1),
        saturated_fat_g=round(row["saturated_fat_g_per_100"] * factor, 1),
        fiber_g=round(row["fiber_g_per_100"] * factor, 1),
        sugar_g=round(row["sugar_g_per_100"] * factor, 1),
        sodium_mg=round(row["sodium_mg_per_100"] * factor, 1),
    )
    return {
        "status": "success",
        "sku": sku,
        "product_name": row["name"],
        "quantity_g_or_ml": round(quantity_g_or_ml, 1),
        "serving_size_desc": row["serving_size_desc"],
        "nutrition": totals.model_dump(),
    }


def calculate_recipe_nutrition_model(
    ingredients: list[IngredientSpec],
    base_servings: int,
    target_servings: int,
    blocked_allergens: set[str],
    prefer_low_sodium: bool = False,
    is_vegetarian: bool = False,
    is_vegan: bool = False,
    sodium_limit_per_serving_mg: float | None = None,
    store_id: str = DEFAULT_STORE_ID,
    db_path: str | Path | None = None,
) -> tuple[NutritionSummary, list[str]]:
    """Deterministically scale ingredients and aggregate exact recipe nutrition from SQLite.

    Returns:
        (NutritionSummary, list_of_matched_skus)
    """
    scale = float(target_servings) / float(max(base_servings, 1))
    totals = {
        "calories": 0.0,
        "protein_g": 0.0,
        "carbs_g": 0.0,
        "fat_g": 0.0,
        "saturated_fat_g": 0.0,
        "fiber_g": 0.0,
        "sugar_g": 0.0,
        "sodium_mg": 0.0,
    }
    total_weight_g = 0.0
    unmatched: list[str] = []
    matched_skus: list[str] = []
    all_tags_sets: list[set[str]] = []

    for ing in ingredients:
        prod, _ = find_best_sku_for_ingredient(
            ing.canonical_ingredient,
            blocked_allergens=blocked_allergens,
            prefer_low_sodium=prefer_low_sodium,
            is_vegetarian=is_vegetarian,
            is_vegan=is_vegan,
            store_id=store_id,
            db_path=db_path,
        )
        if prod is None:
            unmatched.append(ing.canonical_ingredient)
            continue

        matched_skus.append(prod["sku"])
        all_tags_sets.append(set(prod["dietary_tags"]))
        scaled_qty = ing.quantity * scale
        _, grams_or_ml = convert_units_to_base(scaled_qty, ing.unit, prod)
        total_weight_g += grams_or_ml
        sku_nutr = get_sku_nutrition(prod["sku"], grams_or_ml, db_path=db_path)
        if sku_nutr["status"] == "success":
            n = sku_nutr["nutrition"]
            for k in totals:
                totals[k] += n[k]

    servings_f = float(max(target_servings, 1))
    total_model = NutrientTotals(**{k: round(v, 1) for k, v in totals.items()})
    per_serving_model = NutrientTotals(**{k: round(v / servings_f, 1) for k, v in totals.items()})

    badges: list[str] = []
    if all_tags_sets:
        common = set.intersection(*all_tags_sets)
        for tag in ("gluten_free", "vegetarian", "vegan", "dairy_free"):
            if tag in common:
                badges.append(tag)
    if per_serving_model.sodium_mg <= 600.0:
        badges.append("low_sodium")

    sodium_warning = None
    if sodium_limit_per_serving_mg is not None and per_serving_model.sodium_mg > sodium_limit_per_serving_mg:
        sodium_warning = (
            f"Per-serving sodium ({per_serving_model.sodium_mg:.0f} mg) exceeds your "
            f"recommended per-meal target ({sodium_limit_per_serving_mg:.0f} mg)."
        )

    summary = NutritionSummary(
        servings=target_servings,
        approx_serving_weight_g=round(total_weight_g / servings_f, 1),
        per_serving=per_serving_model,
        total_recipe=total_model,
        unmatched_ingredients=unmatched,
        sodium_warning=sodium_warning,
        dietary_badges=sorted(set(badges)),
    )
    return summary, matched_skus


def calculate_recipe_nutrition(
    ingredients: list[dict[str, Any]],
    base_servings: int,
    target_servings: int,
    exclude_allergens: list[str],
) -> dict[str, Any]:
    """Tool wrapper: compute deterministic nutrition totals and per-serving macros for a recipe.

    Args:
        ingredients: List of ingredient dicts ({canonical_ingredient, display_name, quantity, unit}).
        base_servings: Number of servings the base recipe quantities are written for.
        target_servings: Desired number of meals/servings to scale to.
        exclude_allergens: Allergens to exclude when selecting store SKUs.

    Returns:
        Dictionary containing exact per-serving and total calories, macros, sodium, and dietary badges.
    """
    specs = [IngredientSpec(**item) for item in ingredients]
    summary, matched_skus = calculate_recipe_nutrition_model(
        ingredients=specs,
        base_servings=base_servings,
        target_servings=target_servings,
        blocked_allergens={a.strip().lower() for a in exclude_allergens},
    )
    return {
        "status": "success",
        "matched_skus": matched_skus,
        "nutrition_summary": summary.model_dump(),
    }
