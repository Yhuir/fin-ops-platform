---
phase: 40-performance-contract-hot-path-closure
plan: "07"
subsystem: read-model-correctness
tags: [postgresql, workbench, source-proof, bank-flow, playwright, tdd]

requires:
  - phase: 40-05
    provides: Workbench refresh-status self-healing enqueue boundary
  - phase: 40-06
    provides: visible Workbench completion polling and changed-generation reload
provides:
  - Bidirectional canonical writer-to-Workbench source-proof contract matrix
  - Real bank-flow application-to-status-to-queue-to-worker atomic publication proof
  - Removal of the Workbench-local operation barrier DTO and fallback
  - Deterministic browser proof of zero write notification and visible-page convergence
affects: [40-08, workbench, bank-flow-rule-batches, runtime-workers, permissions-inventory]

tech-stack:
  added: []
  patterns:
    - Production writers advance canonical updated_at/version facts; readers derive exact stale proof without write fan-out
    - Visible Workbench status owns exact enqueue and one changed-generation reload

key-files:
  created:
    - tests/test_workbench_source_proof_contract.py
  modified:
    - web/src/features/workbench/api.ts
    - web/src/features/workbench/exceptionTypes.ts
    - web/src/test/WorkbenchApi.test.ts
    - web/e2e/bank-flow-rule-batches-flow.spec.ts
    - web/e2e/fixtures/apiMocks.ts
    - .planning/phases/27-read-model-fan-out/27-COVERAGE-MATRIX.md
    - .planning/phases/40-performance-contract-hot-path-closure/deferred-items.md

key-decisions:
  - "Keep the existing Workbench SQL proof query unchanged because real PostgreSQL mutations proved every mutable dependency advances its exact proof."
  - "Retain freshnessTargets and the global operation-barrier operator surface; delete only the Workbench-local operationBarrierTargets DTO/fallback with no runtime consumer."
  - "Treat the unchanged drawer-motion sampling failure as a deferred UI-test issue, not a reason to modify drawer production code in the Workbench correctness plan."

patterns-established:
  - "Writer-proof matrix rows name mutation family, production owner, exact proof keys, and scope propagation contract."
  - "Browser convergence tests separate write success from visible-page stale detection and generation activation."

requirements-completed: []

duration: 34min
completed: 2026-08-06
---

# Phase 40 Plan 07: Workbench Writer-Proof and Bank-Flow Convergence Summary

**Every mutable Workbench dependency now has real PostgreSQL writer-to-proof coverage, and bank-flow writes converge through the existing visible-page status, exact queue, and atomic worker path without notification fan-out.**

## Performance

- **Duration:** 34 min
- **Started:** 2026-08-06T07:37:30Z
- **Completed:** 2026-08-06T08:11:15Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Added a real disposable-PostgreSQL matrix covering relation/cross-month members, bank/category/confirmation, invoice/OA, exception/override/claim, ETC facts/links, settings, and immutable schema/rule/parser proof keys.
- Proved the full bank-flow correctness chain: application/state-store commit, zero writer dirty/outbox rows, facade freshness mismatch, one exact Workbench active event, worker atomic generation publication, fresh status, visible relation, and unchanged unrelated generation.
- Removed only Workbench-local `operationBarrierTargets` API/type/fallback residue while retaining `freshnessTargets`, global operator endpoints, maintenance paths, and domain jobs.
- Added deterministic browser coverage showing a bank-flow submit response has no barrier/freshness/Workbench signal and the visible Workbench advances from the old proof to one completed new-generation response with the expected business group.
- Removed the proven-dead `unignoreWorkbenchRow` Phase 27 coverage entry; the bidirectional permissions inventory now passes.

## Task Commits

Each task was committed atomically with explicit TDD gates:

1. **Task 1 RED: Workbench source-proof contract** - `477d45edf` (`test`)
2. **Task 1 GREEN: writer proof and bank-flow worker closure** - `e3b034590` (`feat`)
3. **Task 2 RED: reject Workbench-local barrier residue** - `aa541b341` (`test`)
4. **Task 2 GREEN: delete residue and prove browser convergence** - `e7c75bd28` (`feat`)

## Files Created/Modified

- `tests/test_workbench_source_proof_contract.py` - Bidirectional proof inventory, real production-writer mutations, exact scope assertions, and the bank-flow runtime convergence chain.
- `web/src/features/workbench/api.ts` - Removes raw/camel operation barrier fields and the fallback mapper; keeps freshness target normalization.
- `web/src/features/workbench/exceptionTypes.ts` - Removes the retired local result field.
- `web/src/test/WorkbenchApi.test.ts` - Rejects reintroduction of the local operation barrier property.
- `web/e2e/bank-flow-rule-batches-flow.spec.ts` - Verifies zero signals, status-led convergence, one completed new generation, and business identity visibility.
- `web/e2e/fixtures/apiMocks.ts` - Provides the deterministic stale-to-fresh Workbench generation sequence required by the browser contract.
- `.planning/phases/27-read-model-fan-out/27-COVERAGE-MATRIX.md` - Removes only the stale `unignoreWorkbenchRow` export entry after whole-repository proof.
- `.planning/phases/40-performance-contract-hot-path-closure/deferred-items.md` - Records the resolved inventory/shell checks and current unchanged drawer sampling evidence.

## Decisions Made

- The existing `WorkbenchSqlProjectionBuilder.source_versions_for_scopes` implementation is complete for the tested dependency families; no production proof query or writer owner required modification.
- Writer-side Workbench enqueue remains forbidden. Convergence is owned by the visible Workbench freshness/status boundary and the existing durable runtime queue/worker.
- `freshnessTargets` remains part of the Workbench exception result because no dead-consumer proof justified its deletion. Only the named `operationBarrierTargets` residue was removed.
- Global operation barrier tooling, maintenance/repair/rehydrate/backfill paths, Workbench matching, OA/import jobs, and operator endpoints remain untouched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added deterministic convergence state to the shared browser fixture**
- **Found during:** Task 2
- **Issue:** The named browser spec could not prove stale-to-new-generation behavior with the fixture's static refresh-status response.
- **Fix:** Added an opt-in bank-flow Workbench convergence sequence to `web/e2e/fixtures/apiMocks.ts`; no application runtime behavior changed.
- **Files modified:** `web/e2e/fixtures/apiMocks.ts`
- **Verification:** Targeted browser test and complete 9-test bank-flow browser spec passed.
- **Committed in:** `e7c75bd28`

**2. [Rule 1 - Test contract] Corrected RED matrix ownership and settings payload assumptions**
- **Found during:** Task 1 RED
- **Issue:** The first RED test incorrectly required one writer per proof key even though relation/member and direct fact writers legitimately share proof keys, and used non-canonical bank settings field names.
- **Fix:** Enforced unique mutation-family rows while preserving bidirectional proof-key coverage, and used canonical `bank_transaction_tags` plus list-shaped `bank_account_mappings`.
- **Files modified:** `tests/test_workbench_source_proof_contract.py`
- **Verification:** Three new PostgreSQL contract tests and all 50 scoped backend tests passed.
- **Committed in:** `e3b034590`

**3. [Rule 1 - Planning state] Corrected free-form STATE progress after SDK update**
- **Found during:** Final state update
- **Issue:** The state SDK correctly advanced plan counts but wrote an inconsistent frontmatter percentage (`29`) and left the free-form phase line at `6/8` despite seven on-disk summaries.
- **Fix:** Reconciled the frontmatter to overall `84/111 = 76%` and the Phase 40 line to `7/8`, matching the SDK-updated roadmap and on-disk summaries.
- **Files modified:** `.planning/STATE.md`
- **Verification:** `40-07-SUMMARY.md` is the seventh Phase 40 summary and ROADMAP reports `7/8`.
- **Committed in:** final metadata commit

---

**Total deviations:** 3 auto-fixed (1 blocking test infrastructure, 2 correctness fixes)
**Impact on plan:** Both changes were test-only and necessary to prove the requested production contracts; no notification fallback, endpoint, dependency, or production drawer change was added.

## Verification

- `FIN_OPS_TEST_DATABASE_URL=postgresql://localhost/fin_ops_test_40_07_executor PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_workbench_source_proof_contract.py tests/test_postgres_repositories_boundaries.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_runtime_worker_read_model_refresh_scopes.py` - **100 passed**.
- `npm --prefix web test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx` - **119 passed**.
- `python3 -m pytest tests/test_permissions_write_entry_inventory.py -q` - **25 passed**.
- `npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium` - **9 passed**.
- `npm --prefix web run build` - **passed**; existing generated CSS minifier syntax warnings remained non-fatal.
- `bash scripts/verify.sh lint` - **passed**.
- Disposable database `fin_ops_test_40_07_executor` was dropped and PostgreSQL confirmed zero matching databases.

## Issues Encountered

- The unchanged Phase 40-04 responsive-shell test now passes.
- The unchanged primary drawer-motion test remains sampling-sensitive: the combined rerun passed 7/8 with no intermediate frame captured, and an isolated rerun failed with the open edge 3.6084px from the viewport against a 2px threshold. The different assertions under identical code are recorded in `deferred-items.md`; no drawer or shell production code was changed.

## Known Stubs

None. Empty collections found by the stub scan are test recorders, normalization accumulators, or intentional empty fixture states; none blocks the plan goal or flows to a production UI placeholder.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 40-08 can consume the now-closed correctness path for same-clock performance evidence without compensating notification assumptions.
- No in-scope blocker remains. The drawer-motion sampling failure is explicitly deferred to the UI-test owner and does not affect Workbench source-proof or bank-flow convergence correctness.

## Self-Check: PASSED

- Created contract and summary files exist.
- All four task/TDD commits exist in repository history.
- Workbench runtime/type sources contain no `operationBarrierTargets` or `operation_barrier_targets` field; only negative regression assertions retain the string.
- The exact disposable PostgreSQL database is absent after cleanup.

---
*Phase: 40-performance-contract-hot-path-closure*
*Completed: 2026-08-06*
