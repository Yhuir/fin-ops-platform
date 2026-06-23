# Workbench Relations - Turnover Local Pair Snapshot Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:turnover-local-pair-snapshot-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove broad Workbench pair relation service injection from turnover primary builders and local closure connection by extracting an explicit local pair snapshot/restore port.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-app-health-route-builder-pair-service-injection-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-turnover-workbench-pair-port-required-command-constructor.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_workbench_integration.py`

## Change Summary

- Added `TurnoverLedgerLocalPairSnapshotPort`.
- `TurnoverLedgerConfirmPrimaryWriteFacadeBuilder` and `TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder` now accept `pair_snapshot_port` instead of `pair_relation_service`.
- `TurnoverLedgerLocalClosureConnection` now requires `pair_snapshot_port` and no longer accepts or stores broad pair service.
- Pair snapshot/private-field restore behavior is now owned by the explicit port.
- `Application` turnover closure/withdraw builder wiring wraps `_workbench_pair_relation_service` in `TurnoverLedgerLocalPairSnapshotPort`.
- Added a static guard proving turnover builders/local connection no longer accept broad pair service and server wiring uses the explicit port.

## Preserved Semantics

- Turnover local confirm/withdraw rollback still snapshots and restores Workbench pair relation state.
- Turnover command-service writes, relation facade reads and route response shape are unchanged.
- Existing turnover manual closure withdraw restoration behavior is preserved.
- Existing best-effort relation persistence failure behavior is preserved.

## Legacy Classification

- Removed from turnover primary builders/local connection: broad `pair_relation_service` constructor/storage dependency.
- New explicit owner: `TurnoverLedgerLocalPairSnapshotPort`.
- Still open:
  - `SettingsDataResetService(workbench_pair_relation_service=...)` relation reset boundary.
  - final local closure/defer accounting.
  - production evidence defer because no local/staging `PGSQL_URL` exists.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:turnover-local-pair-snapshot-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:settings-data-reset-pair-service-boundary-audit`

## Seven Test Category Decision

1. Business core unit tests: not applicable; turnover relation business rules were not changed.
2. Service-layer tests: covered by turnover local rollback integration and static boundary guard.
3. API contract tests: covered by turnover API regression for persistence failure; no response shape changed.
4. Read model/cache/background job tests: covered by turnover queue regression preserving refresh enqueue behavior.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: existing turnover workbench integration tests cover confirm/withdraw relation restoration behavior.
7. Existing feature regression tests: covered by turnover withdraw/restore and persistence failure regressions.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_local_pair_snapshot_uses_explicit_port -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_relation_persistence_failure_is_best_effort_success_and_still_enqueues_refresh -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_workbench_integration.TurnoverWorkbenchIntegrationTests.test_manual_closure_merges_existing_oa_bank_relations_and_withdraw_restores_them tests.test_turnover_workbench_integration.TurnoverWorkbenchIntegrationTests.test_turnover_withdraw_bank_only_closure_cancels_workbench_relation -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this implementation slice is closed. `workbench_relation` remains `implementation-gap-open`.
