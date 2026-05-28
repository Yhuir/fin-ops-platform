# Bank Tag Filter Popover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bank details page's flat category chip strip with one compact hierarchical tag filter popover that filters transactions by all, uncategorized, primary tag, or exact sub tag.

**Architecture:** Keep the feature inside the existing bank details frontend boundary. `BankDetailsPage.tsx` owns the UI state, tree derivation, popover, and table refresh behavior; `web/src/features/bankDetails/api.ts` continues to own query parameter serialization for existing backend contracts. No backend schema or automatic tag semantics change.

**Tech Stack:** React 18, TypeScript, MUI 7, MUI X Tree View, Vitest, Testing Library.

---

## File Structure

- Modify `web/package.json`: add `@mui/x-tree-view` if missing.
- Modify `web/package-lock.json`: lock the new dependency.
- Modify `web/src/pages/BankDetailsPage.tsx`: replace flat category buttons with one filter button and popover, add structured category filter state, derive tree items, and pass correct fetch/export filters.
- Modify `web/src/features/bankDetails/types.ts`: add shared category filter types only if keeping them local in the page becomes awkward.
- Modify `web/src/features/bankDetails/api.ts`: preserve existing `category_code`, `category_primary_label`, and `category_sub_label` serialization; adjust only if tests expose missing export/list parity.
- Modify `web/src/test/BankDetailsPage.test.tsx`: cover the new one-button toolbar, tree selection behavior, pagination reset, and export inheritance.
- Modify `web/src/test/BankDetailsApi.test.ts`: cover any API query serialization gaps found while implementing.
- Avoid modifying `web/src/app/styles.css` unless a tiny sizing/scrolling adjustment cannot be expressed with MUI props or `sx`.

## Task 1: Add Dependency and Baseline Tests

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`

- [ ] **Step 1: Check whether MUI X Tree View is installed**

Run:

```bash
cd web && node -e "const pkg=require('./package.json'); console.log(pkg.dependencies['@mui/x-tree-view'] || '')"
```

Expected: prints an existing version or an empty line.

- [ ] **Step 2: Add dependency if missing**

Run:

```bash
cd web && npm install @mui/x-tree-view@8.28.5
```

Expected: `package.json` and `package-lock.json` include `@mui/x-tree-view`.

- [ ] **Step 3: Run existing focused tests before behavior changes**

Run:

```bash
cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx
```

Expected: tests pass or any failure is recorded as pre-existing before code changes.

## Task 2: Model Category Filters and Tree Items

**Files:**
- Modify: `web/src/pages/BankDetailsPage.tsx`
- Test: `web/src/test/BankDetailsPage.test.tsx`

- [ ] **Step 1: Add tests for one filter entry and tree labels**

Add tests that render the bank details page with several active tag definitions and assert:

```tsx
expect(screen.getByRole("button", { name: /标签筛选：全部/ })).toBeInTheDocument();
expect(screen.queryByRole("button", { name: /薪资社保福利 \/ 工资/ })).not.toBeInTheDocument();
```

Then open the filter button and assert the popover contains:

```tsx
expect(await screen.findByText(/全部/)).toBeInTheDocument();
expect(screen.getByText(/未分类/)).toBeInTheDocument();
expect(screen.getByText(/薪资社保福利/)).toBeInTheDocument();
expect(screen.getByText(/工资/)).toBeInTheDocument();
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd web && npm test -- --run BankDetailsPage.test.tsx
```

Expected: FAIL because the old flat category strip still renders.

- [ ] **Step 3: Add the filter model**

In `BankDetailsPage.tsx`, add a local type equivalent to:

```ts
type BankCategoryFilter =
  | { kind: "all" }
  | { kind: "uncategorized" }
  | { kind: "primary"; primaryLabel: string }
  | { kind: "tag"; code: string; primaryLabel: string; subLabel: string | null };
```

Replace `selectedCategoryCode` with `selectedCategoryFilter`.

- [ ] **Step 4: Add tree derivation helpers**

Add small pure helpers in `BankDetailsPage.tsx` to:

- build primary groups from `categoryOptions`;
- compute primary counts from child `categoryCounts`;
- produce stable node IDs;
- produce button summary text and selected node ID.

Keep helpers local unless they grow beyond page responsibility.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd web && npm test -- --run BankDetailsPage.test.tsx
```

Expected: tests still fail until UI task is complete, but TypeScript/runtime errors should be resolved.

## Task 3: Implement Popover and RichTreeView UI

**Files:**
- Modify: `web/src/pages/BankDetailsPage.tsx`
- Test: `web/src/test/BankDetailsPage.test.tsx`

- [ ] **Step 1: Replace the flat category summary**

Replace `BankDetailsTableToolbar` category chip rendering with one MUI `Button` labelled with the current summary, for example:

```tsx
标签筛选：全部 · 431 条
```

- [ ] **Step 2: Add Popover open/close state**

Add anchor state and delayed close behavior so the popover opens on hover, focus, and click, remains open when the pointer moves into the popover, and closes on click-away or `Esc`.

- [ ] **Step 3: Render RichTreeView**

Render `RichTreeView` inside the popover using derived items:

- `全部`;
- `未分类`;
- primary tags;
- indented child tags.

Use controlled selected item state derived from `selectedCategoryFilter`.

- [ ] **Step 4: Separate expansion from filtering**

Ensure expanding a primary node does not accidentally change the filter. If default item click selection conflicts with expansion, use `onItemClick`, `onSelectedItemsChange`, or item metadata to apply filter changes only when the intended item content is selected.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd web && npm test -- --run BankDetailsPage.test.tsx
```

Expected: new one-button and popover tests pass.

## Task 4: Wire Fetch, Pagination Reset, and Export Inheritance

**Files:**
- Modify: `web/src/pages/BankDetailsPage.tsx`
- Modify: `web/src/features/bankDetails/api.ts` only if needed
- Test: `web/src/test/BankDetailsPage.test.tsx`
- Test: `web/src/test/BankDetailsApi.test.ts` only if needed

- [ ] **Step 1: Add tests for primary and child selection request params**

Add tests that:

- open the tag filter popover;
- select a primary tag;
- assert the latest transaction request includes `category_primary_label` and no `category_code`;
- select a child tag;
- assert the latest transaction request includes `category_code`;
- assert pagination resets to first page after selection.

- [ ] **Step 2: Add tests for export inheritance**

Extend export tests to select a primary or exact tag before exporting and assert the export request carries the same filter semantics as the visible table.

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
cd web && npm test -- --run BankDetailsPage.test.tsx BankDetailsApi.test.ts
```

Expected: FAIL until fetch/export wiring is updated.

- [ ] **Step 4: Implement filter-to-request mapping**

In `BankDetailsPage.tsx`, map:

- `all` to no category params;
- `uncategorized` to the existing uncategorized convention;
- `primary` to `categoryPrimaryLabel`;
- `tag` to `categoryCode` and, for export parity if useful, primary/sub label.

Keep account, date range, and search keyword unchanged. Reset `paginationModel.page` to `0` on filter changes.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd web && npm test -- --run BankDetailsPage.test.tsx BankDetailsApi.test.ts
```

Expected: PASS.

## Task 5: Build and Final Verification

**Files:**
- Inspect all changed files.

- [ ] **Step 1: Run frontend build**

Run:

```bash
cd web && npm run build
```

Expected: PASS.

- [ ] **Step 2: Check diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; changed files are limited to the planned scope.

- [ ] **Step 3: Review implementation against spec**

Check:

- one stable `标签筛选` button replaced the flat chip strip;
- popover is vertical and hierarchical;
- primary/sub label hierarchy is visually clear;
- primary tag filters across children;
- expansion does not accidentally filter;
- exact sub tag filters by code;
- filter changes reset pagination and preserve account/date/search;
- export inherits category filters;
- no backend tag semantics changed;
- no large CSS-driven implementation was added.

- [ ] **Step 4: Commit**

Run:

```bash
git add web/package.json web/package-lock.json web/src/pages/BankDetailsPage.tsx web/src/features/bankDetails/api.ts web/src/features/bankDetails/types.ts web/src/test/BankDetailsPage.test.tsx web/src/test/BankDetailsApi.test.ts docs/superpowers/plans/2026-05-29-bank-tag-filter-popover.md
git commit -m "Implement bank tag filter popover"
```

Expected: commit succeeds with only planned files staged.
