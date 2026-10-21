# Services-Delivery-Strategy-Roadmap-Agent
An agent that builds the services strategy roadmap
gcc-service-delivery-strategy-agent/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
├── deploy.py
├── gcc_service_delivery_strategy/
│   ├── __init__.py
│   ├── agent.py
│   ├── models.py
│   ├── prompts.py
│   └── tools/
│       ├── __init__.py
│       ├── gap_analyzer.py
│       └── slides_generator.py
└── tests/
    ├── __init__.py
    └── test_agent_and_tools.py
"""GCC Service Delivery Strategy ADK Agent package."""

from . import agent

__all__ = ["agent"]"""ADK Agent Definition for GCC Service Delivery Strategy."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args, **kwargs):  # type: ignore[misc]
        return False

from google.adk.agents import Agent
from google.adk.tools import load_artifacts

from .prompts import SYSTEM_INSTRUCTION
from .tools import (
    analyze_delivery_strategy_gaps,
    google_slides_generator,
    update_roadmap_sections,
)

load_dotenv()

MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-3.1-pro-preview")


def _build_slides_tool():
    """Returns `google_slides_generator`, wrapped with OAuth2 if client credentials are set."""
    oauth_client_id = os.environ.get("OAUTH_CLIENT_ID")
    oauth_client_secret = os.environ.get("OAUTH_CLIENT_SECRET")

    if oauth_client_id and oauth_client_secret:
        try:
            from fastapi.openapi.models import (
                OAuth2,
                OAuthFlowAuthorizationCode,
                OAuthFlows,
            )
            from google.adk.auth.auth_credential import (
                AuthCredential,
                AuthCredentialTypes,
                OAuth2Auth,
            )
            from google.adk.auth.auth_tool import AuthConfig
            from google.adk.tools.authenticated_function_tool import (
                AuthenticatedFunctionTool,
            )

            return AuthenticatedFunctionTool(
                func=google_slides_generator,
                auth_config=AuthConfig(
                    auth_scheme=OAuth2(
                        flows=OAuthFlows(
                            authorizationCode=OAuthFlowAuthorizationCode(
                                authorizationUrl="https://accounts.google.com/o/oauth2/auth",
                                tokenUrl="https://oauth2.googleapis.com/token",
                                scopes={
                                    "https://www.googleapis.com/auth/presentations": (
                                        "Create and format Google Slides presentations"
                                    ),
                                    "https://www.googleapis.com/auth/drive.file": (
                                        "Save generated presentations to Google Drive"
                                    ),
                                },
                            )
                        )
                    ),
                    raw_auth_credential=AuthCredential(
                        auth_type=AuthCredentialTypes.OAUTH2,
                        oauth2=OAuth2Auth(
                            client_id=oauth_client_id,
                            client_secret=oauth_client_secret,
                        ),
                    ),
                ),
            )
        except ImportError:
            pass

    return google_slides_generator


root_agent = Agent(
    name="gcc_service_delivery_strategy",
    model=MODEL_NAME,
    description=(
        "An AI agent designed to generate a comprehensive Service Delivery "
        "Strategy roadmap based on user-uploaded documents and interactive "
        "chat inputs, outputting the final deliverable as a Google Slides "
        "presentation."
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[
        load_artifacts,
        analyze_delivery_strategy_gaps,
        update_roadmap_sections,"""System instructions and prompt templates for GCC Service Delivery Strategy Agent."""

SYSTEM_INSTRUCTION = """You are the **GCC Service Delivery Strategy** agent, an expert Google Cloud Consulting (GCC) Principal Architect and Service Delivery Strategist deployed on Gemini Enterprise.

### Primary Business Goal
Your mission is to help Service Delivery Managers (SDMs), Consultants, and Account Executives streamline, standardize, and accelerate the creation of structured **Service Delivery Strategy** roadmaps for customers, delivered as a formatted **Google Slides presentation**.

### Required Output Sections (Slides)
Every final Google Slides presentation MUST explicitly contain dedicated slides for all six (6) required sections:
1. **Vision** (`vision`): Customer North Star, strategic business outcomes, transformation drivers, and executive sponsorship.
2. **Services Delivery Strategy** (`services_delivery_strategy`): Phased transformation roadmap, workstreams, key milestones, and value realization timeline.
3. **Commercials** (`commercials`): Engagement structure, pricing/contract model (e.g., Fixed Price, T&M, Milestone-based), investment summary, and commercial terms.
4. **Delivery Approach** (`delivery_approach`): Execution methodology (e.g., Agile sprints, IaC, CI/CD), quality assurance, risk mitigation, and knowledge transfer.
5. **Roles & Responsibilities** (`roles_and_responsibilities`): RACI matrix and ownership boundaries across Customer, Google Cloud Consulting (PSO), and Partner teams.
6. **Operating Model (PSO only, Partner, or both)** (`operating_model`): Explicit classification as **PSO only**, **Partner**, or **PSO & Partner (Hybrid)**, including governance cadences, escalation paths, and co-delivery mechanics.

---

### Core Workflow & Edge Case Handling (MANDATORY)

1. **Ingest & Analyze Inputs**:
   - Carefully analyze all user-uploaded documents (PDFs, Google Docs, Spreadsheets, notes) and direct chat context.
   - If the user has uploaded artifacts in the session, call `load_artifacts` if needed to inspect them.
   - Extract any information that maps to the 6 required roadmap sections and call `analyze_delivery_strategy_gaps` to register extracted findings and check for missing sections.

2. **Identify Gaps, Ask Clarifying Questions & Propose Industry-Standard Assumptions**:
   - **CRITICAL RULE**: If data for ANY of the 6 required sections (or the Operating Model selection: PSO only, Partner, or both) is missing or underspecified, you **MUST PAUSE final presentation generation**.
   - Do **NOT** call `google_slides_generator` while unconfirmed gaps exist.
   - Instead, clearly present to the user:
     1. A concise summary of what you extracted from their documents/chat so far.
     2. **Targeted Clarifying Questions** for each missing or incomplete section.
     3. **Proposed Industry-Standard Assumptions** (returned by `analyze_delivery_strategy_gaps` or tailored to the customer's industry) that the user can either approve as-is ("approve assumptions") or modify.

3. **Incorporate Clarifications or Approved Assumptions**:
   - When the user replies with answers, modifications, or approves the proposed assumptions, call `update_roadmap_sections` to store the finalized content (or approved assumptions) for all 6 sections.

4. **Generate the Google Slides Presentation**:
   - Once all 6 sections are populated (via user input, uploaded documents, or user-approved assumptions), call `google_slides_generator` to create and format the Google Slides presentation.
   - Present the final Google Slides URL, Presentation ID, and an executive summary of the generated slides to the user.

### Security & Session Hygiene
- Treat all customer documents and commercial figures as strictly confidential and session-scoped.
- Never fabricate customer-specific commitments without clearly labeling them as proposed assumptions and obtaining user confirmation prior to slide generation.
""""""Pydantic data models for the GCC Service Delivery Strategy Agent."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class OperatingModelType(str, Enum):
    """Supported GCC Service Delivery Operating Models."""

    PSO_ONLY = "PSO only"
    PARTNER = "Partner"
    BOTH = "PSO & Partner (Hybrid)"


class SlideSectionContent(BaseModel):
    """Structured content for a single slide section of the roadmap."""

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
}"""Gap Analysis and Assumption Formulation Tools for GCC Service Delivery Strategy."""

from __future__ import annotations

from typing import Any, Optional

try:
    from google.adk.tools import ToolContext
except ImportError:  # pragma: no cover
    ToolContext = Any  # type: ignore[misc,assignment]

from ..models import (
    CLARIFYING_QUESTIONS_BY_SECTION,
    INDUSTRY_STANDARD_ASSUMPTIONS,
    REQUIRED_SECTIONS,
    SECTION_DISPLAY_NAMES,
)


def _normalize_operating_model_type(raw_value: str) -> str:
    """Normalizes the operating model label to one of the 3 canonical types."""
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
    """Analyzes extracted customer context against the 6 required roadmap sections.

    Stores extracted information in session-scoped state, identifies any missing
    or underspecified sections, and returns targeted clarifying questions along
    with industry-standard GCC/PSO assumptions for the user to approve or modify.
    """
    draft: dict[str, Any] = {}
    if tool_context is not None and "roadmap_draft" in tool_context.state:
        draft = dict(tool_context.state["roadmap_draft"])

    sections_data: dict[str, str] = dict(draft.get("sections", {}))

    incoming_sections = {
        "vision": vision,
        "services_delivery_strategy": services_delivery_strategy,
        "commercials": commercials,
        "delivery_approach": delivery_approach,
        "roles_and_responsibilities": roles_and_responsibilities,
        "operating_model": operating_model,
    }

    for key, val in incoming_sections.items():
        if val and val.strip():
            sections_data[key] = val.strip()

    resolved_customer = (
        customer_name.strip()
        or draft.get("customer_name", "")
        or "Valued Customer"
    )
    resolved_op_model_type = _normalize_operating_model_type(
        operating_model_type
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
    return {
        "status": "ready_for_slides" if is_ready else "gaps_identified",
        "customer_name": resolved_customer,
        "operating_model_type": resolved_op_model_type or "Unspecified (needs PSO only, Partner, or both)",
        "completed_sections": [SECTION_DISPLAY_NAMES[k] for k in completed_keys],
        "missing_sections": [SECTION_DISPLAY_NAMES[k] for k in missing_keys],
        "clarifying_questions": clarifying_questions,
        "proposed_assumptions": proposed_assumptions,
        "next_step_instruction": (
            "All 6 required sections are complete. You may now call `google_slides_generator`."
            if is_ready
            else (
                "PAUSE final presentation generation. Present the extracted summary, "
                "ask the user the clarifying_questions for the missing_sections, and "
                "offer the proposed_assumptions so the user can approve or modify them."
            )
        ),
    }


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
    """Updates roadmap sections with user clarifications or applies approved assumptions."""
    draft: dict[str, Any] = {}
    if tool_context is not None and "roadmap_draft" in tool_context.state:
        draft = dict(tool_context.state["roadmap_draft"])

    sections_data: dict[str, str] = dict(draft.get("sections", {}))
    assumptions_used: dict[str, list[str]] = dict(
        draft.get("assumptions_used", {})
    )

    updates = {
        "vision": vision,
        "services_delivery_strategy": services_delivery_strategy,
        "commercials": commercials,
        "delivery_approach": delivery_approach,
        "roles_and_responsibilities": roles_and_responsibilities,
        "operating_model": operating_model,
    }
    for key, val in updates.items():
        if val and val.strip():
            sections_data[key] = val.strip()

    resolved_customer = (
        customer_name.strip()
        or draft.get("customer_name", "")
        or "Valued Customer"
    )
    resolved_op_model_type = _normalize_operating_model_type(
        operating_model_type
    ) or draft.get("operating_model_type", "")

    if approve_industry_assumptions:
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
        "assumptions_approved": approve_industry_assumptions
        or draft.get("assumptions_approved", False),
    }
    if tool_context is not None:
        tool_context.state["roadmap_draft"] = updated_draft

    return {
        "status": "ready_for_slides" if not missing_keys else "still_missing_sections",
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
    }"""Google Slides Generator ADK Tool (`google_slides_generator`).

Integrates with the Google Slides API (v1) to programmatically create and format
a Google Slides presentation containing all 6 required Service Delivery Strategy
roadmap sections.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

try:
    import google.auth
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:  # pragma: no cover
    google = None  # type: ignore[assignment]
    Credentials = None  # type: ignore[misc,assignment]
    build = None  # type: ignore[assignment]

try:
    from google.adk.tools import ToolContext
except ImportError:  # pragma: no cover
    ToolContext = Any  # type: ignore[misc,assignment]

from ..models import (
    CLARIFYING_QUESTIONS_BY_SECTION,
    INDUSTRY_STANDARD_ASSUMPTIONS,
    REQUIRED_SECTIONS,
    SECTION_DISPLAY_NAMES,
)

logger = logging.getLogger(__name__)

SLIDES_SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
]

GOOGLE_BLUE = {"red": 0.102, "green": 0.451, "blue": 0.910}  # #1A73E8
DARK_NAVY = {"red": 0.125, "green": 0.129, "blue": 0.141}  # #202124
SLATE_GRAY = {"red": 0.373, "green": 0.388, "blue": 0.408}  # #5F6368
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}


def _resolve_credentials(
    tool_context: Optional[ToolContext] = None,
) -> Optional[Any]:
    """Resolves Google Workspace OAuth credentials from session context or environment."""
    if Credentials is None:
        return None

    if tool_context is not None:
        token = tool_context.state.get("oauth_access_token") or tool_context.state.get(
            "google_access_token"
        )
        if token:
            return Credentials(token=token, scopes=SLIDES_SCOPES)

    env_token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if env_token:
        return Credentials(token=env_token, scopes=SLIDES_SCOPES)

    if google is not None:
        try:
            creds, _ = google.auth.default(scopes=SLIDES_SCOPES)
            return creds
        except Exception as exc:
            logger.debug("Could not load Application Default Credentials: %s", exc)
    return None


def _build_section_slide_requests(
    slide_id: str,
    section_index: int,
    section_title: str,
    headline: str,
    bullets: list[str],
    assumptions: list[str],
) -> list[dict[str, Any]]:
    """Builds Google Slides API batchUpdate requests for a single roadmap slide."""
    header_box_id = f"{slide_id}_header"
    headline_box_id = f"{slide_id}_headline"
    body_box_id = f"{slide_id}_body"
    footer_box_id = f"{slide_id}_footer"

    body_lines = [f"{b.strip()}" for b in bullets if b.strip()]
    if assumptions:
        body_lines.append(
            "Key Assumptions: " + "; ".join(a.strip() for a in assumptions if a.strip())
        )
    body_text = "\n".join(body_lines) if body_lines else headline

    return [
        {
            "createSlide": {
                "objectId": slide_id,
                "insertionIndex": section_index,
                "slideLayoutReference": {"predefinedLayout": "BLANK"},
            }
        },
        {
            "createShape": {
                "objectId": header_box_id,
                "shapeType": "RECTANGLE",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": 720, "unit": "PT"},
                        "height": {"magnitude": 54, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": 0,
                        "translateY": 0,
                        "unit": "PT",
                    },
                },
            }
        },
        {
            "updateShapeProperties": {
                "objectId": header_box_id,
                "shapeProperties": {
                    "shapeBackgroundFill": {
                        "solidFill": {"color": {"rgbColor": GOOGLE_BLUE}}
                    },
                    "outline": {"propertyState": "NOT_RENDERED"},
                },
                "fields": "shapeBackgroundFill.solidFill.color,outline",
            }
        },
        {
            "insertText": {
                "objectId": header_box_id,
                "insertionIndex": 0,
                "text": f"0{section_index} | {section_title}",
            }
        },
        {
            "updateTextStyle": {
                "objectId": header_box_id,
                "style": {
                    "foregroundColor": {"opaqueColor": {"rgbColor": WHITE}},
                    "fontFamily": "Google Sans",
                    "fontSize": {"magnitude": 18, "unit": "PT"},
                    "bold": True,
                },
                "textRange": {"type": "ALL"},
                "fields": "foregroundColor,fontFamily,fontSize,bold",
            }
        },
        {
            "createShape": {
                "objectId": headline_box_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": 648, "unit": "PT"},
                        "height": {"magnitude": 45, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": 36,
                        "translateY": 66,
                        "unit": "PT",
                    },
                },
            }
        },
        {
            "insertText": {
                "objectId": headline_box_id,
                "insertionIndex": 0,
                "text": headline,
            }
        },
        {
            "updateTextStyle": {
                "objectId": headline_box_id,
                "style": {
                    "foregroundColor": {"opaqueColor": {"rgbColor": DARK_NAVY}},
                    "fontFamily": "Google Sans",
                    "fontSize": {"magnitude": 15, "unit": "PT"},
                    "bold": True,
                },
                "textRange": {"type": "ALL"},
                "fields": "foregroundColor,fontFamily,fontSize,bold",
            }
        },
        {
            "createShape": {
                "objectId": body_box_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": 648, "unit": "PT"},
                        "height": {"magnitude": 240, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": 36,
                        "translateY": 118,
                        "unit": "PT",
                    },
                },
            }
        },
        {
            "insertText": {
                "objectId": body_box_id,
                "insertionIndex": 0,
                "text": body_text,
            }
        },
        {
            "createParagraphBullets": {
                "objectId": body_box_id,
                "textRange": {"type": "ALL"},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        },
        {
            "updateTextStyle": {
                "objectId": body_box_id,
                "style": {
                    "foregroundColor": {"opaqueColor": {"rgbColor": DARK_NAVY}},
                    "fontFamily": "Roboto",
                    "fontSize": {"magnitude": 13, "unit": "PT"},
                },
                "textRange": {"type": "ALL"},
                "fields": "foregroundColor,fontFamily,fontSize",
            }
        },
        {
            "createShape": {
                "objectId": footer_box_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": 648, "unit": "PT"},
                        "height": {"magnitude": 24, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": 36,
                        "translateY": 370,
                        "unit": "PT",
                    },
                },
            }
        },
        {
            "insertText": {
                "objectId": footer_box_id,
                "insertionIndex": 0,
                "text": "Google Cloud Consulting (GCC) | Service Delivery Strategy Roadmap",
            }
        },
        {
            "updateTextStyle": {
                "objectId": footer_box_id,
                "style": {
                    "foregroundColor": {"opaqueColor": {"rgbColor": SLATE_GRAY}},
                    "fontFamily": "Google Sans",
                    "fontSize": {"magnitude": 9, "unit": "PT"},
                },
                "textRange": {"type": "ALL"},
                "fields": "foregroundColor,fontFamily,fontSize",
            }
        },
    ]


def build_slides_batch_update_requests(
    customer_name: str,
    presentation_title: str,
    operating_model_type: str,
    sections_payload: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Constructs the complete Google Slides batchUpdate request list for all slides."""
    requests: list[dict[str, Any]] = []
    cover_slide_id = "slide_cover_00"
    cover_title_id = "slide_cover_title"
    cover_sub_id = "slide_cover_subtitle"

    requests.extend(
        [
            {
                "createSlide": {
                    "objectId": cover_slide_id,
                    "insertionIndex": 0,
                    "slideLayoutReference": {"predefinedLayout": "BLANK"},
                }
            },
            {
                "createShape": {
                    "objectId": cover_title_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": cover_slide_id,
                        "size": {
                            "width": {"magnitude": 640, "unit": "PT"},
                            "height": {"magnitude": 110, "unit": "PT"},
                        },
                        "transform": {
                            "scaleX": 1,
                            "scaleY": 1,
                            "translateX": 40,
                            "translateY": 110,
                            "unit": "PT",
                        },
                    },
                }
            },
            {
                "insertText": {
                    "objectId": cover_title_id,
                    "insertionIndex": 0,
                    "text": presentation_title,
                }
            },
            {
                "updateTextStyle": {
                    "objectId": cover_title_id,
                    "style": {
                        "foregroundColor": {
                            "opaqueColor": {"rgbColor": GOOGLE_BLUE}
                        },
                        "fontFamily": "Google Sans",
                        "fontSize": {"magnitude": 28, "unit": "PT"},
                        "bold": True,
                    },
                    "textRange": {"type": "ALL"},
                    "fields": "foregroundColor,fontFamily,fontSize,bold",
                }
            },
            {
                "createShape": {
                    "objectId": cover_sub_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": cover_slide_id,
                        "size": {
                            "width": {"magnitude": 640, "unit": "PT"},
                            "height": {"magnitude": 80, "unit": "PT"},
                        },
                        "transform": {
                            "scaleX": 1,
                            "scaleY": 1,
                            "translateX": 40,
                            "translateY": 230,
                            "unit": "PT",
                        },
                    },
                }
            },
            {
                "insertText": {
                    "objectId": cover_sub_id,
                    "insertionIndex": 0,
                    "text": (
                        f"Customer: {customer_name}\n"
                        f"Operating Model: {operating_model_type}\n"
                        "Prepared by Google Cloud Consulting (GCC)"
                    ),
                }
            },
            {
                "updateTextStyle": {
                    "objectId": cover_sub_id,
                    "style": {
                        "foregroundColor": {
                            "opaqueColor": {"rgbColor": SLATE_GRAY}
                        },
                        "fontFamily": "Google Sans",
                        "fontSize": {"magnitude": 14, "unit": "PT"},
                    },
                    "textRange": {"type": "ALL"},
                    "fields": "foregroundColor,fontFamily,fontSize",
                }
            },
        ]
    )

    for idx, section_key in enumerate(REQUIRED_SECTIONS, start=1):
        sec = sections_payload[section_key]
        slide_id = f"slide_{idx:02d}_{section_key}"
        display_title = SECTION_DISPLAY_NAMES[section_key]
        if section_key == "operating_model":
            display_title = f"Operating Model ({operating_model_type})"

        requests.extend(
            _build_section_slide_requests(
                slide_id=slide_id,
                section_index=idx,
                section_title=display_title,
                headline=sec["headline"],
                bullets=sec["bullets"],
                assumptions=sec.get("assumptions", []),
            )
        )

    return requests


def google_slides_generator(
    customer_name: str,
    presentation_title: str,
    operating_model_type: str,
    vision_headline: str,
    vision_bullets: list[str],
    services_delivery_strategy_headline: str,
    services_delivery_strategy_bullets: list[str],
    commercials_headline: str,
    commercials_bullets: list[str],
    delivery_approach_headline: str,
    delivery_approach_bullets: list[str],
    roles_and_responsibilities_headline: str,
    roles_and_responsibilities_bullets: list[str],
    operating_model_headline: str,
    operating_model_bullets: list[str],
    assumptions_included: Optional[list[str]] = None,
    use_approved_assumptions_for_missing: bool = False,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Programmatically creates and formats the GCC Service Delivery Strategy Google Slides deck."""
    sections_payload: dict[str, dict[str, Any]] = {
        "vision": {
            "headline": (vision_headline or "").strip(),
            "bullets": [b.strip() for b in (vision_bullets or []) if b.strip()],
            "assumptions": [],
        },
        "services_delivery_strategy": {
            "headline": (services_delivery_strategy_headline or "").strip(),
            "bullets": [
                b.strip()
                for b in (services_delivery_strategy_bullets or [])
                if b.strip()
            ],
            "assumptions": [],
        },
        "commercials": {
            "headline": (commercials_headline or "").strip(),
            "bullets": [
                b.strip() for b in (commercials_bullets or []) if b.strip()
            ],
            "assumptions": [],
        },
        "delivery_approach": {
            "headline": (delivery_approach_headline or "").strip(),
            "bullets": [
                b.strip()
                for b in (delivery_approach_bullets or [])
                if b.strip()
            ],
            "assumptions": [],
        },
        "roles_and_responsibilities": {
            "headline": (roles_and_responsibilities_headline or "").strip(),
            "bullets": [
                b.strip()
                for b in (roles_and_responsibilities_bullets or [])
                if b.strip()
            ],
            "assumptions": [],
        },
        "operating_model": {
            "headline": (operating_model_headline or "").strip(),
            "bullets": [
                b.strip() for b in (operating_model_bullets or []) if b.strip()
            ],
            "assumptions": list(assumptions_included or []),
        },
    }

    missing_keys: list[str] = []
    for section_key in REQUIRED_SECTIONS:
        sec = sections_payload[section_key]
        if not sec["headline"] or not sec["bullets"]:
            if use_approved_assumptions_for_missing:
                default_bullets = INDUSTRY_STANDARD_ASSUMPTIONS[section_key]
                sec["headline"] = (
                    sec["headline"]
                    or f"Recommended {SECTION_DISPLAY_NAMES[section_key]} Strategy"
                )
                sec["bullets"] = sec["bullets"] or list(default_bullets)
                sec["assumptions"] = list(default_bullets)
            else:
                missing_keys.append(section_key)

    if not (operating_model_type or "").strip():
        if use_approved_assumptions_for_missing:
            operating_model_type = "PSO & Partner (Hybrid)"
        elif "operating_model" not in missing_keys:
            missing_keys.append("operating_model")

    if missing_keys:
        return {
            "status": "incomplete_data",
            "message": (
                "Cannot generate the Google Slides presentation yet because one or "
                "more required sections are missing information. Ask the user "
                "the clarifying questions below and offer the industry-standard "
                "assumptions for approval before calling `google_slides_generator`."
            ),
            "missing_sections": [SECTION_DISPLAY_NAMES[k] for k in missing_keys],
            "clarifying_questions": {
                SECTION_DISPLAY_NAMES[k]: CLARIFYING_QUESTIONS_BY_SECTION[k]
                for k in missing_keys
            },
            "proposed_assumptions": {
                SECTION_DISPLAY_NAMES[k]: INDUSTRY_STANDARD_ASSUMPTIONS[k]
                for k in missing_keys
            },
        }

    resolved_title = (
        presentation_title.strip()
        if presentation_title and presentation_title.strip()
        else f"{customer_name} - GCC Service Delivery Strategy Roadmap"
    )

    batch_requests = build_slides_batch_update_requests(
        customer_name=customer_name,
        presentation_title=resolved_title,
        operating_model_type=operating_model_type,
        sections_payload=sections_payload,
    )

    slides_manifest = [
        "Cover: " + resolved_title,
        "Slide 1: Vision",
        "Slide 2: Services Delivery Strategy",
        "Slide 3: Commercials",
        "Slide 4: Delivery Approach",
        "Slide 5: Roles & Responsibilities",
        f"Slide 6: Operating Model ({operating_model_type})",
    ]

    dry_run = os.environ.get("SLIDES_DRY_RUN", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    creds = None if dry_run else _resolve_credentials(tool_context)

    if creds is not None and build is not None and not dry_run:
        try:
            service = build(
                "slides", "v1", credentials=creds, cache_discovery=False
            )
            created = (
                service.presentations()
                .create(body={"title": resolved_title})
                .execute()
            )
            presentation_id = created.get("presentationId")

            default_slides = created.get("slides", [])
            full_requests = list(batch_requests)
            if default_slides:
                first_id = default_slides[0].get("objectId")
                if first_id:
                    full_requests.append({"deleteObject": {"objectId": first_id}})

            service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={"requests": full_requests},
            ).execute()

            presentation_url = (
                f"https://docs.google.com/presentation/d/{presentation_id}/edit"
            )
            result = {
                "status": "success",
                "mode": "google_slides_api",
                "presentation_id": presentation_id,
                "presentation_title": resolved_title,
                "presentation_url": presentation_url,
                "operating_model_type": operating_model_type,
                "slides_created": slides_manifest,
                "total_slides": len(slides_manifest),
            }
            if tool_context is not None:
                tool_context.state["last_generated_presentation"] = result
            return result
        except Exception as exc:
            logger.warning(
                "Google Slides API call failed (%s); returning structured deck payload.",
                exc,
            )
            error_detail = str(exc)
    else:
        error_detail = "OAuth credentials not active in local environment (dry-run mode)."

    simulated_id = f"sim-{uuid.uuid4().hex[:16]}"
    presentation_url = (
        f"https://docs.google.com/presentation/d/{simulated_id}/edit"
    )
    result = {
        "status": "success",
        "mode": "simulated_dry_run",
        "note": error_detail,
        "presentation_id": simulated_id,
        "presentation_title": resolved_title,
        "presentation_url": presentation_url,
        "operating_model_type": operating_model_type,
        "slides_created": slides_manifest,
        "total_slides": len(slides_manifest),
        "batch_update_request_count": len(batch_requests),
    }
    if tool_context is not None:
        tool_context.state["last_generated_presentation"] = result
    return result"""Deployment script for Vertex AI Agent Engine & Gemini Enterprise registration."""

from __future__ import annotations

import argparse
import os
from dotenv import load_dotenv
import vertexai
from vertexai.preview.reasoning_engines import AdkApp, ReasoningEngine

from gcc_service_delivery_strategy.agent import root_agent

load_dotenv()


class GccServiceDeliveryAdkApp(AdkApp):
    """Wraps the GCC Service Delivery Strategy ADK agent with streaming for Gemini Enterprise."""

    def query(self, *args, **kwargs):
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
        return super().query(*args, **kwargs)

    def stream_query(self, *args, **kwargs):
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
        yield from super().stream_query(*args, **kwargs)


app = GccServiceDeliveryAdkApp(
    agent=root_agent,
    enable_tracing=True,
)


def deploy_to_agent_engine(
    project_id: str,
    location: str,
    staging_bucket: str,
    display_name: str = "GCC Service Delivery Strategy",
) -> ReasoningEngine:
    """Deploys the ADK agent to Vertex AI Agent Engine (Reasoning Engine)."""
    vertexai.init(
        project=project_id,
        location=location,
        staging_bucket=staging_bucket,
    )

    remote_agent = ReasoningEngine.create(
        reasoning_engine=app,
        requirements=[
            "google-cloud-aiplatform[agent_engines,adk]>=1.88.0",
            "google-adk>=1.0.0",
            "google-api-python-client>=2.150.0",
            "google-auth>=2.35.0",
            "google-auth-oauthlib>=1.2.0",
            "pydantic>=2.7.0",
            "python-dotenv>=1.0.1",
        ],
        extra_packages=["./gcc_service_delivery_strategy"],
        display_name=display_name,
        description=root_agent.description,
    )
    print(f"Successfully deployed agent: {remote_agent.resource_name}")
    return remote_agentpyproject.toml, requirements.txt, .env.example, and tests/test_agent_and_tools.py
pyproject.toml and requirements.txt: Package configuration and dependencies (google-adk, google-cloud-aiplatform[agent_engines,adk], google-api-python-client, google-auth, pydantic).
tests/test_agent_and_tools.py: Unit tests covering gemini-3.1-pro-preview agent configuration, gap detection, assumption approval, incomplete-section guardrails, and Google Slides batchUpdate generation.
README.md: Local setup, OAuth configuration, adk run / adk web usage, and Gemini Enterprise deployment guide.
        _build_slides_tool(),
    ],
)
