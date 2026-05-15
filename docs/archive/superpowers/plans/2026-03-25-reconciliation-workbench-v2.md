# Reconciliation Workbench V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production-ready V2 reconciliation workbench and tax-offset page from the approved prototype and requirements document.

**Architecture:** Adopt a small React + TypeScript frontend under `web/` and keep the existing Python backend as the data/API layer. The frontend consumes month-scoped workbench and tax APIs, while OA, bank, and invoice display contracts are normalized on the backend.

**Tech Stack:** Vite, React, TypeScript, CSS, Vitest, Python HTTP service, unittest

---

### Task 1: Frontend Scaffold And Routing

**Files:**
- Create: `web/package.json`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/src/main.tsx`
- Create: `web/src/app/App.tsx`
- Create: `web/src/app/router.tsx`
- Create: `web/src/app/styles.css`
- Test: `web/src/app/App.test.tsx`

- [ ] Step 1: Bootstrap a Vite + React + TypeScript app in `web/`
- [ ] Step 2: Add routes for `ReconciliationWorkbenchPage` and `TaxOffsetPage`
- [ ] Step 3: Add a shared month context
- [ ] Step 4: Add one failing smoke test for route rendering
- [ ] Step 5: Implement the minimal shell to pass the test
- [ ] Step 6: Run frontend tests
- [ ] Step 7: Commit the scaffold

### Task 2: Workbench Page Skeleton

**Files:**
- Create: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Create: `web/src/components/workbench/WorkbenchHeader.tsx`
- Create: `web/src/components/workbench/WorkbenchToolbar.tsx`
- Create: `web/src/components/workbench/WorkbenchStats.tsx`
- Test: `web/src/pages/ReconciliationWorkbenchPage.test.tsx`

- [ ] Step 1: Write a failing test for the top bar, month selector, and tax page entry
- [ ] Step 2: Build the shell with top bar, toolbar, and summary strip
- [ ] Step 3: Add month switching state
- [ ] Step 4: Run tests and confirm pass
- [ ] Step 5: Commit the shell

### Task 3: Resizable Tri-Pane Zones

**Files:**
- Create: `web/src/components/workbench/ResizableTriPane.tsx`
- Create: `web/src/components/workbench/WorkbenchZone.tsx`
- Create: `web/src/components/workbench/PaneTable.tsx`
- Create: `web/src/hooks/useResizablePanes.ts`
- Test: `web/src/components/workbench/ResizableTriPane.test.tsx`

- [ ] Step 1: Write failing tests for splitter drag, 0-width collapse, and restore
- [ ] Step 2: Implement CSS grid-based tri-pane layout
- [ ] Step 3: Implement pointer-based splitter drag
- [ ] Step 4: Implement pane hide/show toggles
- [ ] Step 5: Verify both paired and open zones use the same widths
- [ ] Step 6: Run tests
- [ ] Step 7: Commit the tri-pane layout

### Task 4: Row Selection, Inline Actions, And Detail Drawer

**Files:**
- Create: `web/src/components/workbench/RowActions.tsx`
- Create: `web/src/components/workbench/DetailDrawer.tsx`
- Create: `web/src/hooks/useWorkbenchSelection.ts`
- Modify: `web/src/components/workbench/PaneTable.tsx`
- Test: `web/src/components/workbench/PaneTable.test.tsx`
- Test: `web/src/components/workbench/DetailDrawer.test.tsx`

- [ ] Step 1: Write failing tests for row selection vs detail button behavior
- [ ] Step 2: Implement selected-row and same-case highlighting
- [ ] Step 3: Implement row action buttons per pane type
- [ ] Step 4: Implement drawer open only via `详情`
- [ ] Step 5: Run tests
- [ ] Step 6: Commit the interaction layer

### Task 5: Tax Offset Page

**Files:**
- Create: `web/src/pages/TaxOffsetPage.tsx`
- Create: `web/src/components/tax/TaxSummaryCards.tsx`
- Create: `web/src/components/tax/TaxTable.tsx`
- Create: `web/src/components/tax/TaxResultPanel.tsx`
- Create: `web/src/services/taxApi.ts`
- Test: `web/src/pages/TaxOffsetPage.test.tsx`

- [ ] Step 1: Write a failing test for month-scoped tax totals
- [ ] Step 2: Implement tax summary cards
- [ ] Step 3: Implement selectable output/input tables
- [ ] Step 4: Implement computed payable/carry-forward result
- [ ] Step 5: Run tests
- [ ] Step 6: Commit the tax page

### Task 6: Backend Workbench Contracts

**Files:**
- Create: `backend/src/fin_ops_platform/domain/workbench_models.py`
- Create: `backend/src/fin_ops_platform/services/workbench_query_service.py`
- Create: `backend/src/fin_ops_platform/services/workbench_action_service.py`
- Create: `backend/src/fin_ops_platform/services/bank_account_resolver.py`
- Create: `backend/src/fin_ops_platform/app/routes_workbench.py`
- Test: `tests/test_workbench_api.py`

- [ ] Step 1: Write failing backend tests for `GET /api/workbench`
- [ ] Step 2: Implement month-scoped seed-backed response
- [ ] Step 3: Add single-row detail endpoint
- [ ] Step 4: Add action endpoints with request validation
- [ ] Step 5: Run backend tests
- [ ] Step 6: Commit the workbench API

### Task 7: Backend Tax Contracts And OA Adapter Boundary

**Files:**
- Create: `backend/src/fin_ops_platform/domain/tax_models.py`
- Create: `backend/src/fin_ops_platform/services/tax_offset_service.py`
- Create: `backend/src/fin_ops_platform/services/oa_adapter.py`
- Create: `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- Create: `backend/src/fin_ops_platform/app/routes_tax.py`
- Test: `tests/test_tax_offset_api.py`

- [ ] Step 1: Write failing tests for tax query and calculate endpoints
- [ ] Step 2: Implement month-scoped tax data service
- [ ] Step 3: Implement calculate action
- [ ] Step 4: Add OA adapter interface and stub Mongo implementation
- [ ] Step 5: Run tests
- [ ] Step 6: Commit the tax and OA adapter layer

### Task 8: Frontend/Backend Integration And QA

**Files:**
- Modify: `web/src/services/api.ts`
- Modify: `web/src/services/workbenchApi.ts`
- Modify: `web/src/services/taxApi.ts`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/pages/TaxOffsetPage.tsx`
- Modify: `docs/dev/reconciliation-workbench-v2-testing.md`
- Test: `web/src/**/*.test.tsx`
- Test: `tests/test_workbench_api.py`
- Test: `tests/test_tax_offset_api.py`

- [ ] Step 1: Replace local mock state with API calls
- [ ] Step 2: Add loading, empty, and error states
- [ ] Step 3: Verify month switching stays in sync across both pages
- [ ] Step 4: Run frontend and backend test suites
- [ ] Step 5: Update docs if contracts changed
- [ ] Step 6: Commit the integrated implementation

### Task 9: Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`

- [ ] Step 1: Verify implementation matches `docs/product/银企核销需求.md`
- [ ] Step 2: Verify row click does not open drawer
- [ ] Step 3: Verify splitter can fully collapse panes
- [ ] Step 4: Verify tax page monthly totals are correct
- [ ] Step 5: Run final verification commands
- [ ] Step 6: Prepare handoff summary
