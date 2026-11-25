"""Typed Pydantic v2 schemas for deterministic tool I/O and ADK 2.0 Workflow edges."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DietaryConstraint(BaseModel):
    """A medical condition, allergen, or dietary regime linked to a customer."""

    constraint_type: Literal["medical_condition", "allergen", "diet_regime"]
    code: str
    severity: Literal["hard_block", "warn_threshold"]
    notes: str | None = None


class UserPreference(BaseModel):
    """A customer's taste, cuisine, protein, flavor, or equipment preference."""

    category: Literal["cuisine", "ingredient", "protein", "flavor_profile", "equipment"]
    value: str
    sentiment: Literal["like", "prefer", "dislike", "avoid"]
    weight: float = 1.0
    source_session_id: str | None = None


class UserProfile(BaseModel):
    """Complete structured customer profile loaded from SQLite."""

    user_id: str
    full_name: str
    phone_number: str | None = None
    cooking_skill_level: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    default_servings: int = 2
    daily_calorie_target: int | None = None
    daily_sodium_limit_mg: int | None = None
    constraints: list[DietaryConstraint] = Field(default_factory=list)
    preferences: list[UserPreference] = Field(default_factory=list)


class IngredientSpec(BaseModel):
    """One ingredient entry in a base recipe (for base_servings)."""

    canonical_ingredient: str = Field(
        description="Normalized canonical key matching products.canonical_ingredient (e.g., 'chicken_breast', 'bell_pepper', 'soy_sauce')."
    )
    display_name: str = Field(description="Human-readable ingredient name.")
    quantity: float = Field(
        description="Positive numeric quantity (> 0) for the recipe's base_servings."
    )
    unit: str = Field(
        description="Measurement unit: g, kg, oz, lb, ml, l, cup, tbsp, tsp, count, clove, bunch."
    )
    preparation_note: str = Field(
        default="", description="Optional prep note such as 'diced', 'minced', 'sliced'."
    )

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("quantity must be > 0")
        return value


class RecipeDraft(BaseModel):
    """Structured recipe authored by recipe_author_agent (calibrated to skill & diet)."""

    title: str = Field(description="Concise, appetizing meal title.")
    cuisine: str = Field(description="Cuisine category, e.g. 'mediterranean', 'chinese', 'indian'.")
    difficulty: Literal["beginner", "intermediate", "advanced"]
    prep_time_minutes: int = Field(description="Preparation time in minutes (>= 1).")
    cook_time_minutes: int = Field(description="Cooking time in minutes (>= 0).")
    base_servings: int = Field(
        default=2, description="Number of servings the base ingredient quantities represent (>= 1)."
    )
    summary: str = Field(description="Short 1-2 sentence overview of the dish.")
    ingredients: list[IngredientSpec] = Field(
        description="Non-empty list of ingredients using store canonical_ingredient keys."
    )
    steps: list[str] = Field(description="Non-empty ordered cooking instructions.")
    dietary_notes: list[str] = Field(
        default_factory=list,
        description="Notes on how the recipe accommodates dietary restrictions or preferences.",
    )

    @field_validator("ingredients", "steps")
    @classmethod
    def _non_empty(cls, value: list) -> list:
        if not value:
            raise ValueError("must contain at least one item")
        return value


class MealSelectionOutput(BaseModel):
    """Structured gate output from meal_discovery_agent."""

    meal_confirmed: bool = Field(
        description="True ONLY when the customer has explicitly chosen or requested a specific meal."
    )
    selected_meal: str | None = Field(
        default=None,
        description="Name of the confirmed meal (e.g., 'Lemon Herb Chicken Souvlaki Bowls' or 'Kung Pao Chicken').",
    )
    requested_servings: int | None = Field(
        default=None,
        description="If the user already specified how many meals/servings they want (e.g., 4), capture it here.",
    )
    assistant_reply: str = Field(
        description="Friendly conversational reply to show the customer."
    )


class NutrientTotals(BaseModel):
    """Exact deterministic nutrient figures."""

    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    saturated_fat_g: float
    fiber_g: float
    sugar_g: float
    sodium_mg: float


class NutritionSummary(BaseModel):
    """Deterministic per-serving and total recipe nutrition summary."""

    servings: int
    approx_serving_weight_g: float
    per_serving: NutrientTotals
    total_recipe: NutrientTotals
    unmatched_ingredients: list[str] = Field(default_factory=list)
    sodium_warning: str | None = None
    dietary_badges: list[str] = Field(default_factory=list)


class SafetyViolation(BaseModel):
    """One deterministic safety or dietary violation."""

    severity: Literal["hard_block", "warn_threshold"]
    code: str
    sku: str | None = None
    ingredient: str | None = None
    message: str
    suggested_substitute_sku: str | None = None
    suggested_substitute_name: str | None = None


class SafetyComplianceResult(BaseModel):
    """Result of deterministic allergen, diet-regime, and sodium validation."""

    is_safe: bool
    hard_blocks: list[SafetyViolation] = Field(default_factory=list)
    warnings: list[SafetyViolation] = Field(default_factory=list)
    requires_medical_disclaimer: bool = False


class ShoppingListItem(BaseModel):
    """One concrete store inventory SKU on the customer's shopping list."""

    sku: str
    product_name: str
    canonical_ingredient: str
    aisle_location: str
    required_qty_base: float
    base_unit: Literal["g", "ml", "count"]
    recipe_display_qty: str
    packages_to_buy: int
    package_description: str
    unit_price_usd: float
    line_total_usd: float
    is_pantry_staple: bool = False
    allergen_tags: list[str] = Field(default_factory=list)
    dietary_tags: list[str] = Field(default_factory=list)
    substituted_note: str | None = None
    deselected_by_user: bool = False
    deselect_reason: str | None = None


class ShoppingListResult(BaseModel):
    """Complete shopping list derived deterministically from store inventory."""

    recipe_title: str
    servings: int
    store_id: str
    items: list[ShoppingListItem]
    active_item_count: int
    deselected_item_count: int
    estimated_total_usd: float
    pantry_staples_hint: list[str] = Field(default_factory=list)
    unmatched_ingredients: list[str] = Field(default_factory=list)


class MealOrderReceipt(BaseModel):
    """Confirmation returned after persisting a finalized order to meal_orders."""

    order_id: str
    user_id: str
    session_id: str
    recipe_title: str
    servings_count: int
    active_items_count: int
    deselected_items_count: int
    estimated_total_usd: float
    delivery_channel: str
    status: str
    created_at: str
