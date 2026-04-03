# Prompt 10 Workbench V2 Layout And Resize Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add independently resizable tri-pane workbench zones with full collapse-to-zero behavior, per-zone recovery controls, sticky headers, and component tests.

**Architecture:** Extract the current page-level mock layout into focused workbench components. Each zone owns its own pane-width state through a reusable hook, and a dynamic grid only renders visible panes and the splitters between them so one-zone and two-zone states stay clean.

**Tech Stack:** React, TypeScript, CSS Grid, Pointer Events, Vitest, Testing Library

---

### Task 1: Add failing tests for per-zone collapse and recovery

**Files:**
- Create: `web/src/test/WorkbenchZone.test.tsx`

- [ ] Step 1: Write the failing test for collapsing and restoring panes through zone header buttons.
- [ ] Step 2: Write the failing test for splitter count changing between one-, two-, and three-pane states.
- [ ] Step 3: Run the targeted test and verify it fails for missing workbench components.

### Task 2: Implement pane resizing state and dynamic tri-pane rendering

**Files:**
- Create: `web/src/hooks/useResizablePanes.ts`
- Create: `web/src/components/workbench/ResizableTriPane.tsx`

- [ ] Step 1: Implement the pane-width hook with drag, collapse, and restore behavior.
- [ ] Step 2: Implement the tri-pane renderer that only shows splitters between visible panes.
- [ ] Step 3: Re-run the targeted tests and verify the basic collapse/recovery flow passes.

### Task 3: Extract zone and pane table components

**Files:**
- Create: `web/src/components/workbench/PaneTable.tsx`
- Create: `web/src/components/workbench/WorkbenchZone.tsx`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`

- [ ] Step 1: Move single-pane table rendering into `PaneTable`.
- [ ] Step 2: Move per-zone header and controls into `WorkbenchZone`.
- [ ] Step 3: Update the page to render two independent zones with separate resize state.
- [ ] Step 4: Re-run the targeted tests and verify zone-level behavior still passes.

### Task 4: Add drag-to-zero coverage and styling polish

**Files:**
- Modify: `web/src/test/WorkbenchZone.test.tsx`
- Modify: `web/src/app/styles.css`

- [ ] Step 1: Extend the tests to verify dragging a splitter can collapse a pane.
- [ ] Step 2: Implement the remaining styles for sticky headers, fixed pane height, splitters, and toggle states.
- [ ] Step 3: Re-run the targeted tests and verify drag coverage passes.

### Task 5: Update docs and run full frontend verification

**Files:**
- Modify: `web/README.md`
- Modify: `README.md`

- [ ] Step 1: Document the new per-zone resize behavior.
- [ ] Step 2: Run `npm run test -- --run`.
- [ ] Step 3: Run `npm run build`.
- [ ] Step 4: Verify the local Vite preview shows the new layout behavior.
