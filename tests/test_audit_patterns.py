"""Smoke tests for the 5 audit patterns.

These run without GCP / Dynatrace creds — they hand-craft ServiceSnapshot
instances and verify each pattern detects what it's supposed to detect.
"""

from __future__ import annotations

from cloudrunauditor.audit import (
    Severity,
    ServiceSnapshot,
    pattern_cold_start_spike,
    pattern_error_rate_high,
    pattern_iam_all_users,
    pattern_missing_health_check,
    pattern_oversized_instance,
    run_all,
)


def _baseline_snapshot() -> ServiceSnapshot:
    """A 'clean' snapshot — no patterns should fire on this."""
    return ServiceSnapshot(
        service_name="api",
        region="us-central1",
        config={
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "resources": {"limits": {"memory": "512Mi"}},
                                "livenessProbe": {"httpGet": {"path": "/healthz"}},
                            }
                        ]
                    }
                }
            }
        },
        iam_policy={"bindings": [{"role": "roles/run.invoker", "members": ["serviceAccount:caller@...iam.gserviceaccount.com"]}]},
        metrics_24h={"cold_start_latency_p95_ms": [800, 900], "memory_usage_p95_mb": [300], "request_count": [1000], "error_count": [5]},
        anomalies_24h=[],
        error_rate_24h=0.005,
    )


def test_clean_snapshot_no_findings() -> None:
    s = _baseline_snapshot()
    assert run_all(s) == []


def test_cold_start_spike_fires() -> None:
    s = _baseline_snapshot()
    s.metrics_24h["cold_start_latency_p95_ms"] = [2500, 2800]
    findings = pattern_cold_start_spike(s)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "2800" in findings[0].title


def test_oversized_instance_fires() -> None:
    s = _baseline_snapshot()
    s.config["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] = "2Gi"
    s.metrics_24h["memory_usage_p95_mb"] = [180]
    findings = pattern_oversized_instance(s)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM


def test_missing_health_check_fires() -> None:
    s = _baseline_snapshot()
    s.config["spec"]["template"]["spec"]["containers"][0].pop("livenessProbe", None)
    findings = pattern_missing_health_check(s)
    assert len(findings) == 1


def test_iam_all_users_fires() -> None:
    s = _baseline_snapshot()
    s.iam_policy["bindings"].append({"role": "roles/run.invoker", "members": ["allUsers"]})
    findings = pattern_iam_all_users(s)
    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL


def test_error_rate_high_fires() -> None:
    s = _baseline_snapshot()
    s.error_rate_24h = 0.08
    findings = pattern_error_rate_high(s)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
