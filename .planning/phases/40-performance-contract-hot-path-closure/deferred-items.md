# Deferred Items

## Resolved by 40-04

The three 40-03 verification discoveries were obsolete integration tests for contracts already
removed from production: `save_bank_flow_rule_batches`, the legacy batch-page `total` field,
and the retired `read_model.no_oa_bank_batch_rows` writer. Plan 40-04 removed those tests after
reproducing each failure against a disposable PostgreSQL database and confirming the canonical
no-OA route, command, and Workbench consumers remain covered.

No deferred items remain from 40-03.

## 40-04 full-suite discovery

- `tests/test_permissions_write_entry_inventory.py::PermissionsWriteEntryInventoryTests::test_phase_27_mutating_api_function_coverage_is_bidirectional`
  fails because `.planning/phases/27-read-model-fan-out/27-COVERAGE-MATRIX.md` still lists
  `workbench/api.ts#unignoreWorkbenchRow`, while that frontend export is no longer present.

This inventory drift existed at the 40-04 execution baseline and is unrelated to the Search/no-OA
runtime-fact closure. It remains deferred to the permissions/frontend coverage owner; 40-04 does
not edit Phase 27 history to make its own full-suite gate appear green.

- `web/e2e/app-shell-responsive.spec.ts` exceeded its local animation-frame p95 threshold while
  collapsing the embedded OA shell (`54.225ms > 25ms`).
- `web/e2e/drawer-motion.spec.ts` sampled the closing drawer before it reached the expected right
  edge (`1304.21px < 1364px`).

The complete deterministic browser run finished with 171 passed / 2 failed. Both failures concern
pre-existing shell/drawer motion and are outside the 40-04 runtime-fact and no-OA contract files;
their traces, screenshots, and videos remain in gitignored Playwright test output for the UI owner.
