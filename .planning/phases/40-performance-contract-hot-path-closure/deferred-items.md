# Deferred Items

## Resolved by 40-04

The three 40-03 verification discoveries were obsolete integration tests for contracts already
removed from production: `save_bank_flow_rule_batches`, the legacy batch-page `total` field,
and the retired `read_model.no_oa_bank_batch_rows` writer. Plan 40-04 removed those tests after
reproducing each failure against a disposable PostgreSQL database and confirming the canonical
no-OA route, command, and Workbench consumers remain covered.

No deferred items remain from 40-03.

## Resolved by 40-07

- `tests/test_permissions_write_entry_inventory.py::PermissionsWriteEntryInventoryTests::test_phase_27_mutating_api_function_coverage_is_bidirectional`
  now passes after a whole-repository scan proved `workbench/api.ts#unignoreWorkbenchRow` has no
  export or consumer and 40-07 removed only that stale Phase 27 coverage entry.
- `web/e2e/app-shell-responsive.spec.ts` now passes unchanged in the 40-07 rerun.

## 40-07 unchanged drawer-motion rerun

- `web/e2e/drawer-motion.spec.ts` remains flaky outside the Workbench/bank-flow scope. In the
  combined unchanged-code rerun, 7/8 tests passed and the primary drawer test captured no
  intermediate frame (`intermediateIndex = -1`). An immediate isolated rerun failed a different
  sampling assertion because the open-frame right edge was `3.6084px` from the viewport edge
  (threshold `2px`).

40-07 did not modify drawer or shell production code. The differing failures under identical code
confirm a sampling-sensitive test/runtime issue; current traces, screenshots, and videos remain in
gitignored Playwright output for the UI owner.
