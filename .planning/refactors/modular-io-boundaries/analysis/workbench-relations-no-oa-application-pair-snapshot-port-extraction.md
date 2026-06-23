# Workbench Relations No-OA Application Pair Snapshot Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:no-oa-application-pair-snapshot-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Extract `NoOaBankBatchApplicationService` pair relation snapshot, version, persistence payload and rollback restore usage behind an explicit collaborator, without changing no-OA submit, submit-selection, internal transfer, withdraw, API response, read model refresh or dirty scope semantics.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-pair-service-boundary-audit.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`
- `docs/modules/no-oa-bank-batches/tests.md`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_no_oa_bank_batch_application_service.py`
- `tests/test_no_oa_bank_batch_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for `NoOaBankBatchApplicationService`, `NoOaPairRelationSnapshotPort`, and pair relation service dependencies.

## Implementation

Added `NoOaPairRelationSnapshotPort` as the explicit boundary for no-OA application-level relation snapshot concerns:

- `snapshot()`
- `snapshot_case_ids(...)`
- `snapshot_version()`
- `snapshot_by_case_id(...)`
- `restore(...)`

`NoOaBankBatchApplicationService` now receives `pair_relation_snapshot_port` instead of broad `pair_relation_service`.

The application service now delegates these operations to the port:

- Previous relation snapshot capture before submit, submit-selection, internal transfer and withdraw.
- `pair_relation_snapshot_version` source-version accounting.
- `save_no_oa_bank_batch_mutation(...)` pair relation snapshot payload.
- Fallback `save_workbench_pair_relations(...)` snapshot payload.
- `pair_relation_snapshot_by_case_id(...)`.
- Rollback restore for `_restore_snapshots(...)`.

`Application` now wraps the existing `_workbench_pair_relation_service` with `NoOaPairRelationSnapshotPort` only when constructing `NoOaBankBatchApplicationService`.

`NoOaBankBatchService` still receives `pair_relation_service`. This is intentional: its `_repair_submitted_no_oa_relation_consistency(...)` and `_has_active_no_oa_relation(...)` usage remains in the later domain repair/read port boundary.

## Legacy Classification

| Surface | Result | Notes |
| --- | --- | --- |
| `NoOaBankBatchApplicationService.pair_relation_service` constructor dependency | removed | Application service no longer accepts or stores the broad pair service. |
| Application direct `_pair_relations` / `_pair_relation_history` restore | removed | Direct private-state restore moved behind `NoOaPairRelationSnapshotPort.restore(...)`. |
| Application relation writes | unchanged canonical path | Submit/withdraw/internal transfer still use `WorkbenchRelationCommandService`. |
| Application active relation reads | unchanged canonical path | Active row reads remain facade-backed. |
| `NoOaPairRelationSnapshotPort` | explicit legacy snapshot port | This port is the only place in this module allowed to adapt old pair service snapshot/restore internals. |
| `NoOaBankBatchService._pair_relation_service` | still open | Domain repair/read usage is not migrated in this slice. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`

No global or module state definition changes are required. This slice changes dependency ownership only. It does not alter legal relation modes, no-OA lifecycle states, read model freshness states, operation barrier semantics, or worker states.

`workbench_relation` remains `implementation-gap-open`. The next boundary is `workbench-relations:no-oa-domain-repair-read-port-audit`.

## Seven Test Categories

| Category | Applies? | Coverage |
| --- | --- | --- |
| Business core unit tests | Not directly. | Business status, amount and selection rules were not changed. Existing no-OA application tests still cover submit, withdraw, internal transfer and public lifecycle behavior. |
| Service-layer tests | Yes. | `tests.test_no_oa_bank_batch_application_service` covers service orchestration, mutation persistence snapshots, lifecycle enqueue and command-service relation writes. |
| API contract tests | Yes, targeted. | `NoOaBankBatchApiTests.test_submit_returns_error_and_rolls_back_when_no_oa_batch_persistence_fails` verifies rollback behavior through the HTTP boundary. |
| Read model/cache/background job tests | Partially. | Existing application tests cover durable queue enqueue boundary; no refresh semantics changed. |
| Frontend component and interaction tests | Not applicable. | No frontend code, UI state or API response shape changed. |
| End-to-end business-flow integration tests | Not newly added. | The API rollback test covers a critical submit persistence failure path; broader browser/E2E was not required for this dependency extraction. |
| Existing feature regression tests | Yes. | Static guards prove no-OA application service cannot re-accept broad pair service or directly restore private pair state; downstream read model guard still passes. |

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_api.NoOaBankBatchApiTests.test_submit_returns_error_and_rolls_back_when_no_oa_batch_persistence_fails -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_application_uses_pair_relation_snapshot_port tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_read_models_use_workbench_relation_distribution -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the no-OA application snapshot/persist/rollback extraction. It does not close `workbench_relation`, migrate no-OA domain repair/read pair service usage, classify ETC or WorkbenchWriteFacade relation dependencies, validate production PostgreSQL/worker evidence, or unblock Go admission.
