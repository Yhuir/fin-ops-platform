---
phase: 13-settings-improvements
plan: "08"
subsystem: security
tags: [settings-acl, oa-role-sync, menu-projection, compensation]

requires:
  - phase: 13-settings-improvements
    plan: "07"
    provides: canonical ACL-only APP authorization and casefold-preserve-canonical usernames
provides:
  - fixed finops:app:view OA-only menu selector with unique-menu validation
  - exact three-dedicated-role menu binding validation before OA membership mutation
  - fail-closed Settings ACL persistence when runtime OA projection is unavailable
affects: [settings, oa-integration, permissions-and-audit, 13-10]

tech-stack:
  added: []
  patterns: [validate-before-mutate OA transaction, exact-set projection, fail-closed compensation]

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/services/oa_role_sync_service.py
    - backend/src/fin_ops_platform/services/app_settings_service.py
    - tests/app_test_support.py
    - tests/test_oa_role_sync_service.py
    - tests/test_app_settings_service.py
    - tests/test_workbench_settings_sync_api.py

key-decisions:
  - "FIN_OPS_OA_REQUIRED_PERMISSION must be exactly finops:app:view and remains confined to the OA adapter; it never grants APP access."
  - "Runtime sync locks and validates one menu, three unique dedicated roles, and the exact three bindings before changing only sys_user_role memberships."
  - "Disabled or missing runtime projection fails real ACL mutations through the existing 502 contract; deployment cleanup remains owned by 13-10."

patterns-established:
  - "OA projection validates its complete fixed target inside one transaction before any membership DML."
  - "ACL semantic no-op returns before OA configuration checks; real changes require a configured executor."

requirements-completed: [PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

duration: 8min
completed: 2026-08-02
---

# Phase 13 Plan 08: Strict OA Menu Projection Summary

**Canonical Settings ACL changes now project only through one fixed OA menu and exactly three dedicated roles, failing before PostgreSQL/audit persistence whenever the OA contract is unavailable or drifted.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-08-02T07:06:49Z
- **Completed:** 2026-08-02T07:14:34Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Locked `FIN_OPS_OA_REQUIRED_PERMISSION` to the OA-only `finops:app:view` selector and retained the existing APP ACL-only authorization denial for permission-bearing outsiders.
- Added one-transaction, pre-DML validation for a unique menu, three unique dedicated roles, complete bindings, and no non-dedicated binding drift.
- Preserved exact replacement of only the three dedicated `sys_user_role` memberships; menu rows, role rows, role-menu bindings, business roles, and their memberships are never mutated.
- Converted disabled/missing OA role sync from a silent success into the existing configuration error, 502 route response, and zero PostgreSQL/audit write path.
- Preserved semantic no-op zero I/O, target-success/PG-failure compensation, and compensation-failure `access_control_sync_inconsistent` 503 behavior.

## Task Commits

1. **Task 1 RED: Lock strict fixed-menu and exact-binding behavior** — `df50fd2db` (`test`)
2. **Task 1 GREEN: Enforce exact OA menu projection** — `446b92a02` (`feat`)
3. **Task 2 RED: Lock fail-closed Settings mutation behavior** — `d23091b75` (`test`)
4. **Task 2 GREEN: Fail closed when runtime projection is unavailable** — `f61f4cbda` (`feat`)

## Files Created/Modified

- `backend/src/fin_ops_platform/services/oa_role_sync_service.py` — fixed marker parsing, bounded connection failure mapping, unique menu/role lookup, exact binding validation, and disabled executor failure.
- `backend/src/fin_ops_platform/services/app_settings_service.py` — real ACL changes require an OA sync service before PostgreSQL/audit commit; existing compensation remains unchanged.
- `tests/test_oa_role_sync_service.py` — scripted OA transaction coverage for fixed marker, exact set, drift, mutation scope, and timeout rollback.
- `tests/test_app_settings_service.py` — missing service, zero persistence/audit, no-op, and compensation coverage.
- `tests/test_workbench_settings_sync_api.py` — existing 502 and 503 response contracts for disabled projection and failed compensation.
- `tests/app_test_support.py` — explicit test executor injection only when a test helper intentionally seeds canonical ACL.

`routes_settings.py` required no change: its existing `OARoleSyncError` → 502 and inconsistent compensation → 503 mappings already satisfy the plan.

## Decisions Made

- Used `SELECT ... FOR UPDATE` within the existing OA transaction so role/menu validation and dedicated membership replacement share one locked consistency boundary.
- Required both set equality and row-count equality for role/menu results, preventing duplicate role or binding rows from being hidden by set conversion.
- Kept deployment-time deletion of legacy/non-dedicated `sys_role_menu` bindings out of runtime; drift blocks mutation and 13-10 owns exact cleanup/evidence.
- Reused existing errors, Settings critical section, compensation, and route response shapes; no new service, repository, queue, worker, schema, or endpoint was introduced.

## Test Coverage

- **1. Business core unit:** fixed marker, unique menu, unique dedicated roles, exact binding set, missing/duplicate/drift failure, canonical assignment spelling.
- **2. Service layer:** disabled/missing executor, bounded connect/read/write timeout, rollback, zero pre-validation DML, target/PG compensation, compensation failure.
- **3. API contract:** disabled or failed projection returns `502 oa_role_sync_failed`; compensation failure returns `503 access_control_sync_inconsistent`; canonical ACL remains unchanged.
- **4. Read model/cache/background jobs:** not applicable as new behavior; negative coverage confirms no read model, cache, queue, outbox, worker, or freshness I/O was added.
- **5. Frontend interaction:** not applicable; UI and API DTOs are unchanged.
- **6. End-to-end business flow:** local admin ACL PUT exercises route → Settings service → OA sync boundary → persistence/compensation, including fail-closed 502/503 outcomes; real OA remains an external release gate.
- **7. Existing regression:** auth guard proves `finops:app:view` does not grant APP access, full Settings service/API suites preserve generic settings, no-op, version, audit, and authorization behavior.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_oa_role_sync_service tests.test_auth_guard -v` — 22 passed.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_workbench_settings_sync_api tests.test_oa_role_sync_service -v` — 66 passed.
- `bash scripts/verify.sh lint` — passed.
- `git diff --check df50fd2db^..HEAD` — passed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added an explicit OA executor to the shared canonical ACL test helper**
- **Found during:** Task 2 GREEN verification.
- **Issue:** Production-correct disabled-sync failure would make unrelated tests that intentionally seed ACL through `configure_access_control(...)` depend on production OA configuration.
- **Fix:** The test helper now injects the existing executor protocol only for that explicit seed operation; production services retain fail-closed behavior and tests can still opt into a disabled service.
- **Files modified:** `tests/app_test_support.py`
- **Verification:** Both focused commands and lint pass, including the explicit disabled 502 test.
- **Committed in:** `f61f4cbda`

---

**Total deviations:** 1 auto-fixed (1 blocking test-fixture issue).
**Impact on plan:** Test-only wiring preserves the production contract without adding runtime scope.

## Documentation Impact

No long-term docs were changed in this plan. The plan explicitly assigns consolidated OA/settings runtime and deployment cleanup documentation to the later 13-04 update after 13-09/13-10; no current boundary, API shape, schema, worker, or read-model registry changed.

## Authentication Gates

None.

## Known Stubs

None.

## Remaining Risk

- Local scripted transactions cannot prove the target OA schema, collation, lock behavior, or production network characteristics; 13-10 owns read-only inventory, exact cleanup, rollback artifact, and production evidence.
- Runtime deliberately does not clean non-dedicated menu bindings. It fails closed until the controlled deployment operation removes verified exact targets.

## User Setup Required

None for local execution. Production configuration/evidence remains part of the later deployment plan and was not changed or exercised here.

## Next Phase Readiness

- Runtime projection is strict and fail-closed, ready for phase-level sentinels and the controlled 13-10 cleanup/evidence plan.
- 13-10 was not started; no production, push, deploy, schema, or cleanup action occurred.

## Self-Check: PASSED

- All six modified implementation/test files and this SUMMARY exist.
- Commits `df50fd2db`, `446b92a02`, `d23091b75`, and `f61f4cbda` exist in repository history.
- No goal-blocking stub, unplanned threat surface, file deletion, or untracked runtime artifact remains.

---
*Phase: 13-settings-improvements*
*Completed: 2026-08-02*
