# Workbench Relations Workbench Matching Relation Read Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:workbench-matching-relation-read-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove broad `WorkbenchPairRelationService` constructor/storage dependencies from Workbench matching and reconciliation engine read paths by introducing an explicit matching relation read port for canonical active relation reads.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-matching-pair-service-boundary-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`
- `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_matching_orchestrator.py`
- `tests/test_workbench_reconciliation_engine.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for `WorkbenchMatchingOrchestrator`, `WorkbenchReconciliationEngine`, and `WorkbenchMatchingRelationReadPort`.
- Text search for `pair_relation_service`, `_pair_relation_service`, `list_active_relations`, and `active_relations_for_row_ids`.

## Changes

- Added `WorkbenchMatchingRelationReadPort`.
- Moved matching/orchestrator active relation reads behind the port:
  - `list_active_relations()`
  - `active_relations_for_row_ids(...)`
- `WorkbenchMatchingOrchestrator` now accepts `relation_read_port` and no longer accepts or stores broad `pair_relation_service`.
- `WorkbenchReconciliationEngine` now accepts `relation_read_port` and no longer accepts or stores broad `pair_relation_service`.
- `Application` wires the matching read port with an existing `WorkbenchRelationCommandService` reader using `require_fresh_relations=False`, preserving the previous canonical active relation read behavior.
- The port preserves fail-fast shape validation for non-dict active relation rows.
- Static guard coverage now prevents matching/orchestrator classes from re-accepting or storing broad pair relation service.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `WorkbenchMatchingOrchestrator(pair_relation_service=...)` | removed | Constructor now requires `relation_read_port`; guard forbids broad pair service in the class. |
| `WorkbenchReconciliationEngine(pair_relation_service=...)` | removed | Constructor now requires `relation_read_port`; guard forbids broad pair service in the class. |
| Matching held-row suppression via `list_active_relations()` | retained behind explicit port | Required to suppress rows already held by canonical active relations. |
| Auto-completion lookup via `active_relations_for_row_ids(...)` | retained behind explicit port | Required to upgrade exactly one two-pane relation through command service. |
| `server.py` direct relation read helpers | implementation gap | Text search still finds direct `_workbench_pair_relation_service` read helpers in `server.py`; these require a separate audit before implementation. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice closes one narrow implementation boundary only. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Applies | Existing matching and reconciliation tests cover held-row suppression, auto-completion, matching decisions and rule behavior after the dependency change. |
| Service-layer tests | Applies | `tests/test_workbench_matching_orchestrator.py` and `tests/test_workbench_reconciliation_engine.py` cover service behavior through the new port. |
| API contract tests | Not applicable | No HTTP/API contract, status code or response shape changed. |
| Read model/cache/background job tests | Applies indirectly | Existing orchestrator tests cover read model invalidation behavior; no dirty scope, queue, App Status or worker behavior changed. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not added for this narrow dependency slice | Matching business behavior is covered at service level; no cross-module API behavior changed. |
| Existing feature regression tests | Applies | Static guard and existing matching/reconciliation regression tests prevent broad pair service reintroduction and behavior drift. |

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py backend/src/fin_ops_platform/app/server.py tests/test_workbench_matching_orchestrator.py tests/test_workbench_reconciliation_engine.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_orchestrator tests.test_workbench_reconciliation_engine -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_matching_uses_relation_read_port_not_pair_service -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the matching/orchestrator relation read port extraction. It does not close `workbench_relation`, remove all `server.py` direct relation reads, validate production PostgreSQL/worker evidence, or unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:server-relation-read-helper-boundary-audit`
