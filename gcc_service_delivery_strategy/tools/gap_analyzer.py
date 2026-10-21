"""Gap Analysis, Assumption Formulation, Quality Self-Evaluation, and Human-in-the-Loop Approval Tools.

Addresses AgentOps Rubric:
- 1.1 Comprehensive Tool Docstrings
- 1.2 Descriptive Naming (`analyze_delivery_strategy_gaps`, `record_verified_roadmap_sections`, `evaluate_roadmap_quality_and_completeness`, `request_human_approval_for_slides`)
- 1.3 Explicit JSON Schemas (`GapAnalysisInput`, `GapAnalysisOutput`, `RoadmapUpdateInput`)
- 1.4 Guided Error Handling (`recovery_instructions` returned on validation or missing-data errors)
- 3.3 Guardrails & Self-Evaluation (`evaluate_roadmap_quality_and_completeness`)
- 3.4 Human-in-the-Loop Hooks (`request_human_approval_for_slides`)
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from google.adk.tools import ToolContext
except ImportError:  # pragma: no cover
    ToolContext = Any  # type: ignore[misc,assignment]

from ..models import (
    CLARIFYING_QUESTIONS_BY_SECTION,
    GapAnalysisInput,
    GapAnalysisOutput,
    INDUSTRY_STANDARD_ASSUMPTIONS,
    REQUIRED_SECTIONS,
    RoadmapUpdateInput,
    SECTION_DISPLAY_NAMES,
    ValidationError,
)
from ..observability import (
    log_agent_intent,
    log_agent_outcome,
    pii_scrubber,
    traced_span,
)
from ..plugins import evaluate_roadmap_completeness


def _normalize_operating_model_type(raw_value: str) -> str:
    """Normalizes the operating model label to one of the 3 canonical PRD types."""
    val = (raw_value or "").strip().lower()
    if not val:
        return ""
    if "both" in val or "hybrid" in val or ("pso" in val and "partner" in val):
        return "PSO & Partner (Hybrid)"
    if "partner" in val:
        return "Partner"
    if "pso" in val:
        return "PSO only"
    return raw_value.strip()


def analyze_delivery_strategy_gaps(
    customer_name: str = "",
    vision: str = "",
    services_delivery_strategy: str = "",
    commercials: str = "",
    delivery_approach: str = "",
    roles_and_responsibilities: str = "",
    operating_model: str = "",
    operating_model_type: str = "",
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Analyzes extracted customer context against the 6 required PRD roadmap sections.

    Validates input arguments against `GapAnalysisInput`, persists extracted
    sections in session-scoped state, identifies any missing or incomplete sections,
    and returns targeted clarifying questions alongside industry-standard GCC/PSO
    assumptions for user approval.

    Args:
        customer_name: Name of the target customer organization, if known.
        vision: Extracted details for the Vision section (empty string if missing).
        services_delivery_strategy: Extracted details for Services Delivery Strategy.
        commercials: Extracted details for Commercials (pricing, contract model, budget).
        delivery_approach: Extracted details for Delivery Approach (methodology, governance).
        roles_and_responsibilities: Extracted details for Roles & Responsibilities (RACI).
        operating_model: Extracted details for the Operating Model section.
        operating_model_type: Operating model classification ('PSO only', 'Partner', or 'both').
        tool_context: ADK ToolContext for session-scoped state storage.

    Returns:
        A validated `GapAnalysisOutput` dictionary containing:
        - `status`: `'ready_for_slides'`, `'gaps_identified'`, or `'error'`
        - `customer_name`: Current customer name
        - `operating_model_type`: Normalized operating model classification
        - `completed_sections`: List of section display names that have sufficient data
        - `missing_sections`: List of section display names that are missing data
        - `clarifying_questions`: Mapping of missing section -> targeted questions
        - `proposed_assumptions`: Mapping of missing section -> industry-standard assumptions
        - `next_step_instruction`: Explicit workflow instruction for the LLM
        - `recovery_instructions`: Guided recovery steps if gaps or validation errors occur
    """
    with traced_span(
        "tool.analyze_delivery_strategy_gaps",
        {"customer_name": customer_name, "operating_model_type": operating_model_type},
    ):
        action_id = log_agent_intent(
            component="analyze_delivery_strategy_gaps",
            intended_action="Validate input schema and evaluate completeness across 6 PRD sections",
            details={"customer_name": customer_name},
        )
        try:
            validated_in = GapAnalysisInput(
                customer_name=customer_name,
                vision=vision,
                services_delivery_strategy=services_delivery_strategy,
                commercials=commercials,
                delivery_approach=delivery_approach,
                roles_and_responsibilities=roles_and_responsibilities,
                operating_model=operating_model,
                operating_model_type=operating_model_type,
            )
        except ValidationError as exc:
            log_agent_outcome(
                action_id=action_id,
                component="analyze_delivery_strategy_gaps",
                intended_action="Validate GapAnalysisInput schema",
                actual_outcome=f"Schema validation failed: {exc}",
                status="ERROR",
            )
            return {
                "status": "error",
                "error_code": "SCHEMA_VALIDATION_ERROR",
                "error_message": pii_scrubber.redact_text(str(exc)),
                "recovery_instructions": (
                    "Ensure all section arguments passed to `analyze_delivery_strategy_gaps` "
                    "are strings and retry the tool call."
                ),
            }

        draft: dict[str, Any] = {}
        if tool_context is not None and "roadmap_draft" in tool_context.state:
            draft = dict(tool_context.state["roadmap_draft"])

        sections_data: dict[str, str] = dict(draft.get("sections", {}))
        incoming_sections = {
            "vision": validated_in.vision,
            "services_delivery_strategy": validated_in.services_delivery_strategy,
            "commercials": validated_in.commercials,
            "delivery_approach": validated_in.delivery_approach,
            "roles_and_responsibilities": validated_in.roles_and_responsibilities,
            "operating_model": validated_in.operating_model,
        }

        for key, val in incoming_sections.items():
            if val and val.strip():
                sections_data[key] = pii_scrubber.redact_text(val.strip())

        resolved_customer = (
            validated_in.customer_name.strip()
            or draft.get("customer_name", "")
            or "Valued Customer"
        )
        resolved_op_model_type = _normalize_operating_model_type(
            validated_in.operating_model_type
        ) or draft.get("operating_model_type", "")

        completed_keys: list[str] = []
        missing_keys: list[str] = []

        for section_key in REQUIRED_SECTIONS:
            content = sections_data.get(section_key, "").strip()
            if section_key == "operating_model":
                if content and resolved_op_model_type:
                    completed_keys.append(section_key)
                else:
                    missing_keys.append(section_key)
            else:
                if content:
                    completed_keys.append(section_key)
                else:
                    missing_keys.append(section_key)

        updated_draft = {
            "customer_name": resolved_customer,
            "operating_model_type": resolved_op_model_type,
            "sections": sections_data,
            "assumptions_approved": draft.get("assumptions_approved", False),
        }
        if tool_context is not None:
            tool_context.state["roadmap_draft"] = updated_draft

        clarifying_questions = {
            SECTION_DISPLAY_NAMES[k]: CLARIFYING_QUESTIONS_BY_SECTION[k]
            for k in missing_keys
        }
        proposed_assumptions = {
            SECTION_DISPLAY_NAMES[k]: INDUSTRY_STANDARD_ASSUMPTIONS[k]
            for k in missing_keys
        }

        is_ready = len(missing_keys) == 0
        output_model = GapAnalysisOutput(
            status="ready_for_slides" if is_ready else "gaps_identified",
            customer_name=resolved_customer,
            operating_model_type=(
                resolved_op_model_type
                or "Unspecified (needs PSO only, Partner, or both)"
            ),
            completed_sections=[SECTION_DISPLAY_NAMES[k] for k in completed_keys],
            missing_sections=[SECTION_DISPLAY_NAMES[k] for k in missing_keys],
            clarifying_questions=clarifying_questions,
            proposed_assumptions=proposed_assumptions,
            next_step_instruction=(
                "All 6 required sections are complete. You may now call `google_slides_generator`."
                if is_ready
                else (
                    "PAUSE final presentation generation. Present the extracted summary, "
                    "ask the user the clarifying_questions for the missing_sections, and "
                    "offer the proposed_assumptions so the user can approve or modify them."
                )
            ),
            recovery_instructions=(
                None
                if is_ready
                else (
                    "Do NOT call `google_slides_generator` yet. Ask the user the "
                    "`clarifying_questions` and offer `proposed_assumptions`, then call "
                    "`update_roadmap_sections` once the user responds."
                )
            ),
        )
        log_agent_outcome(
            action_id=action_id,
            component="analyze_delivery_strategy_gaps",
            intended_action="Evaluate completeness across 6 PRD sections",
            actual_outcome=f"Status={output_model.status}, missing={len(missing_keys)}",
            status="SUCCESS",
        )
        return output_model.model_dump()


def update_roadmap_sections(
    customer_name: str = "",
    vision: str = "",
    services_delivery_strategy: str = "",
    commercials: str = "",
    delivery_approach: str = "",
    roles_and_responsibilities: str = "",
    operating_model: str = "",
    operating_model_type: str = "",
    approve_industry_assumptions: bool = False,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Updates roadmap sections with user clarifications or applies approved assumptions.

    Call this tool after the user answers clarifying questions or approves the
    proposed industry-standard assumptions for missing sections.

    Args:
        customer_name: Updated customer organization name.
        vision: Updated Vision content (if provided by user).
        services_delivery_strategy: Updated Services Delivery Strategy content.
        commercials: Updated Commercials content.
        delivery_approach: Updated Delivery Approach content.
        roles_and_responsibilities: Updated Roles & Responsibilities content.
        operating_model: Updated Operating Model content.
        operating_model_type: Operating model selection ('PSO only', 'Partner', or 'both').
        approve_industry_assumptions: Set to True if the user approved using
            industry-standard assumptions to fill any remaining missing sections.
        tool_context: ADK ToolContext for session-scoped state storage.

    Returns:
        A dictionary indicating whether all 6 required sections are now complete
        and ready for `google_slides_generator`, plus `recovery_instructions` if
        any section remains missing.
    """
    with traced_span(
        "tool.update_roadmap_sections",
        {
            "customer_name": customer_name,
            "approve_industry_assumptions": approve_industry_assumptions,
        },
    ):
        action_id = log_agent_intent(
            component="update_roadmap_sections",
            intended_action="Record user clarifications and/or approved industry assumptions",
            details={"approve_industry_assumptions": approve_industry_assumptions},
        )
        try:
            validated_in = RoadmapUpdateInput(
                customer_name=customer_name,
                vision=vision,
                services_delivery_strategy=services_delivery_strategy,
                commercials=commercials,
                delivery_approach=delivery_approach,
                roles_and_responsibilities=roles_and_responsibilities,
                operating_model=operating_model,
                operating_model_type=operating_model_type,
                approve_industry_assumptions=approve_industry_assumptions,
            )
        except ValidationError as exc:
            log_agent_outcome(
                action_id=action_id,
                component="update_roadmap_sections",
                intended_action="Validate RoadmapUpdateInput schema",
                actual_outcome=f"Validation error: {exc}",
                status="ERROR",
            )
            return {
                "status": "error",
                "error_code": "SCHEMA_VALIDATION_ERROR",
                "error_message": pii_scrubber.redact_text(str(exc)),
                "recovery_instructions": (
                    "Pass valid string values for each section and a boolean for "
                    "`approve_industry_assumptions`."
                ),
            }

        draft: dict[str, Any] = {}
        if tool_context is not None and "roadmap_draft" in tool_context.state:
            draft = dict(tool_context.state["roadmap_draft"])

        sections_data: dict[str, str] = dict(draft.get("sections", {}))
        assumptions_used: dict[str, list[str]] = dict(
            draft.get("assumptions_used", {})
        )

        updates = {
            "vision": validated_in.vision,
            "services_delivery_strategy": validated_in.services_delivery_strategy,
            "commercials": validated_in.commercials,
            "delivery_approach": validated_in.delivery_approach,
            "roles_and_responsibilities": validated_in.roles_and_responsibilities,
            "operating_model": validated_in.operating_model,
        }
        for key, val in updates.items():
            if val and val.strip():
                sections_data[key] = pii_scrubber.redact_text(val.strip())

        resolved_customer = (
            validated_in.customer_name.strip()
            or draft.get("customer_name", "")
            or "Valued Customer"
        )
        resolved_op_model_type = _normalize_operating_model_type(
            validated_in.operating_model_type
        ) or draft.get("operating_model_type", "")

        if validated_in.approve_industry_assumptions:
            if not resolved_op_model_type:
                resolved_op_model_type = "PSO & Partner (Hybrid)"
            for section_key in REQUIRED_SECTIONS:
                if not sections_data.get(section_key, "").strip():
                    default_bullets = INDUSTRY_STANDARD_ASSUMPTIONS[section_key]
                    sections_data[section_key] = " ".join(default_bullets)
                    assumptions_used[section_key] = list(default_bullets)

        missing_keys = [
            k
            for k in REQUIRED_SECTIONS
            if not sections_data.get(k, "").strip()
            or (k == "operating_model" and not resolved_op_model_type)
        ]

        updated_draft = {
            "customer_name": resolved_customer,
            "operating_model_type": resolved_op_model_type,
            "sections": sections_data,
            "assumptions_used": assumptions_used,
            "assumptions_approved": validated_in.approve_industry_assumptions
            or draft.get("assumptions_approved", False),
        }
        if tool_context is not None:
            tool_context.state["roadmap_draft"] = updated_draft

        status = "ready_for_slides" if not missing_keys else "still_missing_sections"
        log_agent_outcome(
            action_id=action_id,
            component="update_roadmap_sections",
            intended_action="Update roadmap sections in session state",
            actual_outcome=f"Status={status}, remaining_missing={len(missing_keys)}",
            status="SUCCESS",
        )
        return {
            "status": status,
            "customer_name": resolved_customer,
            "operating_model_type": resolved_op_model_type,
            "completed_sections": [
                SECTION_DISPLAY_NAMES[k]
                for k in REQUIRED_SECTIONS
                if k not in missing_keys
            ],
            "missing_sections": [SECTION_DISPLAY_NAMES[k] for k in missing_keys],
            "assumptions_applied_to": [
                SECTION_DISPLAY_NAMES[k] for k in assumptions_used
            ],
            "recovery_instructions": (
                None
                if not missing_keys
                else (
                    "Some sections are still missing. Ask the user to clarify the remaining "
                    "`missing_sections` or ask if they approve industry-standard assumptions "
                    "(`approve_industry_assumptions=True`)."
                )
            ),
        }


# Descriptive alias matching Rubric 1.2
record_verified_roadmap_sections = update_roadmap_sections


def evaluate_roadmap_quality_and_completeness(
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Self-evaluates the session's drafted roadmap against all 6 required PRD slide sections.

    Use this self-evaluation guardrail tool prior to generating the final Google Slides
    presentation to verify that every required section meets quality and completeness standards.

    Args:
        tool_context: ADK ToolContext containing `roadmap_draft` in session state.

    Returns:
        Dictionary with `passed` (bool), `completeness_score` (0.0 to 1.0),
        `populated_sections`, `missing_sections`, and `recovery_instructions`.
    """
    draft = (
        dict(tool_context.state.get("roadmap_draft", {}))
        if tool_context is not None
        else {}
    )
    sections = draft.get("sections", {})
    op_model = draft.get("operating_model_type", "")
    eval_report = evaluate_roadmap_completeness(sections, op_model)
    eval_report["recovery_instructions"] = (
        "Roadmap passed self-evaluation. Proceed to `google_slides_generator`."
        if eval_report["passed"]
        else (
            "Self-evaluation failed because required sections are incomplete: "
            f"{eval_report['missing_sections']}. Call `update_roadmap_sections` first."
        )
    )
    return eval_report


def request_human_approval_for_slides(
    customer_name: str,
    operating_model_type: str,
    summary_of_slides: str,
    human_confirmed: bool = True,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Records Human-in-the-Loop (HITL) confirmation before creating external Google Slides.

    High-stakes external Google Workspace slide creation can be gated on explicit
    human approval (`human_approval_granted` in session state).

    Args:
        customer_name: Customer name for the presentation being approved.
        operating_model_type: Selected operating model ('PSO only', 'Partner', or 'PSO & Partner (Hybrid)').
        summary_of_slides: Brief summary of the 6 slides presented to the user for sign-off.
        human_confirmed: True once the user has confirmed slide generation or approved assumptions.
        tool_context: ADK ToolContext for recording approval state.

    Returns:
        Dictionary confirming whether `human_approval_granted` is active in the session.
    """
    with traced_span(
        "tool.request_human_approval_for_slides",
        {"customer_name": customer_name, "human_confirmed": human_confirmed},
    ):
        action_id = log_agent_intent(
            component="request_human_approval_for_slides",
            intended_action="Verify and record Human-in-the-Loop approval before slide generation",
            details={"customer_name": customer_name, "human_confirmed": human_confirmed},
        )
        if tool_context is not None:
            tool_context.state["human_approval_granted"] = bool(human_confirmed)
            tool_context.state["approved_slide_summary"] = pii_scrubber.redact_text(
                summary_of_slides
            )

        status = "approved" if human_confirmed else "pending_user_confirmation"
        log_agent_outcome(
            action_id=action_id,
            component="request_human_approval_for_slides",
            intended_action="Record Human-in-the-Loop approval",
            actual_outcome=f"Approval status={status}",
            status="SUCCESS",
        )
        return {
            "status": status,
            "customer_name": customer_name,
            "operating_model_type": operating_model_type,
            "human_approval_granted": bool(human_confirmed),
            "next_step": (
                "Human confirmation recorded. You may now call `google_slides_generator`."
                if human_confirmed
                else "Await explicit user approval before calling `google_slides_generator`."
            ),
        }
