"""ADK Multi-Agent & App Definition for GCC Service Delivery Strategy.

Addresses AgentOps Rubric:
- 2.2 History Compaction (`EventsCompactionConfig` & `ContextCacheConfig` on `App`)
- 3.1 Multi-Agent Patterns (Coordinator `root_agent` + specialized `document_ingestion_triage_agent` and `strategy_gap_and_assumption_agent` sub-agents)
- 3.2 Strategic Model Routing (`gemini-2.5-flash` for fast ingestion/triage; `gemini-3.1-pro-preview` for deep strategic planning)
- 3.3 & 3.4 Guardrails, Policy Plugins (`GccAgentOpsPlugin`), and Human-in-the-Loop Hooks
- 5.3 Secure Secret Management via Google Cloud Secret Manager (`get_secure_credential`)
"""

from __future__ import annotations

import os
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover

    def load_dotenv(*args: Any, **kwargs: Any) -> bool:  # type: ignore[misc]
        return False


try:
    from google.adk.agents import Agent
    from google.adk.apps import App
    from google.adk.tools import load_artifacts
except ImportError:  # pragma: no cover

    class Agent:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class App:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def load_artifacts(*args: Any, **kwargs: Any) -> dict[str, Any]:
        """Fallback stub when google-adk is not installed in bare test env."""
        return {"status": "no_artifacts"}


from .memory import (
    build_context_cache_config,
    build_events_compaction_config,
    build_resumability_config,
    retrieve_historical_delivery_playbooks,
)
from .plugins import (
    FAST_MODEL_ID,
    GccAgentOpsPlugin,
    PRO_MODEL_ID,
)
from .prompts import (
    DOCUMENT_TRIAGE_AGENT_INSTRUCTION,
    STRATEGY_ARCHITECT_AGENT_INSTRUCTION,
    SYSTEM_INSTRUCTION,
)
from .secrets import get_secure_credential
from .tools import (
    analyze_delivery_strategy_gaps,
    evaluate_roadmap_quality_and_completeness,
    google_slides_generator,
    record_verified_roadmap_sections,
    request_human_approval_for_slides,
    update_roadmap_sections,
)

load_dotenv()

MODEL_NAME = os.environ.get("MODEL_NAME", PRO_MODEL_ID)
FAST_TRIAGE_MODEL_NAME = os.environ.get("FAST_MODEL_NAME", FAST_MODEL_ID)


def _build_slides_tool() -> Any:
    """Returns `google_slides_generator`, wrapped with OAuth2 via Secret Manager if configured."""
    oauth_client_id = get_secure_credential(
        "gcc-slides-oauth-client-id", "OAUTH_CLIENT_ID"
    )
    oauth_client_secret = get_secure_credential(
        "gcc-slides-oauth-client-secret", "OAUTH_CLIENT_SECRET"
    )

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


# Sub-Agent 1: Fast Document Triage & Entity Extraction (Gemini Flash)
document_ingestion_triage_agent = Agent(
    name="document_ingestion_triage_agent",
    model=FAST_TRIAGE_MODEL_NAME,
    description=(
        "High-speed document ingestion and triage sub-agent running on Gemini Flash. "
        "Extracts initial facts from uploaded customer PDFs, Docs, and Spreadsheets "
        "and maps them to the 6 required roadmap sections."
    ),
    instruction=DOCUMENT_TRIAGE_AGENT_INSTRUCTION,
    tools=[
        load_artifacts,
        analyze_delivery_strategy_gaps,
    ],
)

# Sub-Agent 2: Deep Strategy Architect & Assumption Formulator (Gemini 3.1 Pro)
strategy_gap_and_assumption_agent = Agent(
    name="strategy_gap_and_assumption_agent",
    model=MODEL_NAME,
    description=(
        "Deep strategic reasoning sub-agent running on gemini-3.1-pro-preview. "
        "Synthesizes GCC reference playbooks, formulates industry-standard assumptions, "
        "and evaluates roadmap completeness across all 6 required sections."
    ),
    instruction=STRATEGY_ARCHITECT_AGENT_INSTRUCTION,
    tools=[
        retrieve_historical_delivery_playbooks,
        analyze_delivery_strategy_gaps,
        record_verified_roadmap_sections,
        evaluate_roadmap_quality_and_completeness,
    ],
)

# Root Coordinator Agent: GCC Service Delivery Strategy (gemini-3.1-pro-preview)
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
    sub_agents=[
        document_ingestion_triage_agent,
        strategy_gap_and_assumption_agent,
    ],
    tools=[
        load_artifacts,
        analyze_delivery_strategy_gaps,
        update_roadmap_sections,
        record_verified_roadmap_sections,
        retrieve_historical_delivery_playbooks,
        evaluate_roadmap_quality_and_completeness,
        request_human_approval_for_slides,
        _build_slides_tool(),
    ],
)

# Top-level ADK App container with Policy Plugin, History Compaction, Context Caching & HITL Resumability
app = App(
    name="gcc_service_delivery_strategy_app",
    root_agent=root_agent,
    plugins=[GccAgentOpsPlugin()],
    events_compaction_config=build_events_compaction_config(),
    context_cache_config=build_context_cache_config(),
    resumability_config=build_resumability_config(),
)
