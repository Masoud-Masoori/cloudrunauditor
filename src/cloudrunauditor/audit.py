"""5 hard-coded audit patterns for Cloud Run services.

Each pattern is a pure function: receives a `ServiceSnapshot` (config + telemetry)
and returns a list of `Finding` objects. Findings are evidence-backed: every
finding cites the exact gcloud config field OR the exact Dynatrace anomaly that
triggered it. No vague "this might be a problem" — only "this IS a problem,
and here's the line/metric that proves it."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Evidence:
    """A citation backing one finding."""
    kind: str  # "gcloud_config" | "dynatrace_anomaly" | "cloud_logging" | "metric"
    locator: str  # e.g. "spec.template.spec.containers[0].resources.limits.memory"
    value: Any
    source_url: str = ""  # Link to gcloud Console or Dynatrace dashboard


@dataclass
class Finding:
    pattern_id: str
    severity: Severity
    title: str
    summary: str  # 1 sentence — what's wrong
    impact: str   # 1 sentence — why it matters
    fix: str      # 1 sentence — what to do
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class ServiceSnapshot:
    """Everything we read about a Cloud Run service before auditing."""
    service_name: str
    region: str
    config: dict[str, Any]            # output of `gcloud run services describe --format=json`
    iam_policy: dict[str, Any]        # output of `gcloud run services get-iam-policy --format=json`
    metrics_24h: dict[str, list[float]]  # via Cloud Monitoring or Dynatrace
    anomalies_24h: list[dict[str, Any]]  # via Dynatrace MCP
    error_rate_24h: float


# ---------------------------------------------------------------------------
# The 5 patterns
# ---------------------------------------------------------------------------


def pattern_cold_start_spike(s: ServiceSnapshot) -> list[Finding]:
    """Pattern 1: p95 cold-start latency > 2s in last 24h.

    Cloud Run's min-instances=0 with low-traffic services means every request
    pays the JVM/import warmup. Operationally invisible until users complain.
    """
    cold_start_p95 = max(s.metrics_24h.get("cold_start_latency_p95_ms", [0]), default=0)
    if cold_start_p95 > 2000:
        return [
            Finding(
                pattern_id="cold_start_spike",
                severity=Severity.HIGH,
                title=f"Cold-start p95 is {cold_start_p95:.0f}ms (> 2s threshold)",
                summary=f"Service '{s.service_name}' shows cold-start p95 latency of {cold_start_p95:.0f}ms in the last 24h.",
                impact="First-request users wait 2+ seconds. Search engines penalize. Conversion drops.",
                fix="Set `--min-instances=1` for production-tier services, OR move container init work out of cold-path (lazy imports, build-time fetches).",
                evidence=[
                    Evidence(
                        kind="metric",
                        locator="cold_start_latency_p95_ms (last 24h)",
                        value=cold_start_p95,
                        source_url=f"https://console.cloud.google.com/run/detail/{s.region}/{s.service_name}/metrics",
                    )
                ],
            )
        ]
    return []


def pattern_oversized_instance(s: ServiceSnapshot) -> list[Finding]:
    """Pattern 2: Memory limit > 1Gi but p95 memory usage < 256Mi."""
    container = (s.config.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}]) or [{}])[0]
    limits = container.get("resources", {}).get("limits", {})
    memory_limit_str = limits.get("memory", "256Mi")
    memory_limit_mb = _parse_memory(memory_limit_str)
    p95_memory_mb = max(s.metrics_24h.get("memory_usage_p95_mb", [0]), default=0)
    if memory_limit_mb >= 1024 and p95_memory_mb > 0 and p95_memory_mb < 256:
        return [
            Finding(
                pattern_id="oversized_instance",
                severity=Severity.MEDIUM,
                title=f"Memory limit {memory_limit_str} but p95 usage only {p95_memory_mb:.0f}MB",
                summary=f"'{s.service_name}' provisioned at {memory_limit_str} but actual usage stays under 256MB.",
                impact="Higher per-request cost; you pay for memory you don't use.",
                fix=f"Drop `--memory=512Mi`. Estimated savings vs current {memory_limit_str}: ~50% on memory billing units.",
                evidence=[
                    Evidence(
                        kind="gcloud_config",
                        locator="spec.template.spec.containers[0].resources.limits.memory",
                        value=memory_limit_str,
                        source_url=f"https://console.cloud.google.com/run/detail/{s.region}/{s.service_name}/yaml",
                    ),
                    Evidence(
                        kind="metric",
                        locator="memory_usage_p95_mb (last 24h)",
                        value=p95_memory_mb,
                    ),
                ],
            )
        ]
    return []


def pattern_missing_health_check(s: ServiceSnapshot) -> list[Finding]:
    """Pattern 3: No `livenessProbe` OR `startupProbe` defined."""
    container = (s.config.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}]) or [{}])[0]
    has_liveness = "livenessProbe" in container
    has_startup = "startupProbe" in container
    if not (has_liveness or has_startup):
        return [
            Finding(
                pattern_id="missing_health_check",
                severity=Severity.MEDIUM,
                title="No livenessProbe or startupProbe configured",
                summary=f"'{s.service_name}' has no probes — Cloud Run can't detect a wedged container.",
                impact="Stuck containers serve 5xx until manual rollback. Users hit them silently.",
                fix="Add `livenessProbe.httpGet.path=/healthz` with a 5s initialDelaySeconds. Add a Flask/FastAPI handler that returns 200 if the app is alive.",
                evidence=[
                    Evidence(
                        kind="gcloud_config",
                        locator="spec.template.spec.containers[0] (no livenessProbe / startupProbe field present)",
                        value="absent",
                        source_url=f"https://console.cloud.google.com/run/detail/{s.region}/{s.service_name}/yaml",
                    ),
                ],
            )
        ]
    return []


def pattern_iam_all_users(s: ServiceSnapshot) -> list[Finding]:
    """Pattern 4: roles/run.invoker granted to allUsers (public-internet exposure)."""
    bindings = s.iam_policy.get("bindings", []) or []
    for b in bindings:
        if b.get("role") == "roles/run.invoker" and "allUsers" in (b.get("members") or []):
            return [
                Finding(
                    pattern_id="iam_all_users",
                    severity=Severity.CRITICAL,
                    title="Service grants roles/run.invoker to allUsers (public)",
                    summary=f"'{s.service_name}' is callable by anyone on the internet without authentication.",
                    impact="If this is an internal-only service, every request is potentially attack traffic. Bills can also balloon from scrapers/abusers.",
                    fix="Restrict invoker to specific principals (`gcloud run services remove-iam-policy-binding ... --member=allUsers`) and switch the client to use a service-account ID token.",
                    evidence=[
                        Evidence(
                            kind="gcloud_config",
                            locator="iam.bindings[role=roles/run.invoker].members[allUsers]",
                            value="present",
                            source_url=f"https://console.cloud.google.com/run/detail/{s.region}/{s.service_name}/permissions",
                        ),
                    ],
                )
            ]
    return []


def pattern_error_rate_high(s: ServiceSnapshot) -> list[Finding]:
    """Pattern 5: 24h error rate > 5%."""
    if s.error_rate_24h > 0.05:
        related_anomalies = [a for a in s.anomalies_24h if a.get("category") in {"error_rate", "5xx"}]
        evidence = [
            Evidence(
                kind="metric",
                locator="error_rate_24h",
                value=f"{s.error_rate_24h * 100:.2f}%",
            )
        ]
        for a in related_anomalies[:3]:
            evidence.append(
                Evidence(
                    kind="dynatrace_anomaly",
                    locator=a.get("problem_id", "unknown"),
                    value=a.get("title", ""),
                    source_url=a.get("url", ""),
                )
            )
        return [
            Finding(
                pattern_id="error_rate_high",
                severity=Severity.HIGH,
                title=f"Error rate {s.error_rate_24h * 100:.2f}% (last 24h)",
                summary=f"'{s.service_name}' returns 5xx on {s.error_rate_24h * 100:.2f}% of requests over the last day.",
                impact="Users hit failures. SLO budget likely exhausted. Trust degrades silently.",
                fix=("Pull the top error-rate Dynatrace anomaly below, drill into the stack trace, ship a fix or rollback to the last known-good revision."),
                evidence=evidence,
            )
        ]
    return []


PATTERNS: list[Callable[[ServiceSnapshot], list[Finding]]] = [
    pattern_cold_start_spike,
    pattern_oversized_instance,
    pattern_missing_health_check,
    pattern_iam_all_users,
    pattern_error_rate_high,
]


def run_all(snapshot: ServiceSnapshot) -> list[Finding]:
    out: list[Finding] = []
    for pat in PATTERNS:
        out.extend(pat(snapshot))
    out.sort(key=lambda f: (_severity_order(f.severity), f.pattern_id))
    return out


def _severity_order(s: Severity) -> int:
    return {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}[s]


def _parse_memory(s: str) -> int:
    """Parse '512Mi' / '2Gi' / '1024Mi' / '2048M' into MB int."""
    s = s.strip()
    if s.endswith("Gi"):
        return int(float(s[:-2]) * 1024)
    if s.endswith("Mi"):
        return int(float(s[:-2]))
    if s.endswith("M"):
        return int(float(s[:-1]))
    if s.endswith("G"):
        return int(float(s[:-1]) * 1024)
    try:
        return int(float(s)) // (1024 * 1024)
    except ValueError:
        return 0
