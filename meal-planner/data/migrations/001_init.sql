-- 001_init.sql: Grocery Store Recipe Planner & Shopping List Schema (SQLite)
-- Version-controlled DDL for Products, Nutritional Facts, Inventory,
-- User Information, Meal Orders, and Local Cross-Session Episodic Memory.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS products (
    sku                     TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    canonical_ingredient    TEXT NOT NULL,
    category                TEXT NOT NULL,
    brand                   TEXT,
    package_qty             REAL NOT NULL,
    package_unit            TEXT NOT NULL,
    base_unit               TEXT NOT NULL CHECK (base_unit IN ('g', 'ml', 'count')),
    grams_or_ml_per_package REAL NOT NULL,
    unit_price_usd          REAL NOT NULL,
    allergen_tags_json      TEXT NOT NULL DEFAULT '[]',
    dietary_tags_json       TEXT NOT NULL DEFAULT '[]',
    is_pantry_staple        INTEGER NOT NULL DEFAULT 0,
    is_active               INTEGER NOT NULL DEFAULT 1,
    updated_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_canonical
    ON products(canonical_ingredient);

CREATE INDEX IF NOT EXISTS idx_products_category
    ON products(category);

CREATE TABLE IF NOT EXISTS nutritional_facts (
    sku                     TEXT PRIMARY KEY REFERENCES products(sku) ON DELETE CASCADE,
    serving_size_desc       TEXT NOT NULL,
    serving_size_g_or_ml    REAL NOT NULL,
    calories_per_100        REAL NOT NULL,
    protein_g_per_100       REAL NOT NULL,
    carbs_g_per_100         REAL NOT NULL,
    fat_g_per_100           REAL NOT NULL,
    saturated_fat_g_per_100 REAL NOT NULL,
    fiber_g_per_100         REAL NOT NULL,
    sugar_g_per_100         REAL NOT NULL,
    sodium_mg_per_100       REAL NOT NULL,
    data_source             TEXT NOT NULL DEFAULT 'USDA_FDC_SEED'
);

CREATE TABLE IF NOT EXISTS inventory (
    store_id        TEXT NOT NULL DEFAULT 'STORE-001',
    sku             TEXT NOT NULL REFERENCES products(sku) ON DELETE CASCADE,
    qty_on_hand     INTEGER NOT NULL CHECK (qty_on_hand >= 0),
    qty_reserved    INTEGER NOT NULL DEFAULT 0 CHECK (qty_reserved >= 0),
    aisle_location  TEXT NOT NULL,
    restock_eta     TEXT,
    last_counted_at TEXT NOT NULL,
    PRIMARY KEY (store_id, sku)
);

CREATE VIEW IF NOT EXISTS v_available_inventory AS
SELECT
    store_id,
    sku,
    (qty_on_hand - qty_reserved) AS available_qty,
    aisle_location,
    restock_eta
FROM inventory;

CREATE TABLE IF NOT EXISTS users (
    user_id               TEXT PRIMARY KEY,
    full_name             TEXT NOT NULL,
    phone_number          TEXT,
    cooking_skill_level   TEXT NOT NULL DEFAULT 'intermediate'
                          CHECK (cooking_skill_level IN ('beginner', 'intermediate', 'advanced')),
    default_servings      INTEGER NOT NULL DEFAULT 2,
    daily_calorie_target  INTEGER,
    daily_sodium_limit_mg INTEGER,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_dietary_constraints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    constraint_type TEXT NOT NULL CHECK (constraint_type IN ('medical_condition', 'allergen', 'diet_regime')),
    code            TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('hard_block', 'warn_threshold')),
    notes           TEXT,
    UNIQUE(user_id, constraint_type, code)
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    category          TEXT NOT NULL CHECK (category IN ('cuisine', 'ingredient', 'protein', 'flavor_profile', 'equipment')),
    value             TEXT NOT NULL,
    sentiment         TEXT NOT NULL CHECK (sentiment IN ('like', 'prefer', 'dislike', 'avoid')),
    weight            REAL NOT NULL DEFAULT 1.0,
    source_session_id TEXT,
    updated_at        TEXT NOT NULL,
    UNIQUE(user_id, category, value)
);

CREATE TABLE IF NOT EXISTS meal_orders (
    order_id               TEXT PRIMARY KEY,
    user_id                TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id             TEXT NOT NULL,
    recipe_title           TEXT NOT NULL,
    servings_count         INTEGER NOT NULL,
    recipe_json            TEXT NOT NULL,
    nutrition_summary_json TEXT NOT NULL,
    estimated_total_usd    REAL NOT NULL,
    delivery_channel       TEXT NOT NULL DEFAULT 'account_attached',
    status                 TEXT NOT NULL DEFAULT 'finalized',
    created_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meal_order_items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id           TEXT NOT NULL REFERENCES meal_orders(order_id) ON DELETE CASCADE,
    sku                TEXT NOT NULL REFERENCES products(sku),
    required_qty_base  REAL NOT NULL,
    packages_to_buy    INTEGER NOT NULL,
    display_qty        TEXT NOT NULL,
    line_total_usd     REAL NOT NULL,
    deselected_by_user INTEGER NOT NULL DEFAULT 0,
    deselect_reason    TEXT
);

-- Local cross-session episodic memory store backing SqliteMemoryService.
CREATE TABLE IF NOT EXISTS user_memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name   TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    session_id TEXT NOT NULL,
    author     TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_memories_lookup
    ON user_memories(app_name, user_id);
