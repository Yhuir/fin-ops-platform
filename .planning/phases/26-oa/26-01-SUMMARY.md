---
phase: 26-oa
plan: "01"
subsystem: turnover-ledger
tags: [turnover, workbench, relation-requirements, tdd, legacy-removal]

requires:
  - phase: 01-turnover-ledger-improvements
    provides: canonical Turnover closure facade/UoW and selected-row write boundary
  - phase: 21-workbench-production-closure
    provides: active relation ownership and paired/unpaired projection contracts
provides:
  - Turnover manual closure relations freeze the actual selected-row OA/invoice policy
  - Active turnover ownership remains same-case unpaired until frozen requirements are met
  - Final bank membership is bounded by selected ids before the relation command
  - Legacy no-OA rule-save relation resynchronization is removed
affects: [26-02, turnover-ledger, reconciliation-workbench, bank-flow-rule-batches]

tech-stack:
  added: []
  patterns: [request-scoped selected-row reuse, frozen relation policy snapshot, fail-closed completion]

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py
    - backend/src/fin_ops_platform/services/workbench_relation_requirements.py
    - backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py
    - backend/src/fin_ops_platform/app/server.py
    - tests/test_turnover_ledger_uow_contract.py
    - tests/test_turnover_workbench_integration.py
    - tests/test_workbench_relation_grouping.py

key-decisions:
  - "Active relation means canonical ownership, not automatic completion; Workbench evaluates the frozen OA/invoice requirements."
  - "Turnover confirmation reuses the existing selected-row cache and canonical requirement helper instead of introducing a new service or policy layer."
  - "Rules saves never rewrite existing relation snapshots; missing legacy metadata stays fail closed for the controlled 26-02 repair."

patterns-established:
  - "Closure snapshot: selected rows and one canonical rules payload produce immutable relation requirement metadata in the creation transaction."
  - "Selected-member invariant: every final merged bank member must be present in the user's normalized selected ids before mutation."

requirements-completed: [TURN-CLOSURE-01, TURN-CLOSURE-02, TURN-CLOSURE-03, TURN-CLOSURE-06]

duration: 31min
completed: 2026-07-22
---

# Phase 26 Plan 01: Turnover Closure Frozen Policy Summary

**Turnover manual closure now creates canonical ownership with the real frozen bank-rule requirements, so an OA-required bank-only case stays unpaired without adding a new runtime layer.**

## Performance

- **Duration:** 31 min
- **Started:** 2026-07-22T17:32:23+08:00
- **Completed:** 2026-07-22T18:03:00+08:00
- **Tasks:** 3
- **Files modified:** 23

## Accomplishments

- Removed the `turnover_manual_closure` unconditional-complete bypass while preserving explicit batch-accounting and ETC completion contracts.
- Reused one request-scoped selected-row read and one canonical rules-payload read to freeze tag codes, OA/invoice flags, policy source and version on the new relation.
- Added a pre-command invariant that rejects any merged bank member outside the selected ids, including zero-mutation and no-extra-I/O assertions.
- Deleted the legacy no-OA rule-save scan/update chain that retroactively rewrote Turnover relations.
- Registered the corrected product, state-machine, module I/O and seven-category test contracts without changing API/DTO, production frontend, schema, worker, queue or read-model ownership.

## Task Commits

Each task was committed atomically:

1. **Task 1: Failure-first completion, policy-snapshot and membership contracts** - `0d5d1d4dd` (test)
2. **Task 2: Online root-cause correction and legacy sync deletion** - `9f5b545f6` (feat)
3. **Task 3: Product, boundary, state-machine and regression documentation** - `965bd4cec` (docs)

## Files Created/Modified

- `backend/src/fin_ops_platform/services/workbench_relation_requirements.py` - Removes only the Turnover unconditional-completion exception.
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py` - Shares selected rows, freezes canonical policy metadata and enforces selected membership.
- `backend/src/fin_ops_platform/app/server.py` - Injects the existing canonical rule provider for PostgreSQL and local composition.
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py` - Removes rule-save relation scanning and retroactive updates.
- `tests/test_workbench_relation_grouping.py` - Covers the four-policy matrix, multi-tag OR, fail-closed inputs and explicit exceptions.
- `tests/test_turnover_ledger_uow_contract.py` - Covers call counts, metadata, merge invariants, invalid rows/rules and zero mutation.
- `tests/test_turnover_workbench_integration.py` - Covers confirm-to-unpaired, direct double-false pairing, merge and withdraw recovery.
- `tests/test_workbench_sql_runtime.py` - Protects production-shape same-case unpaired projection.
- `tests/test_turnover_ledger_api.py` - Protects canonical provider wiring and existing HTTP contract.
- `tests/test_no_oa_bank_batch_tag_selection_api.py` - Proves rule saves perform zero relation list/update I/O.
- `web/src/test/WorkbenchApi.test.ts` and `web/src/test/RelationGroupGrid.test.tsx` - Protect missing/false mapping and pending-document rendering without production frontend changes.
- Turnover, Workbench, bank-flow and product documentation - Records the frozen snapshot, module boundaries, old-chain deletion and seven-category responsibility.

## Decisions Made

- The existing `build_bank_relation_requirement_metadata(...)` helper remains the sole policy-normalization boundary. No second policy service or adapter was introduced.
- `effective_category_code` is authoritative for the selected bank row; `category_code` is used only when the effective field is absent, matching local/legacy row shape without adding a fallback write path.
- Unknown, empty or malformed row/rule inputs fail closed before the relation command. They are not converted to hard-coded double-false requirements.
- Historical relations are not silently rewritten during settings updates. Exact repair, v6 rehydrate and production evidence remain isolated in Plan 26-02.

## Seven-Category Test Coverage

1. **Business core:** OA-only, invoice-only, both, neither, multi-tag OR, missing/unknown/empty metadata, ordinary, batch-accounting and ETC behavior.
2. **Service layer:** selected-row/rules call counts, frozen metadata, valid merge, invalid membership, invalid provider output, atomic no-command failure.
3. **API contract:** production composition wiring plus existing permission, version, idempotency and response-shape coverage; no contract field changed.
4. **Read model/cache/worker:** SQL production-shape completion projection; cache/schema/scope/worker were unchanged and existing freshness tests remained in the matrix.
5. **Frontend interaction:** mapper preserves explicit false and missing fields; grid renders OA/invoice missing hints; production component I/O was unchanged.
6. **End-to-end integration:** browser confirm/withdraw through freshness barriers plus backend confirm -> unpaired/direct paired -> withdraw integration.
7. **Existing regression:** no-OA/bank-flow rule save, ordinary relations, deterministic grouping, batch-accounting, ETC, merge/recovery and other page boundaries.

## Verification Evidence

- `bash scripts/verify.sh lint` - passed.
- Backend affected matrix - **486 passed, 44 subtests passed**, 5 unrelated deprecation warnings.
- Frontend targeted matrix - **2 files, 67 tests passed**.
- Chromium Turnover flow - **4 passed**.
- `npm --prefix web run build` - passed; existing CSS minifier and chunk-size warnings remain non-blocking.
- `bash scripts/verify.sh docs` - passed.
- `git diff --check` - passed.
- Runtime old-symbol scan across `backend tests web` - no matches.

## Deviations from Plan

### Auto-fixed Issues

**1. Test-only legacy wording outside the declared file list**

- **Found during:** Task 2 whole-repository old-chain scan.
- **Issue:** `tests/test_bank_flow_rule_batch_backend_boundary.py` and `tests/test_workbench_relation_command_service.py` still named/asserted the removed Turnover rule-resync operation even though they did not own runtime behavior.
- **Fix:** Replaced the boundary assertion with structural zero relation-list/update I/O and renamed the generic metadata-update fixture to neutral repair semantics.
- **Files modified:** `tests/test_bank_flow_rule_batch_backend_boundary.py`, `tests/test_workbench_relation_command_service.py`.
- **Verification:** Included in the 486-test affected backend matrix; runtime old-symbol scan is empty.
- **Committed in:** `9f5b545f6`.

---

**Total deviations:** 1 auto-fixed blocking cleanup.
**Impact on plan:** Two test files were added to the planned scope solely to remove stale references and preserve equivalent generic command coverage; no runtime, API or architecture scope expanded.

## Issues Encountered

- The local test fixture exposes legacy `category_code` while production SQL rows expose `effective_category_code`; the shared adapter keeps effective-first semantics and tests model both shapes.
- Production build reports pre-existing generated CSS selector and chunk-size warnings, but exits successfully and the changed code adds no frontend production bundle.

## User Setup Required

None - no dependency, environment variable, schema or service configuration was added.

## Next Phase Readiness

- Online root-cause correction is complete and locally verified.
- Plan 26-02 can now implement fingerprint-bound historical repair, Workbench v6 rehydrate, exact-release deployment and production SLO/E2E evidence.
- No production repair, deployment, rehydrate or real business-fixture write was executed in this plan.

---
*Phase: 26-oa*
*Completed: 2026-07-22*
