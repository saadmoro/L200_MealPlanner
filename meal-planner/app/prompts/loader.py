"""Version-controlled prompt loader with metadata for OpenTelemetry spans."""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

PROMPT_VERSIONS: dict[str, str] = {
    "meal_discovery": "v1",
    "recipe_author": "v1",
}


def load_prompt(name: str, version: str | None = None) -> tuple[str, str]:
    """Load a versioned Markdown prompt from app/prompts/<name>.<version>.md.

    Returns:
        Tuple of (prompt_text, prompt_version_tag).
    """
    ver = version or PROMPT_VERSIONS.get(name, "v1")
    path = PROMPTS_DIR / f"{name}.{ver}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip(), f"{name}.{ver}"
