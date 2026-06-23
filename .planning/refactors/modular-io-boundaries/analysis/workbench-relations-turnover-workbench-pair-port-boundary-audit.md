# Workbench Relations Turnover Workbench Pair Port Boundary Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:turnover-workbench-pair-port-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Do not mark `workbench_relation` locally closed yet.

Select the next narrow implementation boundary:

`workbench-relations:turnover-workbench-pair-port-unused-persist-callback-removal`

## Evidence Reviewed

- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_workbench_integration.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `docs/modules/turnover-ledger/README.md`
- `docs/modules/turnover-ledger/state-machine.md`
- `docs/modules/turnover-ledger/tests.md`

CodeGraph/text scan showed:

- `TurnoverLedgerWorkbenchPairPort.create_turnover_manual_closure(...)` requires `relation_command_service_factory`; if no command service is available it raises `workbench_relation_command_unavailable`.
- `withdraw_turnover_manual_closure(...)` and `withdraw_cash_closure_case(...)` also require command service and fail fast when unavailable.
- Existing tests already block direct pair read/write fallback for manual closure, manual closure withdraw and cash closure withdraw.
- Static guard `test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback` already prevents `replace_with_confirmed_relation`, direct `cancel_relation(case_id)` and `_persist_pair_relations(...)` from returning inside the port.
- `TurnoverLedgerWorkbenchPairPort` still accepts and stores `persist_pair_relations`, but the class never reads or calls `_persist_pair_relations`.
- `TurnoverLedgerWorkbenchPairPort` still accepts `pair_relation_service`, but current usage is read-only fallback for `assert_turnover_manual_closure_withdrawable(...)` when facade data is unavailable, not direct write fallback.

## Boundary Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| `TurnoverLedgerWorkbenchPairPort.relation_command_service_factory` | canonical write dependency | Required for manual closure confirm, manual closure withdraw and cash closure withdraw. |
| `TurnoverLedgerWorkbenchPairPort.pair_relation_service` | compat-only read fallback | Only used to inspect active relation by case id when facade/context is unavailable during withdrawability checks. It must not write canonical facts, dirty scopes, outbox, readiness, cache or App Status. |
| `TurnoverLedgerWorkbenchPairPort.persist_pair_relations` | removable unused wiring | Stored as `_persist_pair_relations` but never called. It should be removed from the port constructor and caller wiring. |
| Turnover primary builders | dependency assembly, with unused persist callback | They pass `persist_pair_relations_in_transaction` to the port. The next slice should remove only the unused port parameter/wiring. |
| Turnover legacy fallback facades | compat-only route fallback, with unused persist callback | They pass a persist wrapper into the port. The next slice should remove only the unused port parameter/wiring, not migrate fallback behavior. |

## Why Not Close the Module

This audit proves turnover pair writes are command-service gated, but it does not close every workbench relation local gap. Pending invoice, no-OA, ETC repair/link/migration and WorkbenchWriteFacade relation dependencies still need separate classification.

Production PostgreSQL/worker/App Status/high-row/browser evidence also remains unavailable in this local run.

## Next Implementation Scope

Allowed next slice:

- Remove `persist_pair_relations` from `TurnoverLedgerWorkbenchPairPort.__init__(...)`.
- Remove `_persist_pair_relations` storage from `TurnoverLedgerWorkbenchPairPort`.
- Remove `persist_pair_relations=...` arguments where builders/fallback facades construct `TurnoverLedgerWorkbenchPairPort`.
- Keep `pair_relation_service` as read-only compat fallback for now.
- Extend/update static guard so `_persist_pair_relations` cannot return inside `TurnoverLedgerWorkbenchPairPort`.

Forbidden next slice expansion:

- Do not remove `pair_relation_service` in the same slice.
- Do not change turnover confirm/withdraw/cash-closure business rules.
- Do not change API payload shape, dirty scope semantics, read model refresh semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/turnover-ledger/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This audit closes as `analysis-closed`; `workbench_relation` remains `implementation-gap-open`.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. No behavior changed in this audit. |
| Service-layer tests | Not applicable for this audit. Existing turnover UoW tests prove command-service gating. |
| API contract tests | Not applicable. No HTTP behavior changed. |
| Read model/cache/background job tests | Not applicable. No runtime behavior changed. |
| Frontend component and interaction tests | Not applicable. |
| End-to-end business-flow integration tests | Not applicable. |
| Existing feature regression tests | Applicable through impact review, docs verification and diff check. |

## Verification

Required before commit:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the turnover workbench pair port boundary audit. It does not remove the unused persist callback, close `workbench_relation`, validate production evidence, or unblock Go admission.
