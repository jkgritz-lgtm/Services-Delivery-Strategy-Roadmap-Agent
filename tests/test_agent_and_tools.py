"""Comprehensive Unit & AgentOps Rubric Tests for GCC Service Delivery Strategy Agent."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.run_evaluation import run_golden_dataset_evaluation
from gcc_service_delivery_strategy.agent import (
    app,
    document_ingestion_triage_agent,
    root_agent,
    strategy_gap_and_assumption_agent,
)
from gcc_service_delivery_strategy.memory import (
    compact_conversation_contents,
    consolidate_session_memory_async,
    persistent_roadmap_store,
    retrieve_historical_delivery_playbooks,
)
from gcc_service_delivery_strategy.models import REQUIRED_SECTIONS
from gcc_service_delivery_strategy.observability import (
    INTENT_OUTCOME_AUDIT_LOG,
    pii_scrubber,
)
from gcc_service_delivery_strategy.plugins import (
    FAST_MODEL_ID,
    GccAgentOpsPlugin,
    PRO_MODEL_ID,
    StrategicModelRouter,
)
from gcc_service_delivery_strategy.tools import (
    analyze_delivery_strategy_gaps,
    evaluate_roadmap_quality_and_completeness,
    google_slides_generator,
    request_human_approval_for_slides,
    update_roadmap_sections,
)


class DummyToolContext:
    """Minimal mock of ADK ToolContext with session-scoped state."""

    def __init__(self) -> None:
        self.state: dict = {}


def test_agent_and_multi_agent_configuration() -> None:
    """Verifies PRD specifications and Rubric 3.1/3.2 (Multi-Agent & Model Routing)."""
    assert root_agent.name == "gcc_service_delivery_strategy"
    assert root_agent.model == "gemini-3.1-pro-preview"
    assert document_ingestion_triage_agent.model == FAST_MODEL_ID
    assert strategy_gap_and_assumption_agent.model == PRO_MODEL_ID
    assert StrategicModelRouter.select_model("triage_agent") == FAST_MODEL_ID
    assert StrategicModelRouter.select_model("strategy_architect", "Design a 6-month banking cloud roadmap") == PRO_MODEL_ID
    assert app.name == "gcc_service_delivery_strategy_app"


def test_gap_analysis_identifies_missing_sections_and_assumptions() -> None:
    """Verifies that missing sections trigger targeted questions, assumptions, and recovery instructions."""
    ctx = DummyToolContext()
    result = analyze_delivery_strategy_gaps(
        customer_name="Acme Financial",
        vision="Migrate core banking to Google Cloud and reduce TCO by 30%.",
        services_delivery_strategy="3-phase roadmap over 6 months.",
        tool_context=ctx,
    )

    assert result["status"] == "gaps_identified"
    assert result["customer_name"] == "Acme Financial"
    assert "Vision" in result["completed_sections"]
    assert "Services Delivery Strategy" in result["completed_sections"]
    assert "Commercials" in result["missing_sections"]
    assert "Delivery Approach" in result["missing_sections"]
    assert "Roles & Responsibilities" in result["missing_sections"]
    assert (
        "Operating Model (PSO only, Partner, or both)"
        in result["missing_sections"]
    )
    assert "Commercials" in result["clarifying_questions"]
    assert "Commercials" in result["proposed_assumptions"]
    assert result["recovery_instructions"] is not None


def test_approve_assumptions_and_self_evaluation() -> None:
    """Verifies assumption approval and self-evaluation guardrail (Rubric 3.3)."""
    ctx = DummyToolContext()
    analyze_delivery_strategy_gaps(
        customer_name="Acme Financial",
        vision="Modernize data platform on BigQuery and Vertex AI.",
        tool_context=ctx,
    )

    update_result = update_roadmap_sections(
        operating_model_type="both",
        approve_industry_assumptions=True,
        tool_context=ctx,
    )

    assert update_result["status"] == "ready_for_slides"
    assert update_result["operating_model_type"] == "PSO & Partner (Hybrid)"
    assert update_result["missing_sections"] == []
    assert len(update_result["completed_sections"]) == len(REQUIRED_SECTIONS)

    eval_report = evaluate_roadmap_quality_and_completeness(tool_context=ctx)
    assert eval_report["passed"] is True
    assert eval_report["completeness_score"] == 1.0


def test_google_slides_generator_blocks_incomplete_sections() -> None:
    """Verifies PRD edge-case guardrail and guided error handling (Rubric 1.4)."""
    result = google_slides_generator(
        customer_name="Acme Financial",
        presentation_title="Acme Service Delivery Strategy",
        operating_model_type="PSO only",
        vision_headline="Cloud-First Banking Vision",
        vision_bullets=["Reduce TCO by 30%", "Launch AI customer insights"],
        services_delivery_strategy_headline="",
        services_delivery_strategy_bullets=[],
        commercials_headline="",
        commercials_bullets=[],
        delivery_approach_headline="",
        delivery_approach_bullets=[],
        roles_and_responsibilities_headline="",
        roles_and_responsibilities_bullets=[],
        operating_model_headline="",
        operating_model_bullets=[],
        use_approved_assumptions_for_missing=False,
    )

    assert result["status"] == "incomplete_data"
    assert "Services Delivery Strategy" in result["missing_sections"]
    assert "Commercials" in result["missing_sections"]
    assert "recovery_instructions" in result


def test_google_slides_generator_creates_all_required_slides_dry_run() -> None:
    """Verifies that all 6 required PRD slides + cover slide are built and formatted."""
    os.environ["SLIDES_DRY_RUN"] = "true"
    ctx = DummyToolContext()

    result = google_slides_generator(
        customer_name="Global Retail Corp",
        presentation_title="Global Retail Corp - Service Delivery Strategy",
        operating_model_type="PSO & Partner (Hybrid)",
        vision_headline="Accelerate Omni-Channel Personalization on Google Cloud",
        vision_bullets=[
            "Consolidate 5 regional data silos into BigQuery within 6 months.",
            "Reduce infrastructure TCO by 28% while enabling real-time GenAI recommendations.",
        ],
        services_delivery_strategy_headline="3-Horizon Phased Delivery Strategy",
        services_delivery_strategy_bullets=[
            "Phase 1 (Weeks 1-6): Secure Landing Zone & Data Governance Foundation.",
            "Phase 2 (Weeks 7-16): Lighthouse Data Warehouse & Vertex AI Search Launch.",
            "Phase 3 (Weeks 17-24): Full Regional Rollout & CCoE Handover.",
        ],
        commercials_headline="Hybrid Fixed-Price Foundation & Agile Pod Commercial Model",
        commercials_bullets=[
            "Phase 1 delivered as Fixed-Price Milestone ($250K).",
            "Phases 2-3 delivered via Time & Materials Agile Pods ($600K estimated).",
        ],
        delivery_approach_headline="Agile Sprint Execution with Automated IaC Guardrails",
        delivery_approach_bullets=[
            "2-week sprints with bi-weekly executive demos and Terraform CI/CD.",
            "Weekly RAID log review and Architecture Review Board (ARB) sign-offs.",
        ],
        roles_and_responsibilities_headline="Clear RACI Across Customer, Google Cloud PSO, and Partner",
        roles_and_responsibilities_bullets=[
            "Google Cloud PSO: Principal Architecture, Reference Patterns, and ARB Authority.",
            "Partner: Scaled Migration Execution, Data Pipelines, and Runbooks.",
            "Customer: Product Ownership, Security Approvals, and Domain SMEs.",
        ],
        operating_model_headline="Hybrid PSO + Partner Co-Delivery Operating Model",
        operating_model_bullets=[
            "Operating Model: PSO & Partner (Hybrid) with unified pod leadership.",
            "Governance: Daily Standups, Weekly Tactical Syncs, Monthly SteerCo.",
        ],
        tool_context=ctx,
    )

    assert result["status"] == "success"
    assert result["total_slides"] == 7
    slides = result["slides_created"]
    assert any("Vision" in s for s in slides)
    assert any("Services Delivery Strategy" in s for s in slides)
    assert any("Commercials" in s for s in slides)
    assert any("Delivery Approach" in s for s in slides)
    assert any("Roles & Responsibilities" in s for s in slides)
    assert any("Operating Model (PSO & Partner (Hybrid))" in s for s in slides)


@patch("gcc_service_delivery_strategy.tools.slides_generator.build")
@patch("gcc_service_delivery_strategy.tools.slides_generator._resolve_credentials")
def test_google_slides_generator_live_api_mock(
    mock_resolve_creds: MagicMock,
    mock_build: MagicMock,
) -> None:
    """Verifies integration with Google Slides API presentations().create and batchUpdate."""
    os.environ["SLIDES_DRY_RUN"] = "false"
    mock_resolve_creds.return_value = MagicMock()

    mock_service = MagicMock()
    mock_presentations = mock_service.presentations.return_value
    mock_presentations.create.return_value.execute.return_value = {
        "presentationId": "1AbCdEfGhIjKlMnOpQrStUvWxYz",
        "slides": [{"objectId": "default_slide_0"}],
    }
    mock_presentations.batchUpdate.return_value.execute.return_value = {}
    mock_build.return_value = mock_service

    result = google_slides_generator(
        customer_name="Apex Logistics",
        presentation_title="Apex Logistics - GCC Service Delivery Strategy",
        operating_model_type="PSO only",
        vision_headline="Zero-Downtime Supply Chain Transformation",
        vision_bullets=["Real-time fleet telemetry on Google Cloud"],
        services_delivery_strategy_headline="",
        services_delivery_strategy_bullets=[],
        commercials_headline="",
        commercials_bullets=[],
        delivery_approach_headline="",
        delivery_approach_bullets=[],
        roles_and_responsibilities_headline="",
        roles_and_responsibilities_bullets=[],
        operating_model_headline="",
        operating_model_bullets=[],
        use_approved_assumptions_for_missing=True,
    )

    assert result["status"] == "success"
    assert result["mode"] == "google_slides_api"
    assert result["presentation_id"] == "1AbCdEfGhIjKlMnOpQrStUvWxYz"
    mock_presentations.create.assert_called_once()
    mock_presentations.batchUpdate.assert_called_once()


def test_pii_redaction_and_intent_outcome_logging() -> None:
    """Verifies Rubric 4.2 (Intent vs. Outcome) and 4.4 (PII Redaction)."""
    raw = "Contact jane.doe@example.com or 415-555-0199 with Authorization: Bearer sample_token_value"
    scrubbed = pii_scrubber.redact_text(raw)
    assert "jane.doe@example.com" not in scrubbed
    assert "415-555-0199" not in scrubbed
    assert "sample_token_value" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "[REDACTED_OAUTH_TOKEN]" in scrubbed

    phases = {entry["phase"] for entry in INTENT_OUTCOME_AUDIT_LOG}
    assert "INTENT" in phases
    assert "OUTCOME" in phases


def test_compaction_and_async_memory_operations() -> None:
    """Verifies Rubric 2.2, 2.3, 2.4, and 3.4 (Compaction, Persistent DB, Async Memory, HITL)."""
    turns = [f"turn_{i}" for i in range(20)]
    compacted = compact_conversation_contents(turns, max_turns=6)
    assert len(compacted) == 6
    assert compacted[0] == "turn_0"
    assert compacted[-1] == "turn_19"

    async def _run_async_checks() -> None:
        await consolidate_session_memory_async(
            session_id="sess-test-01",
            customer_name="BankCorp (ceo@bankcorp.com)",
            operating_model_type="PSO only",
            sections={"vision": "Transform core banking"},
        )
        stored = persistent_roadmap_store.get_memory("sess-test-01")
        assert stored is not None
        assert "[REDACTED_EMAIL]" in stored["customer_name"]

        rag_res = await retrieve_historical_delivery_playbooks(
            "Financial Services Core Banking"
        )
        assert rag_res["status"] == "success"

        plugin = GccAgentOpsPlugin(require_hitl_for_slides=True)
        ctx = DummyToolContext()
        fake_tool = MagicMock()
        fake_tool.name = "google_slides_generator"
        blocked = await plugin.before_tool_callback(
            tool=fake_tool,
            tool_args={"customer_name": "BankCorp"},
            tool_context=ctx,
        )
        assert blocked is not None
        assert blocked["status"] == "awaiting_human_approval"

        request_human_approval_for_slides(
            customer_name="BankCorp",
            operating_model_type="PSO only",
            summary_of_slides="6 slides ready",
            human_confirmed=True,
            tool_context=ctx,
        )
        allowed = await plugin.before_tool_callback(
            tool=fake_tool,
            tool_args={"customer_name": "BankCorp"},
            tool_context=ctx,
        )
        assert allowed is None

    asyncio.run(_run_async_checks())


def test_golden_evaluation_suite() -> None:
    """Verifies Rubric 5.1 (Automated Evaluation Suite against golden dataset)."""
    report = run_golden_dataset_evaluation()
    assert report["all_passed"] is True
    assert report["pass_rate"] == 1.0


if __name__ == "__main__":
    test_agent_and_multi_agent_configuration()
    test_gap_analysis_identifies_missing_sections_and_assumptions()
    test_approve_assumptions_and_self_evaluation()
    test_google_slides_generator_blocks_incomplete_sections()
    test_google_slides_generator_creates_all_required_slides_dry_run()
    test_google_slides_generator_live_api_mock()
    test_pii_redaction_and_intent_outcome_logging()
    test_compaction_and_async_memory_operations()
    test_golden_evaluation_suite()
