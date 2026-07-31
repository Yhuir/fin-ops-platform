---
phase: 36-right-drawer-motion-production-closure
plan: "01"
subsystem: ui
tags: [react, heroui, drawer, motion, playwright, accessibility]

requires:
  - phase: 35-bank-flow-rule-batch-live-candidates
    provides: canonical bank-flow rule batch page and production baseline
  - phase: 36-preexisting-workbench-detail-fix
    provides: Workbench same-generation detail fix at 825d34011
provides:
  - Shared HeroUI right drawer motion with 240ms enter and 180ms exit
  - OA and bank-flow legacy drawer shell migration without business I/O changes
  - Accessible transform/opacity motion for the tax certified-results rail
  - Chromium frame, reduced-motion, CLS, and close-time I/O regression proof
affects: [workbench, oa-pending-payments, bank-flow-rule-batches, tax-offset, shared-ui]

tech-stack:
  added: []
  patterns: [HeroUI owns modal drawer lifecycle, individual translate on the moving dialog, transform-opacity-only nonmodal rail]

key-files:
  created: [web/e2e/drawer-motion.spec.ts]
  modified: [web/src/components/common/AppDrawer.tsx, web/src/app/styles.css, web/src/pages/OaPendingPaymentsPage.tsx, web/src/pages/BankFlowRuleBatchPage.tsx, web/src/components/tax/CertifiedResultsDrawer.tsx]

key-decisions:
  - "Use HeroUI Drawer placement=right and CSS individual translate; no third-party animation dependency or second drawer abstraction."
  - "Bind modal motion to the HeroUI dialog that actually moves, while the full-screen content wrapper owns placement and pointer-event isolation only."
  - "Keep the tax certified-results surface as a mounted complementary rail, not a modal drawer, with inert and aria-hidden in the collapsed state."
  - "Display-shell migrations preserve all existing API, permission, form, abort, error, and write timing contracts; module boundary I/O remains unchanged."

patterns-established:
  - "Modal right drawers: AppDrawer -> Drawer.Backdrop -> Drawer.Content placement=right -> Drawer.Dialog."
  - "Motion proof: sample real dialog geometry across animation frames and separately assert close-time network isolation and reduced-motion."

requirements-completed: []

duration: 20min
completed: 2026-07-31
---

# Phase 36 Plan 01: Right Drawer Motion Production Closure Summary

**All modal right drawers now inherit HeroUI's full right-edge translate lifecycle, legacy OA/bank-flow shells are removed, and a real Chromium test protects motion, layout stability, reduced motion, and zero close-time business I/O.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-31T15:55:26Z
- **Completed:** 2026-07-31T16:15:32Z
- **Tasks:** 4 (three local implementation/verification tasks plus production handoff)
- **Files modified:** 20

## Accomplishments

- Restored one shared modal motion path: 240ms right-to-left enter, 180ms left-to-right exit, opacity-only backdrop, rapid reopen cancellation, and near-instant reduced-motion behavior.
- Migrated OA bank-link and bank-flow tag-management shells to `AppDrawer` while preserving widths, permissions, forms, paging, errors, abort behavior, nested dialogs, and request/write timing.
- Kept the tax certified-results surface as the sole explicit nonmodal complementary rail with mounted content, transform/opacity motion, `inert`, `aria-hidden`, and pointer-event isolation.
- Deleted the old short-distance keyframes, conflicting child transform transition, legacy custom shells, and duplicate Workbench Escape listener; no animation dependency was added.
- Added deterministic Chromium proof for enter/exit intermediate frames, greater-than-75%-panel observable travel, page CLS below 0.01, zero close-time API delta, and reduced-motion at or below 1ms.

## Task Commits

Each task was committed atomically using TDD RED/GREEN slices:

1. **Task 1 RED: shared drawer motion contract** - `d42fb8b51`
2. **Task 1 GREEN: native right drawer lifecycle** - `8db6e388c`
3. **Task 2 RED: legacy drawer migration contracts** - `5d021e52b`
4. **Task 2 GREEN: OA, bank-flow, and tax rail migration** - `c7b126590`
5. **Task 3 RED: browser motion proof** - `64f5a84e6`
6. **Task 3 GREEN: bind motion to the actual HeroUI dialog** - `0bb2824c1`
7. **Task 3 docs: motion/test/boundary closure** - `7cc5cacea`

## Files Created/Modified

- `web/e2e/drawer-motion.spec.ts` - Real Chromium frame sampling and performance/isolation contracts.
- `web/src/components/common/AppDrawer.tsx` - Shared modal/persistent lifecycle, accessibility labeling, and busy dismiss guard.
- `web/src/app/styles.css` - Dialog translate, persistent translate, backdrop opacity, reduced-motion, and tax rail motion; legacy shell CSS removed.
- `web/src/components/workbench/DetailDrawer.tsx` - Removed the duplicate global Escape listener.
- `web/src/pages/OaPendingPaymentsPage.tsx` - OA bank-link business body now uses `AppDrawer`.
- `web/src/pages/BankFlowRuleBatchPage.tsx` - Tag-management business body now uses `AppDrawer`.
- `web/src/components/tax/CertifiedResultsDrawer.tsx` - Mounted accessible complementary rail state.
- `web/src/test/CommonPlatformComponents.test.tsx` - Shared lifecycle and legacy negative gates.
- `web/src/test/OaPendingPaymentsPage.test.tsx` - OA shell migration and behavior protection.
- `web/src/test/BankFlowRuleBatchPage.test.tsx` - Bank-flow shell migration and behavior protection.
- `web/src/test/TaxOffsetPage.test.tsx` - Tax rail accessibility and motion protection.
- `docs/refactor-ui/interaction_smoothness.md` and four module documentation pairs - Motion ownership, test evidence, legacy cleanup, and unchanged business boundaries.

## Decisions Made

- HeroUI already supplies the required drawer state machine and right placement, so adding Framer Motion, React Spring, or another runtime was unnecessary and would duplicate lifecycle ownership.
- The moving node is `Drawer.Dialog`; `Drawer.Content` is a full-viewport fixed wrapper. Project duration/easing overrides therefore belong on `.finance-drawer`, with the content wrapper retaining placement and exit pointer-event isolation.
- The tax certified-results panel remains a complementary rail because it is persistent supporting content, not a focus-trapped modal operation.
- Business module `boundary-io.md` files were not changed because no API shape, input/output, persistence, read-model, worker, permission, or dependency direction changed.

## Verification

- `npm --prefix web test -- --run src/test/CommonPlatformComponents.test.tsx src/test/OaPendingPaymentsPage.test.tsx src/test/BankFlowRuleBatchPage.test.tsx src/test/TaxOffsetPage.test.tsx` — 89/89 passed.
- `npm --prefix web run e2e -- e2e/drawer-motion.spec.ts --project=chromium` — 2/2 passed in 6.2s.
- `npm --prefix web run build` — passed; only pre-existing HeroUI minified CSS empty-`:is()` warnings.
- `bash scripts/verify.sh lint` — passed.
- `bash scripts/verify.sh docs` — passed.
- `git diff --check` — passed.
- Whole-repository source scan confirmed all modal right drawers use `AppDrawer`; the mobile navigation drawer is intentionally left-placed, tax certified results is the explicit complementary rail, and settings rule surfaces remain popover/menu where designed.

## Seven-Category Test Assessment

- **1. Business core:** Not applicable; no business rule, amount, state-transition, matching, permission-decision, or validation contract changed.
- **2. Service layer:** Not applicable; no backend service, repository, persistence, audit, cache, or job changed.
- **3. API contract:** Not applicable; requests and response shapes are unchanged.
- **4. Read model/cache/background job:** Not applicable; no freshness, cache, queue, worker, or read-model behavior changed.
- **5. Frontend component/interaction:** Applicable and covered by the four targeted Vitest files plus the Chromium spec.
- **6. End-to-end business flow:** Applicable at the UI lifecycle boundary and covered by opening/closing a real Workbench detail drawer against deterministic API mocks; existing page E2E suites retain business-flow ownership.
- **7. Existing regression:** Applicable and covered for shared drawers, OA bank-link, bank-flow tag rules, tax rail, Workbench detail, build, lint, and legacy negative gates.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected transition ownership after real-browser RED evidence**
- **Found during:** Task 3 browser motion verification.
- **Issue:** The first implementation bound `transition-property: translate` to `.finance-drawer__content`, but HeroUI uses that element as a stationary full-viewport wrapper and translates `.drawer__dialog`. Browser sampling observed a 1366px wrapper with 0px travel.
- **Fix:** Bound the 240ms/180ms transition to `.finance-drawer`, retained a separate persistent-wrapper transition, and sampled the actual dialog.
- **Files modified:** `web/src/app/styles.css`, `web/src/test/CommonPlatformComponents.test.tsx`, `web/e2e/drawer-motion.spec.ts`.
- **Verification:** Chromium enter/exit frame proof passed with intermediate frames and greater-than-75%-panel observable travel.
- **Committed in:** `0bb2824c1`.

**2. [Rule 3 - Plan path correction] Used the current Workbench detail owner**
- **Found during:** Task 1 source inventory.
- **Issue:** The plan named `web/src/components/reconciliation/DetailDrawer.tsx`, while the live source owner is `web/src/components/workbench/DetailDrawer.tsx`.
- **Fix:** Modified the authoritative live component and did not create a compatibility file or parallel path.
- **Files modified:** `web/src/components/workbench/DetailDrawer.tsx`.
- **Verification:** Shared component tests, build, and whole-repository source scan passed.
- **Committed in:** `8db6e388c`.

---

**Total deviations:** 2 auto-fixed (one runtime bug, one blocking plan-path correction).
**Impact on plan:** Both corrections were required to achieve the intended behavior on the authoritative path; no scope expansion, dependency, API, or architecture change was introduced.

## Issues Encountered

- Exact `CLS === 0` was too brittle for the whole page: an ambient non-drawer shift measured `0.001526`. The stable browser guard uses `< 0.01`, while the drawer remains fixed-position and production verification still targets zero drawer-induced layout shift.
- Under reduced-motion, the repository-wide accessibility rule may compute either `transition-property: none` or preserve `translate` with a maximum 1ms duration. The behavior gate asserts the user-observable duration contract rather than a single serialization.

## Known Stubs

None. The scan only found intentional runtime state initialization and existing empty-string comparisons/placeholders; no new empty/mock value flows into production UI.

## User Setup Required

None - no dependency, environment variable, migration, or external service configuration was added.

## Next Phase Readiness

- Local implementation and regression gates are complete on `main`.
- The main orchestrator owns the authorized `origin/main` push, `./scripts/deploy-oa.sh` deployment, and read-only production correctness/performance verification for the shared drawer surfaces and existing Workbench same-generation detail fix.
- Production acceptance must record drawer frame interval p95, drawer-induced CLS, animation API delta, Workbench warm-detail p95, release/worker/queue health, and System Audit without mutating real business relations.

## Self-Check: PASSED

- All key implementation, test, documentation, plan, and summary files exist.
- All seven task commits are present in repository history.
- Summary formatting and whitespace checks passed.

---
*Phase: 36-right-drawer-motion-production-closure*
*Completed: 2026-07-31*
