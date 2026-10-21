"""Pydantic v2 Data Models and Explicit JSON Schemas for GCC Service Delivery Strategy Agent.

Addresses AgentOps Rubric 1.3 (Explicit JSON Schemas):
Utilizes strict Pydantic input and output schemas (`ConfigDict(extra="forbid")`)
to validate tool arguments, constrain LLM outputs, and enforce PRD slide completeness.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError
except ImportError:  # pragma: no cover

    class ValidationError(ValueError):
        """Fallback validation error when pydantic is not installed."""

    def ConfigDict(**kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    def Field(
        default: Any = None,
        *,
        default_factory: Any = None,
        min_length: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        return {
            "__field_spec__": True,
            "default": default,
            "default_factory": default_factory,
            "min_length": min_length,
        }

    class BaseModel:  # type: ignore[no-redef]
        model_config: dict[str, Any] = {}

        def __init__(self, **kwargs: Any) -> None:
            cls_fields = {
                k: v
                for k, v in self.__class__.__dict__.items()
                if not k.startswith("_") and k != "model_config"
            }
            annotations = getattr(self.__class__, "__annotations__", {})
            allowed = set(cls_fields.keys()) | set(annotations.keys())
            if self.model_config.get("extra") == "forbid":
                unknown = set(kwargs.keys()) - allowed
                if unknown:
                    raise ValidationError(f"Unexpected extra fields: {unknown}")

            for name in allowed:
                spec = cls_fields.get(name)
                if name in kwargs:
                    val = kwargs[name]
                elif isinstance(spec, dict) and spec.get("__field_spec__"):
                    if spec["default_factory"] is not None:
                        val = spec["default_factory"]()
                    elif spec["default"] is not ...:
                        val = spec["default"]
                    else:
                        raise ValidationError(f"Field '{name}' is required")
                else:
                    val = spec
                if (
                    isinstance(spec, dict)
                    and spec.get("__field_spec__")
                    and spec.get("min_length")
                    and isinstance(val, str)
                    and len(val) < spec["min_length"]
                ):
                    raise ValidationError(
                        f"Field '{name}' must have min_length={spec['min_length']}"
                    )
                setattr(self, name, val)

        def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for k, v in self.__dict__.items():
                if exclude_none and v is None:
                    continue
                if isinstance(v, BaseModel):
                    out[k] = v.model_dump(exclude_none=exclude_none)
                else:
                    out[k] = v
            return out


class OperatingModelType(str, Enum):
    """Supported GCC Service Delivery Operating Models."""

    PSO_ONLY = "PSO only"
    PARTNER = "Partner"
    BOTH = "PSO & Partner (Hybrid)"


class SlideSectionContent(BaseModel):
    """Structured content for a single slide section of the roadmap."""

    model_config = ConfigDict(extra="forbid")

    section_name: str = Field(
        ...,
        description="Name of the required roadmap section.",
    )
    headline: str = Field(
        ...,
        description=(
            "Executive action-oriented headline summarizing the key takeaway "
            "for this slide (max 15 words)."
        ),
    )
    bullet_points: list[str] = Field(
        default_factory=list,
        description=(
            "3 to 6 concise, high-impact bullet points detailing the strategy, "
            "milestones, or structure for this section."
        ),
    )
    assumptions_applied: list[str] = Field(
        default_factory=list,
        description=(
            "Any industry-standard assumptions approved by the user and "
            "incorporated into this section."
        ),
    )
    speaker_notes: str = Field(
        default="",
        description=(
            "Presenter talking points and context for the Service Delivery "
            "Manager, Consultant, or Account Executive."
        ),
    )


class ServiceDeliveryStrategyRoadmap(BaseModel):
    """Complete structured roadmap required to generate the Google Slides deck."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(
        ...,
        description="Name of the target customer or organization.",
    )
    presentation_title: str = Field(
        ...,
        description="Title of the Google Slides presentation.",
    )
    subtitle: str = Field(
        default="Google Cloud Consulting (GCC) Service Delivery Strategy Roadmap",
        description="Subtitle displayed on the cover slide.",
    )
    operating_model_type: OperatingModelType = Field(
        ...,
        description=(
            "Selected operating model: 'PSO only', 'Partner', or "
            "'PSO & Partner (Hybrid)'."
        ),
    )
    vision: SlideSectionContent = Field(
        ...,
        description="Slide 1: Vision - North Star objectives and business outcomes.",
    )
    services_delivery_strategy: SlideSectionContent = Field(
        ...,
        description=(
            "Slide 2: Services Delivery Strategy - Phased roadmap, workstreams, "
            "and value realization."
        ),
    )
    commercials: SlideSectionContent = Field(
        ...,
        description=(
            "Slide 3: Commercials - Engagement structure, commercial model "
            "(Fixed Price / T&M / Milestone), investment profile, and terms."
        ),
    )
    delivery_approach: SlideSectionContent = Field(
        ...,
        description=(
            "Slide 4: Delivery Approach - Execution methodology, governance, "
            "risk mitigation, and quality gates."
        ),
    )
    roles_and_responsibilities: SlideSectionContent = Field(
        ...,
        description=(
            "Slide 5: Roles & Responsibilities - RACI across Customer, "
            "Google Cloud PSO, and Partner teams."
        ),
    )
    operating_model: SlideSectionContent = Field(
        ...,
        description=(
            "Slide 6: Operating Model (PSO only, Partner, or both) - Governance "
            "cadences, escalation paths, and co-delivery structure."
        ),
    )


# ---------------------------------------------------------------------------
# Strict Input & Output Schemas for Tool Argument & Return Validation
# ---------------------------------------------------------------------------


class GapAnalysisInput(BaseModel):
    """Strict input schema for `analyze_delivery_strategy_gaps`."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(
        default="",
        description="Name of the customer organization, if known.",
    )
    vision: str = Field(
        default="",
        description="Extracted details for the Vision section.",
    )
    services_delivery_strategy: str = Field(
        default="",
        description="Extracted details for Services Delivery Strategy.",
    )
    commercials: str = Field(
        default="",
        description="Extracted details for Commercials (pricing, contract model, budget).",
    )
    delivery_approach: str = Field(
        default="",
        description="Extracted details for Delivery Approach (methodology, governance).",
    )
    roles_and_responsibilities: str = Field(
        default="",
        description="Extracted details for Roles & Responsibilities (RACI).",
    )
    operating_model: str = Field(
        default="",
        description="Extracted details for the Operating Model section.",
    )
    operating_model_type: str = Field(
        default="",
        description="Operating model classification: 'PSO only', 'Partner', or 'both'.",
    )


class GapAnalysisOutput(BaseModel):
    """Strict output schema for `analyze_delivery_strategy_gaps`."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(
        ...,
        description="'ready_for_slides', 'gaps_identified', or 'error'.",
    )
    customer_name: str
    operating_model_type: str
    completed_sections: list[str]
    missing_sections: list[str]
    clarifying_questions: dict[str, list[str]]
    proposed_assumptions: dict[str, list[str]]
    next_step_instruction: str
    recovery_instructions: Optional[str] = None


class RoadmapUpdateInput(BaseModel):
    """Strict input schema for `record_verified_roadmap_sections` / `update_roadmap_sections`."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(default="")
    vision: str = Field(default="")
    services_delivery_strategy: str = Field(default="")
    commercials: str = Field(default="")
    delivery_approach: str = Field(default="")
    roles_and_responsibilities: str = Field(default="")
    operating_model: str = Field(default="")
    operating_model_type: str = Field(default="")
    approve_industry_assumptions: bool = Field(
        default=False,
        description="True if the user approved applying industry-standard assumptions.",
    )


class SlidesGeneratorInput(BaseModel):
    """Strict input schema for `google_slides_generator`."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(..., min_length=1)
    presentation_title: str = Field(default="")
    operating_model_type: str = Field(default="")
    vision_headline: str = Field(default="")
    vision_bullets: list[str] = Field(default_factory=list)
    services_delivery_strategy_headline: str = Field(default="")
    services_delivery_strategy_bullets: list[str] = Field(default_factory=list)
    commercials_headline: str = Field(default="")
    commercials_bullets: list[str] = Field(default_factory=list)
    delivery_approach_headline: str = Field(default="")
    delivery_approach_bullets: list[str] = Field(default_factory=list)
    roles_and_responsibilities_headline: str = Field(default="")
    roles_and_responsibilities_bullets: list[str] = Field(default_factory=list)
    operating_model_headline: str = Field(default="")
    operating_model_bullets: list[str] = Field(default_factory=list)
    assumptions_included: Optional[list[str]] = Field(default=None)
    use_approved_assumptions_for_missing: bool = Field(default=False)


class SlidesGeneratorOutput(BaseModel):
    """Strict output schema for `google_slides_generator`."""

    model_config = ConfigDict(extra="forbid")

    status: str
    mode: Optional[str] = None
    presentation_id: Optional[str] = None
    presentation_title: Optional[str] = None
    presentation_url: Optional[str] = None
    operating_model_type: Optional[str] = None
    slides_created: list[str] = Field(default_factory=list)
    total_slides: int = 0
    batch_update_request_count: Optional[int] = None
    note: Optional[str] = None
    message: Optional[str] = None
    missing_sections: list[str] = Field(default_factory=list)
    clarifying_questions: dict[str, list[str]] = Field(default_factory=dict)
    proposed_assumptions: dict[str, list[str]] = Field(default_factory=dict)
    recovery_instructions: Optional[str] = None


REQUIRED_SECTIONS: tuple[str, ...] = (
    "vision",
    "services_delivery_strategy",
    "commercials",
    "delivery_approach",
    "roles_and_responsibilities",
    "operating_model",
)

SECTION_DISPLAY_NAMES: dict[str, str] = {
    "vision": "Vision",
    "services_delivery_strategy": "Services Delivery Strategy",
    "commercials": "Commercials",
    "delivery_approach": "Delivery Approach",
    "roles_and_responsibilities": "Roles & Responsibilities",
    "operating_model": "Operating Model (PSO only, Partner, or both)",
}

INDUSTRY_STANDARD_ASSUMPTIONS: dict[str, list[str]] = {
    "vision": [
        "Align cloud transformation to measurable executive KPIs (e.g., 25-40% TCO reduction, accelerated feature velocity, and AI-ready data foundations).",
        "Establish an Executive Steering Committee with joint Customer and Google Cloud sponsorship.",
        "Target initial production value realization within the first 90 days via a high-impact lighthouse workload.",
    ],
    "services_delivery_strategy": [
        "Adopt a 3-Horizon Phased Delivery Roadmap: Phase 1 (Foundation & Landing Zone, Weeks 1-6), Phase 2 (Lighthouse Migration & Modernization, Weeks 7-16), Phase 3 (Scale, Optimization & Enablement, Weeks 17-24).",
        "Embed hands-on Customer Engineering enablement alongside delivery workstreams to build self-sufficiency.",
        "Gate phase transitions on Architecture Review Board (ARB) sign-off and production readiness checklists.",
    ],
    "commercials": [
        "Structure Phase 1 (Discovery & Foundation) as Milestone-Based Fixed Price for cost predictability, transitioning to Agile Pod Time & Materials (T&M) for iterative workload waves.",
        "Apply standard remote/on-site hybrid delivery ratio (80% remote, 20% on-site for key workshops and architecture sprints).",
        "Assume standard 10-business-day deliverable review and acceptance window per milestone.",
    ],
    "delivery_approach": [
        "Execute in 2-week Agile sprints with bi-weekly stakeholder demos, automated Terraform/IaC deployment pipelines, and security-by-default guardrails.",
        "Maintain a shared RAID (Risks, Assumptions, Issues, Dependencies) log reviewed weekly by Delivery Leads.",
        "Provide structured shadow-to-lead knowledge transfer during the final 4 weeks of each workstream.",
    ],
    "roles_and_responsibilities": [
        "Google Cloud PSO owns reference architecture authority, principal technical advisory, and quality assurance reviews.",
        "Customer provides dedicated Product Owner, Cloud Platform Lead, Security Approver, and SMEs (minimum 50% allocation).",
        "Delivery Partner (if applicable) owns scaled migration factory execution, runbook authoring, and L1/L2 hypercare.",
    ],
    "operating_model": [
        "Default to a Hybrid Co-Delivery Operating Model (PSO + Partner) where PSO leads architecture & lighthouse patterns and the Partner scales execution.",
        "Establish a 3-tier governance cadence: Daily Pod Standups, Weekly Tactical Delivery Syncs, and Monthly Executive Steering Committees.",
        "Define clear escalation SLAs across Technical Pod Leads -> Engagement Managers -> Executive Sponsors.",
    ],
}

CLARIFYING_QUESTIONS_BY_SECTION: dict[str, list[str]] = {
    "vision": [
        "What are the customer's top 2-3 business outcomes, target timelines, or executive mandates driving this engagement?",
        "Are there specific pain points (e.g., data center exit, legacy modernization, GenAI adoption) that anchor the Vision?",
    ],
    "services_delivery_strategy": [
        "What are the target phases, priority workstreams, or key milestones for the service delivery roadmap?",
        "What is the expected overall timeline (e.g., 3 months, 6 months, 12 months) and target lighthouse workload?",
    ],
    "commercials": [
        "What commercial structure is preferred (Fixed Price milestone, Time & Materials, Subscription, or phased hybrid)?",
        "Are there specific budget envelopes, target resource profiles, or funding incentives to reflect?",
    ],
    "delivery_approach": [
        "What delivery methodology (e.g., Agile sprints, waterfall milestones, migration factory) and tooling standards does the customer use?",
        "Are there specific compliance, security, or environment constraints we should highlight in the delivery approach?",
    ],
    "roles_and_responsibilities": [
        "Which teams from the Customer, Google Cloud PSO, and/or Partner will participate, and who owns technical sign-off?",
        "Does the customer have an existing Cloud Center of Excellence (CCoE), or will this engagement help establish one?",
    ],
    "operating_model": [
        "Should the Operating Model be 'PSO only', 'Partner', or 'both' (Hybrid PSO + Partner)?",
        "What governance cadences (e.g., Weekly Delivery Sync, Monthly SteerCo) and escalation paths should be included?",
    ],
}
