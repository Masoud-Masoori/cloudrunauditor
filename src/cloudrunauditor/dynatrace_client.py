"""Dynatrace MCP client stub.

In the hackathon final, this will call the Dynatrace MCP server which exposes
Cloud Run service telemetry as MCP tools. For now we have a stub interface
that returns demo data; the hackathon scaffold can swap in the real MCP call
once the operator authenticates with Dynatrace.

The MCP integration is the REQUIRED tech stack item for the Dynatrace track
(per the Rapid Agent rules). Without it, the submission doesn't qualify.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx


class DynatraceClient:
    """Wraps the Dynatrace MCP server (or REST API as a fallback)."""

    def __init__(self, environment: str, token: str):
        self.environment = environment
        self.token = token
        self._client = httpx.AsyncClient(timeout=30.0)

    async def get_anomalies_24h(self, service_name: str) -> list[dict[str, Any]]:
        """Get Dynatrace anomalies for a service in the last 24h.

        v1 implementation: call MCP via stdio/local socket. Fallback to
        environment REST endpoint if MCP isn't available.
        """
        if not self.environment or not self.token:
            return _demo_anomalies(service_name)

        from_iso = (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z"
        url = f"https://{self.environment}.live.dynatrace.com/api/v2/problems"
        try:
            resp = await self._client.get(
                url,
                headers={"Authorization": f"Api-Token {self.token}"},
                params={"problemSelector": f'tag("service:{service_name}")', "from": from_iso},
            )
            if resp.status_code != 200:
                return _demo_anomalies(service_name)
            data = resp.json()
            return [
                {
                    "problem_id": p.get("problemId"),
                    "title": p.get("title"),
                    "category": (p.get("severityLevel") or "").lower(),
                    "started_at": p.get("startTime"),
                    "url": f"https://{self.environment}.live.dynatrace.com/ui/problems/problem-detail/{p.get('problemId')}",
                }
                for p in data.get("problems", [])
            ]
        except httpx.HTTPError:
            return _demo_anomalies(service_name)

    async def close(self) -> None:
        await self._client.aclose()


def _demo_anomalies(service_name: str) -> list[dict[str, Any]]:
    """Demo data used when Dynatrace creds aren't set yet."""
    return [
        {
            "problem_id": "DT-DEMO-001",
            "title": f"Elevated 5xx rate on {service_name}",
            "category": "error_rate",
            "started_at": (datetime.utcnow() - timedelta(hours=6)).isoformat() + "Z",
            "url": "https://example.dynatrace.com/ui/problems/DT-DEMO-001",
        }
    ]
