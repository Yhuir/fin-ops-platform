# Workbench Relations WorkbenchWriteFacade Required Port Constructor

**Date:** 2026-06-24
**Boundary:** `workbench-relations:workbench-write-facade-required-port-constructor`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove broad `pair_relation_service` from `WorkbenchWriteFacade.__init__` and require explicit relation read/snapshot and special metadata mutation ports, so WorkbenchWriteFacade cannot be instantiated without declaring its relation IO boundaries.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-post-port-local-implementation-closure-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-cash-special-metadata-port-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_auth_context_idempotency.py`
- `tests/test_platform_runtime_boundary_guards.py`
- Text search for `WorkbenchWriteFacade(`, `pair_relation_service=`, `relation_read_snapshot_port=`, `relation_special_metadata_mutation_port=`, and `_pair_relation_service`.

## Changes

- Removed `pair_relation_service` from `WorkbenchWriteFacade.__init__`.
- Made `relation_read_snapshot_port` and `relation_special_metadata_mutation_port` required constructor dependencies.
- Kept `WorkbenchWriteRelationReadSnapshotPort` and `WorkbenchWriteRelationSpecialMetadataMutationPort` as the only adapters in `workbench_write_facade.py` that hold pair relation service.
- Updated `Application._workbench_write_facade(...)` to pass only explicit ports into the facade.
- Updated `tests/test_workbench_auth_context_idempotency.py::_new_facade(...)` to construct and pass explicit ports.
- Strengthened the static guard so `WorkbenchWriteFacade` cannot re-accept broad `pair_relation_service`.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `WorkbenchWriteFacade.__init__(pair_relation_service=...)` | removed | Constructor no longer accepts broad pair service. |
| Production factory `Application._workbench_write_facade(...)` | explicit port wiring | Factory injects both relation ports. |
| Test helper `_new_facade(...)` | explicit port wiring | Helper constructs the pair service only to build the two ports. |
| Pair service references inside port adapter classes | explicit adapter boundary | Remaining references are confined to `WorkbenchWriteRelationReadSnapshotPort` and `WorkbenchWriteRelationSpecialMetadataMutationPort`. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice updates progress/accounting only. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Not applicable | No business rule, amount rule, relation mode, state transition, permission or idempotency behavior changed. |
| Service-layer tests | Applicable | Ran Workbench auth/context/idempotency tests and full Workbench write characterization. |
| API contract tests | Regression-applicable | Workbench auth/context/idempotency and write characterization exercise route-level behavior and response contracts. |
| Read model/cache/background job tests | Regression-applicable | Full Workbench write characterization covers affected scope scheduling and scheduling failure behavior. |
| Frontend component and interaction tests | Not applicable | No frontend code or UI behavior changed. |
| End-to-end business-flow integration tests | Not added | Constructor dependency cleanup does not change cross-page behavior. |
| Existing feature regression tests | Applicable | Static guard, auth/context/idempotency and Workbench write characterization protect existing behavior. |

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py tests/test_workbench_auth_context_idempotency.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_facade_relation_reads_and_cash_special_mutations_use_ports -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the WorkbenchWriteFacade required-port constructor cleanup. It does not close `workbench_relation`, does not migrate the ports to native command-service special metadata commands, does not validate production PostgreSQL/worker evidence, and does not unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:post-workbench-write-facade-local-implementation-closure-audit`
