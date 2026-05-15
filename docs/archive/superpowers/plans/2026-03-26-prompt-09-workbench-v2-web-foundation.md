# Prompt 09 Workbench V2 Web Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a formal Vite + React + TypeScript frontend foundation for the Workbench V2 UI, with two routes, shared month state, mock data shells, and basic tests.

**Architecture:** Create a small React app inside `web/` that preserves the existing single-file prototype as reference while migrating the confirmed shell into route-based pages. Keep state local plus a shared month context, and defer backend integration and advanced interactions to later prompts.

**Tech Stack:** Vite, React, TypeScript, React Router, Vitest, Testing Library

---

### Task 1: Scaffold the frontend toolchain

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.node.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`

- [ ] Step 1: Write the toolchain config files for Vite, TypeScript, Vitest, and React.
- [ ] Step 2: Install frontend dependencies with `npm install`.
- [ ] Step 3: Verify the package metadata and scripts are valid.

### Task 2: Add app entry, router, and month context

**Files:**
- Create: `web/src/main.tsx`
- Create: `web/src/app/App.tsx`
- Create: `web/src/app/router.tsx`
- Create: `web/src/contexts/MonthContext.tsx`

- [ ] Step 1: Write the failing test for route rendering and shared month state.
- [ ] Step 2: Run the targeted test to verify it fails for the missing app shell.
- [ ] Step 3: Implement the React entry, router, and month context with minimal code.
- [ ] Step 4: Re-run the targeted test to verify the shell passes.

### Task 3: Migrate the workbench and tax pages as mock-backed shells

**Files:**
- Create: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Create: `web/src/pages/TaxOffsetPage.tsx`
- Create: `web/src/features/workbench/mockData.ts`
- Create: `web/src/features/tax/mockData.ts`
- Create: `web/src/app/styles.css`

- [ ] Step 1: Write the failing test for navigation to `税金抵扣` and month display consistency.
- [ ] Step 2: Run the targeted test to verify it fails for missing page content.
- [ ] Step 3: Implement the two route pages with local mock data and shared top navigation.
- [ ] Step 4: Re-run the targeted test to verify the route pages pass.

### Task 4: Add test setup and frontend documentation

**Files:**
- Create: `web/src/test/App.test.tsx`
- Create: `web/src/test/setup.ts`
- Modify: `web/README.md`

- [ ] Step 1: Add the final App-level route and month interaction tests.
- [ ] Step 2: Run `npm run test -- --run` and verify the frontend tests pass.
- [ ] Step 3: Update `web/README.md` with run, test, and build instructions.

### Task 5: Run build and local preview verification

**Files:**
- No code changes required if prior tasks pass

- [ ] Step 1: Run `npm run build` and verify the production build succeeds.
- [ ] Step 2: Start the Vite dev server on a local port.
- [ ] Step 3: Verify both routes render in the browser.
