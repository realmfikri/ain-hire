"""Deploy the AIN Hire ADK agent to Vertex AI Agent Engine.

This script intentionally does not create buckets, datasets, or paid resources.
Run it only after confirming the target GCP project and service account.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import vertexai
from vertexai import agent_engines

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ain_hire.agent import root_agent


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


PROJECT_ID = _required_env("GOOGLE_CLOUD_PROJECT")
REGION = _required_env("AGENT_ENGINE_REGION")
STAGING_BUCKET = _required_env("STAGING_BUCKET")
SERVICE_ACCOUNT = _required_env("AGENT_ENGINE_SERVICE_ACCOUNT")

REQUIREMENTS = [
    "google-adk==1.33.0",
    "google-cloud-aiplatform[agent-engines]==1.158.0",
    "google-genai==1.75.0",
    "pydantic==2.13.4",
    "cloudpickle==3.1.2",
    "numpy==2.4.6",
]


def _build_adk_app():
    if root_agent is None:
        raise RuntimeError("google-adk is not installed; install requirements first.")

    try:
        from vertexai.preview.reasoning_engines import AdkApp
    except Exception:
        from vertexai.agent_engines import AdkApp  # type: ignore

    kwargs = {
        "agent": root_agent,
        "app_name": "app_ain_hire",
    }

    try:
        from google.adk.artifacts import GcsArtifactService

        staging_bucket_name = STAGING_BUCKET.removeprefix("gs://")

        def artifact_service_builder():
            return GcsArtifactService(bucket_name=staging_bucket_name)

        kwargs["artifact_service_builder"] = artifact_service_builder
    except Exception:
        pass

    try:
        return AdkApp(**kwargs)
    except TypeError:
        kwargs.pop("artifact_service_builder", None)
        return AdkApp(**kwargs)


def main() -> None:
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")

    vertexai.init(project=PROJECT_ID, location=REGION, staging_bucket=STAGING_BUCKET)
    app = _build_adk_app()
    remote_app = agent_engines.create(
        app,
        requirements=REQUIREMENTS,
        extra_packages=["ain_hire"],
        service_account=SERVICE_ACCOUNT,
    )
    print(remote_app)


if __name__ == "__main__":
    main()
