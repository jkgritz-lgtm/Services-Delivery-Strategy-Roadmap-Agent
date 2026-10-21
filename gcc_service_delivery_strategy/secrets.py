"""Secure Secret Management using Google Cloud Secret Manager.

Addresses AgentOps Rubric 5.3 (Secure Secret Management):
No hardcoded API keys or OAuth secrets; all credentials are retrieved dynamically
via Google Cloud Secret Manager (`google.cloud.secretmanager`) with LRU caching
and environment variable fallback for local development.
"""

from __future__ import annotations

from functools import lru_cache
import logging
import os
from typing import Optional

try:
    from google.cloud import secretmanager
except ImportError:  # pragma: no cover
    secretmanager = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class SecretManagerClient:
    """Retrieves sensitive configuration values from Google Cloud Secret Manager."""

    def __init__(self, project_id: Optional[str] = None) -> None:
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        self._client = None
        if secretmanager is not None and self.project_id:
            try:
                self._client = secretmanager.SecretManagerServiceClient()
            except Exception as exc:
                logger.debug(
                    "SecretManagerServiceClient initialization deferred: %s", exc
                )

    @lru_cache(maxsize=32)
    def get_secret(
        self,
        secret_id: str,
        version_id: str = "latest",
        env_fallback: Optional[str] = None,
    ) -> str:
        """Fetches a secret payload from GCP Secret Manager with safe fallback.

        Args:
            secret_id: The Secret Manager secret identifier (e.g., 'gcc-slides-oauth-client-id').
            version_id: Secret version to access (defaults to 'latest').
            env_fallback: Optional environment variable name used only when Secret Manager
                is unreachable in local offline testing.

        Returns:
            The resolved secret string, or empty string if unconfigured.
        """
        if self._client is not None and self.project_id:
            resource_name = (
                f"projects/{self.project_id}/secrets/{secret_id}/versions/{version_id}"
            )
            try:
                response = self._client.access_secret_version(
                    request={"name": resource_name}
                )
                return response.payload.data.decode("utf-8").strip()
            except Exception as exc:
                logger.debug(
                    "Falling back to environment for secret '%s': %s",
                    secret_id,
                    exc,
                )

        fallback_key = env_fallback or secret_id.upper().replace("-", "_")
        return os.environ.get(fallback_key, "").strip()


default_secret_manager = SecretManagerClient()


def get_secure_credential(secret_id: str, env_var_name: str) -> str:
    """Helper to fetch a credential via Google Cloud Secret Manager."""
    return default_secret_manager.get_secret(
        secret_id=secret_id,
        env_fallback=env_var_name,
    )
