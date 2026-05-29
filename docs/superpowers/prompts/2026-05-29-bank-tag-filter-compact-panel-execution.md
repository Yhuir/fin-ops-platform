# 银行明细紧凑分组标签筛选面板多任务执行 Prompt

This prompt is intended for Codex workers implementing the approved compact grouped bank tag filter panel.

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Primary spec:

```text
docs/superpowers/specs/2026-05-29-bank-tag-filter-compact-panel-design.md
```

## Orchestrator Prompt

```text
/goal Replace the current bank details tag-filter hover panel with a compact MUI grouped filter panel that is visually smaller and clearer than the current tree-like UI, while preserving the existing bank detail filter model, request contracts, table behavior, and export behavior.

You are working in /Users/yu/Desktop/fin-ops-platform.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/product-specs/bank-details.md
- docs/dev/api-contracts.md
- docs/superpowers/specs/2026-05-29-bank-tag-filter-compact-panel-design.md
- web/README.md
- web/src/pages/BankDetailsPage.tsx
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/features/bankDetails/BankCategoryTag.tsx
- web/src/test/BankDetailsPage.test.tsx
- web/src/test/BankDetailsApi.test.ts
- web/src/test/apiMock.ts
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py

Hard requirements:
- Keep one stable `标签筛选` button in the bank transaction toolbar.
- Replace the current tree-like hover panel visual with a compact MUI grouped filter panel.
- Do not use `RichTreeView` or a file-tree-looking control for the new visual.
- Do not introduce Ant Design or another large UI library unless MUI cannot meet the requirement; MUI should be sufficient.
- The panel must be small: approximately 300-340px wide, 320-360px max height, compact padding, main rows around 30-32px, child rows around 26-28px.
- Counts must be right-aligned and lightweight. Do not use large circular count badges.
- Default-expand all primary groups that have visible children.
- If a primary tag has exactly one child, still show that child so primary summary filtering and exact child filtering remain visually distinct.
- `全部` must be clickable and clear category filters.
- `未分类` must be clickable, even though it is not a real tag, and must filter rows with no effective category.
- Primary tag rows must be clickable and filter all rows under that primary label.
- Child tag rows must be clickable and filter the exact tag.
- Selecting any filter closes the panel and resets the bank transaction table to page 1.
- Selecting any filter preserves current account, date range, and search keyword.
- Export must inherit the active filter for all four filter kinds: all, uncategorized, primary, exact tag.
- Current filter summary/count in the toolbar button must match the active filter.
- Keep backend changes minimal. Do not add new query parameters. The existing `category_code=uncategorized` convention may be preserved/fixed if tests expose a gap.
- Do not change automatic tag rule matching semantics.
- Do not restore manual per-transaction bank tagging.
- Do not convert the MUI Table to DataGrid.
- Avoid large custom CSS. Prefer MUI `sx`, existing classes, and small local style adjustments only.
- Preserve unrelated dirty work. Do not revert files you did not change.

Current-state risks to inspect before editing:
- In `BankDetailsPage.tsx`, the current panel may expose `role="tree"` and tree-like class names such as `bank-category-tree-*`.
- `未分类` may currently be a static/disabled row rather than a clickable filter item.
- Some primary group header rows may be display-only rather than clickable filters.
- Tests may currently assert `role="tree"` or `treeitem`; update them to match the new grouped filter panel semantics.

Execution order:
1. Serial setup:
   - inspect `git status --short`;
   - inspect the current category filter model and panel rendering in `BankDetailsPage.tsx`;
   - inspect current tests around tag filter opening, `未分类`, primary/sub tag selection, and export inheritance;
   - run the focused baseline tests if practical:
     `cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx`.
2. Serial model check:
   - reuse the existing structured filter model if present;
   - if the current state is still code-only, introduce a minimal model that can represent `all`, `uncategorized`, `primary`, and `tag`;
   - keep request mapping explicit and local: all -> no params, uncategorized -> `categoryCode: "uncategorized"`, primary -> `categoryPrimaryLabel`, exact tag -> `categoryCode` plus labels when already used for parity.
3. Parallel-safe implementation after model mapping is clear:
   - UI worker: replace the tree-looking panel content with compact MUI grouped rows in `web/src/pages/BankDetailsPage.tsx`;
   - test worker: update `web/src/test/BankDetailsPage.test.tsx` and `web/src/test/apiMock.ts` expectations for clickable `未分类`, clickable primary rows, exact child rows, and export inheritance;
   - backend worker only if needed: verify existing `uncategorized` backend behavior remains correct in `bank_details_service.py` and `read_models.py`; do not make backend changes unless tests prove a gap.
4. Serial integration:
   - reconcile TypeScript errors;
   - remove stale `tree` role/test assumptions if the UI is no longer a tree;
   - verify compact panel accessibility has a clear role/name such as `menu`, `listbox`, or named `list`;
   - verify all filter rows are keyboard reachable buttons/list items;
   - verify the panel closes after selection and on click-away/Esc.
5. Final verification:
   - `cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx`;
   - `cd web && npm run build`;
   - run backend focused tests only if backend files changed:
     `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_details_sql_runtime -v`;
   - `git diff --check`;
   - inspect changed files for large CSS drift, new heavy UI dependencies, and unrelated edits.

Expected final report:
- changed files;
- dependency changes, if any;
- exact tests run and results;
- whether backend files changed;
- residual risks, especially around visual compactness if no browser/manual screenshot was captured.
```

## Worker 1: Current Model and Request Semantics

```text
/goal Verify and, only if necessary, adjust the bank details category filter model so the compact grouped panel can represent and request all, uncategorized, primary, and exact tag filters.

Owned files:
- web/src/pages/BankDetailsPage.tsx
- web/src/features/bankDetails/types.ts only if a shared type already exists or becomes clearly necessary
- web/src/features/bankDetails/api.ts only if request serialization has a proven gap

Read:
- docs/superpowers/specs/2026-05-29-bank-tag-filter-compact-panel-design.md
- web/src/pages/BankDetailsPage.tsx
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/test/BankDetailsApi.test.ts

Requirements:
- Prefer reusing the existing filter state if it already supports all four states.
- Ensure `all` sends no category params.
- Ensure `uncategorized` maps to the existing `categoryCode: "uncategorized"` convention.
- Ensure `primary` sends `categoryPrimaryLabel` and no `categoryCode`.
- Ensure `tag` sends exact `categoryCode` and retains primary/sub labels where current table/export parity uses them.
- Do not add backend query parameters.
- Preserve account, date range, and search keyword behavior.
- Return changed files, or state that no model/API changes were needed.
```

## Worker 2: Compact MUI Grouped Panel UI

```text
/goal Replace the current bank details tree-like tag filter hover panel with a compact MUI grouped filter panel.

Owned files:
- web/src/pages/BankDetailsPage.tsx
- web/src/app/styles.css only if a tiny existing-class adjustment is unavoidable

Read:
- docs/superpowers/specs/2026-05-29-bank-tag-filter-compact-panel-design.md
- web/src/pages/BankDetailsPage.tsx
- web/src/app/styles.css

Requirements:
- Keep the toolbar as one stable `标签筛选` button.
- Replace tree-looking content with MUI `List`/`ListItemButton`/`Stack`/`Typography`/small `Chip` or text count rows.
- Do not use `RichTreeView` or visual tree control for the panel.
- Panel width should be about 300-340px; max height about 320-360px with internal scrolling.
- Use compact row heights: primary around 30-32px, child around 26-28px.
- Display `全部` and `未分类` as fixed top clickable rows.
- Display every visible primary row as a clickable row.
- Display child rows under their primary row with indentation.
- Default-expand all groups with visible children.
- Show the child row even when a primary has only one child.
- Highlight the active row.
- Counts must be right-aligned and lightweight, not large circular badges.
- Hover/focus/click opens the panel; mouse transition from trigger to panel should not close it immediately.
- Click-away, `Esc`, and selection close the panel.
- Keep custom CSS minimal; prefer `sx` and existing MUI props.
- Return changed files and describe any visual tradeoffs.
```

## Worker 3: Frontend Tests and Mock Behavior

```text
/goal Update bank details frontend tests and mocks so they prove the compact grouped panel behavior and all filter semantics.

Owned files:
- web/src/test/BankDetailsPage.test.tsx
- web/src/test/BankDetailsApi.test.ts only if API serialization changes
- web/src/test/apiMock.ts

Read:
- docs/superpowers/specs/2026-05-29-bank-tag-filter-compact-panel-design.md
- web/src/test/BankDetailsPage.test.tsx
- web/src/test/BankDetailsApi.test.ts
- web/src/test/apiMock.ts
- web/src/pages/BankDetailsPage.tsx

Requirements:
- Stop asserting the old tree visual role if the new panel uses `menu`, `listbox`, or named `list`.
- Assert the panel contains clickable rows for:
  - `全部`;
  - `未分类`;
  - a primary tag;
  - a child tag.
- Add or update tests proving `未分类` click sends `category_code=uncategorized`.
- Add or update tests proving primary click sends `category_primary_label` and no `category_code`.
- Add or update tests proving child click sends exact `category_code`.
- Assert filter changes reset page to 1.
- Assert account/date/search are preserved.
- Assert export inherits active `未分类`, primary, and child filters where practical.
- Assert toolbar summary/count updates after each selection.
- Keep tests behavioral; do not overfit to CSS class names except existing source checks that intentionally guard against regressions.
- Return changed files and tests run.
```

## Worker 4: Backend Verification Only If Needed

```text
/goal Verify backend support for `category_code=uncategorized` remains correct for the compact panel, changing backend only if a failing test proves a gap.

Owned files only if changes are required:
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- tests/test_bank_details_service.py
- tests/test_bank_details_sql_runtime.py

Read:
- docs/superpowers/specs/2026-05-29-bank-tag-filter-compact-panel-design.md
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- tests/test_bank_details_service.py
- tests/test_bank_details_sql_runtime.py

Requirements:
- Do not add a new backend query parameter.
- Preserve existing `category_code=uncategorized` behavior: match rows where effective category is null/empty.
- Preserve primary/sub label filters.
- Do not alter automatic tag rule matching semantics.
- If no backend change is needed, report that explicitly.
- If backend changes are made, run:
  `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_details_sql_runtime -v`.
```

## Serial Integration Prompt

```text
/goal Integrate the compact grouped bank tag filter panel work into one coherent implementation and remove regressions.

Check:
- The toolbar still renders one `标签筛选` button.
- The hover panel no longer looks like a file tree.
- The panel is compact: small width, short rows, minimal padding, lightweight counts.
- `全部` is clickable and clears filters.
- `未分类` is clickable and filters uncategorized rows.
- Primary rows are clickable and filter all rows under that primary label.
- Child rows are clickable and filter exact tags.
- A primary with one child still shows both the primary and the child.
- Visible groups are default-expanded.
- The selected row is visibly highlighted.
- Selection closes the panel.
- Click-away and `Esc` close the panel.
- Filter changes reset pagination and preserve account/date/search.
- Export inherits the same active filter as the visible table.
- No large CSS rewrite was introduced.
- No heavy external UI library was introduced.
- Backend contracts were not expanded.

Run:
- cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx
- cd web && npm run build
- PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_details_sql_runtime -v  # only if backend files changed
- git diff --check
```

## Final Verification Prompt

```text
/goal Review and verify the complete compact grouped bank tag filter panel implementation against the approved spec before reporting completion.

Verify from tests and diff:
- One stable `标签筛选` button remains.
- The panel uses compact grouped MUI rows, not a TreeView/RichTreeView/file-tree visual.
- The panel dimensions and row heights are intentionally small.
- Counts are lightweight and right-aligned.
- `全部`, `未分类`, primary tags, and child tags all select the expected filter.
- `未分类` sends `category_code=uncategorized`.
- Primary selection sends `category_primary_label` without `category_code`.
- Child selection sends exact `category_code`.
- Filter changes reset pagination to page 1.
- Account, date range, and search keyword are preserved.
- Export inherits active filters.
- No automatic tag rule semantics changed.
- No manual bank tagging UI returned.
- No DataGrid conversion happened.
- No large CSS-driven implementation or heavy UI dependency was added.

Run:
- cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx
- cd web && npm run build
- git diff --check
- If backend files changed: PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_details_sql_runtime -v

Final response should include:
- implementation summary;
- changed files;
- verification results;
- dependency changes;
- residual risks, especially whether visual compactness was manually inspected.
```

## Prompt Review

### Review Pass 1

Issues found:

- The old prompt allowed `RichTreeView`; this conflicts with the new visual direction.
- The old prompt did not force `未分类` to be clickable.
- The old prompt did not force primary group rows to be clickable.
- The old prompt allowed a visually large panel.

Resolution:

- Added a hard ban on `RichTreeView`/file-tree visual for this revision.
- Added hard requirements for clickable `全部`、`未分类`、主标签、子标签.
- Added compact size targets for width, height, row height, typography, and counts.

### Review Pass 2

Issues found:

- A primary tag with one child could be collapsed into one row, hiding the distinction between primary summary filtering and exact child filtering.
- Tests might keep asserting `role="tree"` and miss the intended visual redesign.
- Export inheritance needed to include `未分类`, not only primary/sub tags.

Resolution:

- Added hard requirement to show one-child groups as both primary and child rows.
- Added test guidance to stop overfitting to the old tree role.
- Added export inheritance coverage for `未分类`, primary, and child filters.

### Review Pass 3

Issues found:

- Parallel work could conflict if workers edit the same files blindly.
- Backend work should not happen unless needed because this is primarily a UI redesign.
- The prompt needed explicit current-state risks from the existing implementation.

Resolution:

- Split tasks by ownership and made backend verification conditional.
- Added serial setup and serial integration phases around parallel-safe work.
- Added current-state risks: static `未分类`, display-only primary rows, old `tree` role assumptions, and stale `bank-category-tree-*` naming.

### Final Self-Review Checklist

- Covers small UI requirement: yes.
- Covers no browser visual companion requirement: yes, prompt uses text/diff verification and optional manual inspection only.
- Covers `未分类` clickable filtering: yes.
- Covers primary clickable filtering: yes.
- Covers child exact filtering: yes.
- Covers default-expanded hierarchy: yes.
- Covers one-child group display: yes.
- Covers export inheritance: yes.
- Covers no large CSS / no heavy UI dependency: yes.
- Covers backend contract safety: yes.
- Covers tests and final verification: yes.

This prompt is ready for Codex execution.
