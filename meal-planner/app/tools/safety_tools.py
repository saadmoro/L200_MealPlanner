"""Deterministic dietary safety, allergen hard-blocking, and sodium compliance tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db.database import DEFAULT_STORE_ID, get_connection
from app.schemas import (
    IngredientSpec,
    NutritionSummary,
    SafetyComplianceResult,
    SafetyViolation,
    UserProfile,
)
from app.tools.catalog_tools import (
    NON_VEGETARIAN_CATEGORIES,
    NON_VEGETARIAN_INGREDIENTS,
    find_best_sku_for_ingredient,
    normalize_ingredient_key,
)
from app.tools.profile_tools import load_user_profile_model

MEDICAL_DISCLAIMER = (
    "*Nutrition & Medical Disclaimer: Nutritional values are estimates based on store "
    "product data and are provided for informational meal-planning purposes only—not "
    "medical advice. Always verify product packaging labels for allergens and consult "
    "a healthcare professional or registered dietitian for medical dietary management.*"
)

# Ingredients that inherently carry allergens if a recipe names them directly
INHERENT_ALLERGENS_BY_INGREDIENT: dict[str, set[str]] = {
    "pasta": set(),  # Has certified GF variant SKU-PASTA-GF-12OZ
    "soy_sauce": {"soy"},  # Has certified GF tamari variant
    "pita_bread": {"gluten"},
    "flour": {"gluten"},
    "peanuts": {"peanuts"},
    "cashews": {"tree_nuts"},
    "pine_nuts": {"tree_nuts"},
    "salmon_fillet": {"fish"},
    "shrimp": {"shellfish"},
    "tofu": {"soy"},
    "butter": {"dairy"},
    "greek_yogurt": {"dairy"},
    "feta_cheese": {"dairy"},
    "parmesan_cheese": {"dairy"},
    "eggs": {"eggs"},
    "sesame_oil": {"sesame"},
    "tahini": {"sesame"},
}


def extract_safety_flags(profile: UserProfile) -> dict[str, Any]:
    """Deterministically derive enforcement flags from a UserProfile."""
    blocked_allergens: set[str] = set()
    is_vegetarian = False
    is_vegan = False
    prefer_low_sodium = False
    has_medical = False
    disliked_ingredients: set[str] = set()

    for c in profile.constraints:
        code = c.code.lower()
        if c.constraint_type == "medical_condition":
            has_medical = True
        if c.severity == "hard_block":
            if c.constraint_type == "allergen":
                blocked_allergens.add(code)
            elif code == "celiac_disease":
                blocked_allergens.add("gluten")
                has_medical = True
            elif code == "vegetarian":
                is_vegetarian = True
            elif code == "vegan":
                is_vegetarian = True
                is_vegan = True
        if code in {"hypertension", "high_blood_pressure", "low_sodium"}:
            prefer_low_sodium = True
            if code in {"hypertension", "high_blood_pressure"}:
                has_medical = True

    for pref in profile.preferences:
        if pref.sentiment in {"dislike", "avoid"} and pref.category == "ingredient":
            disliked_ingredients.add(normalize_ingredient_key(pref.value))

    sodium_per_meal_limit: float | None = None
    if profile.daily_sodium_limit_mg is not None:
        sodium_per_meal_limit = round(profile.daily_sodium_limit_mg * 0.40, 1)
    elif prefer_low_sodium:
        sodium_per_meal_limit = 600.0

    return {
        "blocked_allergens": blocked_allergens,
        "is_vegetarian": is_vegetarian,
        "is_vegan": is_vegan,
        "prefer_low_sodium": prefer_low_sodium,
        "has_medical_conditions": has_medical,
        "sodium_per_meal_limit_mg": sodium_per_meal_limit,
        "disliked_ingredients": disliked_ingredients,
    }


def check_skus_against_profile(
    profile: UserProfile,
    skus: list[str],
    nutrition_summary: NutritionSummary | None = None,
    db_path: str | Path | None = None,
) -> SafetyComplianceResult:
    """Deterministically verify a list of SKUs (and optional nutrition) against user constraints."""
    flags = extract_safety_flags(profile)
    blocked: set[str] = flags["blocked_allergens"]
    is_veg: bool = flags["is_vegetarian"]
    is_vegan: bool = flags["is_vegan"]
    sodium_limit: float | None = flags["sodium_per_meal_limit_mg"]

    hard_blocks: list[SafetyViolation] = []
    warnings: list[SafetyViolation] = []

    if skus:
        placeholders = ",".join("?" for _ in skus)
        with get_connection(db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM products WHERE sku IN ({placeholders})",
                tuple(skus),
            ).fetchall()
        by_sku = {r["sku"]: r for r in rows}

        for sku in skus:
            row = by_sku.get(sku)
            if row is None:
                continue
            allergens = {a.lower() for a in json.loads(row["allergen_tags_json"])}
            canonical = row["canonical_ingredient"]
            category = row["category"]

            # 1. Hard allergen intersection
            overlap = allergens & blocked
            if overlap:
                sub, _ = find_best_sku_for_ingredient(
                    canonical,
                    blocked_allergens=blocked,
                    prefer_low_sodium=flags["prefer_low_sodium"],
                    is_vegetarian=is_veg,
                    is_vegan=is_vegan,
                    db_path=db_path,
                )
                hard_blocks.append(
                    SafetyViolation(
                        severity="hard_block",
                        code=",".join(sorted(overlap)),
                        sku=sku,
                        ingredient=canonical,
                        message=(
                            f"Blocked SKU '{row['name']}' ({sku}): contains hard-blocked "
                            f"allergen(s) {sorted(overlap)}."
                        ),
                        suggested_substitute_sku=sub["sku"] if sub else None,
                        suggested_substitute_name=sub["name"] if sub else None,
                    )
                )

            # 2. Hard vegetarian / vegan checks
            if is_veg and (
                category in NON_VEGETARIAN_CATEGORIES
                or canonical in NON_VEGETARIAN_INGREDIENTS
            ):
                hard_blocks.append(
                    SafetyViolation(
                        severity="hard_block",
                        code="vegetarian",
                        sku=sku,
                        ingredient=canonical,
                        message=f"Blocked SKU '{row['name']}' ({sku}): violates vegetarian constraint.",
                    )
                )
            elif is_vegan and (
                "dairy" in allergens or "eggs" in allergens or canonical == "honey"
            ):
                hard_blocks.append(
                    SafetyViolation(
                        severity="hard_block",
                        code="vegan",
                        sku=sku,
                        ingredient=canonical,
                        message=f"Blocked SKU '{row['name']}' ({sku}): violates vegan constraint.",
                    )
                )

    if nutrition_summary is not None and sodium_limit is not None:
        sod = nutrition_summary.per_serving.sodium_mg
        if sod > sodium_limit:
            warnings.append(
                SafetyViolation(
                    severity="warn_threshold",
                    code="low_sodium",
                    message=(
                        f"Per-serving sodium ({sod:.0f} mg) exceeds recommended "
                        f"threshold ({sodium_limit:.0f} mg/meal)."
                    ),
                )
            )

    return SafetyComplianceResult(
        is_safe=len(hard_blocks) == 0,
        hard_blocks=hard_blocks,
        warnings=warnings,
        requires_medical_disclaimer=flags["has_medical_conditions"],
    )


def validate_recipe_ingredients_safety(
    profile: UserProfile,
    ingredients: list[IngredientSpec],
    store_id: str = DEFAULT_STORE_ID,
    db_path: str | Path | None = None,
) -> SafetyComplianceResult:
    """Validate a RecipeDraft's ingredients before SKU mapping/presentation.

    Detects:
    - Ingredients with NO safe in-stock SKU matching user's hard_block constraints.
    - Explicitly disliked ingredients (flagged as warnings or blocks).
    """
    flags = extract_safety_flags(profile)
    blocked: set[str] = flags["blocked_allergens"]
    is_veg: bool = flags["is_vegetarian"]
    is_vegan: bool = flags["is_vegan"]
    disliked: set[str] = flags["disliked_ingredients"]

    hard_blocks: list[SafetyViolation] = []
    warnings: list[SafetyViolation] = []

    for ing in ingredients:
        norm = normalize_ingredient_key(ing.canonical_ingredient)

        # Check if user explicitly dislikes this ingredient
        if norm in disliked:
            warnings.append(
                SafetyViolation(
                    severity="warn_threshold",
                    code="disliked_ingredient",
                    ingredient=norm,
                    message=f"Ingredient '{ing.display_name}' matches a recorded customer dislike ('{norm}').",
                )
            )

        # Check if a safe in-stock SKU exists (or safe substitute)
        sku_prod, _ = find_best_sku_for_ingredient(
            norm,
            blocked_allergens=blocked,
            prefer_low_sodium=flags["prefer_low_sodium"],
            is_vegetarian=is_veg,
            is_vegan=is_vegan,
            store_id=store_id,
            db_path=db_path,
        )
        if sku_prod is None:
            hard_blocks.append(
                SafetyViolation(
                    severity="hard_block",
                    code="no_safe_sku",
                    ingredient=norm,
                    message=(
                        f"Ingredient '{ing.display_name}' ({norm}) has no safe, in-stock "
                        f"store SKU matching the customer's hard dietary constraints."
                    ),
                )
            )

    return SafetyComplianceResult(
        is_safe=len(hard_blocks) == 0,
        hard_blocks=hard_blocks,
        warnings=warnings,
        requires_medical_disclaimer=flags["has_medical_conditions"],
    )


def check_dietary_compliance(
    user_id: str,
    skus: list[str],
) -> dict[str, Any]:
    """Tool wrapper: deterministically check whether a list of store SKUs is safe for a customer.

    Args:
        user_id: Unique customer identifier.
        skus: List of store product SKUs to validate.

    Returns:
        Dictionary indicating whether the SKUs are safe, plus any hard blocks or warnings.
    """
    profile = load_user_profile_model(user_id)
    result = check_skus_against_profile(profile=profile, skus=skus)
    return {"status": "success", "compliance": result.model_dump()}
