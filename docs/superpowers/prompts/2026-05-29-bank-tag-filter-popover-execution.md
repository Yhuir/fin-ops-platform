# 银行明细标签筛选 Hover 小窗多任务执行 Prompt

This prompt is intended for Codex workers implementing the approved bank details tag filter popover.

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Primary spec:

```text
docs/superpowers/specs/2026-05-29-bank-tag-filter-popover-design.md
```

## Orchestrator Prompt

```text
/goal Implement the approved bank details tag filter popover so the bank transaction page uses one stable tag-filter button, opens a vertical hierarchical hover/focus/click popover, clearly shows primary/sub tag levels, filters the transaction table when any tag node is selected, and preserves existing bank detail data contracts.

You are working in /Users/yu/Desktop/fin-ops-platform.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/product-specs/bank-details.md
- docs/dev/api-contracts.md
- docs/superpowers/specs/2026-05-29-bank-tag-filter-popover-design.md
- web/README.md
- web/package.json
- web/src/pages/BankDetailsPage.tsx
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/features/bankDetails/BankCategoryTag.tsx
- web/src/test/BankDetailsPage.test.tsx
- web/src/test/BankDetailsApi.test.ts

Hard requirements:
- Replace the current multi-chip category filter strip with one stable tag-filter button in the bank transaction table toolbar.
- The button must show the current filter summary and count, for example `标签筛选：全部 · 431 条`, `标签筛选：费用 · 153 条`, or `标签筛选：费用 / 手续费 · 113 条`.
- Open a compact MUI Popover from hover, focus, and click. On narrow/touch usage, click must be sufficient.
- Use `@mui/x-tree-view` RichTreeView for the vertical hierarchical selector unless local package constraints make it impossible.
- Add `@mui/x-tree-view` as the only new dependency if it is not already installed.
- The hierarchy must be visually clear: fixed top nodes `全部` and `未分类`, then primary tags, then indented sub tags.
- Primary tags with children must support both expansion and filtering. Expanding must not accidentally change the filter; selecting the primary label must filter all rows under that primary tag.
- Selecting a sub tag must filter the exact tag.
- Selecting any filter resets the bank transaction table to page 1 while preserving account, date range, and search keyword.
- Existing API contracts should be reused. Do not add backend fields for this feature unless tests prove an existing contract is missing.
- Keep export requests consistent with the current category filter, including primary-tag and sub-tag filters.
- Do not restore manual per-transaction bank tagging.
- Do not change automatic tag rule matching semantics.
- Do not convert the MUI Table to DataGrid.
- Use MUI component props, MUI theme tokens, `sx`, and MUI X behavior as the main implementation path. Avoid large custom CSS. A small local CSS adjustment is acceptable only for spacing/scrolling/polish.
- Preserve unrelated dirty work. Do not revert files you did not change.

Execution order:
1. Serial setup:
   - inspect git status;
   - confirm current BankDetailsPage category filter rendering and existing API request parameters;
   - inspect current tests for bank category filtering and export inheritance.
2. Serial dependency and type design:
   - add `@mui/x-tree-view` dependency if missing;
   - introduce a small `BankCategoryFilter` type or equivalent local model that can represent all, uncategorized, primary, and exact tag filters;
   - derive tree items from `categoryOptions`, `categoryCounts`, and `rowCount`;
   - keep stable node IDs and avoid collisions when labels repeat.
3. Parallel-safe frontend implementation after the filter model is defined:
   - toolbar/popover UI work in `web/src/pages/BankDetailsPage.tsx`;
   - API request/export propagation work in `web/src/features/bankDetails/api.ts` and relevant page handlers;
   - tests in `web/src/test/BankDetailsPage.test.tsx` and `web/src/test/BankDetailsApi.test.ts`.
4. Serial integration:
   - reconcile TypeScript errors;
   - verify button summary/count behavior;
   - verify primary and sub tag request params;
   - verify export inherits the current filter.
5. Final verification:
   - run focused frontend tests;
   - run frontend build;
   - run `git diff --check`;
   - inspect changed files for scope, large CSS drift, and unrelated changes.

Expected final report:
- changed files;
- dependency changes;
- tests run and results;
- any residual risk, especially around RichTreeView event separation for expansion versus selection.
```

## Worker 1: Filter Model and Tree Derivation

```text
/goal Implement the bank details category filter model and tree derivation needed by the tag popover.

Owned files:
- web/src/pages/BankDetailsPage.tsx
- web/src/features/bankDetails/types.ts if a shared type is clearly useful
- web/src/test/BankDetailsPage.test.tsx

Read:
- docs/superpowers/specs/2026-05-29-bank-tag-filter-popover-design.md
- web/src/pages/BankDetailsPage.tsx
- web/src/features/bankDetails/types.ts
- web/src/features/bankDetails/BankCategoryTag.tsx

Requirements:
- Replace or wrap the existing `selectedCategoryCode` state with a model that can represent:
  - all;
  - uncategorized;
  - primary tag;
  - exact tag.
- Build memoized tree data from `categoryOptions`, `categoryCounts`, and `rowCount`.
- Preserve current tag order from `categoryOptions`.
- Compute primary counts from child tag counts.
- Include selected zero-count nodes so the current filter never disappears from the popover.
- Generate stable node IDs:
  - `all`;
  - `uncategorized`;
  - primary IDs that cannot collide;
  - `tag:<code>`.
- Return changed files and tests run.
```

## Worker 2: Popover and RichTreeView UI

```text
/goal Replace the bank details flat category chip strip with one compact tag-filter button and a vertical hierarchical MUI Popover selector.

Owned files:
- web/src/pages/BankDetailsPage.tsx
- web/src/app/styles.css only if a tiny adjustment is necessary
- web/src/test/BankDetailsPage.test.tsx

Read:
- docs/superpowers/specs/2026-05-29-bank-tag-filter-popover-design.md
- web/src/pages/BankDetailsPage.tsx
- web/src/app/styles.css
- MUI Popover docs
- MUI X RichTreeView item and selection docs

Requirements:
- Use MUI Popover and RichTreeView.
- The toolbar must render one category filter button instead of many category filter buttons.
- The button summary must include current filter label and count.
- Popover opens on hover/focus/click and supports click-away/Esc close.
- Mouse moving from button to popover must not close it immediately.
- The tree must clearly show:
  - `全部`;
  - `未分类`;
  - primary labels;
  - indented sub labels.
- Current selection must be highlighted.
- Primary expansion and primary filtering must not conflict. If RichTreeView default click behavior cannot cleanly separate them, use the documented slots/API or a small controlled interaction layer rather than changing backend semantics.
- Keep custom CSS minimal and local.
- Return changed files and tests run.
```

## Worker 3: API Parameters, Export Inheritance, and Tests

```text
/goal Ensure bank detail transaction fetches and exports use the new category filter semantics for all, uncategorized, primary, and exact tag selections.

Owned files:
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/pages/BankDetailsPage.tsx
- web/src/test/BankDetailsApi.test.ts
- web/src/test/BankDetailsPage.test.tsx

Read:
- docs/superpowers/specs/2026-05-29-bank-tag-filter-popover-design.md
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/pages/BankDetailsPage.tsx
- backend/src/fin_ops_platform/app/server.py only if needed to confirm existing query params

Requirements:
- Do not invent backend query parameters.
- Use existing `category_code`, `category_primary_label`, and `category_sub_label` request support.
- All filter sends no category params.
- Uncategorized uses the repository's current uncategorized convention; inspect existing code/tests before changing.
- Primary filter sends `category_primary_label`.
- Exact tag filter sends `category_code`; include primary/sub label in export only if that is already needed for current export behavior.
- Changing filter resets pagination to first page.
- Search, date range, and account filters remain intact.
- Export inherits the active category filter.
- Add or update tests for fetch URL params and export URL params.
- Return changed files and tests run.
```

## Serial Integration Prompt

```text
/goal Integrate all bank tag filter popover work into one coherent implementation and remove regressions.

Check:
- `BankDetailsPage.tsx` has one clear category filter state model.
- The toolbar no longer maps every category into visible page-level buttons.
- The popover tree shows a clear hierarchy and compact scrollable panel.
- Primary selection and child selection generate different request parameters.
- Current filter summary and count match the selected node.
- Export uses the same selected filter as the visible table.
- No broad CSS rewrite was introduced.
- No backend contract was changed unnecessarily.

Run:
- cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx
- cd web && npm run build
- git diff --check
```

## Final Verification Prompt

```text
/goal Review and verify the complete bank details tag filter popover implementation against the approved spec.

Verify manually from the diff:
- One stable `标签筛选` button replaced the flat chip strip.
- The popover is vertical and hierarchical, not a horizontal grid.
- Main/sub label hierarchy is visually clear.
- `全部`, `未分类`, primary tags, and sub tags all select the expected filter.
- Clicking a primary tag filters all rows under that primary tag.
- Expanding a primary tag does not accidentally filter.
- Clicking a sub tag filters the exact tag.
- Filter changes reset pagination to page 1 and preserve date/account/search.
- Export inherits all category filter kinds.
- No automatic tag rule semantics changed.
- No manual bank tagging UI returned.
- No large CSS-driven implementation was added.

Run:
- cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx
- cd web && npm run build
- git diff --check

Final response should include:
- implementation summary;
- changed files;
- verification results;
- residual risks or explicitly state none found.
```

## Prompt Review

Review pass 1 findings:

- The prompt needed to distinguish primary-label selection from exact tag-code selection. Added explicit `BankCategoryFilter` states and request parameter rules.
- The prompt needed to preserve export behavior. Added export inheritance requirements and tests.
- The prompt needed to avoid CSS-led implementation. Added a hard requirement and final diff review item for CSS drift.
- The prompt needed to protect existing backend contracts. Added a hard requirement not to invent backend query parameters and to inspect existing code before changing uncategorized behavior.

Review pass 2 findings:

- The prompt needed to call out the specific interaction risk in RichTreeView: expansion and selection can conflict. Added explicit requirements for separating expand arrow behavior from primary label selection.
- The prompt needed to keep page space reduction measurable. Added the requirement that the toolbar renders one category filter button instead of many category buttons.
- The prompt needed to handle selected zero-count nodes. Added tree derivation requirement so current filters do not disappear after refresh.

Review pass 3 findings:

- The prompt now covers all confirmed requirements:
  - one hover/focus/click小窗;
  - vertical hierarchy;
  - clear主/子标签层级;
  - click-to-filter for all label kinds;
  - main-label filter across children;
  - table space returned to流水表;
  - MUI/MUI X implementation with minimal CSS;
  - existing contracts and verification.

Review conclusion:

```text
Approved for execution. The prompt is specific enough for Codex to implement the requested feature without inventing backend contracts, changing tag semantics, or drifting into a CSS-heavy redesign.
```
