"""CloudRunAuditor — Cloud Run service audit agent.

Built for the Google Cloud Rapid Agent Hackathon (Dynatrace track).

Architecture:
    1. User pastes a Cloud Run service URL + grants read-only IAM
    2. Agent reads service config via gcloud + telemetry via Dynatrace MCP
    3. Agent runs 5 audit patterns (audit.py)
    4. Returns an audit memo (memo.py) where every finding cites the
       specific Dynatrace anomaly ID or gcloud config line

Same "Specialist Auditor" pattern as TransitionPilot — third domain.
"""

__version__ = "0.1.0"
