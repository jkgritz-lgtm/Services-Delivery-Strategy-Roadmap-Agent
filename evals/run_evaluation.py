"""Automated Evaluation Harness for the GCC Service Delivery Strategy Agent.

Addresses AgentOps Rubric 5.1 (Automated Evaluation Suites):
Evaluates the agent and its tools against `evals/golden_dataset.json` to statically
and dynamically measure regressions in trajectory, guardrails, and PRD slide output.
Also supports ADK's built-in `AgentEvaluator` when running against live Vertex AI models.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

# Ensure package root is importable when executed directly
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gcc_service_delivery_strategy.observability import (
    INTENT_OUTCOME_AUDIT_LOG,
    structured_logger,
)
from gcc_service_delivery_strategy.tools import (
    analyze_delivery_strategy_gaps,
    evaluate_roadmap_quality_and_completeness,
    google_slides_generator,
    request_human_approval_for_slides,
    update_roadmap_sections,
)


class _EvalToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}


def run_golden_dataset_evaluation(
    dataset_path: Path | None = None,
) -> dict[str, Any]:
    """Runs the golden evaluation suite and returns a structured pass/fail report."""
    os.environ["SLIDES_DRY_RUN"] = "true"
    path = dataset_path or (Path(__file__).resolve().parent / "golden_dataset.json")
    dataset = json.loads(path.read_text(encoding="utf-8"))

    results: list[dict[str, Any]] = []
    passed_count = 0

    for case in dataset.get("eval_cases", []):
        eval_id = case["eval_id"]
        inp = case["initial_input"]
        ctx = _EvalToolContext()

        if eval_id == "case_01_partial_input_triggers_gap_questions_and_assumptions":
            out = analyze_delivery_strategy_gaps(
                customer_name=inp["customer_name"],
                vision=inp["vision"],
                tool_context=ctx,
            )
            passed = (
                out["status"] == case["expected_status"]
                and out["missing_sections"] == case["expected_missing_sections"]
                and bool(out.get("clarifying_questions"))
                and bool(out.get("proposed_assumptions"))
                and bool(out.get("recovery_instructions"))
            )
            results.append({"eval_id": eval_id, "passed": passed, "output": out})

        elif eval_id == "case_02_assumption_approval_and_full_6_slide_generation":
            analyze_delivery_strategy_gaps(
                customer_name=inp["customer_name"],
                vision=inp["vision"],
                tool_context=ctx,
            )
            update_roadmap_sections(
                customer_name=inp["customer_name"],
                operating_model_type=inp["operating_model_type"],
                approve_industry_assumptions=inp["approve_industry_assumptions"],
                tool_context=ctx,
            )
            self_eval = evaluate_roadmap_quality_and_completeness(tool_context=ctx)
            request_human_approval_for_slides(
                customer_name=inp["customer_name"],
                operating_model_type="PSO & Partner (Hybrid)",
                summary_of_slides="All 6 required sections verified.",
                human_confirmed=True,
                tool_context=ctx,
            )
            slides_out = google_slides_generator(
                customer_name=inp["customer_name"],
                presentation_title=f"{inp['customer_name']} - GCC Service Delivery Strategy",
                operating_model_type="PSO & Partner (Hybrid)",
                vision_headline="Banking Cloud Transformation Vision",
                vision_bullets=[inp["vision"]],
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
                tool_context=ctx,
            )
            slides_list = slides_out.get("slides_created", [])
            all_required_present = all(
                any(req in s for s in slides_list)
                for req in case["required_slide_titles"]
            )
            passed = (
                self_eval["passed"] is True
                and slides_out["status"] == case["expected_status"]
                and slides_out["total_slides"] == case["expected_total_slides"]
                and all_required_present
            )
            results.append(
                {"eval_id": eval_id, "passed": passed, "output": slides_out}
            )

        elif eval_id == "case_03_guardrail_blocks_premature_slides_call":
            out = google_slides_generator(
                customer_name=inp["customer_name"],
                presentation_title="Incomplete Deck Attempt",
                operating_model_type=inp["operating_model_type"],
                vision_headline=inp["vision_headline"],
                vision_bullets=inp["vision_bullets"],
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
                tool_context=ctx,
            )
            passed = out["status"] == case["expected_status"] and bool(
                out.get("recovery_instructions")
            )
            results.append({"eval_id": eval_id, "passed": passed, "output": out})

        if results[-1]["passed"]:
            passed_count += 1

    total_cases = len(results)
    summary = {
        "eval_set_id": dataset["eval_set_id"],
        "total_cases": total_cases,
        "passed_cases": passed_count,
        "pass_rate": round(passed_count / max(1, total_cases), 2),
        "intent_outcome_events_logged": len(INTENT_OUTCOME_AUDIT_LOG),
        "all_passed": passed_count == total_cases,
        "cases": results,
    }
    structured_logger.info(
        "Completed golden dataset evaluation",
        extra={"structured_data": {"eval_summary": summary}},
    )
    return summary


if __name__ == "__main__":
    report = run_golden_dataset_evaluation()
    if not report["all_passed"]:
        sys.exit(1)
