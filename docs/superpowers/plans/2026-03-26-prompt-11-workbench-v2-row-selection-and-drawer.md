# Prompt 11 Workbench V2 Row Selection And Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add page-level row selection, case-linked highlight states, row-only selection behavior, and a right-side detail drawer that opens exclusively from row action buttons.

**Architecture:** Keep zone resizing isolated from selection by introducing a page-level selection hook and passing minimal selection props down to pane tables. Use lightweight row action and drawer components so the workbench stays table-first while details remain outside the main grid.

**Tech Stack:** React, TypeScript, CSS, Vitest, Testing Library

---

### Task 1: Add failing tests for row click vs detail button behavior

**Files:**
- Create: `web/src/test/WorkbenchSelection.test.tsx`

- [ ] Step 1: Write the failing test for clicking a row without opening the drawer.
- [ ] Step 2: Write the failing test for clicking the row `详情` button and opening the drawer.
- [ ] Step 3: Write the failing test for same-`caseId` highlight linkage.
- [ ] Step 4: Run the targeted test and verify it fails for missing selection/drawer behavior.

### Task 2: Add selection hook and richer mock record metadata

**Files:**
- Create: `web/src/hooks/useWorkbenchSelection.ts`
- Modify: `web/src/features/workbench/mockData.ts`

- [ ] Step 1: Extend mock records with `caseId`, record type, and detail fields.
- [ ] Step 2: Implement the page-level selection hook with selected row, selected case, and detail row state.
- [ ] Step 3: Re-run the targeted tests and verify they still fail only on missing UI wiring.

### Task 3: Add row actions and drawer components

**Files:**
- Create: `web/src/components/workbench/RowActions.tsx`
- Create: `web/src/components/workbench/DetailDrawer.tsx`
- Modify: `web/src/components/workbench/PaneTable.tsx`

- [ ] Step 1: Add a row action button component for `详情`.
- [ ] Step 2: Update `PaneTable` to support row selection and event-safe detail button clicks.
- [ ] Step 3: Add the detail drawer with OA / 银行流水 / 发票 display sections.
- [ ] Step 4: Re-run the targeted tests and verify click behavior passes.

### Task 4: Wire page-level selection across both zones

**Files:**
- Modify: `web/src/components/workbench/ResizableTriPane.tsx`
- Modify: `web/src/components/workbench/WorkbenchZone.tsx`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/app/styles.css`

- [ ] Step 1: Thread selection and drawer callbacks from the page into each zone and pane.
- [ ] Step 2: Add distinct styles for selected rows and related-case rows.
- [ ] Step 3: Add drawer layout styles and close behavior.
- [ ] Step 4: Re-run the targeted tests and verify linked highlighting passes.

### Task 5: Update docs and run full frontend verification

**Files:**
- Modify: `web/README.md`
- Modify: `README.md`

- [ ] Step 1: Document row selection and detail drawer behavior.
- [ ] Step 2: Run `npm run test -- --run`.
- [ ] Step 3: Run `npm run build`.
- [ ] Step 4: Verify the local Vite preview serves the updated workbench.
