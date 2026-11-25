"""Deterministic shopping list builder, item deselection, and purchase persistence tools."""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db.database import DEFAULT_STORE_ID, get_connection
from app.schemas import (
    IngredientSpec,
    MealOrderReceipt,
    NutritionSummary,
    RecipeDraft,
    ShoppingListItem,
    ShoppingListResult,
    UserProfile,
)
from app.tools.catalog_tools import (
    find_best_sku_for_ingredient,
    normalize_ingredient_key,
)
from app.tools.nutrition_tools import convert_units_to_base
from app.tools.profile_tools import load_user_profile_model
from app.tools.safety_tools import MEDICAL_DISCLAIMER, extract_safety_flags


def _format_scaled_qty(qty: float, unit: str) -> str:
    rounded = round(qty, 2)
    if rounded == int(rounded):
        return f"{int(rounded)} {unit}"
    return f"{rounded:g} {unit}"


def build_shopping_list_model(
    recipe: RecipeDraft,
    target_servings: int,
    profile: UserProfile,
    store_id: str = DEFAULT_STORE_ID,
    db_path: str | Path | None = None,
) -> ShoppingListResult:
    """Deterministically scale a recipe to target_servings and map ingredients to in-stock SKUs."""
    flags = extract_safety_flags(profile)
    scale = float(target_servings) / float(max(recipe.base_servings, 1))

    items: list[ShoppingListItem] = []
    unmatched: list[str] = []
    pantry_hints: list[str] = []

    # Merge duplicate canonical ingredients if recipe lists the same one twice
    merged_by_sku: dict[str, ShoppingListItem] = {}

    for ing in recipe.ingredients:
        prod, sub_note = find_best_sku_for_ingredient(
            ing.canonical_ingredient,
            blocked_allergens=flags["blocked_allergens"],
            prefer_low_sodium=flags["prefer_low_sodium"],
            is_vegetarian=flags["is_vegetarian"],
            is_vegan=flags["is_vegan"],
            store_id=store_id,
            db_path=db_path,
        )
        if prod is None:
            unmatched.append(ing.canonical_ingredient)
            continue

        scaled_qty = ing.quantity * scale
        req_base, _ = convert_units_to_base(scaled_qty, ing.unit, prod)
        pkg_capacity = float(prod["grams_or_ml_per_package"])
        sku = prod["sku"]

        if sku in merged_by_sku:
            existing = merged_by_sku[sku]
            new_req = round(existing.required_qty_base + req_base, 2)
            packs = max(1, math.ceil(new_req / max(pkg_capacity, 1e-6)))
            existing.required_qty_base = new_req
            existing.packages_to_buy = packs
            existing.line_total_usd = round(packs * existing.unit_price_usd, 2)
            existing.recipe_display_qty = f"{existing.recipe_display_qty} + {_format_scaled_qty(scaled_qty, ing.unit)}"
        else:
            packs = max(1, math.ceil(req_base / max(pkg_capacity, 1e-6)))
            line_total = round(packs * float(prod["unit_price_usd"]), 2)
            pkg_desc = f"{prod['package_qty']:g} {prod['package_unit']}"
            item = ShoppingListItem(
                sku=sku,
                product_name=prod["name"],
                canonical_ingredient=prod["canonical_ingredient"],
                aisle_location=prod["aisle_location"],
                required_qty_base=round(req_base, 2),
                base_unit=prod["base_unit"],
                recipe_display_qty=_format_scaled_qty(scaled_qty, ing.unit),
                packages_to_buy=packs,
                package_description=pkg_desc,
                unit_price_usd=float(prod["unit_price_usd"]),
                line_total_usd=line_total,
                is_pantry_staple=bool(prod["is_pantry_staple"]),
                allergen_tags=prod["allergen_tags"],
                dietary_tags=prod["dietary_tags"],
                substituted_note=sub_note,
            )
            merged_by_sku[sku] = item
            if item.is_pantry_staple:
                pantry_hints.append(item.product_name)

    items = sorted(merged_by_sku.values(), key=lambda x: (x.aisle_location, x.product_name))
    total_usd = round(sum(i.line_total_usd for i in items if not i.deselected_by_user), 2)

    return ShoppingListResult(
        recipe_title=recipe.title,
        servings=target_servings,
        store_id=store_id,
        items=items,
        active_item_count=len(items),
        deselected_item_count=0,
        estimated_total_usd=total_usd,
        pantry_staples_hint=sorted(set(pantry_hints)),
        unmatched_ingredients=unmatched,
    )


def apply_deselections_model(
    shopping_list: ShoppingListResult,
    skus_or_names_to_remove: list[str],
    reason: str = "already_owned",
) -> tuple[ShoppingListResult, list[str]]:
    """Deterministically mark matching shopping list items as deselected and recompute totals.

    Accepts exact SKUs, canonical ingredient keys, or partial product names (e.g. 'cumin', 'olive oil').

    Returns:
        (updated_shopping_list, list_of_removed_product_names)
    """
    tokens = [t.strip().lower() for t in skus_or_names_to_remove if t.strip()]
    normalized_tokens = {normalize_ingredient_key(t) for t in tokens}
    removed_names: list[str] = []

    updated_items: list[ShoppingListItem] = []
    for item in shopping_list.items:
        copy = item.model_copy(deep=True)
        matched = False
        sku_l = copy.sku.lower()
        name_l = copy.product_name.lower()
        canon_l = copy.canonical_ingredient.lower()
        for tok in tokens:
            if tok == sku_l or tok in name_l or tok in canon_l.replace("_", " "):
                matched = True
                break
        if not matched and canon_l in normalized_tokens:
            matched = True

        if matched and not copy.deselected_by_user:
            copy.deselected_by_user = True
            copy.deselect_reason = reason
            removed_names.append(copy.product_name)
        updated_items.append(copy)

    active = [i for i in updated_items if not i.deselected_by_user]
    deselected = [i for i in updated_items if i.deselected_by_user]
    new_total = round(sum(i.line_total_usd for i in active), 2)

    updated = ShoppingListResult(
        recipe_title=shopping_list.recipe_title,
        servings=shopping_list.servings,
        store_id=shopping_list.store_id,
        items=updated_items,
        active_item_count=len(active),
        deselected_item_count=len(deselected),
        estimated_total_usd=new_total,
        pantry_staples_hint=shopping_list.pantry_staples_hint,
        unmatched_ingredients=shopping_list.unmatched_ingredients,
    )
    return updated, removed_names


def parse_deselections_from_text(
    user_text: str, shopping_list: ShoppingListResult
) -> list[str]:
    """Deterministically detect which items in shopping_list are mentioned in user_text."""
    text_l = user_text.lower()
    matched_skus: list[str] = []
    for item in shopping_list.items:
        if item.deselected_by_user:
            continue
        canon_words = item.canonical_ingredient.replace("_", " ")
        name_words = item.product_name.lower()
        # Check SKU, canonical phrase, or primary noun token (e.g., 'cumin', 'butter', 'salt', 'oil')
        candidates = {
            item.sku.lower(),
            canon_words,
            name_words,
        }
        # Add significant words (>=4 chars) from canonical ingredient if distinctive
        for part in canon_words.split():
            if len(part) >= 4 and part not in {"fresh", "dried", "ground", "whole", "organic", "powder", "sauce", "cheese", "bell"}:
                candidates.add(part)
        if any(c in text_l for c in candidates):
            matched_skus.append(item.sku)
    return matched_skus


def save_meal_order_model(
    user_id: str,
    session_id: str,
    recipe: RecipeDraft,
    nutrition: NutritionSummary,
    shopping_list: ShoppingListResult,
    delivery_channel: str = "account_attached",
    db_path: str | Path | None = None,
) -> MealOrderReceipt:
    """Persist a finalized shopping list (including deselected audit items) and recipe to SQLite."""
    order_id = f"ORD-{uuid.uuid4().hex[:10].upper()}"
    now = datetime.now(UTC).isoformat()

    # Ensure user record exists
    load_user_profile_model(user_id, db_path=db_path)

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO meal_orders (
                order_id, user_id, session_id, recipe_title, servings_count,
                recipe_json, nutrition_summary_json, estimated_total_usd,
                delivery_channel, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'finalized', ?)
            """,
            (
                order_id,
                user_id,
                session_id,
                recipe.title,
                shopping_list.servings,
                recipe.model_dump_json(),
                nutrition.model_dump_json(),
                shopping_list.estimated_total_usd,
                delivery_channel,
                now,
            ),
        )
        for item in shopping_list.items:
            display_qty = f"{item.recipe_display_qty} ({item.packages_to_buy} x {item.package_description})"
            conn.execute(
                """
                INSERT INTO meal_order_items (
                    order_id, sku, required_qty_base, packages_to_buy,
                    display_qty, line_total_usd, deselected_by_user, deselect_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    item.sku,
                    item.required_qty_base,
                    item.packages_to_buy,
                    display_qty,
                    item.line_total_usd,
                    1 if item.deselected_by_user else 0,
                    item.deselect_reason,
                ),
            )

    return MealOrderReceipt(
        order_id=order_id,
        user_id=user_id,
        session_id=session_id,
        recipe_title=recipe.title,
        servings_count=shopping_list.servings,
        active_items_count=shopping_list.active_item_count,
        deselected_items_count=shopping_list.deselected_item_count,
        estimated_total_usd=shopping_list.estimated_total_usd,
        delivery_channel=delivery_channel,
        status="finalized",
        created_at=now,
    )


def get_user_meal_orders(
    user_id: str,
    limit: int = 5,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Fetch recent finalized meal orders attached to a customer's account.

    Args:
        user_id: Unique customer identifier.
        limit: Maximum number of recent orders to return.

    Returns:
        Dictionary containing the customer's recent meal orders and item lists.
    """
    with get_connection(db_path) as conn:
        order_rows = conn.execute(
            """
            SELECT * FROM meal_orders
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        orders = []
        for o in order_rows:
            item_rows = conn.execute(
                """
                SELECT moi.*, p.name AS product_name, p.canonical_ingredient
                FROM meal_order_items moi
                JOIN products p ON moi.sku = p.sku
                WHERE moi.order_id = ?
                """,
                (o["order_id"],),
            ).fetchall()
            orders.append(
                {
                    "order_id": o["order_id"],
                    "recipe_title": o["recipe_title"],
                    "servings_count": o["servings_count"],
                    "estimated_total_usd": o["estimated_total_usd"],
                    "delivery_channel": o["delivery_channel"],
                    "status": o["status"],
                    "created_at": o["created_at"],
                    "items": [dict(r) for r in item_rows],
                }
            )
    return {"status": "success", "count": len(orders), "orders": orders}


def format_shopping_list_markdown(
    shopping_list: ShoppingListResult,
    nutrition: NutritionSummary | None = None,
    include_review_prompt: bool = False,
) -> str:
    """Format an aisle-grouped shopping list (plus optional nutrition summary) in clean Markdown."""
    lines: list[str] = [
        f"## Shopping List — {shopping_list.recipe_title} ({shopping_list.servings} meals)",
        "",
    ]

    if nutrition is not None:
        ps = nutrition.per_serving
        badges = ", ".join(b.replace("_", " ").title() for b in nutrition.dietary_badges) or "Standard"
        lines.extend(
            [
                f"**Nutrition (per serving, ~{nutrition.approx_serving_weight_g:.0f}g):** "
                f"{ps.calories:.0f} kcal | Protein: {ps.protein_g:.1f}g | Carbs: {ps.carbs_g:.1f}g | "
                f"Fat: {ps.fat_g:.1f}g | Fiber: {ps.fiber_g:.1f}g | Sodium: {ps.sodium_mg:.0f} mg",
                f"**Dietary Tags:** {badges}",
                "",
            ]
        )
        if nutrition.sodium_warning:
            lines.extend([f"> ⚠️ **Sodium Notice:** {nutrition.sodium_warning}", ""])

    by_aisle: dict[str, list[ShoppingListItem]] = defaultdict(list)
    deselected: list[ShoppingListItem] = []
    for item in shopping_list.items:
        if item.deselected_by_user:
            deselected.append(item)
        else:
            by_aisle[item.aisle_location].append(item)

    for aisle in sorted(by_aisle):
        lines.append(f"### {aisle}")
        for it in by_aisle[aisle]:
            staple_tag = " *(pantry staple)*" if it.is_pantry_staple else ""
            sub_tag = f" — _{it.substituted_note}_" if it.substituted_note else ""
            lines.append(
                f"- **{it.product_name}** (`{it.sku}`){staple_tag}: "
                f"need {it.recipe_display_qty} -> buy **{it.packages_to_buy} x {it.package_description}** "
                f"(${it.line_total_usd:.2f}){sub_tag}"
            )
        lines.append("")

    if deselected:
        lines.append("### Removed (Already Owned)")
        for it in deselected:
            lines.append(f"- ~~{it.product_name}~~ (`{it.sku}`) — removed ({it.deselect_reason or 'deselected'})")
        lines.append("")

    lines.append(
        f"**Estimated Total ({shopping_list.active_item_count} items):** "
        f"**${shopping_list.estimated_total_usd:.2f}**"
    )

    if include_review_prompt:
        lines.append("")
        if shopping_list.pantry_staples_hint:
            staples = ", ".join(shopping_list.pantry_staples_hint[:5])
            lines.append(f"💡 *Common pantry staples on this list:* {staples}.")
        lines.append(
            "Would you like to **remove any items** you already have at home, "
            "**change the number of servings**, or **confirm** to attach this list and recipe to your account?"
        )

    return "\n".join(lines)


def format_recipe_markdown(
    recipe: RecipeDraft,
    target_servings: int,
    nutrition: NutritionSummary,
    include_medical_disclaimer: bool = False,
) -> str:
    """Format the complete scaled recipe and nutritional breakdown in Markdown."""
    scale = float(target_servings) / float(max(recipe.base_servings, 1))
    ps = nutrition.per_serving
    lines = [
        f"## Complete Recipe — {recipe.title}",
        f"**Cuisine:** {recipe.cuisine.title()} | **Difficulty:** {recipe.difficulty.title()} | "
        f"**Prep:** {recipe.prep_time_minutes} min | **Cook:** {recipe.cook_time_minutes} min | "
        f"**Yield:** {target_servings} servings",
        "",
        recipe.summary,
        "",
        "### Scaled Ingredients",
    ]
    for ing in recipe.ingredients:
        scaled = _format_scaled_qty(ing.quantity * scale, ing.unit)
        prep = f", {ing.preparation_note}" if ing.preparation_note else ""
        lines.append(f"- {scaled} {ing.display_name}{prep}")

    lines.extend(["", "### Instructions"])
    for idx, step in enumerate(recipe.steps, start=1):
        lines.append(f"{idx}. {step}")

    if recipe.dietary_notes:
        lines.extend(["", "### Dietary & Personalization Notes"])
        for note in recipe.dietary_notes:
            lines.append(f"- {note}")

    lines.extend(
        [
            "",
            "### Nutritional Summary (Deterministic Store Data)",
            f"- **Per Serving (~{nutrition.approx_serving_weight_g:.0f}g):** "
            f"{ps.calories:.0f} kcal | Protein {ps.protein_g:.1f}g | Carbs {ps.carbs_g:.1f}g | "
            f"Fat {ps.fat_g:.1f}g (Sat Fat {ps.saturated_fat_g:.1f}g) | Fiber {ps.fiber_g:.1f}g | "
            f"Sugar {ps.sugar_g:.1f}g | Sodium {ps.sodium_mg:.0f} mg",
        ]
    )

    if include_medical_disclaimer:
        lines.extend(["", MEDICAL_DISCLAIMER])

    return "\n".join(lines)


def build_shopping_list(
    recipe_title: str,
    ingredients: list[dict[str, Any]],
    base_servings: int,
    target_servings: int,
    user_id: str,
) -> dict[str, Any]:
    """Tool wrapper: build a deterministic, dietary-safe, in-stock shopping list.

    Args:
        recipe_title: Name of the chosen meal.
        ingredients: List of ingredient dicts ({canonical_ingredient, display_name, quantity, unit}).
        base_servings: Servings the base quantities represent.
        target_servings: Desired number of meals/servings.
        user_id: Unique customer identifier for dietary filtering.

    Returns:
        Dictionary containing the structured shopping list and estimated total cost.
    """
    profile = load_user_profile_model(user_id)
    draft = RecipeDraft(
        title=recipe_title,
        cuisine="general",
        difficulty=profile.cooking_skill_level,
        prep_time_minutes=15,
        cook_time_minutes=20,
        base_servings=base_servings,
        summary=recipe_title,
        ingredients=[IngredientSpec(**i) for i in ingredients],
        steps=["Prepare according to recipe."],
    )
    result = build_shopping_list_model(draft, target_servings=target_servings, profile=profile)
    return {"status": "success", "shopping_list": result.model_dump()}
