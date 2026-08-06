---
phase: 40-performance-contract-hot-path-closure
plan: "06"
subsystem: frontend-runtime
tags: [workbench, polling, visibility, single-flight, vitest, tdd]

requires:
  - phase: 40-performance-contract-hot-path-closure
    provides: Plan 40-05 exact-scope Workbench public refresh-status self-heal
  - phase: 39-production-runtime-and-search-convergence
    provides: retained Workbench active-generation runtime and lightweight refresh-status API
provides:
  - page-local visible completion-plus-one-second Workbench status polling
  - strict single-flight focus, visibility, entry, and timer trigger coalescing
  - fake-timer request/reload count regressions for every status and network failure
affects: [40-07, 40-08, reconciliation-workbench, browser-performance]

tech-stack:
  added: []
  patterns: [completion-driven polling, visibility pause, lifecycle-owned abort, generation debounce]

key-files:
  created: []
  modified:
    - web/src/pages/ReconciliationWorkbenchPage.tsx
    - web/src/test/WorkbenchSelection.test.tsx
    - web/src/test/WorkbenchApiRuntimePath.test.ts

key-decisions:
  - "Keep the scheduler inside the existing Workbench refresh-status effect and use native setTimeout; no hook, dependency, endpoint, or shared scheduler is needed."
  - "Focus, visible re-entry, entry, and timer expiry share one immediate entry that clears a pending timer and coalesces against the lifecycle-owned in-flight controller."

patterns-established:
  - "A visible Workbench status request schedules its successor only in finally, one second after settle; hidden state owns no timer or new request."
  - "Only a changed fresh generation reaches the existing 300ms debounced combined reload; non-fresh and failed checks remain lightweight status-only I/O."

requirements-completed: []

duration: 10 min
completed: 2026-08-06
---

# Phase 40 Plan 06: Workbench Visible Single-Flight Poller Summary

**The Workbench now checks lightweight refresh status immediately while visible and one second after each completed request, with hidden-page pause, strict single-flight coalescing, and one existing debounced reload per new fresh generation.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-08-06T06:33:58Z
- **Completed:** 2026-08-06T06:43:31Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Deleted the fixed five-second `setInterval` and tick-abort overlap path from the Workbench refresh-status effect.
- Added one page-local completion-driven `setTimeout`: entry, focus, and hidden-to-visible transitions check immediately; visible requests schedule the next check exactly 1000ms after settle.
- Enforced one status GET at a time across timer/focus/visibility collisions, paused timers and new I/O while hidden, and retained lifecycle-owned abort/listener cleanup on unmount.
- Preserved the lightweight `/api/workbench/refresh-status?month=all` contract and the existing generation version ref plus 300ms `scheduleWorkbenchReadModelReload` debounce.
- Added deterministic fake-timer/deferred-network coverage for request counts, 999/1000ms boundaries, hidden pause, visible resume, focus coalescing, cleanup, every non-fresh/error outcome, and one reload per changed fresh generation.

## Task Commits

1. **Task 1 RED: lock visible completion-driven poller behavior** - `928995d52` (test)
2. **Task 1 GREEN: replace interval overlap with visible single-flight scheduling** - `a291f092d` (perf)

## Files Created/Modified

- `web/src/pages/ReconciliationWorkbenchPage.tsx` - replaces the obsolete interval/tick-abort loop with the native page-local visibility-aware completion scheduler.
- `web/src/test/WorkbenchSelection.test.tsx` - covers fake timers, deferred requests, focus/visibility coalescing, hidden/unmount cleanup, status cadence, stable visible rows, and reload counts.
- `web/src/test/WorkbenchApiRuntimePath.test.ts` - guards the refresh-status call as one lightweight runtime-routed GET.

## Decisions Made

- Reused the existing page effect, status mapper, version ref, and reload debounce. A generic polling hook or global scheduler would add surface without improving this single-page contract.
- Hidden transitions clear only the pending timer; an already-running proof remains the single in-flight request and its completion schedules nothing until visibility returns.
- Network failure, `refreshing`, `stale`, `failed`, and `unavailable` all retain the same completion cadence. Only a changed `fresh` version schedules the existing combined reload.
- Docs impact assessment: no module boundary, business state machine, API response shape, permission, read-model scope, worker, queue, cache, or deployment contract changed. This is a page-local scheduling replacement protected by the existing module test matrix; Phase 40-08 owns phase-wide performance documentation, so long-term docs are not applicable here.

## Deviations from Plan

None - plan executed exactly as written.

## TDD Gate Compliance

- RED commit `928995d52`: the focused suite produced two expected failures because focus/timer triggers created overlapping status requests and the old five-second interval did not honor completion-plus-one-second cadence.
- GREEN commit `a291f092d`: the plan gate passed 73/73 after the page-local scheduler replaced the interval path.
- Git history contains the required `test(40-06)` commit followed by the GREEN `perf(40-06)` implementation commit.

## Tests

- **Business core unit:** Not applicable. No amount, relation membership, classification, permission, or finance business rule changed.
- **Service layer:** Not applicable. No backend service, repository, state store, audit, queue, or orchestration code changed.
- **API contract:** Applicable. The runtime-path test asserts exactly one authenticated-runtime GET to the existing refresh-status endpoint, with no full-payload fallback.
- **Read model/cache/background job:** Applicable at the frontend consumer edge. Tests cover every refresh status, thrown requests, changed/same generation behavior, and exactly one debounced payload reload; no cache, worker, queue, or read-model producer changed.
- **Frontend component/interaction:** Applicable. Fake-timer and deferred-network tests cover entry, focus, visibility, 999/1000ms cadence, strict single-flight, hidden pause, stable visible rows, unmount abort, and listener/timer cleanup.
- **End-to-end business flow:** Not applicable to this page-local scheduler plan. Plan 40-07 owns writer-to-proof browser E2E; this plan changes no business write or backend convergence path.
- **Existing feature regression:** Applicable. The full 71-test Workbench selection/interaction file passed alongside the runtime API path tests and production frontend build.

## Verification

- RED: `npm --prefix web test -- --run src/test/WorkbenchSelection.test.tsx src/test/WorkbenchApiRuntimePath.test.ts` - 71 existing tests passed, 2 new expected failures.
- GREEN/final plan gate: the same command - 73/73 passed.
- `npm --prefix web run build` - passed TypeScript and Vite production build; only pre-existing HeroUI generated-CSS minifier warnings remained.
- `git diff --check` - passed.
- Whole-file retirement scan found no `WORKBENCH_REFRESH_POLL_INTERVAL_MS`, `setInterval(pollRefreshStatus)`, tick-time abort, full-payload polling, or replacement fallback in the plan-owned path.

## Known Stubs

None. No placeholder, mock runtime source, TODO/FIXME, empty UI payload, or unwired component was introduced.

## Security

- T-40-06-01: completion-driven scheduling, hidden pause, and strict single-flight bound each client to at most one request per request duration plus one second.
- T-40-06-02: the existing read-model status/write gate remains unchanged, and only a changed fresh generation schedules the established combined reload.
- T-40-06-03: the existing authenticated API client and error mapping remain unchanged; no response, exception, token, or secret is logged.
- No endpoint, authentication path, file access, schema, permission, or trust boundary was introduced; no threat flag is required.

## Remaining Risk

- Target concurrency and same-clock browser commit-to-visible p99 remain intentionally owned by Plans 40-07/40-08. This plan made no push, deployment, production mutation, or production performance claim.

## User Setup Required

None - no dependency, environment variable, migration, worker, or external service configuration was added.

## Next Phase Readiness

- Plan 40-07 can rely on one visible lightweight proof stream per Workbench client and exact changed-generation reload counts for its writer-to-proof E2E matrix.
- Plan 40-08 still owns target-capacity, browser p99, final documentation, release, deployment, and rollback evidence.

## Self-Check: PASSED

- All three plan-owned source/test files and this SUMMARY exist.
- RED `928995d52` and GREEN `a291f092d` resolve in git history in the required order.
- The 73-test plan gate, production frontend build, diff check, and obsolete-path retirement scan passed.
- No plan-owned file deletion, untracked runtime artifact, push, or deployment occurred.

---
*Phase: 40-performance-contract-hot-path-closure*
*Completed: 2026-08-06*
