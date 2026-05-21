"""Audit memo template — every finding has citations.

The memo IS the product. Same UX pattern as TransitionPilot's "Discharge
Failure Prevented" memo: severity badges, one-line summary per finding,
clickable Evidence section pointing at the exact line/metric.
"""

from __future__ import annotations

from datetime import datetime

from cloudrunauditor.audit import Finding, ServiceSnapshot, Severity

SEVERITY_BADGE = {
    Severity.CRITICAL: "🔴 CRITICAL",
    Severity.HIGH: "🟠 HIGH",
    Severity.MEDIUM: "🟡 MEDIUM",
    Severity.LOW: "⚪ LOW",
}


def render_memo(snapshot: ServiceSnapshot, findings: list[Finding]) -> str:
    lines: list[str] = []
    lines.append(f"# Audit memo — `{snapshot.service_name}` ({snapshot.region})")
    lines.append("")
    lines.append(f"_Run {datetime.utcnow().isoformat()}Z_")
    lines.append("")

    if not findings:
        lines.append("## No findings")
        lines.append("")
        lines.append("Service passed all 5 audit patterns. Re-run after any deploy.")
        return "\n".join(lines) + "\n"

    # Summary
    by_sev: dict[Severity, int] = {}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    summary_bits = [f"{by_sev[s]} {SEVERITY_BADGE[s]}" for s in Severity if s in by_sev]
    lines.append(f"**{len(findings)} finding(s):** {', '.join(summary_bits)}.")
    lines.append("")

    # Per-finding
    for i, f in enumerate(findings, start=1):
        lines.append(f"## {i}. {SEVERITY_BADGE[f.severity]} — {f.title}")
        lines.append("")
        lines.append(f"**Summary.** {f.summary}")
        lines.append("")
        lines.append(f"**Impact.** {f.impact}")
        lines.append("")
        lines.append(f"**Fix.** {f.fix}")
        lines.append("")
        lines.append("**Evidence:**")
        lines.append("")
        for e in f.evidence:
            line = f"- `{e.locator}` = `{e.value}`"
            if e.source_url:
                line += f" — [open]({e.source_url})"
            lines.append(line)
        lines.append("")

    return "\n".join(lines) + "\n"
