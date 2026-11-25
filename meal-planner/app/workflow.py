"""ADK 2.0 Graph Workflow for the Grocery Store Recipe Planner & Shopping List Agent.

Orchestration Architecture (Option A):
- Root agent is a `google.adk.workflow.Workflow` DAG with deterministic routing edges.
- Creative/conversational work is isolated to two scoped LlmAgents:
    1. `meal_discovery_agent` (greeting, preference capture, ideation, meal selection gate)
    2. `recipe_author_agent` (skill- & diet-calibrated structured RecipeDraft via output_schema)
- All database queries, allergen/sodium safety validation, serving scaling, calorie/macro math,
  SKU inventory matching, item deselection, and purchase persistence execute in deterministic
  Python FunctionNodes.
"""

from __future__ import annotations

import json
import re
from typing import Any

from google.adk import Agent, Context, Event, Workflow
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from app.db.database import DEFAULT_STORE_ID, get_connection, init_db
from app.memory import generate_memories_callback
from app.observability import get_tracer
from app.prompts.loader import load_prompt
from app.schemas import NutritionSummary, RecipeDraft, ShoppingListResult, UserProfile
from app.tools.catalog_tools import list_available_ingredients, search_products
from app.tools.nutrition_tools import calculate_recipe_nutrition_model
from app.tools.profile_tools import (
    get_user_profile,
    load_user_profile_model,
    set_cooking_skill_level,
    upsert_dietary_constraint,
    upsert_user_preference,
)
from app.tools.safety_tools import (
    MEDICAL_DISCLAIMER,
    check_skus_against_profile,
    extract_safety_flags,
    validate_recipe_ingredients_safety,
)
from app.tools.shopping_tools import (
    apply_deselections_model,
    build_shopping_list_model,
    format_recipe_markdown,
    format_shopping_list_markdown,
    parse_deselections_from_text,
    save_meal_order_model,
)

MAX_SAFETY_RETRIES = 2

_WORD_NUMBERS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
}


def _ensure_seeded() -> None:
    """Idempotently ensure the local SQLite database has schema and catalog seed data."""
    init_db()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count == 0:
        from data.seed import seed_database

        seed_database()


def _extract_text(raw: Any) -> str:
    """Extract plain user text from ADK types.Content, dict, or str."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, types.Content) and raw.parts:
        return " ".join(p.text.strip() for p in raw.parts if p.text).strip()
    if isinstance(raw, dict):
        if "text" in raw:
            return str(raw["text"]).strip()
        if "parts" in raw and isinstance(raw["parts"], list):
            return " ".join(
                str(p.get("text", "")).strip()
                for p in raw["parts"]
                if isinstance(p, dict) and p.get("text")
            ).strip()
    return str(raw).strip()


def _model_text_event(
    text: str,
    *,
    output: Any = None,
    route: str | None = None,
    state: dict[str, Any] | None = None,
) -> Event:
    """Create an ADK Event that renders text in web/CLI UIs and passes typed output downstream."""
    kwargs: dict[str, Any] = {
        "content": types.Content(role="model", parts=[types.Part.from_text(text=text)]),
        "output": output if output is not None else text,
    }
    if route is not None:
        kwargs["route"] = route
    if state is not None:
        kwargs["state"] = state
    return Event(**kwargs)


def _format_profile_summary(profile: UserProfile) -> str:
    """Render a compact deterministic summary of a customer's profile for LLM context."""
    constraints_str = (
        ", ".join(f"{c.code} ({c.severity})" for c in profile.constraints)
        or "None on file"
    )
    likes = [
        f"{p.category}:{p.value}"
        for p in profile.preferences
        if p.sentiment in {"like", "prefer"}
    ]
    dislikes = [
        f"{p.category}:{p.value}"
        for p in profile.preferences
        if p.sentiment in {"dislike", "avoid"}
    ]
    return (
        f"Customer: {profile.full_name} (user_id={profile.user_id}) | "
        f"Skill: {profile.cooking_skill_level} | Default servings: {profile.default_servings} | "
        f"Daily sodium limit: {profile.daily_sodium_limit_mg or 'unspecified'} mg | "
        f"Dietary constraints: {constraints_str} | "
        f"Likes/Prefers: {', '.join(likes) or 'None'} | "
        f"Dislikes/Avoids: {', '.join(dislikes) or 'None'}"
    )


def _parse_servings_int(text: str, default_servings: int) -> int | None:
    """Deterministically extract a positive integer serving count (1..20) from user text."""
    text_l = text.strip().lower()
    if any(kw in text_l for kw in ("default", "standard", "usual", "same")):
        return default_servings

    digit_match = re.search(r"\b(\d{1,2})\b", text_l)
    if digit_match:
        val = int(digit_match.group(1))
        if 1 <= val <= 20:
            return val

    for word, val in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\b", text_l):
            return val
    return None


# ---------------------------------------------------------------------------
# Gate Tool used exclusively by meal_discovery_agent
# ---------------------------------------------------------------------------


def confirm_meal_selection(
    meal_name: str,
    requested_servings: int,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Confirm the customer's selected meal to unlock recipe authoring, nutrition, and shopping list generation.

    Call this ONLY after the customer explicitly requests a specific meal (e.g., 'kung pao chicken')
    or chooses one of your suggested meals. Pass requested_servings=0 if the customer has not
    stated how many meals/servings they want yet.

    Args:
        meal_name: Name of the confirmed meal to prepare.
        requested_servings: Desired number of meals/servings if explicitly stated (1-20), or 0 if not yet specified.

    Returns:
        Confirmation dictionary recording the selected meal in workflow state.
    """
    cleaned = meal_name.strip()
    tool_context.state["selected_meal"] = cleaned
    tool_context.state["meal_confirmed"] = True
    tool_context.state["safety_retry_count"] = 0
    tool_context.state["safety_violations"] = []
    if 1 <= requested_servings <= 20:
        tool_context.state["servings_count"] = requested_servings
    else:
        tool_context.state["servings_count"] = None
    return {
        "status": "confirmed",
        "selected_meal": cleaned,
        "requested_servings": requested_servings if 1 <= requested_servings <= 20 else None,
    }


# ---------------------------------------------------------------------------
# Deterministic Workflow FunctionNodes
# ---------------------------------------------------------------------------


def load_user_context(ctx: Context, node_input: Any) -> Event:
    """Node 1: Seed DB if empty, hydrate UserProfile into user:* state, and extract user text."""
    tracer = get_tracer("meal_planner.workflow")
    with tracer.start_as_current_span("node.load_user_context") as span:
        _ensure_seeded()
        user_id = ctx.session.user_id or "cust_guest"
        profile = load_user_profile_model(user_id)
        flags = extract_safety_flags(profile)
        user_text = _extract_text(node_input)

        span.set_attribute("meal_planner.user_id", user_id)
        span.set_attribute("meal_planner.skill_level", profile.cooking_skill_level)
        span.set_attribute("meal_planner.constraints_count", len(profile.constraints))

        state_update: dict[str, Any] = {
            "user:user_id": profile.user_id,
            "user:full_name": profile.full_name,
            "user:cooking_skill_level": profile.cooking_skill_level,
            "user:profile_summary": _format_profile_summary(profile),
            "user:requires_medical_disclaimer": flags["has_medical_conditions"],
            "last_user_message": user_text,
            "session_id": ctx.session.id,
        }
        if not ctx.state.get("workflow_stage"):
            state_update["workflow_stage"] = "meal_selection"

        return Event(output=user_text, state=state_update)


def workflow_router(ctx: Context, node_input: str) -> Event:
    """Node 2: Deterministic stage router enforcing strict stage gating across turns."""
    tracer = get_tracer("meal_planner.workflow")
    user_text = (node_input or "").strip()
    text_l = user_text.lower()
    stage = str(ctx.state.get("workflow_stage") or "meal_selection")

    with tracer.start_as_current_span("node.workflow_router") as span:
        # Allow explicit restart from any stage
        if any(
            phrase in text_l
            for phrase in ("start over", "different meal", "new meal", "reset", "cancel order")
        ):
            stage = "meal_selection"
            span.set_attribute("meal_planner.route", "meal_selection")
            return Event(
                output=user_text,
                route="meal_selection",
                state={
                    "workflow_stage": "meal_selection",
                    "meal_confirmed": False,
                    "selected_meal": None,
                    "servings_count": None,
                    "draft_recipe": None,
                    "shopping_list": None,
                    "safety_retry_count": 0,
                    "safety_violations": [],
                },
            )

        if stage == "sizing" and ctx.state.get("draft_recipe"):
            route = "sizing"
        elif stage == "shopping_list_review" and ctx.state.get("shopping_list"):
            route = "shopping_list_review"
        else:
            route = "meal_selection"

        span.set_attribute("meal_planner.stage", stage)
        span.set_attribute("meal_planner.route", route)
        return Event(output=user_text, route=route)


def meal_selection_gate(ctx: Context, node_input: Any) -> Event:
    """Gate 1: Blocks downstream recipe/nutrition/SKU nodes until a meal is confirmed."""
    tracer = get_tracer("meal_planner.workflow")
    with tracer.start_as_current_span("node.meal_selection_gate") as span:
        confirmed = bool(ctx.state.get("meal_confirmed", False))
        selected = ctx.state.get("selected_meal")
        if confirmed and selected:
            span.set_attribute("meal_planner.route", "meal_selected")
            span.set_attribute("meal_planner.selected_meal", str(selected))
            return Event(
                output={"selected_meal": selected},
                route="meal_selected",
                state={"workflow_stage": "recipe_authoring"},
            )
        span.set_attribute("meal_planner.route", "await_selection")
        return Event(
            output={"status": "awaiting_meal_selection"},
            route="await_selection",
            state={"workflow_stage": "meal_selection"},
        )


def await_meal_selection(ctx: Context, node_input: Any) -> Event:
    """Terminal no-op for Gate 1 when meal_discovery_agent is waiting on customer choice."""
    return Event(output={"status": "awaiting_meal_selection"})


def prepare_recipe_context(ctx: Context, node_input: Any) -> Event:
    """Deterministically build the grounded prompt payload for recipe_author_agent."""
    user_id = str(ctx.state.get("user:user_id") or ctx.session.user_id or "cust_guest")
    profile = load_user_profile_model(user_id)
    selected_meal = str(ctx.state.get("selected_meal") or "Healthy Chef's Choice")
    violations = ctx.state.get("safety_violations") or []
    available = list_available_ingredients(DEFAULT_STORE_ID)

    lines = [
        f"Selected Meal: {selected_meal}",
        f"Customer Profile: {_format_profile_summary(profile)}",
        f"Required Difficulty: {profile.cooking_skill_level}",
        "Base Servings: 2",
        f"Available Store Canonical Ingredients (USE ONLY THESE KEYS): {', '.join(available)}",
    ]
    if violations:
        lines.append(
            "PREVIOUS DRAFT FAILED DETERMINISTIC SAFETY CHECK — YOU MUST FIX THESE VIOLATIONS:"
        )
        for v in violations:
            lines.append(f"- {v}")

    return Event(output="\n".join(lines))


def validate_meal_safety(ctx: Context, node_input: Any) -> Event:
    """Deterministically validate RecipeDraft against hard allergen, diet, and stock constraints."""
    tracer = get_tracer("meal_planner.workflow")
    with tracer.start_as_current_span("node.validate_meal_safety") as span:
        raw_recipe = ctx.state.get("draft_recipe") or node_input
        if isinstance(raw_recipe, str):
            raw_recipe = json.loads(raw_recipe)
        if isinstance(raw_recipe, RecipeDraft):
            recipe = raw_recipe
        else:
            recipe = RecipeDraft(**raw_recipe)

        user_id = str(ctx.state.get("user:user_id") or ctx.session.user_id or "cust_guest")
        profile = load_user_profile_model(user_id)
        result = validate_recipe_ingredients_safety(profile, recipe.ingredients)
        retry_count = int(ctx.state.get("safety_retry_count") or 0)

        span.set_attribute("meal_planner.is_safe", result.is_safe)
        span.set_attribute("meal_planner.hard_blocks", len(result.hard_blocks))
        span.set_attribute("meal_planner.retry_count", retry_count)

        if not result.is_safe and retry_count < MAX_SAFETY_RETRIES:
            violation_msgs = [v.message for v in result.hard_blocks]
            span.set_attribute("meal_planner.route", "unsafe_retry")
            return Event(
                output={"violations": violation_msgs},
                route="unsafe_retry",
                state={
                    "safety_retry_count": retry_count + 1,
                    "safety_violations": violation_msgs,
                },
            )

        servings = ctx.state.get("servings_count")
        if isinstance(servings, int) and 1 <= servings <= 20:
            span.set_attribute("meal_planner.route", "has_servings")
            return Event(
                output=recipe.model_dump(),
                route="has_servings",
                state={
                    "draft_recipe": recipe.model_dump(),
                    "safety_warnings": [w.model_dump() for w in result.warnings],
                    "workflow_stage": "sizing",
                },
            )

        span.set_attribute("meal_planner.route", "ask_servings")
        return Event(
            output=recipe.model_dump(),
            route="ask_servings",
            state={
                "draft_recipe": recipe.model_dump(),
                "safety_warnings": [w.model_dump() for w in result.warnings],
                "workflow_stage": "sizing",
            },
        )


def present_sizing_prompt(ctx: Context, node_input: Any) -> Event:
    """Gate 2 prompt: Deterministically compute baseline nutrition and ask how many meals to plan."""
    user_id = str(ctx.state.get("user:user_id") or ctx.session.user_id or "cust_guest")
    profile = load_user_profile_model(user_id)
    flags = extract_safety_flags(profile)
    recipe = RecipeDraft(**ctx.state["draft_recipe"])

    baseline_servings = profile.default_servings or recipe.base_servings
    summary, _ = calculate_recipe_nutrition_model(
        ingredients=recipe.ingredients,
        base_servings=recipe.base_servings,
        target_servings=baseline_servings,
        blocked_allergens=flags["blocked_allergens"],
        prefer_low_sodium=flags["prefer_low_sodium"],
        is_vegetarian=flags["is_vegetarian"],
        is_vegan=flags["is_vegan"],
        sodium_limit_per_serving_mg=flags["sodium_per_meal_limit_mg"],
    )
    ps = summary.per_serving
    badges = ", ".join(b.replace("_", " ").title() for b in summary.dietary_badges) or "Standard"

    lines = [
        f"Great choice! I've tailored **{recipe.title}** for your **{recipe.difficulty}** skill level.",
        "",
        f"### Nutrition Preview (per serving, ~{summary.approx_serving_weight_g:.0f}g)",
        f"- **Calories:** {ps.calories:.0f} kcal",
        f"- **Protein:** {ps.protein_g:.1f}g | **Carbs:** {ps.carbs_g:.1f}g | **Fat:** {ps.fat_g:.1f}g | **Fiber:** {ps.fiber_g:.1f}g",
        f"- **Sodium:** {ps.sodium_mg:.0f} mg | **Dietary Tags:** {badges}",
    ]
    if summary.sodium_warning:
        lines.append(f"- ⚠️ {summary.sodium_warning}")
    if flags["has_medical_conditions"]:
        lines.extend(["", MEDICAL_DISCLAIMER])
    lines.extend(
        [
            "",
            f"How many **meals / servings** would you like to plan for this recipe? "
            f"(For example, reply `2` or `4`, or say `default` for {baseline_servings}.)",
        ]
    )

    return _model_text_event(
        "\n".join(lines),
        output={"stage": "sizing", "baseline_nutrition": summary.model_dump()},
        state={"workflow_stage": "sizing"},
    )


def parse_servings_node(ctx: Context, node_input: str) -> Event:
    """Gate 2 handler: Deterministically parse the customer's chosen number of meals."""
    user_id = str(ctx.state.get("user:user_id") or ctx.session.user_id or "cust_guest")
    profile = load_user_profile_model(user_id)
    servings = _parse_servings_int(node_input, profile.default_servings)

    if servings is None:
        return _model_text_event(
            "Please let me know how many meals/servings you'd like to make as a number between 1 and 20 "
            "(for example, `2` or `4`).",
            output={"error": "invalid_servings"},
            route="invalid_servings",
            state={"workflow_stage": "sizing"},
        )

    return Event(
        output={"servings_count": servings},
        route="servings_confirmed",
        state={"servings_count": servings, "workflow_stage": "shopping_list_generation"},
    )


def await_servings_retry(ctx: Context, node_input: Any) -> Event:
    """Terminal no-op when servings input could not be parsed."""
    return Event(output={"status": "awaiting_valid_servings"})


def compute_nutrition_and_scale(ctx: Context, node_input: Any) -> Event:
    """Deterministically scale recipe nutrition to the customer's chosen servings_count."""
    tracer = get_tracer("meal_planner.workflow")
    with tracer.start_as_current_span("node.compute_nutrition_and_scale") as span:
        user_id = str(ctx.state.get("user:user_id") or ctx.session.user_id or "cust_guest")
        profile = load_user_profile_model(user_id)
        flags = extract_safety_flags(profile)
        recipe = RecipeDraft(**ctx.state["draft_recipe"])
        servings = int(ctx.state.get("servings_count") or profile.default_servings or 2)

        summary, matched_skus = calculate_recipe_nutrition_model(
            ingredients=recipe.ingredients,
            base_servings=recipe.base_servings,
            target_servings=servings,
            blocked_allergens=flags["blocked_allergens"],
            prefer_low_sodium=flags["prefer_low_sodium"],
            is_vegetarian=flags["is_vegetarian"],
            is_vegan=flags["is_vegan"],
            sodium_limit_per_serving_mg=flags["sodium_per_meal_limit_mg"],
        )

        span.set_attribute("meal_planner.servings", servings)
        span.set_attribute("meal_planner.kcal_per_serving", summary.per_serving.calories)
        span.set_attribute("meal_planner.sodium_mg_per_serving", summary.per_serving.sodium_mg)

        return Event(
            output=summary.model_dump(),
            state={
                "nutrition_summary": summary.model_dump(),
                "matched_skus": matched_skus,
            },
        )


def map_inventory_skus(ctx: Context, node_input: Any) -> Event:
    """Deterministically map scaled recipe ingredients to safe, in-stock store SKUs."""
    tracer = get_tracer("meal_planner.workflow")
    with tracer.start_as_current_span("node.map_inventory_skus") as span:
        user_id = str(ctx.state.get("user:user_id") or ctx.session.user_id or "cust_guest")
        profile = load_user_profile_model(user_id)
        recipe = RecipeDraft(**ctx.state["draft_recipe"])
        servings = int(ctx.state.get("servings_count") or profile.default_servings or 2)
        nutrition = NutritionSummary(**ctx.state["nutrition_summary"])

        shopping_list = build_shopping_list_model(
            recipe=recipe,
            target_servings=servings,
            profile=profile,
            store_id=DEFAULT_STORE_ID,
        )

        # Final deterministic safety double-check on every mapped SKU
        skus = [item.sku for item in shopping_list.items]
        compliance = check_skus_against_profile(profile, skus, nutrition_summary=nutrition)
        if not compliance.is_safe:
            blocked_skus = {v.sku for v in compliance.hard_blocks if v.sku}
            safe_items = [i for i in shopping_list.items if i.sku not in blocked_skus]
            shopping_list.items = safe_items
            shopping_list.active_item_count = len(safe_items)
            shopping_list.estimated_total_usd = round(
                sum(i.line_total_usd for i in safe_items), 2
            )

        span.set_attribute("meal_planner.sku_count", shopping_list.active_item_count)
        span.set_attribute("meal_planner.estimated_total_usd", shopping_list.estimated_total_usd)

        return Event(
            output=shopping_list.model_dump(),
            state={
                "shopping_list": shopping_list.model_dump(),
                "workflow_stage": "shopping_list_review",
            },
        )


def present_shopping_list(ctx: Context, node_input: Any) -> Event:
    """Gate 3 prompt: Present aisle-sorted shopping list and invite deselection or confirmation."""
    shopping_list = ShoppingListResult(**ctx.state["shopping_list"])
    nutrition = (
        NutritionSummary(**ctx.state["nutrition_summary"])
        if ctx.state.get("nutrition_summary")
        else None
    )
    removed_msg = ""
    if isinstance(node_input, dict) and node_input.get("removed_names"):
        removed_str = ", ".join(node_input["removed_names"])
        removed_msg = f"Removed **{removed_str}** from your shopping list.\n\n"

    md = removed_msg + format_shopping_list_markdown(
        shopping_list=shopping_list,
        nutrition=nutrition,
        include_review_prompt=True,
    )
    if ctx.state.get("user:requires_medical_disclaimer"):
        md += f"\n\n{MEDICAL_DISCLAIMER}"

    return _model_text_event(
        md,
        output=shopping_list.model_dump(),
        state={"workflow_stage": "shopping_list_review"},
    )


def review_shopping_list_node(ctx: Context, node_input: str) -> Event:
    """Gate 3 handler: Deterministically route between item removal, resizing, or confirmation."""
    tracer = get_tracer("meal_planner.workflow")
    text = (node_input or "").strip()
    text_l = text.lower()
    shopping_list = ShoppingListResult(**ctx.state["shopping_list"])

    with tracer.start_as_current_span("node.review_shopping_list") as span:
        # 1. Check if customer wants to resize servings
        if any(kw in text_l for kw in ("serving", "meals", "portion", "scale", "change to", "make it")):
            new_servings = _parse_servings_int(text, shopping_list.servings)
            if new_servings is not None and new_servings != shopping_list.servings:
                span.set_attribute("meal_planner.route", "change_servings")
                return Event(
                    output={"servings_count": new_servings},
                    route="change_servings",
                    state={"servings_count": new_servings},
                )

        # 2. Check for item deselections (e.g., "I already have cumin", "remove olive oil and salt")
        deselect_intent = any(
            kw in text_l
            for kw in (
                "remove", "deselect", "drop", "skip", "omit", "without",
                "already have", "already own", "got ", "have ", "don't need", "dont need",
            )
        )
        matched_skus = parse_deselections_from_text(text, shopping_list)
        if matched_skus and (deselect_intent or not any(c in text_l for c in ("confirm", "send", "finalize"))):
            span.set_attribute("meal_planner.route", "remove_items")
            span.set_attribute("meal_planner.removed_count", len(matched_skus))
            return Event(
                output={"skus_to_remove": matched_skus},
                route="remove_items",
            )

        # 3. Check for final confirmation
        confirm_intent = any(
            kw in text_l
            for kw in (
                "confirm", "looks good", "good to go", "send", "finalize",
                "yes", "approve", "done", "checkout", "save", "all set", "keep all", "no changes",
            )
        )
        if confirm_intent:
            span.set_attribute("meal_planner.route", "confirm_order")
            return Event(output={"confirmed": True}, route="confirm_order")

        # 4. Ask cleanly for clarification
        span.set_attribute("meal_planner.route", "clarify_review")
        return _model_text_event(
            "I didn't match an item to remove from your current list. "
            "Reply with the item name(s) you already own (e.g., `remove cumin and olive oil`), "
            "a new serving count (e.g., `change to 4 meals`), or say **`confirm`** to finalize "
            "and attach your shopping list and recipe to your account.",
            output={"status": "clarify_review"},
            route="clarify_review",
            state={"workflow_stage": "shopping_list_review"},
        )


def await_review_clarification(ctx: Context, node_input: Any) -> Event:
    """Terminal no-op when Gate 3 asks for clarification."""
    return Event(output={"status": "awaiting_list_review"})


def apply_list_edits(ctx: Context, node_input: dict[str, Any]) -> Event:
    """Deterministically apply user item deselections and update workflow state."""
    shopping_list = ShoppingListResult(**ctx.state["shopping_list"])
    skus = node_input.get("skus_to_remove", [])
    updated, removed_names = apply_deselections_model(
        shopping_list, skus, reason="already_owned"
    )
    return Event(
        output={"removed_names": removed_names, "shopping_list": updated.model_dump()},
        state={"shopping_list": updated.model_dump()},
    )


def persist_meal_order(ctx: Context, node_input: Any) -> Event:
    """Stage 4: Persist finalized list + recipe to meal_orders and emit final message."""
    tracer = get_tracer("meal_planner.workflow")
    with tracer.start_as_current_span("node.persist_meal_order") as span:
        user_id = str(ctx.state.get("user:user_id") or ctx.session.user_id or "cust_guest")
        session_id = str(ctx.state.get("session_id") or ctx.session.id)
        recipe = RecipeDraft(**ctx.state["draft_recipe"])
        nutrition = NutritionSummary(**ctx.state["nutrition_summary"])
        shopping_list = ShoppingListResult(**ctx.state["shopping_list"])
        requires_disclaimer = bool(ctx.state.get("user:requires_medical_disclaimer", False))

        receipt = save_meal_order_model(
            user_id=user_id,
            session_id=session_id,
            recipe=recipe,
            nutrition=nutrition,
            shopping_list=shopping_list,
            delivery_channel="account_attached",
        )

        span.set_attribute("meal_planner.order_id", receipt.order_id)
        span.set_attribute("meal_planner.active_items", receipt.active_items_count)
        span.set_attribute("meal_planner.deselected_items", receipt.deselected_items_count)
        span.set_attribute("meal_planner.estimated_total_usd", receipt.estimated_total_usd)

        shopping_md = format_shopping_list_markdown(
            shopping_list=shopping_list,
            nutrition=nutrition,
            include_review_prompt=False,
        )
        recipe_md = format_recipe_markdown(
            recipe=recipe,
            target_servings=shopping_list.servings,
            nutrition=nutrition,
            include_medical_disclaimer=requires_disclaimer,
        )
        final_text = (
            f"Your meal plan and shopping list have been attached to your account (**Order `{receipt.order_id}`**)!\n\n"
            f"{shopping_md}\n\n---\n\n{recipe_md}"
        )

        return _model_text_event(
            final_text,
            output=receipt.model_dump(),
            state={
                "last_order_id": receipt.order_id,
                "workflow_stage": "meal_selection",
                "meal_confirmed": False,
                "selected_meal": None,
                "servings_count": None,
            },
        )


# ---------------------------------------------------------------------------
# Factory: Build the complete ADK 2.0 Workflow
# ---------------------------------------------------------------------------


def build_meal_planner_workflow(
    model_name: str,
    root_agent_name: str = "meal_planner",
) -> Workflow:
    """Construct the complete ADK 2.0 graph Workflow for the Grocery Store Recipe Planner."""
    discovery_prompt, _ = load_prompt("meal_discovery")
    author_prompt, _ = load_prompt("recipe_author")

    model = Gemini(
        model=model_name,
        retry_options=types.HttpRetryOptions(attempts=3),
    )

    meal_discovery_agent = Agent(
        name="meal_discovery_agent",
        model=model,
        mode="single_turn",
        description="Greets customers, recalls dietary needs/preferences, suggests meals, and confirms meal selection.",
        instruction=(
            f"{discovery_prompt}\n\n"
            "Active customer context:\n{user:profile_summary}\n"
            "Current session ID: {session_id}\n"
            "Current user ID: {user:user_id}"
        ),
        tools=[
            PreloadMemoryTool(),
            get_user_profile,
            upsert_user_preference,
            upsert_dietary_constraint,
            set_cooking_skill_level,
            search_products,
            confirm_meal_selection,
        ],
        after_agent_callback=generate_memories_callback,
    )

    recipe_author_agent = Agent(
        name="recipe_author_agent",
        model=model,
        mode="single_turn",
        description="Authors structured, skill- and diet-calibrated recipes grounded in store canonical ingredients.",
        instruction=author_prompt,
        output_schema=RecipeDraft,
        output_key="draft_recipe",
        include_contents="none",
    )

    return Workflow(
        name=root_agent_name,
        description=(
            "Grocery store recipe planner and shopping list agentic workflow built on ADK 2.0 "
            "with deterministic nutrition/inventory/safety tools and cross-session memory."
        ),
        edges=[
            # Entry: hydrate user context and route deterministically by workflow_stage
            ("START", load_user_context, workflow_router),
            (
                workflow_router,
                {
                    "meal_selection": meal_discovery_agent,
                    "sizing": parse_servings_node,
                    "shopping_list_review": review_shopping_list_node,
                },
            ),
            # Stage 1: Meal Selection Gate
            (meal_discovery_agent, meal_selection_gate),
            (
                meal_selection_gate,
                {
                    "await_selection": await_meal_selection,
                    "meal_selected": prepare_recipe_context,
                },
            ),
            # Stage 1b -> Stage 2: Recipe Authoring + Deterministic Safety Loop
            (prepare_recipe_context, recipe_author_agent, validate_meal_safety),
            (
                validate_meal_safety,
                {
                    "unsafe_retry": prepare_recipe_context,
                    "ask_servings": present_sizing_prompt,
                    "has_servings": compute_nutrition_and_scale,
                },
            ),
            # Stage 2: Serving Sizing Gate -> Deterministic Nutrition & SKU Mapping
            (
                parse_servings_node,
                {
                    "invalid_servings": await_servings_retry,
                    "servings_confirmed": compute_nutrition_and_scale,
                },
            ),
            (compute_nutrition_and_scale, map_inventory_skus, present_shopping_list),
            # Stage 3: Shopping List Review & Deselection Gate -> Stage 4 Persistence
            (
                review_shopping_list_node,
                {
                    "remove_items": apply_list_edits,
                    "change_servings": compute_nutrition_and_scale,
                    "confirm_order": persist_meal_order,
                    "clarify_review": await_review_clarification,
                },
            ),
            (apply_list_edits, present_shopping_list),
        ],
    )
