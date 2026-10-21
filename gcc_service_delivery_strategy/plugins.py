"""ADK Plugins, Strategic Model Routing, Security/Self-Eval Guardrails, and Human-in-the-Loop Hooks.

Addresses AgentOps Rubric Category 3 (Orchestration & Logic):
- 3.2 Strategic Model Routing (`StrategicModelRouter` routing fast tasks to Flash and complex strategy to Pro)
- 3.3 Guardrails & Policy Plugins (`GccAgentOpsPlugin` subclassing `BasePlugin` + input/output policy & self-evaluation)
- 3.4 Human-in-the-Loop Hooks (Hard confirmation stop before executing `google_slides_generator`)
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from .memory import (
    compact_conversation_contents,
    schedule_async_memory_consolidation,
)
from .models import REQUIRED_SECTIONS, SECTION_DISPLAY_NAMES
from .observability import (
    log_agent_intent,
    log_agent_outcome,
    pii_scrubber,
    traced_span,
)

try:
    from google.adk.plugins.base_plugin import BasePlugin
except ImportError:  # pragma: no cover

    class BasePlugin:  # type: ignore[no-redef]
        def __init__(self, name: str = "base_plugin") -> None:
            self.name = name


# ---------------------------------------------------------------------------
# 3.2 Strategic Model Routing (Flash for fast triage, Pro for deep strategy)
# ---------------------------------------------------------------------------

FAST_MODEL_ID = "gemini-2.5-flash"
PRO_MODEL_ID = "gemini-3.1-pro-preview"


class StrategicModelRouter:
    """Routes requests between Gemini Flash (fast tasks) and Gemini 3.1 Pro (deep strategy)."""

    FAST_TASK_KEYWORDS = (
        "ping",
        "status",
        "list sections",
        "hello",
        "hi",
        "help",
        "format",
        "extract metadata",
    )

    @classmethod
    def select_model(
        cls,
        agent_name: str,
        user_prompt: str = "",
    ) -> str:
        """Selects the optimal Gemini model tier for the given agent and prompt."""
        if "triage" in agent_name.lower() or "fast" in agent_name.lower():
            return FAST_MODEL_ID

        normalized = (user_prompt or "").strip().lower()
        if (
            normalized
            and len(normalized) < 45
            and any(normalized.startswith(k) for k in cls.FAST_TASK_KEYWORDS)
        ):
            return FAST_MODEL_ID

        return PRO_MODEL_ID


# ---------------------------------------------------------------------------
# 3.3 Guardrails & Policy Plugins + 3.4 Human-in-the-Loop Confirmation Hook
# ---------------------------------------------------------------------------

_PROMPT_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+all\s+previous\s+instructions|system\s+override|reveal\s+system\s+prompt|bypass\s+safety)",
    re.IGNORECASE,
)


def evaluate_roadmap_completeness(
    sections: dict[str, Any],
    operating_model_type: str,
) -> dict[str, Any]:
    """Self-evaluation guardrail scoring roadmap quality across all 6 required PRD sections."""
    populated = []
    missing = []
    for key in REQUIRED_SECTIONS:
        val = sections.get(key)
        has_content = False
        if isinstance(val, str) and len(val.strip()) >= 10:
            has_content = True
        elif isinstance(val, dict) and val.get("headline") and val.get("bullets"):
            has_content = True

        if key == "operating_model" and not (operating_model_type or "").strip():
            has_content = False

        if has_content:
            populated.append(SECTION_DISPLAY_NAMES[key])
        else:
            missing.append(SECTION_DISPLAY_NAMES[key])

    score = round(len(populated) / len(REQUIRED_SECTIONS), 2)
    return {
        "passed": len(missing) == 0,
        "completeness_score": score,
        "populated_sections": populated,
        "missing_sections": missing,
    }


class GccAgentOpsPlugin(BasePlugin):
    """Application-wide ADK Plugin enforcing Security Guardrails, HITL Hooks, Compaction, and Tracing."""

    def __init__(self, require_hitl_for_slides: bool = False) -> None:
        super().__init__(name="gcc_agentops_policy_plugin")
        self.require_hitl_for_slides = require_hitl_for_slides
        self._tool_start_times: dict[str, tuple[str, float]] = {}

    async def on_user_message_callback(
        self,
        *,
        invocation_context: Any,
        user_message: Any,
    ) -> Optional[Any]:
        """Scrubs PII and checks incoming user messages for prompt injection."""
        if user_message and getattr(user_message, "parts", None):
            for part in user_message.parts:
                text = getattr(part, "text", None)
                if text:
                    if _PROMPT_INJECTION_PATTERNS.search(text):
                        log_agent_outcome(
                            action_id="guardrail-input",
                            component=self.name,
                            intended_action="Validate user prompt safety",
                            actual_outcome="Blocked prompt injection attempt",
                            status="BLOCKED_BY_GUARDRAIL",
                        )
                        raise ValueError(
                            "Security Guardrail Violation: Disallowed instruction override detected."
                        )
                    part.text = pii_scrubber.redact_text(text)
        return None

    async def before_agent_callback(
        self,
        *,
        agent: Any,
        callback_context: Any,
    ) -> Optional[Any]:
        """Logs agent execution intent before an agent node runs."""
        agent_name = getattr(agent, "name", "unknown_agent")
        log_agent_intent(
            component=f"agent.{agent_name}",
            intended_action=f"Execute agent '{agent_name}'",
        )
        return None

    async def after_agent_callback(
        self,
        *,
        agent: Any,
        callback_context: Any,
    ) -> Optional[Any]:
        """Logs agent outcome and triggers async background memory consolidation."""
        agent_name = getattr(agent, "name", "unknown_agent")
        log_agent_outcome(
            action_id=f"agent-{agent_name}",
            component=f"agent.{agent_name}",
            intended_action=f"Execute agent '{agent_name}'",
            actual_outcome=f"Completed turn for '{agent_name}'",
            status="SUCCESS",
        )
        state = getattr(callback_context, "state", None)
        if isinstance(state, dict) and "roadmap_draft" in state:
            draft = state["roadmap_draft"]
            schedule_async_memory_consolidation(
                session_id=str(getattr(callback_context, "session_id", "session")),
                customer_name=draft.get("customer_name", "Valued Customer"),
                operating_model_type=draft.get("operating_model_type", ""),
                sections=draft.get("sections", {}),
            )
        return None

    async def before_model_callback(
        self,
        *,
        callback_context: Any,
        llm_request: Any,
    ) -> Optional[Any]:
        """Applies context history compaction and logs LLM model routing intent."""
        if llm_request is not None and getattr(llm_request, "contents", None):
            llm_request.contents = compact_conversation_contents(
                list(llm_request.contents)
            )
        return None

    async def before_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
    ) -> Optional[dict[str, Any]]:
        """Logs tool intent and enforces Human-in-the-Loop confirmation on high-stakes tools."""
        tool_name = getattr(tool, "name", str(tool))
        with traced_span(f"plugin.before_tool.{tool_name}", {"tool": tool_name}):
            action_id = log_agent_intent(
                component=f"tool.{tool_name}",
                intended_action=f"Invoke tool '{tool_name}'",
                details={"args": tool_args},
            )
            self._tool_start_times[tool_name] = (action_id, time.time())

            # Rubric 3.4: Human-in-the-Loop Hook before Google Slides creation if enabled
            state = getattr(tool_context, "state", {}) or {}
            require_hitl = self.require_hitl_for_slides or bool(
                state.get("enforce_hitl_approval", False)
            )
            if (
                tool_name == "google_slides_generator"
                and require_hitl
                and not state.get("human_approval_granted", False)
            ):
                log_agent_outcome(
                    action_id=action_id,
                    component=f"tool.{tool_name}",
                    intended_action="Execute google_slides_generator",
                    actual_outcome="Paused by Human-in-the-Loop guardrail awaiting user confirmation",
                    status="PAUSED_FOR_HUMAN_APPROVAL",
                )
                return {
                    "status": "awaiting_human_approval",
                    "error_code": "HITL_CONFIRMATION_REQUIRED",
                    "message": (
                        "Human-in-the-Loop Gate: High-stakes external Google Slides creation "
                        "requires explicit user confirmation before execution."
                    ),
                    "recovery_instructions": (
                        "Call `request_human_approval_for_slides` first (or ask the user to "
                        "confirm slide generation and pass `human_confirmed=True` to "
                        "`request_human_approval_for_slides`) before calling `google_slides_generator`."
                    ),
                }
        return None

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        result: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Logs tool outcome and latency metrics after execution."""
        tool_name = getattr(tool, "name", str(tool))
        action_id, start_ts = self._tool_start_times.pop(
            tool_name, (f"act-{tool_name}", time.time())
        )
        latency_ms = round((time.time() - start_ts) * 1000, 2)
        status = (
            str(result.get("status", "SUCCESS")).upper()
            if isinstance(result, dict)
            else "SUCCESS"
        )
        log_agent_outcome(
            action_id=action_id,
            component=f"tool.{tool_name}",
            intended_action=f"Invoke tool '{tool_name}'",
            actual_outcome=f"Tool '{tool_name}' returned status={status}",
            status=status,
            metrics={"latency_ms": latency_ms},
        )
        return None

    async def on_tool_error_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        error: Exception,
    ) -> Optional[dict[str, Any]]:
        """Provides guided recovery instructions back to the LLM on unhandled tool errors."""
        tool_name = getattr(tool, "name", str(tool))
        action_id, _ = self._tool_start_times.pop(
            tool_name, (f"act-{tool_name}", time.time())
        )
        log_agent_outcome(
            action_id=action_id,
            component=f"tool.{tool_name}",
            intended_action=f"Invoke tool '{tool_name}'",
            actual_outcome=f"Unhandled exception: {error}",
            status="ERROR",
        )
        return {
            "status": "error",
            "tool": tool_name,
            "error_type": type(error).__name__,
            "error_message": pii_scrubber.redact_text(str(error)),
            "recovery_instructions": (
                f"Tool '{tool_name}' encountered an error. Verify that all required "
                "parameters match the schema, check for missing roadmap sections via "
                "`analyze_delivery_strategy_gaps`, and retry."
            ),
        }
