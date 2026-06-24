# Read Model No-OA Bank Batch Repository State-Store Boundary Audit

**Date:** 2026-06-24
**Boundary:** `read-models:no-oa-bank-batch-repository-state-store-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`no_oa_bank_batch` was selected as the eleventh non-Go read model implementation pilot after `turnover_ledger` local support was accounted for. The selected reason was page-level stale-read risk: no-OA combines draft/submitted/withdrawn lifecycle, Bank Detail dependency, Workbench relation adjacency, public snapshot persistence, operation barrier requirements and cleanup of legacy exception states.

The previous selection slice also fixed one constructor compatibility break in `NoOaBankBatchReadModelRefreshService`: it now passes `pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(...)` to `NoOaBankBatchApplicationService`.

Go/Fiber/Go Worker admission remains blocked while this non-Go modular IO/read model boundary is still implementation-gap-open.

## Selected Boundary

Audit no-OA read model repository/state-store/public-snapshot/refresh-worker ownership before choosing the first implementation extraction.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-turnover-ledger.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-search-and-no-oa-bank-batch-contract.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`
- `docs/modules/no-oa-bank-batches/implementation-notes.md`
- `docs/modules/no-oa-bank-batches/tests.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- `tests/test_no_oa_bank_batch_read_model_refresh.py`
- `tests/test_no_oa_bank_batch_application_service.py`
- `tests/test_no_oa_bank_batch_workbench_integration.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph was used before selecting the next implementation slice. It identified `NoOaBankBatchReadModelRefreshService` as the no-OA worker entry point, the application service list/read owner, and the current refresh tests that prevent relation repair from the read model path.

## Current Boundary Classification

| Surface | Current classification | Evidence | Gap / decision |
| --- | --- | --- | --- |
| `read_model_manifest.py` entry | Explicit contract boundary | `no_oa_bank_batch` is registered with scope type `no_oa_bank_batch`, event `no_oa_bank_batch.read_model.refresh`, worker `no-oa-bank-batch`, `scoped_incremental`, `fan_out_command`, `gateway_force_refresh`, and operation barrier target. | Keep. No definition change. |
| `ReadModelScopePolicyRegistry` | Explicit scope boundary | `no_oa_bank_batch` uses month-or-all validation. | Keep. No definition change. |
| `runtime_worker_registry.py` | Explicit worker registration | Dedicated `no-oa-bank-batch` worker owns `no_oa_bank_batch.read_model.refresh`. | Keep. No definition change. |
| `NoOaBankBatchApiRoutes` | Explicit HTTP mapping boundary | Routes call `NoOaBankBatchApplicationService` and map service errors to HTTP status/payload. | Keep. It does not own SQL or read model persistence. |
| `NoOaBankBatchApplicationService.list_batches_payload(...)` | Current read/query owner, but still broad read repository injection | It calls `workbench_sql_read_repository.list_no_oa_bank_batch_rows(...)` when available, returns missing/stale/fresh/unavailable payloads and enqueues via gateway-backed callback. | A narrow `NoOaBankBatchReadModelRepositoryPort` is still needed later, but it is not the highest-risk first implementation because current manifest read port is list-only. |
| `NoOaBankBatchApplicationService.refresh_batches(...)` | Explicit application refresh orchestration | It reads target scope bank rows, effective categories, active relations and calls `NoOaBankBatchService.build_batches(...)`. Worker passes `apply_relation_repairs=False`. | Keep behavior. Do not change business rules in the persistence extraction slice. |
| `NoOaBankBatchReadModelRefreshService` | Implementation gap | The worker handler still constructs the full application service, keeps `_state_store`, calls `refresh_batches(...)`, pulls `public_snapshot()`, then calls `_state_store.save_no_oa_bank_batches(snapshot)`. | First implementation target. Refresh persistence should go through an explicit no-OA read model persistence boundary instead of direct broad state-store access. |
| `NoOaBankBatchService.public_snapshot()` | Explicit public lifecycle projection | Module docs/tests require only public `draft/submitted/withdrawn` lifecycle to be persisted; old `conflict/stale/superseded` rows absent from snapshot must be cleaned. | Keep as projection source. Persistence ownership should be separated from refresh handler. |
| `PostgresStateStore.load_no_oa_bank_batches(...)` | Compatibility/domain state façade | It loads through `PostgresWorkbenchRepository.load_no_oa_bank_batches()` and falls back to legacy snapshot. | Keep as startup/bootstrap compatibility. Not a new read model port. |
| `PostgresStateStore.save_no_oa_bank_batches(...)` | Broad state-store façade | It delegates to `PostgresWorkbenchRepository.save_no_oa_bank_batches(snapshot)` and also saves fallback snapshot. | Quarantine from worker refresh by inserting an explicit no-OA read model persistence port/adapter. |
| `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)` | SQL/table owner for no-OA batch persistence | It writes `app.no_oa_bank_batches`, `read_model.no_oa_bank_batch_rows`, deletes rows absent from public snapshot, and replaces audit events in one transaction. | Keep SQL ownership here for now. The next slice should wrap this capability, not duplicate SQL. |
| `PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)` | SQL read owner for list rows | It reads `read_model.no_oa_bank_batch_rows`, applies filters and returns `None` unless readiness proves fresh/empty. | Later repository-port extraction target. Do not prioritize ahead of refresh persistence boundary. |
| local/Mongo `StateStore.save_no_oa_bank_batches(...)` | compat-only local persistence | It writes local pickle or Mongo detailed no-OA collections. | Keep as local compatibility; future persistence port must preserve local tests. |
| `Application._enqueue_no_oa_bank_batch_read_model_refreshes(...)` and `_derived_lifecycle_no_oa_bank_batch_executor(...)` | Future app-owned helper gap | Enqueue uses `ReadModelRefreshGateway` and scope filtering; derived lifecycle helper still lives in `Application`. | Account as follow-up after refresh persistence/read repository port. It is not the first repository/state-store slice. |

## Decision

The next implementation slice should be:

`read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction`

Reasoning:

- A list-only `NoOaBankBatchReadModelRepositoryPort` would help read-side isolation, but it would leave the higher-risk worker write path unchanged.
- The current worker refresh handler still depends on broad `state_store` and directly persists `NoOaBankBatchService.public_snapshot()`.
- `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)` already owns the actual SQL cleanup/write contract, so the implementation should not duplicate SQL or change business persistence semantics.
- The safer first step is to add an explicit no-OA read model persistence boundary/adapter around `save_no_oa_bank_batches(...)`, inject it into `NoOaBankBatchReadModelRefreshService`, and add/extend guards proving the worker handler no longer calls broad state-store persistence directly or relation mutation paths.
- This keeps public snapshot semantics, month-scope merge behavior, stale source-version skip, queue completion and API shape unchanged.

Expected next-slice scope:

- Introduce a narrow no-OA refresh persistence port/adapter, naming to follow local patterns.
- Wire worker construction through the explicit persistence boundary.
- Remove direct `_state_store.save_no_oa_bank_batches(snapshot)` from `NoOaBankBatchReadModelRefreshService.handle_runtime_event(...)`.
- Preserve local/state-store compatibility by having the adapter delegate to the existing store capability.
- Add/extend tests in `tests/test_no_oa_bank_batch_read_model_refresh.py` and static boundary guard coverage.
- Do not change business rules, API response shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning, frontend behavior or Go/Fiber/Go Worker.

Follow-up boundaries after the persistence slice:

- `read-models:no-oa-bank-batch-read-model-repository-port-extraction` for `list_no_oa_bank_batch_rows`.
- no-OA refresh producer / derived lifecycle app helper extraction if the next audit still finds app-owned enqueue/lifecycle behavior.
- local closure audit before production evidence defer.

## Legacy / Pollution Classification

| Legacy or pollution risk | Current status | Required guard |
| --- | --- | --- |
| Worker refresh silently performs relation repair | Already guarded | Keep `apply_relation_repairs=False` and forbid relation write calls in handler. |
| Worker refresh writes via broad state-store | Implementation gap | Extract persistence boundary and guard against direct `save_no_oa_bank_batches` in handler. |
| GET list missing/stale sync rebuilds batches | Already guarded by service/tests | Keep list path returning missing/stale/unavailable plus refresh enqueue. |
| Old public snapshot exception rows remain in SQL read model | SQL write contract exists | Preserve `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)` cleanup semantics. |
| Search/no-OA read ports mixed | Manifest guard exists | Keep repository port contracts disjoint. |
| `Application` derived lifecycle helper owns no-OA enqueue result shape | Future gap | Audit after refresh persistence and read port extraction. |

## State Machine Impact

- `read-models:no-oa-bank-batch-repository-state-store-boundary-audit` transitions from `pending` to `analysis-closed`.
- Insert `read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction` as the next pending implementation boundary before blocked Go candidates.
- `no_oa_bank_batch` remains `implementation-gap-open`; this audit is not module closure.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `analysis-closed` semantics.
- `docs/modules/no-oa-bank-batches/state-machine.md` definitions do not change because no business state, UI state, worker state, queue transition, read model status, operation barrier state or force-refresh state changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No no-OA lifecycle, relation, amount, tag or status rule changed. |
| 2. Service-layer tests | Applicable next | Next slice must cover refresh persistence adapter and worker handler dependency boundary. |
| 3. API contract tests | Not applicable for audit | No HTTP status or response shape changed. If read/list shape changes later, no-OA API tests become required. |
| 4. Read model/cache/background job tests | Applicable next | Next slice must cover refresh worker persistence, stale source-version skip, month scope preservation and queue completion. |
| 5. Frontend component and interaction tests | Not applicable for audit | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for audit | No submit/withdraw/import/worker runtime flow changed. |
| 7. Existing feature regression tests | Applicable next | Next slice must keep existing no-OA refresh and application service regressions passing. |

## Verification

This slice is analysis/accounting only. Required verification:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_workbench_integration -v
bash scripts/verify.sh docs
git diff --check
```

## Next Boundary

`read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction`
