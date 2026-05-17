# api-shadow-validation-report-20260517

- Gate: **NO_GO**
- Python base URL: `[REDACTED_LOCAL_SHADOW_PYTHON_BASE_URL]`
- Axum base URL: `[REDACTED_LOCAL_SHADOW_AXUM_BASE_URL]`
- Fixture: `docs/dev/api-fixtures/business-api-shadow-validation.json`
- Endpoint filters: `all`
- Risk filters: `all`
- Generated at: `2026-05-17T01:58:54Z`
- Sensitive diff values: `[REDACTED]`

## Summary

- Total: 139
- GO: 0
- NO_GO: 139
- Unexpected diffs: 139
- Permission failure cases: 69
- Fixture validation errors: 0

## Endpoints

| Endpoint | Method | Risk | Owner | Source | Gate | Unexpected diffs |
| --- | --- | --- | --- | --- | --- | --- |
| /api/app-health | GET | medium | platform-ops | PostgreSQL app.oa_sync_runs/app.oa_sync_watermarks, job.worker_tasks, read_model.workbench_snapshots, and OA identity adapter; no app Mongo | NO_GO | 1 |
| /api/app-health | GET | medium | platform-ops | PostgreSQL app.oa_sync_runs/app.oa_sync_watermarks, job.worker_tasks, read_model.workbench_snapshots, and OA identity adapter; no app Mongo | NO_GO | 1 |
| /api/app-health/stream | GET | medium | platform-ops | SSE wrapper over the Axum app-health PostgreSQL/read_model/job facts snapshot; samples only the first app_health and heartbeat events and does not read app M... | NO_GO | 1 |
| /api/app-health/stream | GET | medium | platform-ops | SSE wrapper over the Axum app-health PostgreSQL/read_model/job facts snapshot; samples only the first app_health and heartbeat events and does not read app M... | NO_GO | 1 |
| /api/app-metadata | GET | low | platform-ops | Axum static contract metadata; no app Mongo | NO_GO | 1 |
| /api/session/me | GET | medium | platform-ops | OA identity adapter/session contract; no app Mongo | NO_GO | 1 |
| /api/session/me | GET | medium | platform-ops | OA identity adapter/session contract; no app Mongo | NO_GO | 1 |
| /api/search | GET | medium | platform-ops | PostgreSQL read_model.search_index_rows; empty query returns bounded empty payload | NO_GO | 1 |
| /api/search | GET | medium | platform-ops | PostgreSQL read_model.search_index_rows; empty query returns bounded empty payload | NO_GO | 1 |
| /api/tasks/${WORKER_TASK_ID}/status | GET | medium | platform-ops | PostgreSQL job.worker_tasks + job.worker_attempts | NO_GO | 1 |
| /api/tasks/${WORKER_TASK_ID}/status | GET | medium | platform-ops | PostgreSQL job.worker_tasks + job.worker_attempts | NO_GO | 1 |
| /api/bank-details/accounts | GET | high | finance-ops | PostgreSQL app.bank_transactions | NO_GO | 1 |
| /api/bank-details/accounts | GET | high | finance-ops | PostgreSQL app.bank_transactions | NO_GO | 1 |
| /api/bank-details/transactions | GET | high | finance-ops | PostgreSQL app.bank_transactions + app.bank_transaction_categories | NO_GO | 1 |
| /api/bank-details/transactions | GET | high | finance-ops | PostgreSQL app.bank_transactions + app.bank_transaction_categories | NO_GO | 1 |
| /api/bank-details/transactions/categories | PATCH | high | finance-ops | PostgreSQL app.bank_transactions, app.bank_transaction_categories, app.bank_transaction_category_events, audit.events, app.write_idempotency_records, job.wor... | NO_GO | 1 |
| /api/bank-details/transactions/categories | PATCH | high | finance-ops | PostgreSQL app.bank_transactions, app.bank_transaction_categories, app.bank_transaction_category_events, audit.events, app.write_idempotency_records, job.wor... | NO_GO | 1 |
| /api/turnover-ledger | GET | high | finance-ops | PostgreSQL app.bank_transactions + active app.bank_transaction_categories raw_payload.category_code using Python turnover category rules; no app Mongo | NO_GO | 1 |
| /api/turnover-ledger | GET | high | finance-ops | PostgreSQL app.bank_transactions + active app.bank_transaction_categories raw_payload.category_code using Python turnover category rules; no app Mongo | NO_GO | 1 |
| /api/turnover-ledger | GET | high | finance-ops | PostgreSQL app.bank_transactions + active app.bank_transaction_categories raw_payload.category_code using Python turnover category rules; no app Mongo | NO_GO | 1 |
| /api/turnover-ledger | GET | high | finance-ops | PostgreSQL app.bank_transactions + active app.bank_transaction_categories raw_payload.category_code using Python turnover category rules; no app Mongo | NO_GO | 1 |
| /api/turnover-ledger/export-preview | GET | high | finance-ops | PostgreSQL app.bank_transactions + active app.bank_transaction_categories raw_payload.category_code using Python turnover category and export-preview rules; ... | NO_GO | 1 |
| /api/turnover-ledger/export-preview | GET | high | finance-ops | PostgreSQL app.bank_transactions + active app.bank_transaction_categories raw_payload.category_code using Python turnover category and export-preview rules; ... | NO_GO | 1 |
| /api/turnover-ledger/relations/${TURNOVER_RELATION_ID} | GET | high | finance-ops | PostgreSQL app.bank_transactions + active app.bank_transaction_categories raw_payload.category_code using Python turnover category/detail rules and SHA1 rela... | NO_GO | 1 |
| /api/turnover-ledger/relations/${TURNOVER_RELATION_ID} | GET | high | finance-ops | PostgreSQL app.bank_transactions + active app.bank_transaction_categories raw_payload.category_code using Python turnover category/detail rules and SHA1 rela... | NO_GO | 1 |
| /api/no-oa-bank-batches | GET | high | finance-ops | PostgreSQL app.no_oa_bank_batches | NO_GO | 1 |
| /api/no-oa-bank-batches | GET | high | finance-ops | PostgreSQL app.no_oa_bank_batches | NO_GO | 1 |
| /api/no-oa-bank-batches/${NO_OA_BATCH_ID} | GET | high | finance-ops | PostgreSQL app.no_oa_bank_batches + app.bank_transactions + app.bank_transaction_categories | NO_GO | 1 |
| /api/no-oa-bank-batches/${NO_OA_BATCH_ID} | GET | high | finance-ops | PostgreSQL app.no_oa_bank_batches + app.bank_transactions + app.bank_transaction_categories | NO_GO | 1 |
| /api/no-oa-bank-batches/${NO_OA_SUBMIT_BATCH_ID}/submit | POST | high | finance-ops | PostgreSQL app.no_oa_bank_batches + transactional workbench write command + job/outbox rebuild marker | NO_GO | 1 |
| /api/no-oa-bank-batches/${NO_OA_SUBMIT_BATCH_ID}/submit | POST | high | finance-ops | PostgreSQL app.no_oa_bank_batches + transactional workbench write command + job/outbox rebuild marker | NO_GO | 1 |
| /api/no-oa-bank-batches/${NO_OA_WITHDRAW_BATCH_ID}/withdraw | POST | high | finance-ops | PostgreSQL app.no_oa_bank_batches + transactional workbench write command + job/outbox rebuild marker | NO_GO | 1 |
| /api/no-oa-bank-batches/${NO_OA_WITHDRAW_BATCH_ID}/withdraw | POST | high | finance-ops | PostgreSQL app.no_oa_bank_batches + transactional workbench write command + job/outbox rebuild marker | NO_GO | 1 |
| /api/no-oa-bank-batches/submit | POST | high | finance-ops | PostgreSQL app.no_oa_bank_batches + transactional workbench write command + per-item job/outbox rebuild marker | NO_GO | 1 |
| /api/no-oa-bank-batches/submit | POST | high | finance-ops | PostgreSQL app.no_oa_bank_batches + transactional workbench write command + per-item job/outbox rebuild marker | NO_GO | 1 |
| /api/tax-offset | GET | medium | tax-ops | PostgreSQL read_model.tax_offset_read_models | NO_GO | 1 |
| /api/tax-offset | GET | medium | tax-ops | PostgreSQL read_model.tax_offset_read_models | NO_GO | 1 |
| /api/tax-offset/certified-imports | GET | medium | tax-ops | PostgreSQL app.invoice_certifications + app.invoices | NO_GO | 1 |
| /api/tax-offset/certified-imports | GET | medium | tax-ops | PostgreSQL app.invoice_certifications + app.invoices | NO_GO | 1 |
| /api/tax-offset/calculate | POST | medium | tax-ops | PostgreSQL read_model.tax_offset_read_models payload only; no write/audit/outbox side effect | NO_GO | 1 |
| /api/tax-offset/calculate | POST | medium | tax-ops | PostgreSQL read_model.tax_offset_read_models payload only; no write/audit/outbox side effect | NO_GO | 1 |
| /api/etc/import | POST | medium | tax-ops | Static legacy compatibility contract; no PostgreSQL/app Mongo/OA side effect | NO_GO | 1 |
| /api/etc/import | POST | medium | tax-ops | Static legacy compatibility contract; no PostgreSQL/app Mongo/OA side effect | NO_GO | 1 |
| /api/etc/invoices | GET | high | tax-ops | PostgreSQL app.invoices ETC columns + raw_payload | NO_GO | 1 |
| /api/etc/invoices | GET | high | tax-ops | PostgreSQL app.invoices ETC columns + raw_payload | NO_GO | 1 |
| /api/etc/batches | GET | high | tax-ops | PostgreSQL app.invoices ETC columns + raw_payload grouped by import_batch_id/current_batch_id; no app Mongo | NO_GO | 1 |
| /api/etc/batches | GET | high | tax-ops | PostgreSQL app.invoices ETC columns + raw_payload grouped by import_batch_id/current_batch_id; no app Mongo | NO_GO | 1 |
| /api/etc/batches/${ETC_BATCH_ID} | GET | high | tax-ops | PostgreSQL app.invoices ETC columns + raw_payload grouped by import_batch_id/current_batch_id; no app Mongo | NO_GO | 1 |
| /api/etc/batches/${ETC_BATCH_ID} | GET | high | tax-ops | PostgreSQL app.invoices ETC columns + raw_payload grouped by import_batch_id/current_batch_id; no app Mongo | NO_GO | 1 |
| /api/cost-statistics | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models | NO_GO | 1 |
| /api/cost-statistics | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models | NO_GO | 1 |
| /api/cost-statistics/explorer | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models | NO_GO | 1 |
| /api/cost-statistics/explorer | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models | NO_GO | 1 |
| /api/cost-statistics/projects/${COST_PROJECT_NAME_PATH} | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models time_rows | NO_GO | 1 |
| /api/cost-statistics/projects/${COST_PROJECT_NAME_PATH} | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models time_rows | NO_GO | 1 |
| /api/cost-statistics/transactions/${COST_TRANSACTION_ID} | GET | medium | cost-ops | PostgreSQL app.bank_transactions + read_model.cost_statistics_read_models + read_model.workbench_rows | NO_GO | 1 |
| /api/cost-statistics/transactions/${COST_TRANSACTION_ID} | GET | medium | cost-ops | PostgreSQL app.bank_transactions + read_model.cost_statistics_read_models + read_model.workbench_rows | NO_GO | 1 |
| /api/cost-statistics/export-preview | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models time_rows; no app Mongo/workbench recalculation | NO_GO | 1 |
| /api/cost-statistics/export-preview | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models time_rows; no app Mongo/workbench recalculation | NO_GO | 1 |
| /api/cost-statistics/export-preview | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models time_rows project aggregate; no app Mongo/workbench detail recalculation | NO_GO | 1 |
| /api/cost-statistics/export-preview | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models time_rows project aggregate; no app Mongo/workbench detail recalculation | NO_GO | 1 |
| /api/cost-statistics/export-preview | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models time_rows expense_type filter; no app Mongo/workbench recalculation | NO_GO | 1 |
| /api/cost-statistics/export-preview | GET | medium | cost-ops | PostgreSQL read_model.cost_statistics_read_models time_rows expense_type filter; no app Mongo/workbench recalculation | NO_GO | 1 |
| /api/background-jobs/active | GET | medium | platform-ops | PostgreSQL job.worker_tasks system tasks, legacy active/attention list envelope | NO_GO | 1 |
| /api/background-jobs/active | GET | medium | platform-ops | PostgreSQL job.worker_tasks system tasks, legacy active/attention list envelope | NO_GO | 1 |
| /api/background-jobs/${BACKGROUND_JOB_ID} | GET | medium | platform-ops | PostgreSQL job.worker_tasks system task detail, legacy {job} envelope | NO_GO | 1 |
| /api/background-jobs/${BACKGROUND_JOB_ID} | GET | medium | platform-ops | PostgreSQL job.worker_tasks system task detail, legacy {job} envelope | NO_GO | 1 |
| /imports/templates | GET | medium | platform-ops | Static contract mirrored from legacy Python TEMPLATE_DEFINITIONS | NO_GO | 1 |
| /imports/templates | GET | medium | platform-ops | Static contract mirrored from legacy Python TEMPLATE_DEFINITIONS | NO_GO | 1 |
| /imports/batches | GET | medium | platform-ops | PostgreSQL app.import_batches metadata only | NO_GO | 1 |
| /imports/batches | GET | medium | platform-ops | PostgreSQL app.import_batches metadata only | NO_GO | 1 |
| /imports/batches/${IMPORT_BATCH_ID} | GET | medium | platform-ops | PostgreSQL app.import_batches + app.import_files + app.file_objects metadata only | NO_GO | 1 |
| /imports/batches/${IMPORT_BATCH_ID} | GET | medium | platform-ops | PostgreSQL app.import_batches + app.import_files + app.file_objects metadata only | NO_GO | 1 |
| /imports/files/${IMPORT_FILE_ID} | GET | medium | platform-ops | PostgreSQL app.import_files + app.file_objects metadata only | NO_GO | 1 |
| /imports/files/${IMPORT_FILE_ID} | GET | medium | platform-ops | PostgreSQL app.import_files + app.file_objects metadata only | NO_GO | 1 |
| /api/files/objects/${FILE_OBJECT_ID} | GET | medium | platform-ops | PostgreSQL app.file_objects metadata plus object-storage access provider for bounded presigned access metadata; no object content | NO_GO | 1 |
| /api/files/objects/${FILE_OBJECT_ID} | GET | medium | platform-ops | PostgreSQL app.file_objects metadata plus object-storage access provider for bounded presigned access metadata; no object content | NO_GO | 1 |
| /imports/files/upload-preflight | POST | medium | platform-ops | PostgreSQL app.file_objects checksum lookup + deterministic object-key planning; no object write | NO_GO | 1 |
| /imports/files/upload-preflight | POST | medium | platform-ops | PostgreSQL app.file_objects checksum lookup + deterministic object-key planning; no object write | NO_GO | 1 |
| /api/workbench | GET | high | finance-ops | PostgreSQL read_model.workbench_snapshots; no app Mongo, no request-path rebuild | NO_GO | 1 |
| /api/workbench | GET | high | finance-ops | PostgreSQL read_model.workbench_snapshots; no app Mongo, no request-path rebuild | NO_GO | 1 |
| /api/workbench/ignored | GET | high | finance-ops | PostgreSQL read_model.workbench_snapshots ignored_rows projection; no app Mongo | NO_GO | 1 |
| /api/workbench/ignored | GET | high | finance-ops | PostgreSQL read_model.workbench_snapshots ignored_rows projection; no app Mongo | NO_GO | 1 |
| /api/workbench/read-model/status | GET | high | finance-ops | PostgreSQL read_model.workbench_snapshots status only; no app Mongo | NO_GO | 1 |
| /api/workbench/read-model/status | GET | high | finance-ops | PostgreSQL read_model.workbench_snapshots status only; no app Mongo | NO_GO | 1 |
| /api/workbench/rows/${WORKBENCH_ROW_ID} | GET | high | finance-ops | PostgreSQL read_model.workbench_rows row payload; sensitive values sanitized | NO_GO | 1 |
| /api/workbench/rows/${WORKBENCH_ROW_ID} | GET | high | finance-ops | PostgreSQL read_model.workbench_rows row payload; sensitive values sanitized | NO_GO | 1 |
| /api/workbench/actions/confirm-link | POST | high | finance-ops | PostgreSQL transactional workbench write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/confirm-link | POST | high | finance-ops | PostgreSQL transactional workbench write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/confirm-link/preview | POST | high | finance-ops | PostgreSQL transactional workbench write preflight/command validation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/confirm-link/preview | POST | high | finance-ops | PostgreSQL transactional workbench write preflight/command validation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/cancel-link | POST | high | finance-ops | PostgreSQL transactional workbench write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/cancel-link | POST | high | finance-ops | PostgreSQL transactional workbench write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/withdraw-link/preview | POST | high | finance-ops | PostgreSQL transactional workbench write preflight/command validation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/withdraw-link/preview | POST | high | finance-ops | PostgreSQL transactional workbench write preflight/command validation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/withdraw-link | POST | high | finance-ops | PostgreSQL transactional workbench write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/withdraw-link | POST | high | finance-ops | PostgreSQL transactional workbench write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/mark-exception | POST | high | finance-ops | PostgreSQL transactional exception write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/mark-exception | POST | high | finance-ops | PostgreSQL transactional exception write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/update-bank-exception | POST | high | finance-ops | PostgreSQL transactional exception write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/update-bank-exception | POST | high | finance-ops | PostgreSQL transactional exception write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/oa-bank-exception | POST | high | finance-ops | PostgreSQL transactional exception write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/oa-bank-exception | POST | high | finance-ops | PostgreSQL transactional exception write command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/confirm-personal-advance-repayment | POST | high | finance-ops | PostgreSQL transactional special reconciliation command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/confirm-personal-advance-repayment | POST | high | finance-ops | PostgreSQL transactional special reconciliation command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/confirm-cash-pass-through | POST | high | finance-ops | PostgreSQL transactional special reconciliation command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/confirm-cash-pass-through | POST | high | finance-ops | PostgreSQL transactional special reconciliation command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/confirm-cash-ticket-purchase | POST | high | finance-ops | PostgreSQL transactional special reconciliation command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/confirm-cash-ticket-purchase | POST | high | finance-ops | PostgreSQL transactional special reconciliation command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/cancel-cash-special | POST | high | finance-ops | PostgreSQL transactional special reconciliation command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/cancel-cash-special | POST | high | finance-ops | PostgreSQL transactional special reconciliation command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/exception/apply | POST | high | finance-ops | PostgreSQL transactional exception application command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/exception/apply | POST | high | finance-ops | PostgreSQL transactional exception application command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/cancel-exception | POST | high | finance-ops | PostgreSQL transactional exception cancel command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/cancel-exception | POST | high | finance-ops | PostgreSQL transactional exception cancel command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/ignore-row | POST | high | finance-ops | PostgreSQL transactional workbench override command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/ignore-row | POST | high | finance-ops | PostgreSQL transactional workbench override command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/unignore-row | POST | high | finance-ops | PostgreSQL transactional workbench override command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/actions/unignore-row | POST | high | finance-ops | PostgreSQL transactional workbench override command + job/outbox read-model invalidation; isolated fixture data only | NO_GO | 1 |
| /api/workbench/settings | GET | high | platform-ops | Axum static PostgreSQL/read-model cutover-safe settings projection; no app Mongo, no project sync, no mutation | NO_GO | 1 |
| /api/workbench/settings | GET | high | platform-ops | Axum static PostgreSQL/read-model cutover-safe settings projection; no app Mongo, no project sync, no mutation | NO_GO | 1 |
| /api/workbench/settings/data-reset/jobs/active | GET | high | platform-ops | PostgreSQL job.worker_tasks filtered to task_type=settings_data_reset active system jobs | NO_GO | 1 |
| /api/workbench/settings/data-reset/jobs/active | GET | high | platform-ops | PostgreSQL job.worker_tasks filtered to task_type=settings_data_reset active system jobs | NO_GO | 1 |
| /api/workbench/settings/data-reset/jobs/${DATA_RESET_JOB_ID} | GET | high | platform-ops | PostgreSQL job.worker_tasks filtered to task_type=settings_data_reset | NO_GO | 1 |
| /api/workbench/settings/data-reset/jobs/${DATA_RESET_JOB_ID} | GET | high | platform-ops | PostgreSQL job.worker_tasks filtered to task_type=settings_data_reset | NO_GO | 1 |
| /api/oa-sync/status | GET | medium | platform-ops | PostgreSQL app.oa_sync_runs + app.oa_sync_watermarks | NO_GO | 1 |
| /api/oa-sync/status | GET | medium | platform-ops | PostgreSQL app.oa_sync_runs + app.oa_sync_watermarks | NO_GO | 1 |
| /api/background-jobs/${BACKGROUND_JOB_ID}/retry | POST | medium | platform-ops | PostgreSQL job.worker_tasks, job.outbox_events, audit.events and app.write_idempotency_records; request creates retry task only | NO_GO | 1 |
| /api/background-jobs/${BACKGROUND_JOB_ID}/retry | POST | medium | platform-ops | PostgreSQL job.worker_tasks, job.outbox_events, audit.events and app.write_idempotency_records; request creates retry task only | NO_GO | 1 |
| /imports/files/retry | POST | high | platform-ops | PostgreSQL app.import_files metadata plus job.worker_tasks/job.outbox_events/audit/idempotency request record; request creates parse retry task only | NO_GO | 1 |
| /imports/files/retry | POST | high | platform-ops | PostgreSQL app.import_files metadata plus job.worker_tasks/job.outbox_events/audit/idempotency request record; request creates parse retry task only | NO_GO | 1 |
| /imports/files/sessions/${IMPORT_SESSION_ID} | GET | high | platform-ops | PostgreSQL app.import_batches legacy_session_id projection joined to app.import_files | NO_GO | 1 |
| /imports/files/sessions/${IMPORT_SESSION_ID} | GET | high | platform-ops | PostgreSQL app.import_batches legacy_session_id projection joined to app.import_files | NO_GO | 1 |
| /matching/run | POST | high | platform-ops | PostgreSQL job.worker_tasks, job.outbox_events, audit.events and app.write_idempotency_records; request queues workbench matching only | NO_GO | 1 |
| /matching/run | POST | high | platform-ops | PostgreSQL job.worker_tasks, job.outbox_events, audit.events and app.write_idempotency_records; request queues workbench matching only | NO_GO | 1 |
| /matching/results | GET | high | platform-ops | PostgreSQL read_model.workbench_candidate_matches | NO_GO | 1 |
| /matching/results | GET | high | platform-ops | PostgreSQL read_model.workbench_candidate_matches | NO_GO | 1 |
| /matching/results/${MATCHING_RESULT_ID} | GET | high | platform-ops | PostgreSQL read_model.workbench_candidate_matches | NO_GO | 1 |
| /matching/results/${MATCHING_RESULT_ID} | GET | high | platform-ops | PostgreSQL read_model.workbench_candidate_matches | NO_GO | 1 |

## Diff Details

| Endpoint | Case | Kind | Path | Python | Axum |
| --- | --- | --- | --- | --- | --- |
| /api/app-health | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/app-health | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/app-health/stream | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/app-health/stream | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/app-metadata | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/session/me | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/session/me | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/search | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/search | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/tasks/${WORKER_TASK_ID}/status | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/tasks/${WORKER_TASK_ID}/status | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/bank-details/accounts | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/bank-details/accounts | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/bank-details/transactions | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/bank-details/transactions | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/bank-details/transactions/categories | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/bank-details/transactions/categories | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/turnover-ledger | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/turnover-ledger | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/turnover-ledger | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/turnover-ledger | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/turnover-ledger/export-preview | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/turnover-ledger/export-preview | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/turnover-ledger/relations/${TURNOVER_RELATION_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/turnover-ledger/relations/${TURNOVER_RELATION_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches/${NO_OA_BATCH_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches/${NO_OA_BATCH_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches/${NO_OA_SUBMIT_BATCH_ID}/submit | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches/${NO_OA_SUBMIT_BATCH_ID}/submit | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches/${NO_OA_WITHDRAW_BATCH_ID}/withdraw | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches/${NO_OA_WITHDRAW_BATCH_ID}/withdraw | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches/submit | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/no-oa-bank-batches/submit | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/tax-offset | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/tax-offset | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/tax-offset/certified-imports | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/tax-offset/certified-imports | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/tax-offset/calculate | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/tax-offset/calculate | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/etc/import | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/etc/import | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/etc/invoices | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/etc/invoices | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/etc/batches | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/etc/batches | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/etc/batches/${ETC_BATCH_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/etc/batches/${ETC_BATCH_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/explorer | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/explorer | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/projects/${COST_PROJECT_NAME_PATH} | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/projects/${COST_PROJECT_NAME_PATH} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/transactions/${COST_TRANSACTION_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/transactions/${COST_TRANSACTION_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/export-preview | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/export-preview | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/export-preview | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/export-preview | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/export-preview | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/cost-statistics/export-preview | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/background-jobs/active | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/background-jobs/active | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/background-jobs/${BACKGROUND_JOB_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/background-jobs/${BACKGROUND_JOB_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /imports/templates | primary | `expected_status` | `$.status` | `null` | `null` |
| /imports/templates | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /imports/batches | primary | `expected_status` | `$.status` | `null` | `null` |
| /imports/batches | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /imports/batches/${IMPORT_BATCH_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /imports/batches/${IMPORT_BATCH_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /imports/files/${IMPORT_FILE_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /imports/files/${IMPORT_FILE_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/files/objects/${FILE_OBJECT_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/files/objects/${FILE_OBJECT_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /imports/files/upload-preflight | primary | `expected_status` | `$.status` | `null` | `null` |
| /imports/files/upload-preflight | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/ignored | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/ignored | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/read-model/status | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/read-model/status | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/rows/${WORKBENCH_ROW_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/rows/${WORKBENCH_ROW_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-link | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-link | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-link/preview | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-link/preview | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/cancel-link | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/cancel-link | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/withdraw-link/preview | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/withdraw-link/preview | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/withdraw-link | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/withdraw-link | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/mark-exception | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/mark-exception | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/update-bank-exception | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/update-bank-exception | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/oa-bank-exception | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/oa-bank-exception | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-personal-advance-repayment | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-personal-advance-repayment | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-cash-pass-through | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-cash-pass-through | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-cash-ticket-purchase | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/confirm-cash-ticket-purchase | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/cancel-cash-special | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/cancel-cash-special | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/exception/apply | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/exception/apply | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/cancel-exception | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/cancel-exception | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/ignore-row | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/ignore-row | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/unignore-row | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/actions/unignore-row | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/settings | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/settings | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/settings/data-reset/jobs/active | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/settings/data-reset/jobs/active | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/settings/data-reset/jobs/${DATA_RESET_JOB_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/workbench/settings/data-reset/jobs/${DATA_RESET_JOB_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/oa-sync/status | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/oa-sync/status | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /api/background-jobs/${BACKGROUND_JOB_ID}/retry | primary | `expected_status` | `$.status` | `null` | `null` |
| /api/background-jobs/${BACKGROUND_JOB_ID}/retry | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /imports/files/retry | primary | `expected_status` | `$.status` | `null` | `null` |
| /imports/files/retry | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /imports/files/sessions/${IMPORT_SESSION_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /imports/files/sessions/${IMPORT_SESSION_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /matching/run | primary | `expected_status` | `$.status` | `null` | `null` |
| /matching/run | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /matching/results | primary | `expected_status` | `$.status` | `null` | `null` |
| /matching/results | permission_failure | `expected_status` | `$.status` | `null` | `null` |
| /matching/results/${MATCHING_RESULT_ID} | primary | `expected_status` | `$.status` | `null` | `null` |
| /matching/results/${MATCHING_RESULT_ID} | permission_failure | `expected_status` | `$.status` | `null` | `null` |

Any endpoint with an unexplained status, field, ordering, money-format, date-format, or value diff keeps the overall gate at `NO_GO`.
