---
status: resolved
trigger: "Uploaded several invoice files successfully, but reconciliation workbench remains refreshing/syncing for more than ten minutes."
created: 2026-06-18
updated: 2026-06-19
---

# Debug Session: invoice-upload-workbench-sync

## Symptoms

- Expected behavior: after invoice import succeeds, reconciliation workbench read models finish refresh and the UI stops showing "同步中/关联台刷新中".
- Actual behavior: the workbench stays in refreshing/syncing state for more than ten minutes.
- Error messages: no explicit UI error shown in screenshots; status popover shows multiple data domains still "同步".
- Timeline: observed after uploading several invoice files on 2026-06-18 around 23:38 Asia/Shanghai.
- Reproduction: import invoice files, then open reconciliation workbench and app health/status popover.

## Current Focus

- hypothesis: production import worker is running in RabbitMQ mode and does not claim `import.fact.changed`, leaving import dirty scopes pending and keeping App Status / workbench-related domains in syncing state.
- test: inspect read model status docs, worker/queue runtime state, import worker registration, and current durable queue tables.
- expecting: `import.fact.changed` events remain pending while `workbench.read_model.refresh` events can still complete.
- next_action: decide whether to apply a code/config fix and then drain/reprocess the pending import fact events through the supported worker path.

## Evidence

- 2026-06-18 23:41 Asia/Shanghai: production `fin-ops.service` active; all required worker units including `fin-ops-worker@import.service`, `fin-ops-worker@workbench.service`, and `fin-ops-worker@workbench-relation.service` active; `/health/ready` returned `status=ready`, release consistent, blocker count 0.
- 2026-06-18 23:42 Asia/Shanghai: PostgreSQL durable queue had long-lived non-done runtime facts from 2026-06-18 17:49. `job.outbox_events` included pending `import.fact.changed` events for `workbench`, `workbench_relation`, `invoice_lifecycle`, `pending_invoice`, `bank_detail`, `tax_offset`, `cost_statistics`, and other import fan-out domains.
- 2026-06-18 23:42 Asia/Shanghai: `workbench.read_model.refresh` events created around 23:40-23:41 completed by 23:42, so the workbench read-model worker itself was not globally stopped.
- 2026-06-18 23:44 Asia/Shanghai: `import.fact.changed` pending count was 98 total, 7 each for 14 scope types; `workbench` and `workbench_relation` each had pending `global` plus `2026-01` through `2026-06` import fact events. `job.read_model_dirty_scopes` had 86 pending rows, including `workbench/global` and `workbench_relation/global`.
- 2026-06-18 23:44 Asia/Shanghai: production import worker check showed `FIN_OPS_QUEUE_BACKEND=rabbitmq`, `event_types=["import.process.requested"]`, handlers included both `import.process.requested` and `import.fact.changed`, registration `postgres_claim_event_types=["import.process.requested","import.fact.changed"]`, and `rabbitmq_claim_event_types=["import.process.requested"]`.
- Code evidence: `RuntimeWorkerRegistration.claim_event_types(...)` only returns `postgres_claim_event_types` when transport is `postgres`; otherwise it returns `event_types`. `_apply_registration_args(...)` selects `transport="rabbitmq"` when queue backend is RabbitMQ. The import registration puts `import.fact.changed` only in `postgres_claim_event_types`, not in `event_types`, so RabbitMQ-mode import worker does not claim it even though a handler exists.
- 2026-06-19 00:01 Asia/Shanghai: current production state still had `import.fact.changed` pending count 98 and dirty scope pending count 86; `workbench/global` and `workbench_relation/global` remained pending. Latest workbench refresh rows were still done, last observed at 2026-06-18 23:42:23.

## Eliminated

- Worker process not running: eliminated. Production service and required worker units were active.
- Workbench worker globally unable to rebuild: eliminated. Recent `workbench.read_model.refresh` rows completed successfully.
- Browser-only stale UI: unlikely. PostgreSQL durable queue/readiness facts show current pending runtime state.

## Resolution

- root_cause: `import.fact.changed` events are persisted to PostgreSQL after import fan-out, but production import worker is in RabbitMQ mode and only claims `import.process.requested`; therefore `import.fact.changed` acknowledgements and associated dirty-scope completion do not drain, leaving App Status/workbench-related domains in syncing state.
- fix:
  - `runtime_worker_registry.py`: import worker now claims `import.process.requested` and `import.fact.changed` in all transports.
  - `app/worker.py`: direct `--enable-import-job-processing` check/runtime path also appends `import.fact.changed` regardless of queue backend.
  - RabbitMQ dispatcher env example now includes `import.fact.changed`; production `/etc/fin-ops/fin-ops.rabbitmq-dispatcher.env` was backed up and updated with the same event.
  - Production RabbitMQ topology was applied so queue `finops.import.fact.changed` exists, then dispatcher/import worker were restarted.
  - Reconciliation workbench page no longer renders the inline stale/refreshing banner; status belongs in App Status.
  - App Status task labels infer invoice/ETC/bank import object and display progress such as `正在导入发票 210/500`.
- verification:
  - Local backend target tests passed: `tests.test_runtime_worker_registry`, `tests.test_import_job_queue`, `tests.test_rabbitmq_runtime`, `tests.test_app_status_overview_service`.
  - Local frontend target tests passed: `AppStatusIndicator.test.tsx`, `WorkbenchSelection.test.tsx`.
  - `npm run build`, `bash scripts/verify.sh docs`, and `git diff --check` passed.
  - Production release `main-6956b8e2-20260619002659` deployed successfully.
  - Production import worker check now reports `event_types=["import.process.requested","import.fact.changed"]`, RabbitMQ routes include `import.fact.changed`, and runtime transport is `rabbitmq`.
  - Production `import.fact.changed` backlog drained to done.
  - The 2026-06-18 17:49 import was cleaned for re-import validation: 391 linked invoices inspected; 175 newly-created invoices soft-deleted; 216 pre-existing invoices preserved; target import source links remaining = 0.
- files_changed:
  - `backend/src/fin_ops_platform/app/worker.py`
  - `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
  - `deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example`
  - `web/src/components/shell/AppStatusIndicator.tsx`
  - `web/src/pages/ReconciliationWorkbenchPage.tsx`
  - `web/src/app/styles.css`
  - targeted backend/frontend tests
  - module implementation notes
