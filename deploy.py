"""Deployment script for Vertex AI Agent Engine & Gemini Enterprise registration."""

from __future__ import annotations

import argparse
import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover

    def load_dotenv(*args, **kwargs):  # type: ignore[misc]
        return False


import vertexai
from vertexai.preview.reasoning_engines import AdkApp, ReasoningEngine

from gcc_service_delivery_strategy.agent import root_agent
from gcc_service_delivery_strategy.observability import structured_logger

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
            "google-cloud-secret-manager>=2.20.0",
            "google-cloud-dlp>=3.21.0",
            "google-cloud-discoveryengine>=0.13.0",
            "opentelemetry-api>=1.25.0",
            "opentelemetry-sdk>=1.25.0",
            "pydantic>=2.7.0",
            "python-dotenv>=1.0.1",
        ],
        extra_packages=["./gcc_service_delivery_strategy"],
        display_name=display_name,
        description=root_agent.description,
    )
    structured_logger.info(
        "Successfully deployed agent to Vertex AI Agent Engine",
        extra={"structured_data": {"resource_name": remote_agent.resource_name}},
    )
    return remote_agent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy GCC Service Delivery Strategy Agent to Vertex AI Agent Engine."
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        required=not bool(os.environ.get("GOOGLE_CLOUD_PROJECT")),
        help="Google Cloud Project ID",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        help="GCP Region for Reasoning Engine deployment (default: us-central1)",
    )
    parser.add_argument(
        "--staging-bucket",
        default=os.environ.get("STAGING_BUCKET"),
        required=not bool(os.environ.get("STAGING_BUCKET")),
        help="GCS Staging Bucket URI (e.g., gs://my-staging-bucket)",
    )
    parser.add_argument(
        "--display-name",
        default="GCC Service Delivery Strategy",
        help="Display name in Vertex AI Agent Registry / Gemini Enterprise",
    )
    args = parser.parse_args()

    deploy_to_agent_engine(
        project_id=args.project,
        location=args.location,
        staging_bucket=args.staging_bucket,
        display_name=args.display_name,
    )


if __name__ == "__main__":
    main()
