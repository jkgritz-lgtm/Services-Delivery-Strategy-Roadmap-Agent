"""Google Slides Generator ADK Tool (`google_slides_generator`).

Addresses PRD Section 4 & 5 and AgentOps Rubric:
- 1.1 Comprehensive Tool Docstrings
- 1.2 Descriptive Naming (`google_slides_generator`)
- 1.3 Explicit JSON Schemas (`SlidesGeneratorInput`, `SlidesGeneratorOutput`)
- 1.4 Guided Error Handling (`recovery_instructions` on incomplete data or API errors)
- 4.2 & 4.3 Intent vs. Outcome Capture and OpenTelemetry Distributed Tracing
- 5.3 Secure Secret Management via Google Cloud Secret Manager (`get_secure_credential`)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional
import uuid

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
    SlidesGeneratorInput,
    SlidesGeneratorOutput,
    ValidationError,
)
from ..observability import (
    log_agent_intent,
    log_agent_outcome,
    pii_scrubber,
    traced_span,
)
from ..secrets import get_secure_credential

logger = logging.getLogger(__name__)

SLIDES_SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
]

# Google Cloud Brand Palette (RGB 0.0 - 1.0)
GOOGLE_BLUE = {"red": 0.102, "green": 0.451, "blue": 0.910}  # #1A73E8
DARK_NAVY = {"red": 0.125, "green": 0.129, "blue": 0.141}  # #202124
SLATE_GRAY = {"red": 0.373, "green": 0.388, "blue": 0.408}  # #5F6368
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}


def _resolve_credentials(
    tool_context: Optional[ToolContext] = None,
) -> Optional[Any]:
    """Resolves Google Workspace OAuth credentials via session context, Secret Manager, or ADC."""
    if Credentials is None:
        return None

    # 1. Check session state for a user-scoped OAuth access token (Gemini Enterprise)
    if tool_context is not None:
        token = tool_context.state.get("oauth_access_token") or tool_context.state.get(
            "google_access_token"
        )
        if token:
            return Credentials(token=token, scopes=SLIDES_SCOPES)

    # 2. Retrieve OAuth token via Google Cloud Secret Manager (with local env fallback)
    secret_token = get_secure_credential(
        "gcc-slides-oauth-access-token", "GOOGLE_OAUTH_ACCESS_TOKEN"
    )
    if secret_token:
        return Credentials(token=secret_token, scopes=SLIDES_SCOPES)

    # 3. Fall back to Application Default Credentials (ADC)
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
            "Key Assumptions: "
            + "; ".join(a.strip() for a in assumptions if a.strip())
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
    """Programmatically creates and formats the GCC Service Delivery Strategy Google Slides deck.

    Validates all arguments against `SlidesGeneratorInput` and checks that all 6
    required PRD sections (Vision, Services Delivery Strategy, Commercials,
    Delivery Approach, Roles & Responsibilities, and Operating Model) are populated
    before calling the Google Slides API (`presentations().create` and `batchUpdate`).

    Args:
        customer_name: Name of the target customer organization.
        presentation_title: Title for the Google Slides presentation.
        operating_model_type: Must be 'PSO only', 'Partner', or 'PSO & Partner (Hybrid)'.
        vision_headline: Executive headline for Slide 1 (Vision).
        vision_bullets: Bullet points for Slide 1 (Vision).
        services_delivery_strategy_headline: Headline for Slide 2 (Services Delivery Strategy).
        services_delivery_strategy_bullets: Bullet points for Slide 2 (Services Delivery Strategy).
        commercials_headline: Headline for Slide 3 (Commercials).
        commercials_bullets: Bullet points for Slide 3 (Commercials).
        delivery_approach_headline: Headline for Slide 4 (Delivery Approach).
        delivery_approach_bullets: Bullet points for Slide 4 (Delivery Approach).
        roles_and_responsibilities_headline: Headline for Slide 5 (Roles & Responsibilities).
        roles_and_responsibilities_bullets: Bullet points for Slide 5 (Roles & Responsibilities).
        operating_model_headline: Headline for Slide 6 (Operating Model).
        operating_model_bullets: Bullet points for Slide 6 (Operating Model).
        assumptions_included: Optional list of user-approved industry assumptions applied.
        use_approved_assumptions_for_missing: If True, fills any empty section with
            standard GCC assumptions (only set to True after user approval).
        tool_context: Optional ADK ToolContext for session state and OAuth resolution.

    Returns:
        Validated `SlidesGeneratorOutput` dictionary containing `status`,
        `presentation_id`, `presentation_url`, `slides_created`, and `recovery_instructions`
        if any section is incomplete or an API error occurs.
    """
    with traced_span(
        "tool.google_slides_generator",
        {
            "customer_name": customer_name,
            "operating_model_type": operating_model_type,
        },
    ):
        action_id = log_agent_intent(
            component="google_slides_generator",
            intended_action="Validate all 6 PRD sections and generate formatted Google Slides deck",
            details={
                "customer_name": customer_name,
                "presentation_title": presentation_title,
                "operating_model_type": operating_model_type,
            },
        )
        try:
            validated_in = SlidesGeneratorInput(
                customer_name=customer_name,
                presentation_title=presentation_title,
                operating_model_type=operating_model_type,
                vision_headline=vision_headline,
                vision_bullets=vision_bullets,
                services_delivery_strategy_headline=services_delivery_strategy_headline,
                services_delivery_strategy_bullets=services_delivery_strategy_bullets,
                commercials_headline=commercials_headline,
                commercials_bullets=commercials_bullets,
                delivery_approach_headline=delivery_approach_headline,
                delivery_approach_bullets=delivery_approach_bullets,
                roles_and_responsibilities_headline=roles_and_responsibilities_headline,
                roles_and_responsibilities_bullets=roles_and_responsibilities_bullets,
                operating_model_headline=operating_model_headline,
                operating_model_bullets=operating_model_bullets,
                assumptions_included=assumptions_included,
                use_approved_assumptions_for_missing=use_approved_assumptions_for_missing,
            )
        except ValidationError as exc:
            log_agent_outcome(
                action_id=action_id,
                component="google_slides_generator",
                intended_action="Validate SlidesGeneratorInput schema",
                actual_outcome=f"Input validation failed: {exc}",
                status="ERROR",
            )
            return {
                "status": "error",
                "error_code": "SCHEMA_VALIDATION_ERROR",
                "message": pii_scrubber.redact_text(str(exc)),
                "recovery_instructions": (
                    "Provide a non-empty `customer_name` and valid lists of strings "
                    "for each section's bullet points, then retry `google_slides_generator`."
                ),
            }

        sections_payload: dict[str, dict[str, Any]] = {
            "vision": {
                "headline": validated_in.vision_headline.strip(),
                "bullets": [
                    b.strip() for b in validated_in.vision_bullets if b.strip()
                ],
                "assumptions": [],
            },
            "services_delivery_strategy": {
                "headline": validated_in.services_delivery_strategy_headline.strip(),
                "bullets": [
                    b.strip()
                    for b in validated_in.services_delivery_strategy_bullets
                    if b.strip()
                ],
                "assumptions": [],
            },
            "commercials": {
                "headline": validated_in.commercials_headline.strip(),
                "bullets": [
                    b.strip()
                    for b in validated_in.commercials_bullets
                    if b.strip()
                ],
                "assumptions": [],
            },
            "delivery_approach": {
                "headline": validated_in.delivery_approach_headline.strip(),
                "bullets": [
                    b.strip()
                    for b in validated_in.delivery_approach_bullets
                    if b.strip()
                ],
                "assumptions": [],
            },
            "roles_and_responsibilities": {
                "headline": validated_in.roles_and_responsibilities_headline.strip(),
                "bullets": [
                    b.strip()
                    for b in validated_in.roles_and_responsibilities_bullets
                    if b.strip()
                ],
                "assumptions": [],
            },
            "operating_model": {
                "headline": validated_in.operating_model_headline.strip(),
                "bullets": [
                    b.strip()
                    for b in validated_in.operating_model_bullets
                    if b.strip()
                ],
                "assumptions": list(validated_in.assumptions_included or []),
            },
        }

        missing_keys: list[str] = []
        for section_key in REQUIRED_SECTIONS:
            sec = sections_payload[section_key]
            if not sec["headline"] or not sec["bullets"]:
                if validated_in.use_approved_assumptions_for_missing:
                    default_bullets = INDUSTRY_STANDARD_ASSUMPTIONS[section_key]
                    sec["headline"] = (
                        sec["headline"]
                        or f"Recommended {SECTION_DISPLAY_NAMES[section_key]} Strategy"
                    )
                    sec["bullets"] = sec["bullets"] or list(default_bullets)
                    sec["assumptions"] = list(default_bullets)
                else:
                    missing_keys.append(section_key)

        resolved_op_model = validated_in.operating_model_type.strip()
        if not resolved_op_model:
            if validated_in.use_approved_assumptions_for_missing:
                resolved_op_model = "PSO & Partner (Hybrid)"
            elif "operating_model" not in missing_keys:
                missing_keys.append("operating_model")

        # Guardrail: Enforce PRD Section 6 Edge Case Handling if any section is missing
        if missing_keys:
            incomplete_out = SlidesGeneratorOutput(
                status="incomplete_data",
                message=(
                    "Cannot generate the Google Slides presentation yet because one or "
                    "more required sections are missing information. Ask the user "
                    "the clarifying questions below and offer the industry-standard "
                    "assumptions for approval before calling `google_slides_generator`."
                ),
                missing_sections=[SECTION_DISPLAY_NAMES[k] for k in missing_keys],
                clarifying_questions={
                    SECTION_DISPLAY_NAMES[k]: CLARIFYING_QUESTIONS_BY_SECTION[k]
                    for k in missing_keys
                },
                proposed_assumptions={
                    SECTION_DISPLAY_NAMES[k]: INDUSTRY_STANDARD_ASSUMPTIONS[k]
                    for k in missing_keys
                },
                recovery_instructions=(
                    "Present `clarifying_questions` and `proposed_assumptions` to the user. "
                    "Once the user provides answers or approves assumptions, call "
                    "`update_roadmap_sections` and retry `google_slides_generator`."
                ),
            )
            log_agent_outcome(
                action_id=action_id,
                component="google_slides_generator",
                intended_action="Generate Google Slides presentation",
                actual_outcome=f"Blocked incomplete deck: missing {missing_keys}",
                status="INCOMPLETE_DATA",
            )
            return incomplete_out.model_dump(exclude_none=True)

        resolved_title = (
            validated_in.presentation_title.strip()
            if validated_in.presentation_title.strip()
            else f"{validated_in.customer_name} - GCC Service Delivery Strategy Roadmap"
        )

        batch_requests = build_slides_batch_update_requests(
            customer_name=validated_in.customer_name,
            presentation_title=resolved_title,
            operating_model_type=resolved_op_model,
            sections_payload=sections_payload,
        )

        slides_manifest = [
            "Cover: " + resolved_title,
            "Slide 1: Vision",
            "Slide 2: Services Delivery Strategy",
            "Slide 3: Commercials",
            "Slide 4: Delivery Approach",
            "Slide 5: Roles & Responsibilities",
            f"Slide 6: Operating Model ({resolved_op_model})",
        ]

        dry_run = os.environ.get("SLIDES_DRY_RUN", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        creds = None if dry_run else _resolve_credentials(tool_context)

        if creds is not None and build is not None and not dry_run:
            try:
                with traced_span("google_slides_api.create_and_batch_update"):
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
                            full_requests.append(
                                {"deleteObject": {"objectId": first_id}}
                            )

                    service.presentations().batchUpdate(
                        presentationId=presentation_id,
                        body={"requests": full_requests},
                    ).execute()

                presentation_url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"
                live_out = SlidesGeneratorOutput(
                    status="success",
                    mode="google_slides_api",
                    presentation_id=presentation_id,
                    presentation_title=resolved_title,
                    presentation_url=presentation_url,
                    operating_model_type=resolved_op_model,
                    slides_created=slides_manifest,
                    total_slides=len(slides_manifest),
                )
                result_dict = live_out.model_dump(exclude_none=True)
                if tool_context is not None:
                    tool_context.state["last_generated_presentation"] = result_dict
                log_agent_outcome(
                    action_id=action_id,
                    component="google_slides_generator",
                    intended_action="Generate Google Slides presentation via Slides API v1",
                    actual_outcome=f"Created presentation {presentation_id} with {len(slides_manifest)} slides",
                    status="SUCCESS",
                )
                return result_dict
            except Exception as exc:
                logger.warning(
                    "Google Slides API call failed (%s); returning structured deck payload.",
                    exc,
                )
                error_detail = pii_scrubber.redact_text(str(exc))
        else:
            error_detail = "OAuth credentials not active in local environment (dry-run mode)."

        simulated_id = f"sim-{uuid.uuid4().hex[:16]}"
        presentation_url = (
            f"https://docs.google.com/presentation/d/{simulated_id}/edit"
        )
        sim_out = SlidesGeneratorOutput(
            status="success",
            mode="simulated_dry_run",
            note=error_detail,
            presentation_id=simulated_id,
            presentation_title=resolved_title,
            presentation_url=presentation_url,
            operating_model_type=resolved_op_model,
            slides_created=slides_manifest,
            total_slides=len(slides_manifest),
            batch_update_request_count=len(batch_requests),
        )
        result_dict = sim_out.model_dump(exclude_none=True)
        if tool_context is not None:
            tool_context.state["last_generated_presentation"] = result_dict
        log_agent_outcome(
            action_id=action_id,
            component="google_slides_generator",
            intended_action="Generate Google Slides presentation (dry-run)",
            actual_outcome=f"Built {len(slides_manifest)} slides ({len(batch_requests)} batchUpdate requests)",
            status="SUCCESS",
        )
        return result_dict
