# Workbench Relations Turnover Workbench Pair Port Required Command Constructor

**Date:** 2026-06-24
**Boundary:** `workbench-relations:turnover-workbench-pair-port-required-command-constructor`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove broad `pair_relation_service` from `TurnoverLedgerWorkbenchPairPort` construction while preserving turnover command-service writes, relation facade reads, and local rollback snapshot behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-workbench-write-facade-local-implementation-closure-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for the turnover Workbench pair port boundary.
- Text search for `TurnoverLedgerWorkbenchPairPort`, `pair_relation_service`, `_pair_relation_service`, and turnover builder/fallback construction.

## Changes

- Removed `pair_relation_service` from `TurnoverLedgerWorkbenchPairPort.__init__`.
- Removed the port's `_pair_relation_service` field.
- Removed the port's pair-service fallback active relation reader.
- Kept `TurnoverLedgerWorkbenchPairPort` dependent only on:
  - `relation_command_service_factory`
  - `relation_facade`
- Updated primary turnover confirm/withdraw builders so they no longer pass broad pair service into `TurnoverLedgerWorkbenchPairPort`.
- Updated turnover legacy fallback facades so they no longer accept or pass broad pair service into the port.
- Preserved builder-level `pair_relation_service` for `TurnoverLedgerLocalClosureConnection`, where it still snapshots and restores local pair relation state for rollback.
- Strengthened the static guard so `TurnoverLedgerWorkbenchPairPort` cannot re-accept/store pair service or reintroduce the removed fallback reader.
- Removed now-dead `BlockingPairService` fakes from turnover UoW tests; the constructor itself now enforces that broad pair service cannot be passed.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `TurnoverLedgerWorkbenchPairPort(pair_relation_service=...)` | removed | Constructor no longer accepts broad pair service. |
| Port `_pair_relation_service` read fallback | removed | `assert_turnover_manual_closure_withdrawable(...)` now uses relation facade only when available and otherwise does not inspect pair service. |
| Turnover primary builder pair service for port construction | removed | Builders construct `TurnoverLedgerWorkbenchPairPort` with command factory/facade only. |
| Turnover legacy fallback facade pair service for port construction | removed | Fallback facades no longer accept or pass broad pair service. |
| `TurnoverLedgerLocalClosureConnection(pair_relation_service=...)` | retained for later classification | It is a local transaction snapshot/rollback boundary, not the Workbench pair port constructor surface closed by this slice. |

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
| Business core unit tests | Regression-applicable | Turnover amount/mode/state rules were not changed; existing turnover UoW tests covering merge/conflict/withdraw behavior were run. |
| Service-layer tests | Applicable | Updated and ran turnover UoW contract tests for `TurnoverLedgerWorkbenchPairPort`. |
| API contract tests | Regression-applicable | `python3 -m fin_ops_platform.app.main --check` verified app construction and route wiring; no API response shape changed. |
| Read model/cache/background job tests | Regression-applicable | No dirty scope/outbox behavior changed; turnover UoW tests preserve command-service write path and existing read-model behavior. |
| Frontend component and interaction tests | Not applicable | No frontend code or UI behavior changed. |
| End-to-end business-flow integration tests | Not added | Constructor dependency cleanup does not change cross-page behavior; existing turnover/workbench integration remains the broader regression surface. |
| Existing feature regression tests | Applicable | Static guard and turnover UoW contract tests protect against reintroducing broad pair service or direct pair fallback. |

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_uow_contract.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_manual_closure_merges_existing_oa_bank_relations tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_manual_closure_rejects_rows_already_in_turnover_closure tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_withdraw_restores_merged_oa_bank_relations tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure_withdraw tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_cash_closure_withdraw_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_cash_closure_withdraw -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

Pending before commit:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the turnover Workbench pair port required-command constructor cleanup. It does not remove local rollback snapshot pair service usage, close `workbench_relation`, validate production PostgreSQL/worker evidence, or unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:workbench-matching-pair-service-boundary-audit`
