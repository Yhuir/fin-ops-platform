---
phase: 30-workbench-concurrent-recovery-performance
plan: "03"
subsystem: reconciliation-workbench-frontend
tags: [react, typescript, relation-preview, concurrency, accessibility, security, tdd]

requires:
  - phase: 30-02
    provides: bounded confirm/withdraw preview selection DTO with generation proof
provides:
  - preview-only adapter for real selection DTOs without expanding the formal paired/unpaired page model
  - one synchronous confirm/withdraw pending boundary with duplicate prevention and stale response dropping
  - module-owned safe Workbench API errors with stable Chinese messages and retained support fields
  - focused component and Chromium regression coverage for confirm/withdraw preview recovery
affects: [30-04, reconciliation-workbench, relation-preview, frontend-api-errors]

tech-stack:
  added: []
  patterns:
    - preview-only DTO adapter isolated from ordinary Workbench group mapping
    - synchronous ref guard paired with renderable React pending state
    - context-key validation before installing asynchronous preview responses
    - allowlisted user messages with typed machine support fields

key-files:
  created: []
  modified:
    - web/src/features/workbench/api.ts
    - web/src/pages/ReconciliationWorkbenchPage.tsx
    - web/src/components/workbench/WorkbenchZone.tsx
    - web/src/test/apiMock.ts
    - web/src/test/WorkbenchApi.test.ts
    - web/src/test/WorkbenchSelection.test.tsx
    - web/src/test/WorkbenchZone.test.tsx
    - web/e2e/fixtures/apiMocks.ts
    - web/e2e/fixtures/workbenchFlow.ts
    - web/e2e/workbench-relation-fanout.spec.ts
    - web/e2e/workbench-withdraw-flow.spec.ts
    - docs/modules/reconciliation-workbench/boundary-io.md
    - docs/modules/reconciliation-workbench/state-machine.md
    - docs/modules/reconciliation-workbench/tests.md

key-decisions:
  - "Accept group_type=selection only inside relation preview mapping and only when zone/status are both unpaired; ordinary Workbench mappers remain strict."
  - "Use one synchronous request-kind ref plus React pending state for confirm and withdraw so toolbar and inline entry points share duplicate prevention without a new state library."
  - "Install a preview response only when selection context and active read-model version still match the request snapshot."
  - "Trust only WorkbenchApiError for user-visible API messages; backend message/raw text/parser exceptions are never echoed."

patterns-established:
  - "Preview pending state is idle -> confirm|withdraw -> idle and does not alter the formal drawer submit/sync/load state machine."
  - "Workbench API errors preserve status/code/requestId while deriving UI text solely from an approved code/status map."

requirements-completed: [RELCL-05, RELVIS-01, RELVIS-08, RMF-08]

duration: 24min
completed: 2026-07-26
---

# Phase 30 Plan 03: Relation Preview Frontend Recovery Summary

**Confirm/withdraw previews now consume the real preview-only selection DTO, expose immediate accessible pending feedback, reject duplicates and stale responses, and surface only approved Chinese errors.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-07-25T18:49:09Z
- **Completed:** 2026-07-25T19:13:23Z
- **Tasks:** 3
- **Files modified:** 14 implementation/test/documentation files

## Accomplishments

- Added a relation-preview-only group adapter that maps `selection + zone/status=unpaired` into the existing unpaired page model while preserving `rawGroupType=selection`; paired relation previews require `relation + zone/status=paired`.
- Kept combined initial and ordinary group-page mapping fail-closed for `selection`, so the formal page state machine remains exactly paired/unpaired.
- Unified confirm and withdraw preview requests behind one synchronous duplicate guard and renderable `relationPreviewRequestKind` state.
- Added next-render spinner, busy label, disabled, `aria-disabled` and `aria-busy` feedback without timers or another state library.
- Dropped successful preview responses after selection or active read-model version drift, while preserving the existing formal preview drawer submit/sync/load flow.
- Added `WorkbenchApiError` with stable code/status message mapping and retained `status`, `code` and `requestId`; unknown backend English, raw response bodies and JavaScript/parser exceptions no longer reach the UI.
- Updated deterministic Browser fixtures to use real preview selection groups and covered confirm/withdraw pending, successful drawer completion and safe failure recovery in the two requested Chromium specs.
- Synchronized the reconciliation-workbench boundary, state-machine and test-matrix documentation required by `AGENTS.md`.

## Task Commits

Each TDD gate and production task was committed atomically:

1. **Task 1 RED: real selection DTO adapter coverage** - `5d00f3614` (`test`)
2. **Task 1 GREEN: preview-only selection adapter** - `dddfb6536` (`feat`)
3. **Task 2 RED: pending, duplicate and stale-response coverage** - `8920ec0ca` (`test`)
4. **Task 2 GREEN: shared relation preview request boundary** - `d0854de54` (`feat`)
5. **Task 3 RED: safe error and Browser recovery coverage** - `98b4b9d60` (`test`)
6. **Task 3 GREEN: typed safe errors and real Chromium fixtures** - `e4beb6809` (`feat`)

Additional AGENTS-required contract documentation:

- `36d418cbd` - document preview mapping, pending state and safe error contracts

## TDD Gate Compliance

- **Task 1 RED:** confirm-before and withdraw-after real selection fixtures, illegal selection states and the ordinary mapper strictness tests failed before the preview adapter existed.
- **Task 1 GREEN:** the preview-only adapter made all 33 Workbench API tests pass without changing `WorkbenchGroupType`.
- **Task 2 RED:** next-render busy controls, duplicate POST count and stale-response tests failed while the page still issued independent requests.
- **Task 2 GREEN:** the shared pending/ref guard made all 79 Selection and Zone tests pass.
- **Task 3 RED:** typed error, approved-message and raw-sentinel tests failed against the prior backend-message passthrough.
- **Task 3 GREEN:** the safe error boundary and deterministic Browser fixtures made all 123 focused Vitest tests, all 3 requested Chromium tests and the production build pass.
- No separate behavior-neutral refactor commit was needed.

## Files Created/Modified

- `web/src/features/workbench/api.ts` - preview-only selection/relation mapper and typed safe Workbench API errors.
- `web/src/pages/ReconciliationWorkbenchPage.tsx` - shared confirm/withdraw request boundary, stale-success response check and safe UI error trust boundary.
- `web/src/components/workbench/WorkbenchZone.tsx` - accessible primary selection pending presentation.
- `web/src/test/apiMock.ts` - real confirm-before and withdraw-after selection fixtures.
- `web/src/test/WorkbenchApi.test.ts` - selection validation, ordinary mapper strictness, safe error matrix and support-field coverage.
- `web/src/test/WorkbenchSelection.test.tsx` - duplicate prevention, stale response, failure recovery, sentinel non-disclosure and formal flow regression tests.
- `web/src/test/WorkbenchZone.test.tsx` - next-render accessible busy control contract.
- `web/e2e/fixtures/apiMocks.ts` - real preview selection/relation DTOs, deterministic preview delays and safe failure fixture.
- `web/e2e/fixtures/workbenchFlow.ts` - pending-state observation hook inside the existing confirm helper.
- `web/e2e/workbench-relation-fanout.spec.ts` - confirm pending and real selection end-to-end regression.
- `web/e2e/workbench-withdraw-flow.spec.ts` - withdraw pending, completion and safe failure recovery regression.
- `docs/modules/reconciliation-workbench/boundary-io.md` - frontend preview DTO, duplicate and error trust boundaries.
- `docs/modules/reconciliation-workbench/state-machine.md` - `idle -> pending(confirm|withdraw) -> idle` request state.
- `docs/modules/reconciliation-workbench/tests.md` - focused component/API/Browser verification matrix.

## Decisions Made

- The preview adapter is deliberately private to `mapRelationPreview`; adding `selection` to the public page group type or normal mapper was rejected.
- A ref owns same-tick mutual exclusion while React state owns UI presentation. This closes the click/render race without timers, global state or additional dependencies.
- The stale check uses the active month, active read-model version and both selection row-id sets. A response is installed only when this context remains unchanged.
- API payload `message` and response text are diagnostic inputs, not trusted UI copy. User messages come only from a maintained code/status allowlist, with `requestId` appended when available.
- Existing relation preview drawer state and submit behavior remain authoritative; request pending is a separate pre-drawer state.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test Fixture Bug] Updated legacy custom preview fixtures to the real zone/status contract**
- **Found during:** Task 2 full focused regression
- **Issue:** Three older Selection tests supplied relation/unpaired preview groups without the now-required preview `zone/status`, so the strict adapter correctly rejected them.
- **Fix:** Updated only those preview fixtures to `selection + unpaired` or `relation + paired` as appropriate.
- **Files modified:** `web/src/test/WorkbenchSelection.test.tsx`
- **Verification:** All 66 Selection tests pass.
- **Committed in:** `d0854de54`

**2. [Rule 1 - Test Accessibility Query] Corrected failure-dialog assertions to the existing accessible name**
- **Found during:** Task 3 safe-error tests
- **Issue:** The existing `ActionStatusModal` accessible name is `操作状态弹窗`; new tests initially queried the visual title `操作失败`.
- **Fix:** Query the established accessible dialog name and assert `操作失败` as visible title content.
- **Files modified:** `web/src/test/WorkbenchSelection.test.tsx`, `web/e2e/workbench-withdraw-flow.spec.ts`
- **Verification:** Focused Vitest and Chromium failure-recovery tests pass.
- **Committed in:** `e4beb6809`

**3. [Rule 2 - AGENTS.md Contract Maintenance] Updated affected module documentation**
- **Found during:** Closeout docs impact assessment
- **Issue:** The preview input mapper, request state, error trust boundary and test matrix are module facts that `AGENTS.md` requires to remain current.
- **Fix:** Updated reconciliation-workbench boundary I/O, state machine and test documentation.
- **Files modified:** three files under `docs/modules/reconciliation-workbench/`
- **Verification:** Documentation changes are scoped to the implemented contracts and `git diff --check` passes.
- **Committed in:** `36d418cbd`

---

**Total deviations:** 3 auto-fixed (2 Rule 1, 1 Rule 2)
**Impact on plan:** The fixture/query fixes enforce the planned strict contract and repository documentation rules; no product, API, schema, worker or infrastructure scope was added.

## Issues Encountered

- The first confirm Browser pending assertion observed the whole helper from outside and could miss the short deterministic pending window. The existing helper was minimally extended with an optional pending observer executed immediately after the click and before awaiting the preview response; no production timing behavior changed.
- Production build succeeds with pre-existing generated CSS selector and main bundle-size warnings. They are recorded in `deferred-items.md`; no dependency, generated CSS or unrelated bundle structure was changed.

## Known Stubs

None. No placeholder production data, mock-only runtime branch or unwired component was introduced.

## Threat Flags

None. No endpoint, auth path, file access, schema or new trust boundary was added. The change narrows an existing UI trust boundary by rejecting invalid preview DTOs and preventing raw server diagnostics from reaching users.

## Verification

- `cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx src/test/WorkbenchZone.test.tsx` — 123 passed.
- `cd web && npm run e2e -- e2e/workbench-relation-fanout.spec.ts e2e/workbench-withdraw-flow.spec.ts --project=chromium` — 3 passed in Chromium.
- `cd web && npm run build` — TypeScript project build and Vite production build passed.
- `git diff --check` — passed before each production/documentation commit.
- Per instruction, the unrelated 183-test Browser suite, full CI, deploy, push and backend tests were not run.

## Test Coverage Categories

1. **Business core unit tests — applicable:** strict selection/relation zone validation, duplicate input behavior and stale context handling are covered.
2. **Service-layer tests — not applicable:** no backend service, repository, audit store, queue or persistent side effect changed.
3. **API contract tests — applicable:** real preview DTO shapes, invalid groups, stable status/code messages and `requestId` support fields are covered.
4. **Read model/cache/background jobs — applicable in part:** active read-model version drift prevents stale preview installation; no cache, queue or worker changed.
5. **Frontend component and interaction tests — applicable:** next-render pending accessibility, duplicate clicks, clear-selection drift, failure recovery and formal drawer regression are covered.
6. **End-to-end business-flow integration — applicable:** confirm fanout and withdraw/recovery flows pass with real preview selection fixtures in Chromium.
7. **Existing feature regression — applicable:** ordinary page mapping remains strict, formal submit drawer behavior is unchanged, read-only/settings/data-reset/error-state regressions remain green in the focused Selection suite.

## User Setup Required

None - no dependency, environment variable, migration, state library or external service configuration was added.

## Next Phase Readiness

- Plan 30-04 can verify the full Phase 30 matrix against a frontend that matches the bounded backend preview DTO and closes duplicate/stale/error races.
- No implementation blocker remains. Production latency and full-system evidence remain Plan 30-04 scope; this plan made no deploy or production claim.

## Self-Check: PASSED

- All implementation, test, Browser fixture, module documentation and summary files listed above exist.
- Task/TDD/documentation commits `5d00f3614`, `dddfb6536`, `8920ec0ca`, `d0854de54`, `98b4b9d60`, `e4beb6809` and `36d418cbd` are present in git history.

---
*Phase: 30-workbench-concurrent-recovery-performance*
*Completed: 2026-07-26*
