"""gcloud / Cloud Monitoring shim — reads service config + telemetry.

Two paths:
    a) Local dev: shells out to `gcloud run services describe ...` (operator must `gcloud auth` first)
    b) Cloud Run runtime: uses the google-cloud-* SDK with the service's own service account

For the hackathon scaffold we ship path (a) so the operator can iterate
locally without granting too many SA scopes to the deployed Cloud Run instance.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timedelta
from typing import Any


class GcloudClient:
    """Thin async wrapper around `gcloud` CLI calls."""

    def __init__(self, project: str):
        self.project = project
        if not shutil.which("gcloud"):
            raise RuntimeError("`gcloud` CLI not found on PATH. Install Google Cloud SDK.")

    async def describe_service(self, service: str, region: str) -> dict[str, Any]:
        return await self._run_json([
            "gcloud", "run", "services", "describe", service,
            "--region", region, "--project", self.project, "--format", "json",
        ])

    async def get_iam_policy(self, service: str, region: str) -> dict[str, Any]:
        return await self._run_json([
            "gcloud", "run", "services", "get-iam-policy", service,
            "--region", region, "--project", self.project, "--format", "json",
        ])

    async def get_metrics_24h(self, service: str, region: str) -> dict[str, list[float]]:
        """Use Cloud Monitoring API via google-cloud-monitoring."""
        # Hackathon scaffold returns demo data; real call wires in google-cloud-monitoring later.
        return _demo_metrics()

    async def _run_json(self, argv: list[str]) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"gcloud failed: {stderr.decode('utf-8', 'ignore')}")
        try:
            return json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError:
            return {}


def _demo_metrics() -> dict[str, list[float]]:
    return {
        "request_count": [120, 240, 220, 180, 260],
        "error_count": [3, 15, 8, 22, 12],
        "cold_start_latency_p95_ms": [2400, 2600, 2100, 2800],
        "memory_usage_p95_mb": [180, 192, 175, 188],
    }
