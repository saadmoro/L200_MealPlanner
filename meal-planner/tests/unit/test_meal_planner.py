"""Deterministic unit & integration tests for DB schemas, tools, plugins, memory, OTel, and ADK 2.0 Workflow."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.adk.sessions.session import Session
from google.genai import types

from app.memory import SqliteMemoryService
from app.observability import configure_local_otel
from app.plugins import DietarySafetyPlugin, ObservabilityPlugin
from app.schemas import IngredientSpec, RecipeDraft
from app.tools import (
    MEDICAL_DISCLAIMER,
    apply_deselections_model,
    build_shopping_list_model,
    calculate_recipe_nutrition_model,
    check_skus_against_profile,
    find_best_sku_for_ingredient,
    get_user_meal_orders,
    load_user_profile_model,
    parse_deselections_from_text,
    save_meal_order_model,
    set_cooking_skill_level,
    upsert_dietary_constraint,
    upsert_user_preference,
)
from app.workflow import build_meal_planner_workflow
from data.seed import seed_database


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create and seed an isolated SQLite database for each test."""
    db_file = tmp_path / "test_grocery.db"
    monkeypatch.setenv("MEAL_PLANNER_DB_PATH", str(db_file))
    seed_database(db_file)
    return db_file


def _sample_mediterranean_chicken_recipe() -> RecipeDraft:
    return RecipeDraft(
        title="Lemon Herb Chicken Souvlaki Bowls",
        cuisine="mediterranean",
        difficulty="intermediate",
        prep_time_minutes=15,
        cook_time_minutes=20,
        base_servings=2,
        summary="Bright lemon, garlic, and oregano chicken served over jasmine rice with crisp vegetables.",
        ingredients=[
            IngredientSpec(canonical_ingredient="chicken_breast", display_name="Chicken Breast", quantity=0.75, unit="lb"),
            IngredientSpec(canonical_ingredient="jasmine_rice", display_name="Jasmine Rice", quantity=1.0, unit="cup"),
            IngredientSpec(canonical_ingredient="bell_pepper", display_name="Red Bell Pepper", quantity=1.0, unit="count"),
            IngredientSpec(canonical_ingredient="cucumber", display_name="English Cucumber", quantity=0.5, unit="count"),
            IngredientSpec(canonical_ingredient="olive_oil", display_name="Extra Virgin Olive Oil", quantity=2.0, unit="tbsp"),
            IngredientSpec(canonical_ingredient="lemon", display_name="Fresh Lemon", quantity=1.0, unit="count"),
            IngredientSpec(canonical_ingredient="cumin_powder", display_name="Ground Cumin", quantity=1.0, unit="tsp"),
            IngredientSpec(canonical_ingredient="dried_oregano", display_name="Dried Oregano", quantity=1.0, unit="tsp"),
        ],
        steps=[
            "Marinate diced chicken breast with lemon juice, olive oil, oregano, and cumin.",
            "Cook jasmine rice according to package directions.",
            "Sear chicken in a hot skillet until cooked through (165F).",
            "Assemble bowls with rice, chicken, diced bell pepper, and cucumber.",
        ],
        dietary_notes=["Certified gluten-free ingredients.", "Naturally low sodium for blood pressure support."],
    )


def test_seed_database_integrity(temp_db: Path) -> None:
    """Verify catalog, nutrition, inventory, and Malcom Munson's fixture profile."""
    profile = load_user_profile_model("cust_malcom_munson", db_path=temp_db)
    assert profile.full_name == "Malcom Munson"
    assert profile.cooking_skill_level == "intermediate"
    assert profile.daily_sodium_limit_mg == 1500
    codes = {(c.code, c.severity) for c in profile.constraints}
    assert ("celiac_disease", "hard_block") in codes
    assert ("gluten", "hard_block") in codes
    assert ("hypertension", "warn_threshold") in codes
    prefs = {(p.category, p.value, p.sentiment) for p in profile.preferences}
    assert ("cuisine", "mediterranean", "like") in prefs
    assert ("protein", "chicken", "prefer") in prefs
    assert ("ingredient", "eggplant", "dislike") in prefs


@pytest.mark.asyncio
async def test_profile_and_sqlite_memory_persist_across_restarts(temp_db: Path) -> None:
    """Preferences, skill level, and episodic memories survive across sessions and restarts."""
    res_pref = upsert_user_preference("cust_new_shopper", "ingredient", "eggplant", "dislike", "sess-1")
    assert res_pref["status"] == "success"
    res_skill = set_cooking_skill_level("cust_new_shopper", "beginner")
    assert res_skill["status"] == "success"
    res_cond = upsert_dietary_constraint("cust_new_shopper", "medical_condition", "celiac_disease", "hard_block", "Celiac")
    assert res_cond["status"] == "success"

    reloaded = load_user_profile_model("cust_new_shopper", db_path=temp_db)
    assert reloaded.cooking_skill_level == "beginner"
    assert any(c.code == "gluten" and c.severity == "hard_block" for c in reloaded.constraints)
    assert any(p.value == "eggplant" and p.sentiment == "dislike" for p in reloaded.preferences)

    # Write episodic memory in Session 1
    mem1 = SqliteMemoryService(db_path=temp_db)
    session1 = Session(
        id="sess-1",
        app_name="app",
        user_id="cust_new_shopper",
        events=[
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="I have celiac disease and hate eggplant, keep recipes easy.")],
                ),
            )
        ],
    )
    await mem1.add_session_to_memory(session1)

    # Simulate process restart with a brand-new SqliteMemoryService instance in Session 2
    mem2 = SqliteMemoryService(db_path=temp_db)
    found = await mem2.search_memory(app_name="app", user_id="cust_new_shopper", query="dinner ideas")
    assert len(found.memories) >= 1
    assert any("celiac" in m.content.parts[0].text.lower() for m in found.memories)


def test_deterministic_nutrition_calculation_and_scaling(temp_db: Path) -> None:
    """4 servings doubles total recipe nutrients while keeping per-serving macros identical."""
    recipe = _sample_mediterranean_chicken_recipe()
    nutr_2, skus_2 = calculate_recipe_nutrition_model(
        ingredients=recipe.ingredients,
        base_servings=2,
        target_servings=2,
        blocked_allergens={"gluten"},
        prefer_low_sodium=True,
        sodium_limit_per_serving_mg=600.0,
        db_path=temp_db,
    )
    nutr_4, _ = calculate_recipe_nutrition_model(
        ingredients=recipe.ingredients,
        base_servings=2,
        target_servings=4,
        blocked_allergens={"gluten"},
        prefer_low_sodium=True,
        sodium_limit_per_serving_mg=600.0,
        db_path=temp_db,
    )
    assert len(skus_2) == len(recipe.ingredients)
    assert nutr_2.unmatched_ingredients == []
    assert nutr_2.per_serving.calories > 300
    assert nutr_2.per_serving.protein_g > 30
    assert "gluten_free" in nutr_2.dietary_badges
    assert "low_sodium" in nutr_2.dietary_badges
    assert nutr_2.sodium_warning is None
    assert abs(nutr_4.per_serving.calories - nutr_2.per_serving.calories) < 1.0
    assert abs(nutr_4.total_recipe.calories - (2.0 * nutr_2.total_recipe.calories)) < 2.0


def test_hard_allergen_blocks_and_safe_substitutions(temp_db: Path) -> None:
    """Celiac, vegetarian, peanut allergy, and out-of-stock SKUs are deterministically enforced."""
    malcom = load_user_profile_model("cust_malcom_munson", db_path=temp_db)

    # Standard wheat soy sauce & wheat pasta MUST be hard-blocked for Malcom
    comp = check_skus_against_profile(
        malcom, ["SKU-SOY-STD-15OZ", "SKU-PASTA-WH-16OZ"], db_path=temp_db
    )
    assert comp.is_safe is False
    assert len(comp.hard_blocks) == 2
    assert comp.requires_medical_disclaimer is True
    assert comp.hard_blocks[0].suggested_substitute_sku == "SKU-TAMARI-GF-LS-10OZ"
    assert comp.hard_blocks[1].suggested_substitute_sku == "SKU-PASTA-GF-12OZ"

    # Out-of-stock pine nuts deterministically substitute in-stock cashews
    prod, sub_note = find_best_sku_for_ingredient("pine_nuts", blocked_allergens=set(), db_path=temp_db)
    assert prod is not None
    assert prod["sku"] == "SKU-CASH-UNSLT-10OZ"
    assert sub_note is not None

    # Vegetarian + peanut allergy (Priya) hard-blocks chicken and peanuts
    priya = load_user_profile_model("cust_priya_patel", db_path=temp_db)
    comp_priya = check_skus_against_profile(
        priya, ["SKU-CHK-BRST-16OZ", "SKU-PNUT-UNSLT-12OZ"], db_path=temp_db
    )
    assert comp_priya.is_safe is False
    assert len(comp_priya.hard_blocks) == 2


def test_shopping_list_scaling_deselection_and_order_persistence(temp_db: Path) -> None:
    """Scaling 2->4 meals updates package counts; deselection removes owned items & records audit trail."""
    malcom = load_user_profile_model("cust_malcom_munson", db_path=temp_db)
    recipe = _sample_mediterranean_chicken_recipe()

    list_2 = build_shopping_list_model(recipe, target_servings=2, profile=malcom, db_path=temp_db)
    list_4 = build_shopping_list_model(recipe, target_servings=4, profile=malcom, db_path=temp_db)

    chicken_2 = next(i for i in list_2.items if i.canonical_ingredient == "chicken_breast")
    chicken_4 = next(i for i in list_4.items if i.canonical_ingredient == "chicken_breast")
    # 0.75 lb -> 1 pack; 1.5 lb -> 2 packs
    assert chicken_2.packages_to_buy == 1
    assert chicken_4.packages_to_buy == 2
    assert list_4.estimated_total_usd > list_2.estimated_total_usd

    # User says they already have cumin powder and olive oil
    matched = parse_deselections_from_text("I already have cumin powder and olive oil", list_4)
    assert "SKU-SPC-CUMIN-2OZ" in matched
    assert "SKU-OIL-OLV-16OZ" in matched

    updated, removed = apply_deselections_model(list_4, matched)
    assert len(removed) == 2
    assert updated.deselected_item_count == 2
    assert updated.active_item_count == list_4.active_item_count - 2
    assert updated.estimated_total_usd < list_4.estimated_total_usd

    nutr_4, _ = calculate_recipe_nutrition_model(
        recipe.ingredients, 2, 4, {"gluten"}, prefer_low_sodium=True, db_path=temp_db
    )
    receipt = save_meal_order_model(
        user_id="cust_malcom_munson",
        session_id="sess-test-1",
        recipe=recipe,
        nutrition=nutr_4,
        shopping_list=updated,
        db_path=temp_db,
    )
    assert receipt.order_id.startswith("ORD-")
    assert receipt.deselected_items_count == 2

    orders = get_user_meal_orders("cust_malcom_munson", db_path=temp_db)
    assert orders["count"] == 1
    saved_items = orders["orders"][0]["items"]
    deselected_rows = [it for it in saved_items if it["deselected_by_user"] == 1]
    assert len(deselected_rows) == 2


@pytest.mark.asyncio
async def test_dietary_safety_plugin_blocks_allergen_and_adds_disclaimer(temp_db: Path) -> None:
    """Runner-wide DietarySafetyPlugin blocks allergen SKUs in tool results and appends medical disclaimer."""
    plugin = DietarySafetyPlugin(db_path=str(temp_db))
    fake_tool = SimpleNamespace(name="search_products")
    fake_tool_ctx = SimpleNamespace(state={"user:user_id": "cust_malcom_munson"})

    blocked = await plugin.after_tool_callback(
        tool=fake_tool,
        tool_args={},
        tool_context=fake_tool_ctx,
        result={"products": [{"sku": "SKU-SOY-STD-15OZ", "name": "Wheat Soy Sauce"}]},
    )
    assert blocked is not None
    assert blocked["status"] == "blocked_by_safety_plugin"

    fake_cb_ctx = SimpleNamespace(state={"user:requires_medical_disclaimer": True})
    llm_resp = LlmResponse(
        content=types.Content(role="model", parts=[types.Part.from_text(text="Here is a Mediterranean chicken idea.")])
    )
    modified = await plugin.after_model_callback(callback_context=fake_cb_ctx, llm_response=llm_resp)
    assert modified is not None
    assert MEDICAL_DISCLAIMER in modified.content.parts[0].text


@pytest.mark.asyncio
async def test_workflow_deterministic_stages_and_otel_traces(
    temp_db: Path, tmp_path: Path
) -> None:
    """Exercise ADK 2.0 Workflow stages (sizing -> deselection -> order persist) and verify OTel JSONL spans."""
    trace_file = tmp_path / "traces.jsonl"
    configure_local_otel(trace_log_path=trace_file, force=True)

    wf = build_meal_planner_workflow(model_name="gemini-3.8-flash", root_agent_name="meal_planner")
    app = App(
        name="app",
        root_agent=wf,
        resumability_config=ResumabilityConfig(is_resumable=True),
        plugins=[DietarySafetyPlugin(db_path=str(temp_db)), ObservabilityPlugin()],
    )
    runner = InMemoryRunner(app=app)
    recipe = _sample_mediterranean_chicken_recipe()

    # Start session already past Gate 1 (simulating meal_discovery_agent + recipe_author_agent output)
    session = await runner.session_service.create_session(
        app_name="app",
        user_id="cust_malcom_munson",
        state={
            "workflow_stage": "sizing",
            "meal_confirmed": True,
            "selected_meal": recipe.title,
            "draft_recipe": recipe.model_dump(),
        },
    )

    async def _send(text: str) -> str:
        chunks: list[str] = []
        async for ev in runner.run_async(
            user_id="cust_malcom_munson",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=text)]),
        ):
            if ev.content and ev.content.parts:
                for p in ev.content.parts:
                    if p.text:
                        chunks.append(p.text)
        return "\n".join(chunks)

    # Turn 1 (Gate 2): Choose 4 meals -> deterministic nutrition + SKU list
    reply1 = await _send("4 meals")
    assert "4 meals" in reply1
    assert "SKU-CHK-BRST-16OZ" in reply1
    assert "Cumin" in reply1

    # Turn 2 (Gate 3): Remove cumin and olive oil
    reply2 = await _send("I already have cumin powder and olive oil")
    assert "Removed" in reply2
    assert "Removed (Already Owned)" in reply2

    # Turn 3 (Stage 4): Confirm -> persists order + returns complete recipe & shopping list
    reply3 = await _send("confirm")
    assert "ORD-" in reply3
    assert "Complete Recipe" in reply3
    assert "Shopping List" in reply3
    assert "Medical Disclaimer" in reply3

    # Verify DB persistence
    orders = get_user_meal_orders("cust_malcom_munson", db_path=temp_db)
    assert orders["count"] == 1
    assert orders["orders"][0]["servings_count"] == 4

    # Verify OpenTelemetry spans were written to traces.jsonl
    assert trace_file.exists()
    spans = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    span_names = {s["name"] for s in spans}
    assert "node.load_user_context" in span_names
    assert "node.workflow_router" in span_names
    assert "node.compute_nutrition_and_scale" in span_names
    assert "node.map_inventory_skus" in span_names
    assert "node.persist_meal_order" in span_names
    assert "workflow.state_transition" in span_names
