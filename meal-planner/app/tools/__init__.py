"""Deterministic tools package for the Grocery Store Recipe Planner."""

from .catalog_tools import (
    find_best_sku_for_ingredient,
    list_available_ingredients,
    normalize_ingredient_key,
    search_products,
)
from .nutrition_tools import (
    calculate_recipe_nutrition,
    calculate_recipe_nutrition_model,
    convert_units_to_base,
    get_sku_nutrition,
)
from .profile_tools import (
    get_user_profile,
    load_user_profile_model,
    set_cooking_skill_level,
    upsert_dietary_constraint,
    upsert_user_preference,
)
from .safety_tools import (
    MEDICAL_DISCLAIMER,
    check_dietary_compliance,
    check_skus_against_profile,
    extract_safety_flags,
    validate_recipe_ingredients_safety,
)
from .shopping_tools import (
    apply_deselections_model,
    build_shopping_list,
    build_shopping_list_model,
    format_recipe_markdown,
    format_shopping_list_markdown,
    get_user_meal_orders,
    parse_deselections_from_text,
    save_meal_order_model,
)

__all__ = [
    "MEDICAL_DISCLAIMER",
    "apply_deselections_model",
    "build_shopping_list",
    "build_shopping_list_model",
    "calculate_recipe_nutrition",
    "calculate_recipe_nutrition_model",
    "check_dietary_compliance",
    "check_skus_against_profile",
    "convert_units_to_base",
    "extract_safety_flags",
    "find_best_sku_for_ingredient",
    "format_recipe_markdown",
    "format_shopping_list_markdown",
    "get_sku_nutrition",
    "get_user_meal_orders",
    "get_user_profile",
    "list_available_ingredients",
    "load_user_profile_model",
    "normalize_ingredient_key",
    "parse_deselections_from_text",
    "save_meal_order_model",
    "search_products",
    "set_cooking_skill_level",
    "upsert_dietary_constraint",
    "upsert_user_preference",
    "validate_recipe_ingredients_safety",
]
