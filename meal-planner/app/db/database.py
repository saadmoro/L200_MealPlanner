"""SQLite connection management and schema migration runner."""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "grocery_store.db"
DEFAULT_STORE_ID = "STORE-001"


def get_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve the active SQLite database path."""
    if db_path is not None:
        return Path(db_path)
    env_path = os.environ.get("MEAL_PLANNER_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


@contextlib.contextmanager
def get_connection(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with foreign keys enabled and dict-like Row access."""
    resolved = get_db_path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path | None = None) -> Path:
    """Apply all version-controlled SQL migrations in lexical order."""
    resolved = get_db_path(db_path)
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with get_connection(resolved) as conn:
        for sql_file in sql_files:
            conn.executescript(sql_file.read_text(encoding="utf-8"))
    return resolved
