# Read Model No-OA Bank Batch Read Model Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:no-oa-bank-batch-read-model-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction` moved the worker refresh write path behind `NoOaBankBatchReadModelPersistencePort`, but the no-OA list/query path still read `list_no_oa_bank_batch_rows(...)` from broad `workbench_sql_read_repository` inside `NoOaBankBatchApplicationService`.

That meant the public page read path had the correct freshness behavior locally, but the dependency boundary still pointed at a shared Workbench-shaped repository surface.

## Selected Boundary

Extract a narrow no-OA read model repository port for manifest-listed `list_no_oa_bank_batch_rows(...)` and wire list/query consumers through it without changing API shape, business rules, freshness semantics, queue schema, worker event names, Redis/cache behavior, permissions, audit meaning or frontend behavior.

## Implementation

- Added `NoOaBankBatchReadModelRepositoryPort` in `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_repository.py`.
- The port exposes only `list_no_oa_bank_batch_rows(filters)` and delegates to the existing SQL owner.
- `NoOaBankBatchApplicationService` now accepts `no_oa_bank_batch_read_model_repository`.
- `list_batches_payload(...)` now reads through `_no_oa_bank_batch_read_model_repository` instead of `_workbench_sql_read_repository`.
- The previous `workbench_sql_read_repository` constructor parameter remains as a compatibility adapter path only; it is wrapped in the no-OA port when the new port is absent.
- `PostgresStateStore` now creates and exposes `no_oa_bank_batch_sql_read_repository`.
- `Application` now wires `NoOaBankBatchApplicationService` with `_no_oa_bank_batch_sql_read_repository`.
- `READ_MODEL_MANIFEST["no_oa_bank_batch"].repository_owner` is updated to `NoOaBankBatchReadModelRepositoryPort`.

## Preserved Behavior

- `PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)` remains the SQL/table owner; SQL was not duplicated.
- List payload shape is unchanged.
- Missing SQL read model still returns `read_model_status=missing`, empty payload and refresh enqueue.
- Stale source versions still return visible rows with `read_model_status=stale`, stale reasons and refresh enqueue.
- Fresh rows still return `read_model_status=fresh`.
- Pagination, summary calculation and public lifecycle filtering remain unchanged.
- API route, permission behavior, audit meaning, worker event names, queue schema, Redis/cache behavior and frontend behavior are unchanged.

## Legacy Path Classification

- Old direct list dependency on `_workbench_sql_read_repository` is removed from `list_batches_payload(...)`.
- `workbench_sql_read_repository` remains a constructor compatibility input only for existing local construction paths; it is immediately wrapped in `NoOaBankBatchReadModelRepositoryPort` and does not remain the read path owner.
- Broad `PostgresReadModelRepository` remains a transitional SQL owner for the actual query method, consistent with current read model repository split rules.

## Tests Added Or Updated

- `tests/test_no_oa_bank_batch_application_service.py`
  - Added `test_read_model_repository_port_excludes_unrelated_methods`.
  - Updated SQL read model tests to inject `no_oa_bank_batch_read_model_repository`.
- `tests/test_no_oa_bank_batch_workbench_integration.py`
  - Updated route-level stale/missing tests to inject `_no_oa_bank_batch_sql_read_repository`.
- `tests/test_read_model_manifest.py`
  - Added manifest owner assertion for `NoOaBankBatchReadModelRepositoryPort`.
- `tests/test_platform_runtime_boundary_guards.py`
  - Added `test_no_oa_list_read_model_uses_repository_port`.

## State Machine Impact

- `read-models:no-oa-bank-batch-read-model-repository-port-extraction` transitions to `implementation-closed`.
- `no_oa_bank_batch` remains `implementation-gap-open`; this is not module closure.
- Next boundary is `read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit`.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `implementation-closed` semantics.
- `docs/modules/no-oa-bank-batches/state-machine.md` definitions do not change because no business state, UI state, read model status, worker event, queue transition, operation barrier state or force-refresh state changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No lifecycle, relation, amount, tag, permission or status rule changed. |
| 2. Service-layer tests | Applicable and covered | Application service tests cover repository port injection and list payload behavior through the existing no-OA service test matrix. |
| 3. API contract tests | Not directly applicable | HTTP response shape and status codes are unchanged; route-level integration tests cover stale/missing list responses. |
| 4. Read model/cache/background job tests | Applicable and covered | no-OA Workbench integration tests cover stale/missing/fresh SQL read model behavior; manifest and static guard tests cover repository port ownership. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior, operation barrier target or UI state changed. |
| 6. End-to-end business-flow integration tests | Not directly applicable | No submit/withdraw/import/user flow changed; no-OA Workbench integration regressions were run. |
| 7. Existing feature regression tests | Applicable and covered | no-OA application service, Workbench integration and manifest regressions were run. |

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_repository.py backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_workbench_integration tests.test_read_model_manifest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_list_read_model_uses_repository_port -v
```

Passed:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Next Boundary

`read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit`
