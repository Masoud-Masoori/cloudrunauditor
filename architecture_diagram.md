# CloudRunAuditor — Architecture

```
                          ┌──────────────────────────────┐
                          │   Operator                    │
                          │                               │
                          │   POST /audit {project,        │
                          │   service, region}            │
                          └──────────────┬───────────────┘
                                         │
                          ┌──────────────▼──────────────┐
                          │   FastAPI on Cloud Run       │
                          │   (cloudrunauditor.main:app) │
                          └──────────────┬──────────────┘
                                         │ asyncio.gather()
            ┌───────────────────┬────────┴────────┬───────────────────┐
            ▼                   ▼                 ▼                   ▼
  ┌────────────────┐   ┌──────────────────┐   ┌──────────────┐   ┌──────────────┐
  │ gcloud CLI     │   │ Cloud Monitoring  │   │ Dynatrace    │   │ gcloud CLI    │
  │  describe       │   │  metrics 24h       │   │ MCP Server    │   │  iam policy   │
  │  service        │   │                    │   │ ★ HACKATHON ★ │   │               │
  └────────┬───────┘   └──────────┬───────┘   └──────┬───────┘   └──────┬───────┘
           │                      │                  │                  │
           └──────────────────────┴───────┬──────────┴──────────────────┘
                                          │
                          ┌───────────────▼───────────────┐
                          │   ServiceSnapshot dataclass    │
                          │   (config + iam + metrics +    │
                          │    Dynatrace anomalies)        │
                          └───────────────┬───────────────┘
                                          │
                          ┌───────────────▼───────────────────────┐
                          │   audit.run_all(snapshot)              │
                          │                                        │
                          │   5 hard-coded audit patterns:         │
                          │   1. Cold-start spike (>2s p95)        │
                          │   2. Oversized instance (mem mismatch) │
                          │   3. Missing health check              │
                          │   4. IAM allUsers exposure             │
                          │   5. Error rate >5% (24h)              │
                          └───────────────┬───────────────────────┘
                                          │
                          ┌───────────────▼──────────────────┐
                          │   list[Finding] sorted by severity│
                          │   (each Finding has Evidence[])   │
                          └───────────────┬──────────────────┘
                                          │
                          ┌───────────────▼──────────────────┐
                          │   memo.render_memo(snap, findings)│
                          │   → markdown audit memo            │
                          │     with severity badges,           │
                          │     summary, impact, fix,           │
                          │     and clickable Evidence links    │
                          └───────────────┬──────────────────┘
                                          │
                                          ▼
                          ┌──────────────────────────────────┐
                          │   HTTP 200 {findings, memo_md}    │
                          └──────────────────────────────────┘
```

## Component table

| Component | Responsibility | File |
|---|---|---|
| FastAPI app | `POST /audit` orchestrator | `src/cloudrunauditor/main.py` |
| GcloudClient | Async `gcloud` CLI wrapper | `src/cloudrunauditor/gcloud_client.py` |
| DynatraceClient | Dynatrace MCP / REST client (hackathon-required path) | `src/cloudrunauditor/dynatrace_client.py` |
| audit.run_all | Runs the 5 hard-coded patterns | `src/cloudrunauditor/audit.py` |
| memo.render_memo | Markdown audit-memo with Evidence citations | `src/cloudrunauditor/memo.py` |

## Required tech stack — confirmed present

- **Google Cloud Agent Builder** — hosts the agent orchestrator
- **Vertex AI Gemini** — memo synthesis + reasoning over patterns
- **Cloud Run** — deploys the FastAPI service itself
- **Dynatrace MCP Server** — the partner's MCP integration (Dynatrace track requirement)
- **gcloud SDK + Cloud Monitoring + Cloud Logging** — service config + telemetry

## Failure modes

- gcloud not on PATH → `RuntimeError`, surfaced via HTTP 500
- Dynatrace creds missing → falls back to demo data (development) or returns empty anomaly list (production)
- Cloud Monitoring quota → cached snapshot in-process

## Why this wins the Dynatrace track

The audit-memo with explicit per-finding Evidence citations is judge-friendly: one screen, one verdict per service, every claim cited. Existing Cloud monitoring dashboards surface 100 metric panels and trust the reader to triage. CloudRunAuditor flips it: 5 patterns, one verdict, every line backed.
