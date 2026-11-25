"""Deterministic tools for reading and updating customer profiles, constraints, and preferences."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db.database import get_connection
from app.schemas import DietaryConstraint, UserPreference, UserProfile


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_user_exists(conn: Any, user_id: str, full_name: str | None = None) -> None:
    row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO users (
                user_id, full_name, cooking_skill_level, default_servings,
                created_at, updated_at
            ) VALUES (?, ?, 'intermediate', 2, ?, ?)
            """,
            (user_id, full_name or user_id, now, now),
        )


def load_user_profile_model(
    user_id: str, db_path: str | Path | None = None
) -> UserProfile:
    """Load a typed UserProfile from SQLite (creating a default guest record if new)."""
    with get_connection(db_path) as conn:
        _ensure_user_exists(conn, user_id)
        u = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        c_rows = conn.execute(
            """
            SELECT constraint_type, code, severity, notes
            FROM user_dietary_constraints
            WHERE user_id = ?
            ORDER BY severity ASC, code ASC
            """,
            (user_id,),
        ).fetchall()
        p_rows = conn.execute(
            """
            SELECT category, value, sentiment, weight, source_session_id
            FROM user_preferences
            WHERE user_id = ?
            ORDER BY weight DESC, value ASC
            """,
            (user_id,),
        ).fetchall()

    return UserProfile(
        user_id=u["user_id"],
        full_name=u["full_name"],
        phone_number=u["phone_number"],
        cooking_skill_level=u["cooking_skill_level"],
        default_servings=u["default_servings"],
        daily_calorie_target=u["daily_calorie_target"],
        daily_sodium_limit_mg=u["daily_sodium_limit_mg"],
        constraints=[DietaryConstraint(**dict(r)) for r in c_rows],
        preferences=[UserPreference(**dict(r)) for r in p_rows],
    )


def get_user_profile(user_id: str) -> dict[str, Any]:
    """Retrieve a customer's complete dietary profile, restrictions, preferences, and skill level.

    Args:
        user_id: Unique customer identifier (e.g., 'cust_malcom_munson').

    Returns:
        Dictionary containing the customer's profile, medical/allergen constraints, and preferences.
    """
    profile = load_user_profile_model(user_id)
    return {"status": "success", "profile": profile.model_dump()}


def upsert_user_preference(
    user_id: str,
    category: str,
    value: str,
    sentiment: str,
    session_id: str,
) -> dict[str, Any]:
    """Save or update a customer's food preference so it persists across sessions.

    Args:
        user_id: Unique customer identifier.
        category: One of 'cuisine', 'ingredient', 'protein', 'flavor_profile', 'equipment'.
        value: Normalized preference value (e.g., 'mediterranean', 'eggplant', 'spicy', 'chicken').
        sentiment: One of 'like', 'prefer', 'dislike', 'avoid'.
        session_id: Current session identifier for traceability.

    Returns:
        Confirmation dictionary with the saved preference.
    """
    valid_categories = {"cuisine", "ingredient", "protein", "flavor_profile", "equipment"}
    valid_sentiments = {"like", "prefer", "dislike", "avoid"}
    norm_cat = category.strip().lower()
    norm_sent = sentiment.strip().lower()
    norm_val = value.strip().lower()

    if norm_cat not in valid_categories:
        return {"status": "error", "message": f"Invalid category '{category}'. Expected one of {sorted(valid_categories)}."}
    if norm_sent not in valid_sentiments:
        return {"status": "error", "message": f"Invalid sentiment '{sentiment}'. Expected one of {sorted(valid_sentiments)}."}

    now = _now_iso()
    with get_connection() as conn:
        _ensure_user_exists(conn, user_id)
        conn.execute(
            """
            INSERT INTO user_preferences (
                user_id, category, value, sentiment, weight, source_session_id, updated_at
            ) VALUES (?, ?, ?, ?, 1.5, ?, ?)
            ON CONFLICT(user_id, category, value) DO UPDATE SET
                sentiment = excluded.sentiment,
                source_session_id = excluded.source_session_id,
                updated_at = excluded.updated_at
            """,
            (user_id, norm_cat, norm_val, norm_sent, session_id, now),
        )
    return {
        "status": "success",
        "saved_preference": {
            "user_id": user_id,
            "category": norm_cat,
            "value": norm_val,
            "sentiment": norm_sent,
        },
    }


def upsert_dietary_constraint(
    user_id: str,
    constraint_type: str,
    code: str,
    severity: str,
    notes: str,
) -> dict[str, Any]:
    """Save or update a medical condition, allergen, or dietary regime for a customer.

    Args:
        user_id: Unique customer identifier.
        constraint_type: One of 'medical_condition', 'allergen', 'diet_regime'.
        code: Normalized code (e.g., 'celiac_disease', 'gluten', 'peanuts', 'vegetarian', 'low_sodium').
        severity: 'hard_block' for strict exclusions or 'warn_threshold' for advisory thresholds.
        notes: Short clinical or dietary context note.

    Returns:
        Confirmation dictionary with the persisted constraint(s).
    """
    valid_types = {"medical_condition", "allergen", "diet_regime"}
    valid_sev = {"hard_block", "warn_threshold"}
    norm_type = constraint_type.strip().lower()
    norm_code = code.strip().lower().replace(" ", "_")
    norm_sev = severity.strip().lower()

    if norm_type not in valid_types:
        return {"status": "error", "message": f"Invalid constraint_type '{constraint_type}'."}
    if norm_sev not in valid_sev:
        return {"status": "error", "message": f"Invalid severity '{severity}'."}

    implied: list[tuple[str, str, str, str]] = [(norm_type, norm_code, norm_sev, notes)]
    # Deterministic clinical expansions:
    if norm_code == "celiac_disease":
        implied.append(("allergen", "gluten", "hard_block", "Auto-derived from celiac_disease."))
    if norm_code in {"hypertension", "high_blood_pressure"}:
        implied.append(("diet_regime", "low_sodium", "warn_threshold", "Auto-derived from hypertension."))

    with get_connection() as conn:
        _ensure_user_exists(conn, user_id)
        for c_type, c_code, c_sev, c_notes in implied:
            conn.execute(
                """
                INSERT INTO user_dietary_constraints (user_id, constraint_type, code, severity, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, constraint_type, code) DO UPDATE SET
                    severity = excluded.severity,
                    notes = excluded.notes
                """,
                (user_id, c_type, c_code, c_sev, c_notes),
            )
        if norm_code in {"hypertension", "high_blood_pressure"}:
            conn.execute(
                """
                UPDATE users
                SET daily_sodium_limit_mg = COALESCE(daily_sodium_limit_mg, 1500),
                    updated_at = ?
                WHERE user_id = ?
                """,
                (_now_iso(), user_id),
            )

    return {
        "status": "success",
        "saved_constraints": [
            {"constraint_type": t, "code": c, "severity": s} for t, c, s, _ in implied
        ],
    }


def set_cooking_skill_level(user_id: str, skill_level: str) -> dict[str, Any]:
    """Update a customer's cooking skill level across sessions.

    Args:
        user_id: Unique customer identifier.
        skill_level: One of 'beginner', 'intermediate', or 'advanced'.

    Returns:
        Confirmation dictionary with the updated skill level.
    """
    norm = skill_level.strip().lower()
    if norm not in {"beginner", "intermediate", "advanced"}:
        return {
            "status": "error",
            "message": f"Invalid skill_level '{skill_level}'. Must be beginner, intermediate, or advanced.",
        }
    with get_connection() as conn:
        _ensure_user_exists(conn, user_id)
        conn.execute(
            "UPDATE users SET cooking_skill_level = ?, updated_at = ? WHERE user_id = ?",
            (norm, _now_iso(), user_id),
        )
    return {"status": "success", "user_id": user_id, "cooking_skill_level": norm}
