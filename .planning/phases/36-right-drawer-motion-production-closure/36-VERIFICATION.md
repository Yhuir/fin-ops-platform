---
phase: 36-right-drawer-motion-production-closure
verified: 2026-07-31T17:37:27Z
status: gaps_found
score: 5/6 must-haves verified
overrides_applied: 0
gaps:
  - truth: "Targeted frontend/backend gates, one pushed main deployment, authenticated Workbench detail probes and browser motion measurements prove correctness, page isolation and production performance."
    status: failed
    reason: "The local implementation and regression gates pass, but the remote main branch still points to 825d34011 while local HEAD 18cee1a97 is 21 commits ahead. No deployed release SHA, authenticated production probe result, production browser measurement, or production health evidence exists in the phase artifacts."
    artifacts:
      - path: ".planning/phases/36-right-drawer-motion-production-closure/36-01-SUMMARY.md"
        issue: "Contains only an explicit orchestrator handoff for push, deploy, and production verification; it records no completed external closure evidence."
      - path: "scripts/deploy-oa.sh"
        issue: "Canonical deployment entry point exists, but this verification did not deploy and no Phase 36 deployment result is recorded."
    missing:
      - "Push the approved Phase 36 candidate (currently local HEAD 18cee1a97) to origin/main and record the exact release SHA."
      - "Deploy that exact SHA with ./scripts/deploy-oa.sh and record deployment success/health evidence."
      - "Run authenticated read-only production Workbench detail probes for same-generation success, one retry on version conflict, and explicit no-retry unavailable states."
      - "Record production Workbench warm-detail p95 < 1s, drawer frame interval p95 <= 25ms, drawer-induced CLS = 0, animation business-request delta = 0, and queue/worker/System Audit health."
---

# Phase 36: 全站右侧抽屉滑入动效与详情链路生产闭环 Verification Report

**Phase Goal:** Make every right-side drawer enter from the right and exit back to the right through one native HeroUI/CSS motion contract, remove custom drawer shells that bypass it, and release the already-landed Workbench exact-generation detail fix with measured production correctness and performance.
**Verified:** 2026-07-31T17:37:27Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

ROADMAP success criteria are the non-negotiable contract. PLAN truths that restated them were deduplicated; the Workbench same-generation detail truth was retained as additional detail.

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Modal right drawers reuse HeroUI right placement and travel 100% right → 0 → 100% with 240ms enter, 180ms exit, transform-only spatial motion, and reduced-motion support. | ✓ VERIFIED | `AppDrawer.tsx:189-232` is `Drawer.Backdrop -> Drawer.Content placement="right" -> Drawer.Dialog`; `styles.css:10348-10500` owns `translate` at 240/180ms and disables transitions for both reduced-motion mechanisms. The fresh Chromium suite proves >75% panel-width travel, right-edge endpoints, intermediate frames, exit unmount, and <=1ms reduced motion. |
| 2 | OA bank-link and bank-flow tag-management use `AppDrawer` without changing business I/O, permissions, forms, loading/error behavior, write timing, or busy/race handling. | ✓ VERIFIED | OA uses `AppDrawer` at `OaPendingPaymentsPage.tsx:634-741`, retains candidate GET and link POST, blocks every dismiss path while loading/submitting, aborts on close, and rejects stale request generations (`:540-631`). Bank-flow uses `AppDrawer` at `BankFlowRuleBatchPage.tsx:1037-1147`, preserves `min(960px, 92vw)`, permission/dirty grid behavior, GET/PUT flow, request sequencing, CAS version, write then one current-page reload, and busy close lock. Targeted component and Chromium tests pass. |
| 3 | Tax certified-results remains a mounted non-modal complementary rail; only transform/opacity animate, hidden content is inert/non-interactive, focus remains on the stable toggle, and no width/grid animation is introduced. | ✓ VERIFIED | `CertifiedResultsDrawer.tsx:65-99` keeps the `role="complementary"` aside and body mounted, with stable toggle, `aria-controls`, `aria-expanded`, `aria-hidden`, and `inert`. `styles.css:15702-15723` transitions only opacity/transform and applies pointer-events none plus reduced motion. `TaxOffsetPage.tsx:489-495` feeds real `monthData` rows. Unit and Chromium collapse/expand tests pass without API writes. |
| 4 | Workbench detail reads a complete row from the same active generation, retries a version conflict at most once, and does not blindly retry missing/invariant/unavailable states. | ✓ VERIFIED | Baseline commit `825d34011` is an ancestor of HEAD. `ReconciliationWorkbenchPage.tsx:1455-1532` retries only `workbench_read_model_version_conflict`, reloads once, retries with the refreshed generation, and commits only if request/generation still match. `workbench_query_facade.py:785-883` and `read_models.py:5220-5302` bind detail to active generation, classify missing visible detail as invariant 503, and do no stale-source recheck/enqueue. Fresh focused frontend tests (2) and backend tests (5) pass. |
| 5 | Conflicting legacy animation/shell/Escape ownership is removed; no animation dependency, fallback path, or parallel drawer abstraction exists. | ✓ VERIFIED | Whole-source scan finds direct HeroUI `Drawer` use only in `AppDrawer` and the intentionally left-placed mobile sidebar. All right-drawer consumers route through `AppDrawer` directly or via `PendingInvoiceDrawerFrame`; tax is the explicit complementary rail. No legacy 28px/22px keyframes, `.finance-drawer` `will-change`, OA/bank-flow custom backdrop/aside/close shell, Workbench keydown listener, animation package, or second right-drawer abstraction was found. |
| 6 | Targeted gates plus a pushed `main` deployment and authenticated production probes/measurements prove production correctness, isolation, health, and performance. | ✗ FAILED | Local gates pass, but `git ls-remote origin refs/heads/main` returns `825d34011`; local HEAD is `18cee1a97` and 21 commits ahead. The phase summary explicitly hands push/deploy/production verification to the orchestrator. There is no deployed SHA or production detail/frame/CLS/request/health evidence. |

**Score:** 5/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `web/src/components/common/AppDrawer.tsx` | Unique modal/persistent right-drawer lifecycle and accessibility shell | ✓ VERIFIED | Exists and substantive. Modal branch is wired to HeroUI; persistent branch owns 180ms delayed unmount, rapid reopen cancellation, inert exit state, and focus restoration. Imported by every discovered right-drawer consumer, directly or through the pending-invoice frame. |
| `web/src/app/styles.css` | Native right translate, 240/180ms timing, reduced motion, and tax rail contract | ✓ VERIFIED | Shared drawer motion is translate-only; backdrop is opacity-only. Persistent drawer and tax rail use explicit transform/opacity contracts. No conflicting legacy keyframe or permanent `will-change` remains. |
| `web/e2e/drawer-motion.spec.ts` | Real-browser intermediate-frame, lifecycle, CLS, reduced-motion, and network-isolation evidence | ✓ VERIFIED | Substantive six-test Chromium suite. Fresh execution: 6/6 passed. It covers Workbench modal, bank-flow modal, OA modal busy lifecycle, production persistent drawer, tax rail, and reduced motion. |
| `web/src/pages/OaPendingPaymentsPage.tsx` | OA bank-link body wired into shared shell with original behavior | ✓ VERIFIED | Real candidate rows flow from the existing API; submit uses the existing link API. Abort, request-generation, local error, pagination, permission, and busy contracts are wired and tested. |
| `web/src/pages/BankFlowRuleBatchPage.tsx` | Tag-management body wired into shared shell with existing behavior | ✓ VERIFIED | Real tag selection flows from GET into draft state and PUT/CAS save; stale opening responses cannot overwrite the active drawer; save is disabled while loading/mutating and triggers one current-page reload. |
| `web/src/components/tax/CertifiedResultsDrawer.tsx` | Mounted accessible complementary rail | ✓ VERIFIED | Real tax month rows render through the mounted body. Hidden state is inert/aria-hidden and CSS-isolated; toggle remains the same mounted control through state changes. |
| Workbench detail frontend/backend chain | Same-generation row detail and bounded retry | ✓ VERIFIED | UI, API mapping, facade, PostgreSQL repository, and regression tests are wired. Commit `825d34011` remains in the current history. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `AppDrawer.tsx` | `@heroui/react Drawer` | Backdrop → Content `placement="right"` → Dialog | ✓ WIRED | `gsd-tools query verify.key-links` verified the pattern; live source confirms lifecycle and dismissal guards. |
| `OaPendingPaymentsPage.tsx` | `AppDrawer.tsx` | Display-shell reuse only | ✓ WIRED | Existing GET/POST handlers and state remain in the page body; only shell ownership is shared. |
| `BankFlowRuleBatchPage.tsx` | `AppDrawer.tsx` | Display-shell reuse only | ✓ WIRED | Existing rule state, permissions, CAS save, reload, and nested dialog remain page-owned. |
| `TaxOffsetPage.tsx` | `CertifiedResultsDrawer.tsx` | `monthData` props + session collapse state | ✓ WIRED | Matched/outside-plan rows are real page query data, not empty hardcoded props. |
| `ReconciliationWorkbenchPage.tsx` | Workbench detail API → facade → PostgreSQL repository | Expected active generation and bounded conflict recovery | ✓ WIRED | Detail request passes the list generation; repository checks active generation and returns only matching active-generation rows. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| OA bank-link drawer | `rows`, `selectedBankIds`, `candidateError` | `GET /api/oa-pending-payments/bank-transaction-candidates`; mutation `POST /api/oa-pending-payments/link-bank-transactions` | Yes; response rows populate state and submitted IDs flow to the existing command endpoint. | ✓ FLOWING |
| Bank-flow tag drawer | `tagSelection`, `draftTagRequirements` | `GET/PUT /api/bank-flow-rule-batches/tag-rules` | Yes; GET populates active tags/version and PUT returns the saved versioned selection before current-page reload. | ✓ FLOWING |
| Tax certified rail | `matchedRows`, `outsidePlanRows` | `TaxOffsetPage.monthData.certifiedMatchedInvoices/certifiedOutsidePlanInvoices` | Yes; the canonical tax page response populates `monthData`, then props render without hardcoded empty values. | ✓ FLOWING |
| Workbench detail drawer | `detailedRow`, `detailRow` | `GET /api/workbench/rows/{id}` → `WorkbenchQueryFacade.row_detail` → `read_model.workbench_rows` joined to active generation | Yes; PostgreSQL query returns the actual active-generation row payload and explicitly rejects invariant/missing/unavailable states. | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Phase UI/component regression | `npm test -- --run` on the five reviewed files | 5 files, 118 tests passed | ✓ PASS |
| Workbench bounded detail retry/no-retry | Targeted `WorkbenchSelection.test.tsx` names | 2 passed, 67 skipped | ✓ PASS |
| Workbench backend generation/invariant/unavailable contract | Targeted pytest expression across query facade and SQL runtime | 5 passed, 219 deselected | ✓ PASS |
| Drawer motion/lifecycle in Chromium | `npx playwright test e2e/drawer-motion.spec.ts --project=chromium` | 6 passed | ✓ PASS |
| Production frontend build | `npm run build` | Passed; only existing generated HeroUI empty-`:is()` minifier warnings | ✓ PASS |
| Repository lint gate | `bash scripts/verify.sh lint` | `All checks passed!` | ✓ PASS |
| Documentation gate | `bash scripts/verify.sh docs` | Exit 0 | ✓ PASS |
| Whitespace/diff integrity | `git diff --check` | Exit 0 | ✓ PASS |
| Remote release presence | `git ls-remote origin refs/heads/main`; compare `origin/main..HEAD` | Remote `825d34011`; local `18cee1a97`; 21 commits ahead | ✗ FAIL |

### Probe Execution

| Probe | Command | Result | Status |
| --- | --- | --- | --- |
| Repository probe discovery | `find scripts -path '*/tests/probe-*.sh'` plus PLAN/SUMMARY probe-path scan | No declared or conventional Phase 36 probe scripts | ? SKIP |
| Authenticated production Workbench/browser probes | Orchestrator-owned post-verification operation | Not run; no deployed Phase 36 release exists to probe | ✗ PENDING EXTERNAL CLOSURE |

No executor narration, local browser test, or summary claim was substituted for production probe evidence.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| N/A | `36-01-PLAN.md` | Phase declares `requirements: []`; ROADMAP states there are no new product requirement IDs. | N/A | No orphaned Phase 36 requirement IDs were found in `.planning/REQUIREMENTS.md`. ROADMAP success criteria are assessed directly above. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| — | — | No `TBD`/`FIXME`/`XXX`, placeholder implementation, console-only handler, legacy drawer keyframe/shell, duplicate Workbench Escape listener, hardcoded empty render prop, or animation dependency in the Phase 36 implementation scope. | ℹ️ Info | No blocker. `return null`/empty-array matches were inspected and are intentional unmount/formatter/no-result branches, not stubs. |

### Disconfirmation Pass

- **Partial requirement:** Local correctness is strong, but the roadmap's release/production criterion is observably incomplete; it is the blocker above.
- **Test limitation:** The tax Chromium test proves mounted/inert state and no API writes, but does not directly assert `document.activeElement` after the toggle. The implementation keeps the same toggle node mounted and does not move focus; this supports the truth, while a production keyboard smoke remains appropriate.
- **Uncovered external path:** No local test can establish deployed-device frame p95, production warm-detail latency, deployment health, or authenticated production unavailable-state behavior.

### Human Verification Required

These checks are part of the blocking external closure rather than evidence already earned by the local phase.

#### 1. Exact release and deployment

**Test:** After approval, push the exact Phase 36 candidate to `origin/main`, deploy it with `./scripts/deploy-oa.sh`, and record the remote/deployed SHA.
**Expected:** `origin/main` and the production release report the same approved SHA containing baseline `825d34011` and all Phase 36 fixes.
**Why human/orchestrator:** Push and production deployment are authorized external state changes intentionally owned by the main orchestrator.

#### 2. Production Workbench exact-generation detail

**Test:** With authenticated read-only access, open a visible Workbench row detail, exercise an observed version conflict, and exercise unavailable/missing states without mutating real relations.
**Expected:** Same-generation detail succeeds; a generation conflict reloads and retries once; missing/invariant/unavailable states fail explicitly with no blind retry, stale-source recheck, or refresh enqueue.
**Why human/orchestrator:** Requires deployed production identity, data, auth, and health visibility unavailable to local verification.

#### 3. Production drawer correctness and performance

**Test:** Exercise shared AppDrawer, OA bank-link, bank-flow tag management, persistent drawer, and tax rail on the deployed build while recording frame intervals, drawer-induced CLS, network delta, long tasks, and warm-detail latency.
**Expected:** Full right↔left motion, reduced motion, drawer frame interval p95 <= 25ms, drawer-induced CLS = 0, animation request delta = 0, warm-detail p95 < 1s, and healthy queue/worker/System Audit signals.
**Why human/orchestrator:** Real production load, device rendering, network, workers, and audit state cannot be inferred from deterministic local mocks.

### Gaps Summary

The local implementation goal is achieved: source, wiring, data flow, regression tests, browser motion, Workbench same-generation behavior, build, lint, and docs gates all verify cleanly. The phase goal as written also requires release and measured production closure. That portion is not merely unproven: the authoritative remote branch still lacks all 21 Phase 36 commits. Push, deployment, authenticated read-only probes, and production measurements must be completed before Phase 36 can pass goal-backward verification.

---

_Verified: 2026-07-31T17:37:27Z_
_Verifier: the agent (gsd-verifier)_
