---
phase: 13-settings-improvements
plan: "09"
subsystem: security-testing
tags: [settings-acl, authorization, regression, inventory, oa-selector]

# Dependency graph
requires:
  - phase: 13-settings-improvements
    plan: "07"
    provides: canonical Settings ACL-only APP authorization and immediate fail-closed decisions
  - phase: 13-settings-improvements
    plan: "08"
    provides: fixed OA-only menu selector and fail-closed role projection
  - phase: 13-settings-improvements
    plan: "10"
    provides: retired env rejection and fixed-menu deployment cleanup contracts
provides:
  - backend role matrix with permission-bearing YNSYLP006 negative fixtures
  - direct API, module-owned guard, admin-only control-plane and immediate revocation regressions
  - single whole-repo owner for retired authority, fixed OA selector and no-new-runtime inventory
affects: [13-04, 13-05, 13-11, 13-12, 13-13, 13-14, 13-15, permissions-and-audit]

# Tech tracking
tech-stack:
  added: []
  patterns: [canonical ACL attack fixtures, explicit-path authority inventory, runtime topology fingerprints]

key-files:
  created: []
  modified:
    - tests/test_session_api.py
    - tests/test_auth_guard.py
    - tests/test_route_access_policy.py
    - tests/test_oa_pending_payment_api.py
    - tests/test_app_health_api.py
    - tests/test_oa_applicant_credentials_api.py
    - tests/test_settings_data_reset_job.py
    - tests/test_permissions_write_entry_inventory.py

key-decisions:
  - "YNSYLP006 attack fixtures retain OA business/dedicated roles and finops:app:view while canonical ACL absence still yields denied."
  - "test_permissions_write_entry_inventory.py is the only authorization whole-repo scanner; every surviving retired-env or OA-selector path is explicit and reviewable."
  - "No production evaluator, read model, cache, queue, worker or compatibility branch was needed because plans 07/08/10 already supplied the runtime behavior."

patterns-established:
  - "Authorization negative fixtures preserve the hostile identity inputs instead of stripping roles or permissions."
  - "New retired-authority or OA-selector references fail with path and line evidence until the single owner allowlist is deliberately extended."

requirements-completed: [PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

# Metrics
duration: 10min
completed: 2026-08-02
---

# Phase 13 Plan 09: Backend Permission Matrix and Authority Inventory Summary

**Canonical Settings ACL authorization is protected by permission-bearing YNSYLP006 regressions and one whole-repo scanner that freezes retired authority, the OA-only selector, and the existing runtime topology.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-08-02T07:48:36Z
- **Completed:** 2026-08-02T07:57:59Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Locked fixed `YNSYLP005` admin, canonical full/read tiers, absence-derived denial, normalized denied session payloads, direct GET/unsafe API rejection, OA pending module-owned guards, and provider fail-closed behavior.
- Preserved the real attack conditions for `YNSYLP006`: `finance`/`finops_full_access` roles and `finops:app:view` remain visible in the identity/session payload but never grant APP access without canonical ACL membership.
- Proved a reused identity is denied on the next session/API decision immediately after ACL revocation; no `AccessDecision` cache invalidation path was introduced.
- Kept App Health, OA applicant credentials and data reset admin-only while full-access generic settings/read-export behavior and existing page contracts remain covered by focused regression suites.
- Extended the existing inventory owner across backend, web, tests, deploy, scripts and docs with explicit path allowlists, fixed-selector checks, AST constructor checks, one-provider/no-role-lookup guards, generic-save/no-op I/O ordering, and exact read-model/worker baselines.

## Task Commits

1. **Task 1: 完成backend七类权限与跨模块回归矩阵** — `91c09a4dd` (`test`)
2. **Task 2: 以唯一inventory owner锁定旧authority删除与机械I/O预算** — `ba7be0b8d` (`test`)

## Files Created/Modified

- `tests/test_session_api.py` — exact 005/full/read/denied/006 matrix and permission-bearing immediate-revocation proof.
- `tests/test_auth_guard.py` — direct read/unsafe API denial for real 006 attack input; stale legacy constructor test removed.
- `tests/test_route_access_policy.py` — explicit settings/App Health/data-reset safe and unsafe method classification.
- `tests/test_oa_pending_payment_api.py` — module-owned read guard rejects permission-bearing 006 across every representative query route.
- `tests/test_app_health_api.py` — canonical full-access 006 remains blocked from the admin dashboard.
- `tests/test_oa_applicant_credentials_api.py` — canonical full-access 006 cannot list or mutate OA credentials.
- `tests/test_settings_data_reset_job.py` — canonical full-access 006 cannot enqueue destructive reset work.
- `tests/test_permissions_write_entry_inventory.py` — sole whole-repo authorization deletion and no-new-runtime scanner.

## Decisions Made

- Reused the real `AccessControlService`, `configure_access_control(...)`, existing route policy and module-owned guard instead of mocking away hostile roles/permissions or creating a second auth suite.
- Kept retired env references only where they prove rejection, migration history or deployment blocking. The scanner reports exact path/line content and requires later documentation owners to extend one explicit allowlist deliberately.
- Treated `FIN_OPS_OA_REQUIRED_PERMISSION=finops:app:view` as OA metadata only: production backend hits are limited to OA role sync and preflight, while tests/docs/deploy may carry the fixed marker without becoming APP authority.
- Froze the current two read models and six required workers mechanically; settings ACL changes still add no Redis, cache, outbox, dirty scope, read model or worker.

## Test Coverage

- **1. Business core unit — applicable/covered:** 005/full/read/denied tiers, permission/role-bearing 006, one snapshot fetch, provider failure and immediate revoke.
- **2. Service/repository — applicable/covered:** generic settings preserves ACL and performs zero OA sync; ACL semantic no-op performs zero OA/audit/persistence; exact OA projection regressions remain green.
- **3. API contract — applicable/covered:** `/api/session/me` normalized denial, representative direct GET/unsafe 403, OA pending module guard, App Health, OA credentials and data reset admin-only responses with key error fields.
- **4. Read model/cache/background jobs — applicable as negative coverage:** manifest remains exactly `workbench`/`workbench_relation`; worker registry remains the existing six instances; evaluator/ACL save contain no new cache/outbox/dirty/read-model path.
- **5. Frontend interaction — not applicable:** this plan intentionally owns backend/inventory only; frontend and Browser permission coverage belongs to 13-11.
- **6. End-to-end business flow — applicable at backend integration boundary:** real request dispatch covers identity → evaluator → global/module guard → response and ACL revoke → next session/API decision. No production/OA mutation was authorized.
- **7. Existing regression — applicable/covered:** focused session/auth/settings/OA/App Health/data-reset/page contracts and lint all pass.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_session_api tests.test_auth_guard tests.test_route_access_policy tests.test_oa_pending_payment_api tests.test_app_health_api tests.test_oa_applicant_credentials_api tests.test_settings_data_reset_job -v` — 91 passed.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory tests.test_app_settings_service tests.test_oa_role_sync_service -v` — 82 passed.
- `bash scripts/verify.sh lint` — passed.
- `git diff --check HEAD~2..HEAD` — passed.
- Full backend discovery was not required by this plan; its two focused backend commands are the specified acceptance gate.

## Deviations from Plan

None - the plan was executed as a test/inventory-only closure with no production implementation changes.

The tasks were marked `tdd=true`, but their planned output was regression/inventory tests over behavior already delivered by dependency plans 07/08/10. Baseline tests confirmed that behavior before edits, so no artificial failing production change or compatibility shim was introduced.

## Documentation Impact

Long-term docs were intentionally not changed. This plan changes only regression ownership; 13-04/12/13/14 must rerun the single inventory guard and extend its explicit documentation allowlists only when their new long-term facts are proven.

## Authentication Gates

None.

## Known Stubs

None. Empty collections and `None` values found by the stub scan are test accumulators, optional fake inputs or expected empty runtime evidence; none flow to a production UI or block the plan goal.

## Threat Flags

None. All changes are tests; no endpoint, auth path, file-access path, schema or trust-boundary implementation was introduced.

## Remaining Risk

- Browser/UI permission behavior is outside this backend plan and remains owned by 13-11.
- Explicit historical/docs allowlists are intentionally narrow; later authorized docs changes must update this one scanner rather than duplicate its logic.

## User Setup Required

None.

## Next Phase Readiness

- 13-04/12/13/14 can reuse the single inventory command without copying scanner logic.
- 13-11 can independently verify frontend/Browser behavior; no frontend files were touched here.
- No blocker, production mutation, push, deploy or 13-11 work occurred.

## Self-Check: PASSED

- All eight modified test files and this SUMMARY exist.
- Task commits `91c09a4dd` and `ba7be0b8d` exist in repository history.
- No deleted tracked file, untracked runtime artifact, goal-blocking stub or new threat surface remains.

---
*Phase: 13-settings-improvements*
*Completed: 2026-08-02*
