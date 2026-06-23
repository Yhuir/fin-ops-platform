# Workbench Relation Transaction Persist Repository Owner Split

**Date:** 2026-06-24
**Boundary:** `workbench-relations:transaction-persist-repository-owner-split`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Decision

Move transaction-bound relation persistence in `server.py` from the broad Workbench repository owner to the relation-specific PostgreSQL repository owner.

This closes only one SQL owner split boundary. It does not remove app-level relation snapshot/apply helpers or migrate the broader relation lifecycle.

## Runtime Change

`Application._persist_workbench_pair_relations_in_transaction(...)` now calls:

```python
PostgresWorkbenchRelationRepository(transaction).save_workbench_pair_relations(...)
```

instead of:

```python
PostgresWorkbenchRepository(transaction).save_workbench_pair_relations(...)
```

Preserved behavior:

- `transaction is required` fail-fast behavior.
- `self._search_service.clear_cache()`.
- snapshot selection via `snapshot_case_ids(...)` or full `snapshot()`.
- normalized `changed_case_ids` set semantics.
- relation repository transactional save/outbox/dirty-scope behavior.

## Legacy Path Classification

- Removed from this helper: broad `PostgresWorkbenchRepository(...).save_workbench_pair_relations(...)`.
- Retained as implementation-pending: app-level `_persist_workbench_pair_relations(...)`, `_schedule_workbench_pair_relation_persist(...)`, `_persist_workbench_pair_relations_in_background(...)`, command repository snapshot/apply helpers and WorkbenchWriteFacade relation callback wiring.
- Compat-only: none introduced.
- Blocked-by-human-gate: none.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/state-machine.md`

No state definition changes are needed. The existing `implementation-closed` slice status and `implementation-gap-open` module closure value are sufficient.

Next boundary:

`workbench-relations:command-repository-snapshot-adapter-audit`

That audit should decide whether to extract the Application-owned callback repository and snapshot merge/apply logic into an explicit adapter/port, or first split another smaller persist/schedule helper.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. No relation mode/status/amount/idempotency rules changed. |
| Service-layer tests | Applicable. `tests/test_workbench_relation_repository.py` verifies the relation-specific repository save/fan-out behavior. |
| API contract tests | Not directly applicable. No HTTP route or response shape changed. |
| Read model/cache/background job tests | Applicable. `tests/test_workbench_uow_contract.py` and `tests/test_workbench_write_characterization.py` protect transaction dirty/outbox and write rollback behavior. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this repository owner split. |
| Existing feature regression tests | Applicable. Workbench UoW/write characterization tests, app check and static guard protect existing relation write behavior. |

## Verification

Executed:

- `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py -q`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_transaction_pair_relation_persist_uses_relation_repository_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract tests.test_workbench_write_characterization -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`

Pending before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Completion Claim

This slice closes only the transaction persist repository owner split. `workbench_relation` remains implementation-gap-open; app-level command repository snapshot/apply helpers, pair relation persist/schedule/background helpers, production PostgreSQL/worker/App Status/high-row/browser evidence and Go admission remain open.
