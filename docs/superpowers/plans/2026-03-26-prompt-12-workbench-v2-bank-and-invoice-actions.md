# Prompt 12 Workbench V2 Bank And Invoice Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the workbench main tables and row actions with the requirement document by adding pane-specific columns, horizontal scrolling, and mock-backed inline actions.

**Architecture:** Keep the existing tri-pane and selection architecture, but switch pane rendering to configuration-driven columns and action variants. This keeps field expansion isolated from the selection/drawer logic and avoids duplicating three separate table implementations.

**Tech Stack:** React, TypeScript, CSS, Vitest, Testing Library

---

### Task 1: Add failing tests for columns and row actions

**Files:**
- Create: `web/src/test/WorkbenchColumns.test.tsx`

- [ ] Step 1: Write the failing test for OA / 银行 / 发票 column headers.
- [ ] Step 2: Write the failing test for bank row actions `详情 + 更多`.
- [ ] Step 3: Write the failing test for unpaired OA / 发票 row actions `确认关联 + 标记异常`.
- [ ] Step 4: Run the targeted test and verify it fails for missing columns/actions.

### Task 2: Add column configuration and richer table-field data

**Files:**
- Create: `web/src/features/workbench/tableConfig.ts`
- Modify: `web/src/features/workbench/mockData.ts`

- [ ] Step 1: Add pane column definitions keyed to the requirement document.
- [ ] Step 2: Add `tableFields` and action variants to the mock records.
- [ ] Step 3: Re-run the targeted tests and verify they still fail only on rendering gaps.

### Task 3: Update pane rendering and row actions

**Files:**
- Modify: `web/src/components/workbench/PaneTable.tsx`
- Modify: `web/src/components/workbench/RowActions.tsx`
- Modify: `web/src/components/workbench/ResizableTriPane.tsx`
- Modify: `web/src/components/workbench/WorkbenchZone.tsx`

- [ ] Step 1: Make `PaneTable` render columns from pane config.
- [ ] Step 2: Update `RowActions` for bank `更多` actions and open-row confirm/exception actions.
- [ ] Step 3: Thread pane column and action config through tri-pane and zone components.
- [ ] Step 4: Re-run the targeted tests and verify field/action coverage passes.

### Task 4: Polish wide-table styling and sticky actions

**Files:**
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/app/styles.css`

- [ ] Step 1: Ensure each pane table supports horizontal scroll with many columns.
- [ ] Step 2: Make the action column stable and sticky on the right.
- [ ] Step 3: Verify the updated page still works with selection and drawer state.

### Task 5: Update docs and run full frontend verification

**Files:**
- Modify: `web/README.md`
- Modify: `README.md`

- [ ] Step 1: Document the requirement-aligned field and action coverage.
- [ ] Step 2: Run `npm run test -- --run`.
- [ ] Step 3: Run `npm run build`.
- [ ] Step 4: Verify the local Vite preview serves the updated workbench.
