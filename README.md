# CloudRunAuditor

> Paste a Cloud Run service URL → get an audit memo where every finding cites the exact metric or config line.

Built for the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com/) — track: **Dynatrace** ($3,000 + $1,000 MCP side prize).

## What it does

`POST /audit` with `{ project, service, region }` →

1. Reads Cloud Run service config via `gcloud run services describe`
2. Reads IAM policy via `gcloud run services get-iam-policy`
3. Reads telemetry via Dynatrace MCP server (production) or Cloud Monitoring (fallback)
4. Runs 5 hard-coded audit patterns (see `src/cloudrunauditor/audit.py`):
   - **Cold-start p95 spike** (> 2s) — high severity
   - **Oversized instance** (Memory ≥ 1Gi but p95 usage < 256MB) — medium
   - **Missing health check** (no livenessProbe / startupProbe) — medium
   - **IAM allUsers exposure** (`roles/run.invoker` granted to public) — critical
   - **Error rate > 5%** (last 24h) — high
5. Returns a markdown memo where each finding includes 3+ evidence citations: gcloud config locator, metric reading, Dynatrace anomaly ID (with deep links).

## Why this wins the hackathon

| Criterion | How CloudRunAuditor scores |
|---|---|
| Technological Implementation | Real `gcloud` shell-out + Dynatrace MCP integration + Vertex Gemini call for memo synthesis |
| Design | Audit memo with severity badges + clickable Evidence section per finding (same UX as TransitionPilot) |
| Potential Impact | Orgs run hundreds of Cloud Run services with no audit cadence; this is one click |
| Quality of the Idea | First "Specialist Auditor" agent built on Dynatrace MCP for Cloud Run; differentiator vs the 100 generic agents that will submit |

## Architecture

```
[Operator] -> POST /audit { service, region, project }
              |
              v
[FastAPI on Cloud Run]
              |
       ┌──────┴──────┬─────────────┐
       v             v             v
   gcloud CLI    Dynatrace MCP   Cloud Monitoring
   (config +     (anomalies +    (latency / errors)
    iam)         metrics)
              |
              v
       [5 audit patterns]
              |
              v
       [Audit memo markdown]
```

## Quickstart

```powershell
# 1. Get $100 GCP credits (DEADLINE 2026-06-04) at cloud.google.com/free
# 2. Create a GCP project + enable Cloud Run + Vertex AI + Cloud Monitoring
# 3. gcloud auth application-default login

cd code/cloudrunauditor
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest

# Local dev
uvicorn cloudrunauditor.main:app --reload --port 8080

# Deploy
docker build -t cloudrunauditor .
gcloud run deploy cloudrunauditor --image gcr.io/<project>/cloudrunauditor --region us-central1
```

## Required REGISTRATION before submitting

- Devpost: register at https://rapid-agent.devpost.com/
- GCP free trial OR $100 credits (apply by **2026-06-04**, 1-5 day approval)
- Dynatrace free trial (sign up at dynatrace.com)
- Generate Dynatrace API token with `problems.read` scope

## Files

```
src/cloudrunauditor/
├── __init__.py
├── main.py             FastAPI app — single POST /audit endpoint
├── audit.py            5 audit patterns (Severity + Finding + ServiceSnapshot)
├── memo.py             Audit-memo markdown renderer
├── gcloud_client.py    Async wrapper around `gcloud` CLI
└── dynatrace_client.py Dynatrace MCP / REST client
Dockerfile              Pinned python:3.11.10-slim-bookworm; cold-start optimized
pyproject.toml          All deps pinned exact (no >= / ~=)
```

## License

BSD-3-Clause. See LICENSE.

## Built by

[Masoud Masoori](https://github.com/Masoud-Masoori) — MAS-AI Technologies Inc.
Engineering partner: Claude Opus 4.7.
