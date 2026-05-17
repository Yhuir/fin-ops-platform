# api-shadow-validation-report-20260517

- Gate: **GO**
- Python base URL: `http://127.0.0.1:8001`
- Axum base URL: `http://127.0.0.1:8002`
- Fixture: `/Users/yu/Desktop/fin-ops-platform/docs/dev/api-fixtures/business-api-shadow-validation.json`
- Endpoint filters: `background-job-acknowledge-request, ledger-detail, ledger-status-update, ledgers-list, project-assign-request, project-detail, projects-create-manual-profile, projects-hub-list, reminder-run-request, reminders-list, settings-data-reset-create-job, settings-data-reset-direct-queues-job, workbench-settings-project-create-request, workbench-settings-project-delete-request, workbench-settings-project-sync-request, workbench-settings-write-contract`
- Risk filters: `all`
- Generated at: `2026-05-17T11:33:56Z`
- Sensitive diff values: `[REDACTED]`

## Summary

- Total: 32
- GO: 32
- NO_GO: 0
- Unexpected diffs: 0
- Accepted production changes: 3
- Permission failure cases: 16
- Fixture validation errors: 0

## Endpoints

| Endpoint | Method | Risk | Owner | Source | Gate | Unexpected diffs |
| --- | --- | --- | --- | --- | --- | --- |
| /api/background-jobs/${BACKGROUND_JOB_ID}/acknowledge | POST | medium | platform-ops | PostgreSQL job.worker_tasks + job.worker_task_acknowledgements, audit.events, app.write_idempotency_records; does not mutate core worker task status | GO | 0 |
| /api/background-jobs/${BACKGROUND_JOB_ID}/acknowledge | POST | medium | platform-ops | PostgreSQL job.worker_tasks + job.worker_task_acknowledgements, audit.events, app.write_idempotency_records; does not mutate core worker task status | GO | 0 |
| /api/workbench/settings | POST | high | platform-ops | PostgreSQL app.settings_profiles, audit.events and app.write_idempotency_records | GO | 0 |
| /api/workbench/settings | POST | high | platform-ops | PostgreSQL app.settings_profiles, audit.events and app.write_idempotency_records | GO | 0 |
| /api/workbench/settings/projects/sync | POST | high | platform-ops | PostgreSQL job.worker_tasks/job.outbox_events/audit/idempotency; request queues project sync and does not scan OA source | GO | 0 |
| /api/workbench/settings/projects/sync | POST | high | platform-ops | PostgreSQL job.worker_tasks/job.outbox_events/audit/idempotency; request queues project sync and does not scan OA source | GO | 0 |
| /api/workbench/settings/projects | POST | high | platform-ops | PostgreSQL app.project_profiles, audit.events and app.write_idempotency_records | GO | 0 |
| /api/workbench/settings/projects | POST | high | platform-ops | PostgreSQL app.project_profiles, audit.events and app.write_idempotency_records | GO | 0 |
| /api/workbench/settings/projects/${PROJECT_DELETE_ID} | DELETE | high | platform-ops | PostgreSQL app.project_profiles soft-deactivation, audit.events and app.write_idempotency_records | GO | 0 |
| /api/workbench/settings/projects/${PROJECT_DELETE_ID} | DELETE | high | platform-ops | PostgreSQL app.project_profiles soft-deactivation, audit.events and app.write_idempotency_records | GO | 0 |
| /api/workbench/settings/data-reset/jobs | POST | high | platform-ops | PostgreSQL job.worker_tasks/job.outbox_events/audit/idempotency; request queues destructive reset only | GO | 0 |
| /api/workbench/settings/data-reset/jobs | POST | high | platform-ops | PostgreSQL job.worker_tasks/job.outbox_events/audit/idempotency; request queues destructive reset only | GO | 0 |
| /api/workbench/settings/data-reset | POST | high | platform-ops | PostgreSQL job.worker_tasks/job.outbox_events/audit/idempotency; API route queues settings_data_reset worker task and direct destructive execution remains wo... | GO | 0 |
| /api/workbench/settings/data-reset | POST | high | platform-ops | PostgreSQL job.worker_tasks/job.outbox_events/audit/idempotency; API route queues settings_data_reset worker task and direct destructive execution remains wo... | GO | 0 |
| /projects | GET | high | platform-ops | PostgreSQL app.project_profiles active project hub projection | GO | 0 |
| /projects | GET | high | platform-ops | PostgreSQL app.project_profiles active project hub projection | GO | 0 |
| /projects/${PROJECT_ID} | GET | high | platform-ops | PostgreSQL app.project_profiles project detail projection | GO | 0 |
| /projects/${PROJECT_ID} | GET | high | platform-ops | PostgreSQL app.project_profiles project detail projection | GO | 0 |
| /projects | POST | high | platform-ops | PostgreSQL app.project_profiles, audit.events and app.write_idempotency_records | GO | 0 |
| /projects | POST | high | platform-ops | PostgreSQL app.project_profiles, audit.events and app.write_idempotency_records | GO | 0 |
| /projects/assign | POST | high | platform-ops | PostgreSQL app.project_profiles target project check, target object fact check, app.project_assignments, app.project_profile_events, audit.events and app.wri... | GO | 0 |
| /projects/assign | POST | high | platform-ops | PostgreSQL app.project_profiles target project check, target object fact check, app.project_assignments, app.project_profile_events, audit.events and app.wri... | GO | 0 |
| /ledgers | GET | high | platform-ops | PostgreSQL app.ledgers legacy FollowUpLedger projection | GO | 0 |
| /ledgers | GET | high | platform-ops | PostgreSQL app.ledgers legacy FollowUpLedger projection | GO | 0 |
| /ledgers/${LEDGER_ID} | GET | high | platform-ops | PostgreSQL app.ledgers + app.ledger_events legacy detail projection | GO | 0 |
| /ledgers/${LEDGER_ID} | GET | high | platform-ops | PostgreSQL app.ledgers + app.ledger_events legacy detail projection | GO | 0 |
| /reminders | GET | high | platform-ops | PostgreSQL app.reminders legacy reminder projection | GO | 0 |
| /reminders | GET | high | platform-ops | PostgreSQL app.reminders legacy reminder projection | GO | 0 |
| /ledgers/${LEDGER_ID}/status | POST | high | platform-ops | PostgreSQL app.ledgers/app.ledger_events with audit.events and app.write_idempotency_records | GO | 0 |
| /ledgers/${LEDGER_ID}/status | POST | high | platform-ops | PostgreSQL app.ledgers/app.ledger_events with audit.events and app.write_idempotency_records | GO | 0 |
| /reminders/run | POST | high | platform-ops | PostgreSQL job.worker_tasks/job.outbox_events/audit/idempotency; request queues reminder scan and sends no external notification | GO | 0 |
| /reminders/run | POST | high | platform-ops | PostgreSQL job.worker_tasks/job.outbox_events/audit/idempotency; request queues reminder scan and sends no external notification | GO | 0 |

## Accepted Production Changes

| Endpoint | Change | Legacy | Axum | Source Contract | Owner | Next Verification |
| --- | --- | --- | --- | --- | --- | --- |
| workbench-settings-project-sync-request | p0-platform-project-sync-queue-only | 200 | 200 | docs/architecture/backend-refactor/remaining-api-contracts.md#prompt04-platform-contract-delta-2026-05-17 | platform-ops | Runtime shadow must verify queued sync metadata and worker execution evidence without restoring request-path OA scans. |
| workbench-settings-project-create-request | p0-platform-settings-project-profile-facts | 200 | 200 | docs/architecture/backend-refactor/remaining-api-contracts.md#prompt04-platform-contract-delta-2026-05-17 | platform-ops | Runtime shadow must verify UUID project id projection and frontend settings compatibility. |
| workbench-settings-project-delete-request | p0-platform-settings-project-soft-delete | 200 | 200 | docs/architecture/backend-refactor/remaining-api-contracts.md#prompt04-platform-contract-delta-2026-05-17 | platform-ops | Runtime shadow must verify deactivated project disappears from active settings projection and remains auditable. |

## Explained Diffs

| Endpoint | Case | Kind | Path | Python | Axum |
| --- | --- | --- | --- | --- | --- |
| /api/background-jobs/${BACKGROUND_JOB_ID}/acknowledge | primary | `date_format` | `$.job.acknowledged_at` | `2026-05-17T11:33:50.199256+00:00` | `2026-05-17T11:33:50Z` |
| /api/background-jobs/${BACKGROUND_JOB_ID}/acknowledge | primary | `date_format` | `$.job.created_at` | `2026-05-17T01:00:00+00:00` | `2026-05-17T01:00:00Z` |
| /api/background-jobs/${BACKGROUND_JOB_ID}/acknowledge | primary | `date_format` | `$.job.updated_at` | `2026-05-17T11:33:50.199256+00:00` | `2026-05-17T01:00:00Z` |
| /api/workbench/settings/projects/sync | primary | `field` | `$.settings.access_control.admin_usernames.length` | `2` | `1` |
| /api/workbench/settings/projects/sync | primary | `field` | `$.settings.access_control.allowed_usernames.length` | `2` | `1` |
| /api/workbench/settings/projects/sync | primary | `field` | `$.settings.bank_account_mappings.length` | `1` | `0` |
| /api/workbench/settings/projects/sync | primary | `field` | `$.settings.projects.active.length` | `4` | `2` |
| /api/workbench/settings/projects/sync | primary | `date_format` | `$.sync.finished_at` | `2026-05-17T11:33:51.213288+00:00` | `2026-05-17T11:33:51+00:00` |
| /api/workbench/settings/projects/sync | primary | `date_format` | `$.sync.started_at` | `2026-05-17T11:33:51.213266+00:00` | `2026-05-17T11:33:51+00:00` |
| /api/workbench/settings/projects | primary | `field` | `$.settings.access_control.admin_usernames.length` | `2` | `1` |
| /api/workbench/settings/projects | primary | `field` | `$.settings.access_control.allowed_usernames.length` | `2` | `1` |
| /api/workbench/settings/projects | primary | `field` | `$.settings.bank_account_mappings.length` | `1` | `0` |
| /api/workbench/settings/projects | primary | `value` | `$.settings.projects.active[0].id` | `proj_manual_0001` | `7480cc13-3d1f-457b-8814-ab38e83c2cdf` |
| /api/workbench/settings/projects/${PROJECT_DELETE_ID} | primary | `field` | `$.settings.access_control.admin_usernames.length` | `2` | `1` |
| /api/workbench/settings/projects/${PROJECT_DELETE_ID} | primary | `field` | `$.settings.access_control.allowed_usernames.length` | `2` | `1` |
| /api/workbench/settings/projects/${PROJECT_DELETE_ID} | primary | `field` | `$.settings.bank_account_mappings.length` | `1` | `0` |
| /api/workbench/settings/projects/${PROJECT_DELETE_ID} | primary | `value` | `$.settings.projects.active[0].id` | `proj_manual_0001` | `7480cc13-3d1f-457b-8814-ab38e83c2cdf` |
| /api/workbench/settings/data-reset/jobs | primary | `date_format` | `$.job.created_at` | `2026-05-17T11:33:52.517041+00:00` | `2026-05-17T11:33:52+00:00` |
| /api/workbench/settings/data-reset/jobs | primary | `value` | `$.job.job_id` | `job_20260517_113352_28834d30` | `672104b6-8632-4206-af24-72aab5c7c256` |
| /api/workbench/settings/data-reset/jobs | primary | `date_format` | `$.job.updated_at` | `2026-05-17T11:33:52.517041+00:00` | `2026-05-17T11:33:52+00:00` |
| /api/workbench/settings/data-reset | primary | `date_format` | `$.job.created_at` | `2026-05-17T11:33:53.354255+00:00` | `2026-05-17T11:33:53+00:00` |
| /api/workbench/settings/data-reset | primary | `value` | `$.job.job_id` | `job_20260517_113353_95e5bb8f` | `b99fce0d-d3c9-4f7a-902e-5422501d3569` |
| /api/workbench/settings/data-reset | primary | `date_format` | `$.job.updated_at` | `2026-05-17T11:33:53.354255+00:00` | `2026-05-17T11:33:53+00:00` |
| /projects | primary | `value` | `$.hub.projects[0].id` | `proj_manual_0001` | `b15c5b89-bc7c-4ba7-ac73-ffa82479ac8f` |
| /projects | primary | `value` | `$.hub.projects[0].project_id` | `proj_manual_0001` | `b15c5b89-bc7c-4ba7-ac73-ffa82479ac8f` |
| /projects | primary | `value` | `$.hub.projects[0].project_uuid` | `null` | `b15c5b89-bc7c-4ba7-ac73-ffa82479ac8f` |
| /projects | primary | `value` | `$.hub.summaries[0].project_id` | `proj_manual_0001` | `b15c5b89-bc7c-4ba7-ac73-ffa82479ac8f` |
| /projects | primary | `value` | `$.hub.summaries[0].project_uuid` | `null` | `b15c5b89-bc7c-4ba7-ac73-ffa82479ac8f` |
| /projects | primary | `value` | `$.project.id` | `proj_manual_0001` | `b15c5b89-bc7c-4ba7-ac73-ffa82479ac8f` |
| /projects/assign | primary | `date_format` | `$.assignment.created_at` | `2026-05-17T11:33:54.961925+00:00` | `2026-05-17T11:33:54.856946+00:00` |
| /projects/assign | primary | `date_format` | `$.assignments[0].created_at` | `2026-05-17T11:33:54.961925+00:00` | `2026-05-17T11:33:54.856946+00:00` |
| /ledgers/${LEDGER_ID}/status | primary | `date_format` | `$.ledger.events[0].created_at` | `2026-05-17T11:33:56Z` | `2026-05-17T11:33:55Z` |
| /reminders/run | primary | `field` | `$.sent_reminders` | `null` | `[]` |
| /reminders/run | primary | `date_format` | `$.job.created_at` | `2026-05-17T11:33:56.550648+00:00` | `2026-05-17T11:33:56+00:00` |
| /reminders/run | primary | `value` | `$.job.job_id` | `job_20260517_113356_fb242632` | `24451a4e-9e3b-475c-9b25-19a883fb6604` |
| /reminders/run | primary | `date_format` | `$.job.updated_at` | `2026-05-17T11:33:56.550648+00:00` | `2026-05-17T11:33:56+00:00` |

Any endpoint with an unexplained status, field, ordering, money-format, date-format, or value diff keeps the overall gate at `NO_GO`.
