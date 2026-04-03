# Prompt 13 Tax Offset Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the tax offset page into an interactive monthly workbench with selectable invoice rows and live deduction calculations.

**Architecture:** Keep the shared `MonthContext` from Prompt 09 and build the tax page from small React components: summary cards, tax tables, and a result panel. Centralize month-based mock data and tax calculations in the tax feature module so the page only coordinates selection state and rendering.

**Tech Stack:** React, TypeScript, React Router, CSS, Vitest, Testing Library

---

### Task 1: Add failing tests for tax recalculation and month switching

**Files:**
- Create: `web/src/test/TaxOffsetPage.test.tsx`

- [ ] Step 1: Add a test that unchecks an input invoice and expects tax summaries to recalculate.
- [ ] Step 2: Add a test that changes the shared month, verifies new month rows appear, and returns to the workbench without losing month state.
- [ ] Step 3: Run the targeted test and verify it fails for the missing interactive tax workbench behavior.

### Task 2: Reshape tax mock data into monthly datasets and calculation helpers

**Files:**
- Modify: `web/src/features/tax/mockData.ts`

- [ ] Step 1: Replace the single static summary with month-based invoice datasets.
- [ ] Step 2: Add helpers for default selection ids, money parsing/formatting, and tax summary calculation.
- [ ] Step 3: Keep data contracts simple so future backend integration can swap in real data.

### Task 3: Build interactive tax page components

**Files:**
- Create: `web/src/components/tax/TaxSummaryCards.tsx`
- Create: `web/src/components/tax/TaxTable.tsx`
- Create: `web/src/components/tax/TaxResultPanel.tsx`
- Modify: `web/src/pages/TaxOffsetPage.tsx`

- [ ] Step 1: Split the tax page into summary cards, tables, and result panel components.
- [ ] Step 2: Wire page state for selected output/input invoice ids.
- [ ] Step 3: Reset selection when month changes.
- [ ] Step 4: Add page-level `返回关联台` navigation.
- [ ] Step 5: Re-run the targeted tests and verify tax interactions pass.

### Task 4: Polish styling and verify end-to-end

**Files:**
- Modify: `web/src/app/styles.css`
- Modify: `web/README.md`
- Modify: `README.md`

- [ ] Step 1: Style the result panel and selectable tax tables to match the existing workbench tone.
- [ ] Step 2: Document Prompt 13 outcomes and current mock-only boundary.
- [ ] Step 3: Run `npm run test -- --run`.
- [ ] Step 4: Run `npm run build`.
- [ ] Step 5: Verify the local Vite preview still serves `/` and `/tax-offset`.
