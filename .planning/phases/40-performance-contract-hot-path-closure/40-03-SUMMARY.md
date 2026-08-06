---
phase: 40-performance-contract-hot-path-closure
plan: "03"
subsystem: database-performance
tags: [postgresql, imports, batch-upsert, owner-guard, transaction-rollback]

requires:
  - phase: 39-production-runtime-and-search-convergence
    provides: canonical PostgreSQL import facts and transactional repository boundary
provides:
  - import batch-row writes use only bounded multi-value execution
  - query-count, fail-fast capability, same-owner idempotency, and cross-owner rollback regression proof
affects: [40-08, imports-bank-transactions, imports-invoices]

tech-stack:
  added: []
  patterns: [bounded multi-value upsert, affected-count owner guard, fail-fast transaction capability]

key-files:
  created:
    - .planning/phases/40-performance-contract-hot-path-closure/deferred-items.md
  modified:
    - backend/src/fin_ops_platform/services/postgres_repositories/core.py
    - tests/test_postgres_repositories_core.py
    - tests/test_postgres_state_store_integration.py

key-decisions:
  - "Require PostgresTransaction.execute_many_values directly for import batch rows; a connection without the bounded capability fails fast instead of issuing per-row SQL."
  - "Keep the existing owner-guard ON CONFLICT predicate and affected-count rollback contract unchanged; optimize only the benchmark-proven import row hotspot."

patterns-established:
  - "Import row persistence routes through the existing 1000-row/60000-parameter transaction helper with no compatibility fallback."
  - "Cross-owner partial INSERT results raise inside the transaction so the new batch and all preceding rows roll back atomically."

requirements-completed: []

duration: 8 min
completed: 2026-08-06
---

# Phase 40 Plan 03: Import Batch-Row Round-Trip Closure Summary

**Import batch rows now use the existing bounded PostgreSQL multi-value upsert exclusively, preserving owner-guard idempotency and whole-transaction rollback while deleting the per-row compatibility path.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-08-06T06:08:25Z
- **Completed:** 2026-08-06T06:16:02Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Deleted the `getattr(...)/sum(connection.execute(...))` compatibility branch; `_save_batch_rows` now directly requires `execute_many_values`.
- Locked 2,001 import rows to three SQL executions through the existing 1,000-row helper boundary, with no change to `postgres_connection.py` or its 60,000-parameter cap.
- Added real PostgreSQL proof that same-owner repeats remain one row and a mixed new-row/cross-owner conflict rolls back the new batch and every partial row.
- Preserved the existing `ON CONFLICT ... where legacy_batch_id = excluded.legacy_batch_id` owner guard, affected-count failure, formal-table round trip, and canonical invoice persistence.
- Made no Bank/Pending DTO, Pending options, Turnover lots, Cost ordering, App Health, schema, migration, dependency, cache, worker, API, or frontend change.

## Task Commits

1. **Task 1 RED: lock bounded batch/query-count and owner rollback contracts** - `68c0d2efa` (test)
2. **Task 1 GREEN: require bounded multi-value import-row upserts** - `5bd527915` (perf)

## Files Created/Modified

- `backend/src/fin_ops_platform/services/postgres_repositories/core.py` - removes the per-row fallback and calls the existing bounded helper directly.
- `tests/test_postgres_repositories_core.py` - covers 2,001-row query count, cross-owner affected count, and fail-fast missing capability.
- `tests/test_postgres_state_store_integration.py` - covers real same-owner idempotency, successful persistence, and whole-transaction rollback on mixed-row ownership conflict.
- `.planning/phases/40-performance-contract-hot-path-closure/deferred-items.md` - records three unrelated pre-existing integration-test contract failures without expanding 40-03 scope.

## Decisions Made

- Reused the `PostgresTransaction.execute_many_values` capability introduced before this plan; no helper, abstraction, dependency, or second batch implementation was added.
- Kept owner validation as the existing SQL predicate plus exact affected-count comparison. A conflict may produce a partial statement row count, but the raised exception keeps the surrounding PostgreSQL transaction atomic.
- Docs impact assessment: module boundary, I/O, API shape, worker/read-model contract, permissions, and long-lived verification entry points are unchanged; long-term docs are not applicable.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added the required `imported_at` value to the PostgreSQL test fixture**
- **Found during:** Task 1 real PostgreSQL GREEN verification
- **Issue:** The new direct fixture omitted the existing non-null `app.import_batches.imported_at` column.
- **Fix:** Inserted `now()` in the test-owned batch row.
- **Files modified:** `tests/test_postgres_state_store_integration.py`
- **Verification:** Targeted disposable PostgreSQL gate passed 21 tests.
- **Committed in:** `5bd527915`

---

**Total deviations:** 1 auto-fixed blocking test-fixture issue

**Impact on plan:** No production scope expansion; the correction only made the planned real transaction proof valid against the current schema.

## Issues Encountered

- The first disposable PostgreSQL URL used a local socket form without a host; the migration safety boundary rejected it. The rerun used explicit `postgresql://localhost/...` and the database was removed after each run.
- The exact two-file verification discovered three pre-existing failures unrelated to import rows: two stale Bank Flow expectations and one retired no-OA read-model writer expectation. Per scope rules, they were not changed or hidden; details are in `deferred-items.md`.

## Deferred Issues

- Full `tests/test_postgres_state_store_integration.py` remains red in three unrelated tests listed in `deferred-items.md`. They require separate contract/test retirement work and do not affect the import batch-row acceptance slice.

## TDD Gate Compliance

- RED commit `68c0d2efa`: repository slice produced 18 passed / 1 expected failure because the per-row fallback still accepted a connection without `execute_many_values`.
- GREEN commit `5bd527915`: repository slice passed 19/19; disposable PostgreSQL import slice passed 21/21.
- Git history contains the required `test(40-03)` commit followed by the GREEN `perf(40-03)` implementation commit.

## Tests

- **Business core unit:** Applicable. Owner conflict, same-owner idempotency, invalid missing capability, and exact affected-count failure are covered.
- **Service/repository:** Applicable. Repository query count and real transaction persistence/rollback are covered.
- **API contract:** Not applicable; no HTTP route, status, DTO, permission, or response shape changed.
- **Read model/cache/background job:** Not applicable; import row persistence does not alter freshness, cache, queue, worker, or read-model behavior.
- **Frontend component/interaction:** Not applicable; no frontend file or user interaction changed.
- **End-to-end business flow:** Not applicable; the change stays inside one existing repository transaction and adds no cross-module flow.
- **Existing feature regression:** Applicable. Formal import/file/invoice round trip and owner preservation remain protected.

## Verification

- `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_postgres_repositories_core.py` (RED) — 18 passed, 1 expected failure.
- `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_postgres_repositories_core.py` (GREEN) — 19 passed.
- Disposable PostgreSQL targeted gate for both repository tests plus import formal-table round trip and owner-conflict rollback — 21 passed.
- Exact plan two-file gate before the fixture correction — 33 passed, 4 failed; the plan-owned fixture failure was corrected and passed, while three unrelated pre-existing failures remain deferred.
- `bash scripts/verify.sh lint` — passed.
- `git diff --check` — passed.
- Disposable PostgreSQL cleanup — each uniquely named test database was dropped by the command trap.

## Known Stubs

None. Scanner hits are existing typed empty containers, optional values, or test recorders; none is an unwired UI or placeholder implementation.

## Security

- T-40-03-01: cross-owner affected-count mismatch raises within the real transaction; rollback proof confirms no re-parenting or half-write.
- T-40-03-02: 2,001 rows execute in three bounded statements through the existing 1,000-row/60,000-parameter helper.
- T-40-03-03: only the named import-row hotspot changed; all speculative page candidates have zero production diff.
- No endpoint, auth path, file access, schema, or new trust boundary was introduced; no threat flag is required.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 40-08 can reuse the query-count and real PostgreSQL owner-rollback evidence for final performance-contract closure.
- Import batch-row behavior has no implementation blocker. The three unrelated integration-test failures remain explicit deferred test-contract work.

## Self-Check: PASSED

- All three plan-owned source/test files and this SUMMARY exist.
- RED `68c0d2efa` and GREEN `5bd527915` resolve in git history in the required order.
- The plan-owned import slice, lint, diff check, owner/idempotency/rollback, and disposable database cleanup passed.

---
*Phase: 40-performance-contract-hot-path-closure*
*Completed: 2026-08-06*
