# p0-platform-runtime-shadow-20260517

- Status: `GO`
- Generated at: `2026-05-17T11:33:56Z`
- Preflight status: `GO`
- Shadow validation status: `GO`
- Endpoint count: `16`

## Blocking Reasons

- `none`

## Health Checks

| Check | Status | HTTP | URL | Error |
| --- | --- | --- | --- | --- |
| `python_health` | `GO` | `200` | `http://127.0.0.1:8001/health` |  |
| `axum_healthz` | `GO` | `200` | `http://127.0.0.1:8002/healthz` |  |
| `axum_readyz` | `GO` | `200` | `http://127.0.0.1:8002/readyz` |  |

## Preflight Findings

| Code | Severity | Message | Required action |
| --- | --- | --- | --- |
| `NONE` | `none` | No preflight findings. | Run runtime shadow validation. |

## Blocking Details

| Code | Type | Message | Required action |
| --- | --- | --- | --- |
| `NONE` | `none` | No runtime blockers. | Shadow validation completed. |

## Shadow Report

```json
{
  "status": "GO",
  "json_path": "/Users/yu/Desktop/fin-ops-platform/docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
  "markdown_path": "/Users/yu/Desktop/fin-ops-platform/docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
  "summary": {
    "total": 32,
    "go": 32,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "explained_diff_count": 36,
    "accepted_production_change_count": 3,
    "permission_failure_cases": 16,
    "fixture_error_count": 0,
    "permission_failure_required_count": 88,
    "permission_failure_missing_count": 0
  },
  "filters": {
    "endpoint_ids": [
      "background-job-acknowledge-request",
      "ledger-detail",
      "ledger-status-update",
      "ledgers-list",
      "project-assign-request",
      "project-detail",
      "projects-create-manual-profile",
      "projects-hub-list",
      "reminder-run-request",
      "reminders-list",
      "settings-data-reset-create-job",
      "settings-data-reset-direct-queues-job",
      "workbench-settings-project-create-request",
      "workbench-settings-project-delete-request",
      "workbench-settings-project-sync-request",
      "workbench-settings-write-contract"
    ],
    "risks": []
  }
}
```
