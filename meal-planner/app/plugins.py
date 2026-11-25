"""Runner-wide ADK BasePlugins for deterministic dietary safety and OpenTelemetry tracing.

Adapted from core/python/safety-plugins: attaching plugins to App(plugins=[...]) ensures
every agent, workflow node, and tool call is uniformly guarded and traced.
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from opentelemetry import trace

from app.observability import get_tracer
from app.prompts.loader import PROMPT_VERSIONS
from app.tools.profile_tools import load_user_profile_model
from app.tools.safety_tools import MEDICAL_DISCLAIMER, check_skus_against_profile

logger = logging.getLogger(__name__)


def _extract_skus_from_payload(payload: Any) -> list[str]:
    """Recursively collect SKU identifiers from structured tool output dicts."""
    found: list[str] = []
    if isinstance(payload, dict):
        if "sku" in payload and isinstance(payload["sku"], str):
            found.append(payload["sku"])
        if "matched_skus" in payload and isinstance(payload["matched_skus"], list):
            found.extend(s for s in payload["matched_skus"] if isinstance(s, str))
        for val in payload.values():
            if isinstance(val, (dict, list)):
                found.extend(_extract_skus_from_payload(val))
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, (dict, list)):
                found.extend(_extract_skus_from_payload(item))
    return sorted(set(found))


class DietarySafetyPlugin(BasePlugin):
    """Runner-wide deterministic safety plugin enforcing hard allergen blocking & disclaimers."""

    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(name="dietary_safety_plugin")
        self._db_path = db_path

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Deterministically block any tool output leaking a hard-blocked allergen SKU."""
        # Skip blocking check on compliance/inspection tools themselves
        if tool.name in {"check_dietary_compliance", "get_user_profile"}:
            return None

        # Immediately activate medical disclaimer flag if a medical condition was just recorded
        if tool.name == "upsert_dietary_constraint" and isinstance(result, dict):
            saved = result.get("saved_constraints") or []
            if any(
                c.get("constraint_type") == "medical_condition"
                or c.get("code") in {"celiac_disease", "hypertension", "high_blood_pressure"}
                for c in saved
                if isinstance(c, dict)
            ):
                tool_context.state["user:requires_medical_disclaimer"] = True
            return None

        user_id = (
            tool_context.state.get("user:user_id")
            or tool_context.state.get("user_id")
            or tool_args.get("user_id")
        )
        if not user_id:
            return None

        skus = _extract_skus_from_payload(result)
        if not skus:
            return None

        profile = load_user_profile_model(str(user_id), db_path=self._db_path)
        compliance = check_skus_against_profile(
            profile=profile, skus=skus, db_path=self._db_path
        )
        if not compliance.is_safe:
            messages = "; ".join(v.message for v in compliance.hard_blocks)
            logger.warning(
                "DietarySafetyPlugin blocked tool '%s' output for user '%s': %s",
                tool.name,
                user_id,
                messages,
            )
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("meal_planner.safety_blocked", True)
                span.add_event(
                    "dietary_safety_hard_block",
                    {"tool": tool.name, "user_id": str(user_id), "details": messages},
                )
            return {
                "status": "blocked_by_safety_plugin",
                "error": f"DietarySafetyPlugin blocked unsafe allergen SKU(s): {messages}",
                "hard_blocks": [v.model_dump() for v in compliance.hard_blocks],
            }
        return None

    async def after_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        """Append non-medical-advice disclaimer when customer has medical dietary constraints."""
        requires_disclaimer = bool(
            callback_context.state.get("user:requires_medical_disclaimer", False)
        )
        if not requires_disclaimer:
            return None

        content = llm_response.content
        if not content or not content.parts:
            return None

        # Only annotate plain text responses (not pure structured JSON or function calls)
        if any(getattr(p, "function_call", None) is not None for p in content.parts):
            return None

        text = "\n".join(p.text for p in content.parts if p.text).strip()
        if not text or text.startswith("{") or "Medical Disclaimer" in text:
            return None

        updated_text = f"{text}\n\n{MEDICAL_DISCLAIMER}"
        return LlmResponse(
            content=types.Content(
                role=content.role or "model",
                parts=[types.Part.from_text(text=updated_text)],
            )
        )


class ObservabilityPlugin(BasePlugin):
    """Enriches OpenTelemetry spans with workflow stage, route, user, and prompt version data."""

    def __init__(self) -> None:
        super().__init__(name="observability_plugin")
        self._tracer = get_tracer("meal_planner.plugin")

    async def before_run_callback(
        self,
        *,
        invocation_context: InvocationContext,
    ) -> types.Content | None:
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("meal_planner.user_id", invocation_context.user_id)
            span.set_attribute("meal_planner.session_id", invocation_context.session.id)
            span.set_attribute(
                "meal_planner.prompt_versions",
                ",".join(f"{k}:{v}" for k, v in sorted(PROMPT_VERSIONS.items())),
            )
        return None

    async def on_event_callback(
        self,
        *,
        invocation_context: InvocationContext,
        event: Event,
    ) -> Event | None:
        """Record state transitions and routing decisions as OTel span events."""
        route = getattr(event, "route", None) or getattr(
            getattr(event, "actions", None), "route", None
        )
        state_delta = getattr(getattr(event, "actions", None), "state_delta", None) or {}
        if route is not None or state_delta:
            with self._tracer.start_as_current_span("workflow.state_transition") as span:
                span.set_attribute("meal_planner.author", event.author or "workflow")
                span.set_attribute("meal_planner.user_id", invocation_context.user_id)
                span.set_attribute("meal_planner.session_id", invocation_context.session.id)
                if route is not None:
                    span.set_attribute("meal_planner.route", str(route))
                if "workflow_stage" in state_delta:
                    span.set_attribute(
                        "meal_planner.stage", str(state_delta["workflow_stage"])
                    )
                if state_delta:
                    span.set_attribute(
                        "meal_planner.state_keys", ",".join(sorted(state_delta.keys()))
                    )
        return None
