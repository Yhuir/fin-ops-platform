---
phase: 13-settings-improvements
plan: "14"
subsystem: deployment-security
tags: [access-control, oa-router, release-fingerprint, zero-reupload, playwright]

# Dependency graph
requires:
  - phase: 13-settings-improvements
    plan: "13"
    provides: OA/app-shell/deploy ownership boundaries and candidate release contract
provides:
  - exact permission-bearing YNSYLP006 preflight and fresh OA router post-deploy evidence
  - post-migration 0132/CHECK assertion before candidate runtime synchronization
  - deterministic uploaded source/helper/migration fingerprints for zero-reupload activation
  - exact auth-gate browser error classification with protected dashboard non-call proof
affects: [13-15, production-bootstrap, release-activation, oa-access-control]

# Tech tracking
tech-stack:
  added: []
  patterns: [candidate-recomputed source fingerprints, response-bound auth error allowlists, fail-closed database guards]

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/tools/settings_access_control_preflight.py
    - deploy/oa/bin/finops-deploy-control.sh
    - scripts/deploy_oa.py
    - scripts/with-production-admin-token.sh
    - web/e2e/app-shell.spec.ts

key-decisions:
  - "Candidate eligibility requires the representative bearer to be exactly permission-bearing YNSYLP006 while its APP tier starts denied."
  - "activate-existing trusts only a clean 40-hex commit whose uploaded source tree, deploy helper and migration hashes are recomputed on the release host."
  - "Expected auth browser errors are allowed only for exact endpoint/status pairs; every other HTTP, console, page or request error remains fail closed."

patterns-established:
  - "OA router visibility is freshly sampled at admin, denied, full, read and final-restore stages instead of inferred from APP session state."
  - "Zero-reupload activation accepts connection coordinates but rejects every build, upload, replacement or runtime-worker bootstrap option."

requirements-completed: [PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03]

# Metrics
duration: 40min
completed: 2026-08-02
---

# Phase 13 Plan 14: Candidate Release Preparation Summary

**Secret-safe YNSYLP005/006 evidence, fresh OA router restore checks and recomputed source/helper/migration fingerprints now gate a single zero-reupload candidate activation path.**

## Performance

- **Duration:** 40 min
- **Started:** 2026-08-02T09:13:30Z
- **Completed:** 2026-08-02T09:53:45Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Preflight now requires exact `YNSYLP005/admin` plus distinct, permission-bearing `YNSYLP006` whose APP access starts denied; evidence continues to expose salted facts rather than raw identities or tokens.
- Post-deploy now samples fresh OA router visibility across initial denied, full, read, denied and finally-restored states, and fails when router/session/OA role restoration is incomplete.
- Release activation runs an independent 0132 migration and validated policy CHECK read-back before runtime sync/install.
- Release archives carry a deterministic source-tree SHA-256; candidate status recomputes source, deploy-control and migration hashes from the already-uploaded release and requires clean commit metadata.
- `--activate-existing` remains one SSH release-gate call with no build, upload, replace, helper self-update or runtime-worker bootstrap path; the local wrapper also rejects reused admin/bearer secrets.
- Full backend, frontend, production build, docs and 168-test browser smoke gates passed without any production SSH, upload, bootstrap or mutation.

## Task Commits

1. **Task 1 RED: candidate ACL release-gate contracts** — `4760bc12f` (`test`)
2. **Task 1 GREEN: preflight/post-deploy/database guards** — `f102add23` (`feat`)
3. **Task 2 RED: exact uploaded candidate activation contracts** — `d0284778a` (`test`)
4. **Task 2 GREEN: deterministic zero-reupload activation** — `c980d2925` (`feat`)
5. **Task 3: exact auth-gate E2E response classification** — `38a3f76bd` (`test`)

Task 3's env and OA membership SQL already matched the required fixed selector and three-role ownership contract, so no redundant asset rewrite was made.

## Files Created/Modified

- `backend/src/fin_ops_platform/tools/settings_access_control_preflight.py` — exact representative bearer, fresh OA router transition/restore evidence and database-guard CLI.
- `deploy/oa/bin/finops-deploy-control.sh` — OA base URL wiring, post-migration 0132/CHECK assertion and remote source fingerprint verification.
- `deploy/oa/README.md` — exact YNSYLP006, router and pre-runtime database-gate runbook contract.
- `scripts/deploy_oa.py` — deterministic archive source digest and strict activate-existing option contract.
- `scripts/with-production-admin-token.sh` — distinct admin/bearer secret enforcement.
- `tests/test_settings_access_control_preflight.py` — preflight, post-deploy router and database-guard behavior coverage.
- `tests/test_deploy_oa_script.py` — exact fingerprint, zero-reupload, option isolation and dual-token coverage.
- `web/e2e/app-shell.spec.ts` — endpoint/status-bound expected auth failures while preserving strict browser error capture.

## Decisions Made

- Hash archive paths, entry types, permission modes and payload bytes while excluding `RELEASE.json`, generated caches and implicit `src/web`/`src/deploy` container directories; this makes local and extracted-tree fingerprints deterministic without self-reference.
- Treat old releases without the new exact source capability as unsafe rollback targets; failed activation therefore remains in maintenance for forward repair rather than restoring an unverifiable binary.
- Keep expected denied/expired browser failures narrow: session and global active-job auth responses are explicit, while protected AppHealth dashboard requests must remain at zero.

## Test Coverage

- **1. Business core unit — applicable and covered:** canonical ACL normalization, protected admin, exact YNSYLP006, invalid/colliding identities, role transitions and restoration are covered by service/preflight tests.
- **2. Service/deployment layer — applicable and covered:** OA sync compensation, migration guard, deterministic metadata, candidate recomputation, activation ordering and zero-reupload behavior are covered.
- **3. API contract — applicable and covered:** session tiers, direct authorization, admin-only routes, generic-save isolation and exact auth HTTP status behavior are asserted.
- **4. Read model/cache/background jobs — regression-only and covered:** inventory/full backend/E2E verify existing worker/read-model boundaries; this plan adds no read model, queue, cache or worker.
- **5. Frontend interaction — applicable and covered:** 36 targeted Vitest tests and 919 full Vitest tests cover session gate, settings visibility, route host and existing pages.
- **6. End-to-end business flow — applicable and covered locally:** the 8-test permission matrix and final 168-test deterministic smoke suite cover denied/read/full/admin navigation and protected API behavior.
- **7. Existing feature regression — applicable and covered:** 3,847 backend tests, full frontend/build, docs, lint and browser smoke protect existing APIs, pages, permissions, workers and release tooling.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_settings_access_control_preflight tests.test_deploy_oa_script tests.test_postgres_migrations -v` — 122 passed.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory tests.test_app_settings_service tests.test_oa_role_sync_service tests.test_settings_access_control_preflight tests.test_deploy_oa_script -v` — 133 passed.
- `bash scripts/verify.sh lint` — passed.
- targeted frontend Vitest command from the plan — 36 passed.
- `npx playwright test e2e/permissions-role-matrix.spec.ts` — 8 passed.
- `bash scripts/verify.sh all` — backend 3,847 passed (52 external-infrastructure skips); its first frontend run hit one load-timing failure in `App.test.tsx`.
- `bash scripts/verify.sh frontend` — retry passed 919/919 and production build passed, confirming the prior failure was transient; no unrelated UI change was made.
- targeted denied/expired app-shell E2E — 2 passed after exact response classification.
- `bash scripts/verify.sh e2e` — final 168/168 passed.
- `bash scripts/verify.sh docs`, shell syntax checks and `git diff --check` — passed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Bound expected auth resource errors to exact endpoint/status pairs**
- **Found during:** Task 3 full browser smoke.
- **Issue:** The generic browser-error collector treated intentional session/global-shell 401/403 responses as unexpected console failures, leaving the deterministic smoke gate at 166/168 despite correct denied/expired UI and zero protected-dashboard calls.
- **Fix:** Added response-level endpoint/status classification for only `/api/session/me` and `/api/background-jobs/active`, retained strict capture for every other response/console/page/request error, and asserted both auth calls plus zero AppHealth dashboard calls.
- **Files modified:** `web/e2e/app-shell.spec.ts`
- **Verification:** targeted 2/2 and full smoke 168/168 passed.
- **Committed in:** `38a3f76bd`

---

**Total deviations:** 1 auto-fixed blocking test-contract issue.
**Impact on plan:** Closed the required full local gate without changing production frontend/backend behavior or broadening error suppression.

## Issues Encountered

- The first full Vitest run reported one `App.test.tsx` settings-tree load timing failure under suite load; the planned targeted run and the full frontend retry both passed. No product or test change was made for this transient result.
- PostgreSQL/RabbitMQ integration tests were skipped by the repository suite because their disposable external test URLs were not configured; all deterministic tests ran.
- `gsd-tools` was not on `PATH`; the same SDK was invoked through `node /Users/yu/.codex/gsd-core/bin/gsd-tools.cjs`.

## Documentation Impact

Updated only the canonical `deploy/oa/README.md` runbook because the release evidence/order contract changed. Long-lived module boundaries from 13-13 did not change.

## Authentication Gates

None. No production credential was requested or used.

## Known Stubs

None. The diff stub scan found no new TODO/FIXME/placeholder/empty rendering path.

## Threat Flags

None. Source hashing, token separation and auth response handling implement the plan's T13-53/T13-54/T13-55 mitigations; no unplanned endpoint, schema, auth path or trust boundary was introduced.

## User Setup Required

None for this local preparation plan. Real production candidate upload, manual-root helper bootstrap, fresh token preflight, activation and post-deploy evidence remain explicitly reserved for 13-15/13-05.

## Next Phase Readiness

- Local candidate tooling and deterministic gates are ready for the controlled 13-15 production bootstrap/preflight checkpoint.
- Production DB/OA/session/router/latency facts are still unknown and must be collected by approved remote artifacts; this Summary makes no production-pass claim.
- No local blocker remains.

## Self-Check: PASSED

- All 8 modified implementation/test/runbook files and this Summary exist.
- Task commits `4760bc12f`, `f102add23`, `d0284778a`, `c980d2925` and `38a3f76bd` exist in current history.
- No tracked deletion, generated test artifact, secret, target-blocking stub or unplanned threat surface remains.

---
*Phase: 13-settings-improvements*
*Completed: 2026-08-02*
