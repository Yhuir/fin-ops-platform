# Workbench Relations Turnover Workbench Pair Port Unused Persist Callback Removal

**Date:** 2026-06-24
**Boundary:** `workbench-relations:turnover-workbench-pair-port-unused-persist-callback-removal`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove unused `persist_pair_relations` wiring from `TurnoverLedgerWorkbenchPairPort` without changing turnover closure/withdraw behavior.

## Changes

- Removed the unused `persist_pair_relations` constructor parameter from `TurnoverLedgerWorkbenchPairPort`.
- Removed the unused `_persist_pair_relations` field.
- Removed `persist_pair_relations=...` arguments from turnover primary builder and legacy fallback facade port construction.
- Removed now-unused `persist_pair_relations_in_transaction` plumbing from turnover primary builder constructors and `server.py` calls.
- Kept `pair_relation_service` read-only compat fallback unchanged.
- Strengthened the static guard so `_persist_pair_relations` cannot return inside `TurnoverLedgerWorkbenchPairPort`.

## Preserved Behavior

- Manual closure confirm still delegates relation writes to `WorkbenchRelationCommandService`.
- Manual closure withdraw still delegates relation writes to `WorkbenchRelationCommandService`.
- Cash closure withdraw still delegates relation writes to `WorkbenchRelationCommandService`.
- Missing command service still fails fast with `workbench_relation_command_unavailable`.
- No API payload, dirty scope, read model refresh or production behavior changed.

## Legacy Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `TurnoverLedgerWorkbenchPairPort.relation_command_service_factory` | canonical write dependency | Required by confirm and withdraw methods. |
| `TurnoverLedgerWorkbenchPairPort.pair_relation_service` | compat-only read fallback | Still retained only for withdrawability check fallback. |
| `TurnoverLedgerWorkbenchPairPort.persist_pair_relations` | removed | Constructor parameter, field and port call wiring removed. |
| `persist_pair_relations_in_transaction` in turnover primary builders | removed from turnover port path | It was only passed to the port's unused callback. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/turnover-ledger/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This implementation closes one unused turnover pair port callback gap. `workbench_relation` remains `implementation-gap-open`; pending invoice, no-OA, ETC and WorkbenchWriteFacade relation dependencies remain for later classification.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. Business relation rules did not change. |
| Service-layer tests | Covered by turnover UoW tests proving command-service delegation and fail-fast behavior are unchanged. |
| API contract tests | Not applicable. No HTTP/API shape changed. |
| Read model/cache/background job tests | Not applicable. No refresh, dirty scope, cache or worker behavior changed. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this wiring-only slice. |
| Existing feature regression tests | Covered by turnover UoW command delegation tests and runtime boundary guard. |

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure_withdraw tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_delegates_cash_closure_withdraw_to_relation_command_service tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_turnover_workbench_pair_port_requires_relation_command_service_for_cash_closure_withdraw -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback -v
```

Pending before commit:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the turnover unused persist callback removal. It does not remove the pair service read-only fallback, close `workbench_relation`, validate production evidence, or unblock Go admission.
