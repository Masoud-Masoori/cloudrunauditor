"""FastAPI entry point — single endpoint POST /audit.

Deployment shape:
    docker build -t cloudrunauditor .
    gcloud run deploy cloudrunauditor --image gcr.io/<project>/cloudrunauditor --region us-central1
    POST https://cloudrunauditor-<hash>.run.app/audit { "service": "...", "region": "...", "project": "..." }
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from cloudrunauditor import audit
from cloudrunauditor.dynatrace_client import DynatraceClient
from cloudrunauditor.gcloud_client import GcloudClient
from cloudrunauditor.memo import render_memo

app = FastAPI(
    title="CloudRunAuditor",
    description="Audit any Cloud Run service — every finding cites the metric or config that triggered it.",
    version="0.1.0",
)


class AuditRequest(BaseModel):
    service: str = Field(..., description="Cloud Run service name")
    region: str = Field(..., description="Region, e.g. us-central1")
    project: str = Field(..., description="GCP project id")
    dynatrace_environment: str | None = Field(None, description="Dynatrace env id, optional")


class FindingDTO(BaseModel):
    pattern_id: str
    severity: str
    title: str
    summary: str
    impact: str
    fix: str
    evidence: list[dict[str, Any]]


class AuditResponse(BaseModel):
    service: str
    region: str
    project: str
    findings_count: int
    findings: list[FindingDTO]
    memo_markdown: str


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/audit", response_model=AuditResponse)
async def audit_service(req: AuditRequest) -> AuditResponse:
    """Audit one Cloud Run service end-to-end."""
    gcloud = GcloudClient(project=req.project)
    dynatrace = DynatraceClient(
        environment=req.dynatrace_environment or os.environ.get("DYNATRACE_ENV", ""),
        token=os.environ.get("DYNATRACE_TOKEN", ""),
    )

    try:
        snapshot = await _build_snapshot(gcloud, dynatrace, req)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"failed to fetch snapshot: {e}") from e

    findings = audit.run_all(snapshot)
    memo = render_memo(snapshot, findings)

    return AuditResponse(
        service=req.service,
        region=req.region,
        project=req.project,
        findings_count=len(findings),
        findings=[
            FindingDTO(
                pattern_id=f.pattern_id,
                severity=f.severity.value,
                title=f.title,
                summary=f.summary,
                impact=f.impact,
                fix=f.fix,
                evidence=[
                    {
                        "kind": e.kind,
                        "locator": e.locator,
                        "value": e.value,
                        "source_url": e.source_url,
                    }
                    for e in f.evidence
                ],
            )
            for f in findings
        ],
        memo_markdown=memo,
    )


async def _build_snapshot(
    gcloud: GcloudClient,
    dynatrace: DynatraceClient,
    req: AuditRequest,
) -> audit.ServiceSnapshot:
    """Fan out: get config + iam + metrics + dynatrace anomalies in parallel."""
    import asyncio

    config_task = asyncio.create_task(gcloud.describe_service(req.service, req.region))
    iam_task = asyncio.create_task(gcloud.get_iam_policy(req.service, req.region))
    metrics_task = asyncio.create_task(gcloud.get_metrics_24h(req.service, req.region))
    anomalies_task = asyncio.create_task(dynatrace.get_anomalies_24h(req.service))

    config, iam_policy, metrics, anomalies = await asyncio.gather(
        config_task, iam_task, metrics_task, anomalies_task,
    )

    error_rate = _compute_error_rate(metrics)

    return audit.ServiceSnapshot(
        service_name=req.service,
        region=req.region,
        config=config,
        iam_policy=iam_policy,
        metrics_24h=metrics,
        anomalies_24h=anomalies,
        error_rate_24h=error_rate,
    )


def _compute_error_rate(metrics: dict[str, list[float]]) -> float:
    total = sum(metrics.get("request_count", [])) or 1.0
    errors = sum(metrics.get("error_count", []))
    return errors / total
