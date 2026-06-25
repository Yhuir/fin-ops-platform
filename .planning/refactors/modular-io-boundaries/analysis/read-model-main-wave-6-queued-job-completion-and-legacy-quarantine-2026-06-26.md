# Read Model Main Closure Wave 6 - queued job completion targets

Date: 2026-06-26

## Boundary

`main-read-model-closure:wave-6-queued-job-completion-and-legacy-quarantine`

This wave closed the queued import job completion target propagation gap for currently consumed frontend job completion paths.

## Codebase analysis before implementation

- File import queued jobs already wrote `affected_scope_keys`, `read_model_scope_keys`, `freshness_targets`, and `operation_barrier_targets` into `BackgroundJob.result_summary` after `execute_file_import_confirm_job(...)` knew the confirmed files and affected scopes.
- The frontend background job mapper only exposed raw `resultSummary`; consumers had no typed `operationBarrierTargets`, so completed job consumers could refresh pages without waiting for affected read models.
- `EtcTicketManagementPage` consumes completed `etc_invoice_import` background jobs and refreshes batch/task lists, but it did not wait for read model freshness.
- ETC import queued jobs only wrote import counters into `result_summary`; they did not expose affected months or read model targets after changed months became knowable.
- No safe legacy route deletion was proven in this wave. The active gap was queued completion target propagation, not a dead compatibility path.

## Implementation

- Added ETC import job completion target envelope after changed months are known:
  - `affected_months`
  - `affected_scope_keys`
  - `read_model_scope_keys`
  - `freshness_targets`
  - `operation_barrier_targets`
- Standardized frontend `BackgroundJob` mapping from `result_summary`:
  - `affectedScopeKeys`
  - `readModelScopeKeys`
  - `operationBarrierTargets`
  - `affectedMonths` fallback from result summary
- Updated `EtcTicketManagementPage` completed import job consumer to wait for operation barrier targets before emitting domain updates and refreshing batch/task lists.
- Added backend and frontend tests for ETC job result targets, background job mapper targets, and ETC page wait-before-refresh behavior.
- Updated module docs for read models, runtime workers/background jobs, bank/invoice/ETC imports, and ETC tickets.

## Legacy deletion / quarantine judgment

- No old code was removed in this wave because the touched paths are active production paths:
  - `file_import` background job result propagation,
  - `etc_invoice_import` background job result propagation,
  - `EtcTicketManagementPage` completed job consumption.
- Existing legacy route surfaces remain for a dedicated deletion/quarantine sweep.

## Verification performed

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/import_processing_service.py
PYTHONPATH=backend/src python3 -m pytest -q tests/test_import_processing_service.py
npm test -- --run src/test/BackgroundJobProgress.test.tsx src/test/EtcTicketManagementPage.test.tsx src/test/EtcApi.test.ts
```

## Remaining work

- Run the broad read model/runtime/docs/frontend verification gates before committing this wave.
- Perform a legacy deletion/quarantine sweep for `routes_legacy_workbench_actions.py`, `routes_etc_legacy_batches.py`, live-scan fallback and compat repository methods.
- Prepare production evidence after local PSCIP-L3 gates pass. Production validation actions must use business logic first; sample restoration uses business inverse when available, otherwise the preapproved bounded DB restore protocol.

## Closure status

- Queued import job completion target propagation: local PSCIP-L3 closed for the currently consumed file/ETC import job completion paths.
- Global all-page PSCIP-L4: not claimed.
