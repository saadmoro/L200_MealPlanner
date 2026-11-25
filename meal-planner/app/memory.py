"""Cross-session memory service (SQLite-backed) and memory persistence callback.

Adapted from core/python/cross-session-memory:
- Uses ADK's PreloadMemoryTool + after_agent_callback (add_session_to_memory).
- Locally backed by SQLite (user_memories table) so episodic memory survives restarts.
- Swaps cleanly to VertexAiMemoryBankService when deployed with memory_service_uri=agentengine://...
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from google.adk.agents.callback_context import CallbackContext
from google.adk.memory import BaseMemoryService
from google.adk.memory.base_memory_service import SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions.session import Session
from google.genai import types

from app.db.database import get_connection, init_db

logger = logging.getLogger(__name__)


class SqliteMemoryService(BaseMemoryService):
    """Persistent local ADK BaseMemoryService backed by SQLite user_memories."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = db_path
        init_db(db_path)

    async def add_session_to_memory(self, session: Session) -> None:
        """Persist meaningful user & model utterances from a session to SQLite."""
        now = datetime.now(UTC).isoformat()
        entries: list[tuple[str, str, str, str, str, str]] = []
        for ev in session.events:
            if not ev.content or not ev.content.parts:
                continue
            text = " ".join(p.text.strip() for p in ev.content.parts if p.text).strip()
            if not text or len(text) < 4:
                continue
            author = ev.author or (ev.content.role or "user")
            entries.append((session.app_name, session.user_id, session.id, author, text, now))

        if not entries:
            return

        with get_connection(self._db_path) as conn:
            # Replace prior snapshot for this session_id so repeated callbacks stay idempotent
            conn.execute(
                "DELETE FROM user_memories WHERE app_name = ? AND user_id = ? AND session_id = ?",
                (session.app_name, session.user_id, session.id),
            )
            conn.executemany(
                """
                INSERT INTO user_memories (app_name, user_id, session_id, author, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                entries,
            )

    async def search_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
    ) -> SearchMemoryResponse:
        """Recall relevant prior session memories for user_id via keyword overlap + recency."""
        tokens = {
            t for t in re.findall(r"[a-z0-9_]+", query.lower()) if len(t) >= 3
        }
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT author, content, created_at
                FROM user_memories
                WHERE app_name = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT 100
                """,
                (app_name, user_id),
            ).fetchall()

        scored: list[tuple[int, MemoryEntry]] = []
        for r in rows:
            content_l = r["content"].lower()
            overlap = sum(1 for tok in tokens if tok in content_l)
            # Always include recent user preference/dietary utterances even if query is generic ("hello")
            is_user_fact = r["author"] == "user" and any(
                kw in content_l
                for kw in (
                    "celiac", "gluten", "allergy", "allergic", "blood pressure",
                    "sodium", "vegetarian", "vegan", "prefer", "like", "hate",
                    "dislike", "beginner", "advanced", "easy", "spicy", "eggplant",
                )
            )
            score = overlap + (2 if is_user_fact else 0)
            if score > 0 or not tokens:
                scored.append(
                    (
                        score,
                        MemoryEntry(
                            content=types.Content(
                                role="user" if r["author"] == "user" else "model",
                                parts=[types.Part.from_text(text=r["content"])],
                            ),
                            author=r["author"],
                            timestamp=r["created_at"],
                        ),
                    )
                )

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return SearchMemoryResponse(memories=[m for _, m in scored[:8]])


async def generate_memories_callback(callback_context: CallbackContext) -> None:
    """After-agent callback that persists the session to the configured MemoryService."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError:
        # Runner has no MemoryService attached (e.g., lightweight unit runner)
        logger.debug("No memory service configured on runner; skipping memory persist.")
    except Exception as exc:
        logger.warning("Failed to persist session to memory service: %s", exc)
    return None
