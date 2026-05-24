# 进项发票使用情况页面多任务执行 Prompt

This prompt is intended for Codex workers implementing the approved `进项发票使用情况` feature.

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Primary spec:

```text
docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md
```

## Orchestrator Prompt

```text
/goal Implement the production-grade 进项发票使用情况 page as a real read-only query workflow with a production API contract for later 发票反提 OA and 支付状态规则设置 workflows.

You are working in /Users/yu/Desktop/fin-ops-platform.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- DESIGN.md
- docs/dev/frontend.md
- docs/product-specs/workbench.md
- docs/product-specs/tax-offset-and-etc.md
- docs/dev/etc-business-batches-api.md
- docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md

Hard requirements:
- This is not a temporary/rescue implementation. Produce integrated production-grade code aligned with the existing architecture.
- First version scope is real read-only query + production API contract design.
- Add a left-sidebar page named 进项发票使用情况, route /input-invoice-usage.
- Do not use DataGrid. Use MUI native Table components only.
- One row = one invoice. Aggregate repeated invoice line items into one invoice row and expose line details through detail.
- Keep all key information in one page width without horizontal scrolling.
- Use 4 big columns: 进项发票, 支付状态, OA, 流水.
- Do not use two-layer DataGrid-style headers and do not repeat small-column labels inside each row.
- Every small column has a header menu with suitable single/multi-select filtering, select all, clear, ascending sort and descending sort.
- Filtering, sorting and pagination must be server-side.
- Long cell content may wrap to two lines. If still too long, show an expand button.
- 发票号码 column shows invoice number and a date tag; add a detail button next to the date.
- 流水 对方户名 column shows counterparty and transaction date tag; add a detail button next to the date.
- All detail buttons must show complete information for that item, not just the visible row summary.
- 支付状态 column must have a distinct suitable background color.
- Big-column separators and small-column separators must be visually distinct.
- 以发票反提 OA opens a right-side workflow drawer, not a dialog and not a new sidebar page.
- 发票与支付状态规则设置 opens a right-side workflow drawer, not a dialog and not a new sidebar page.
- Drawers should feel like Codex show/hide sidebar: transform-based, smooth, no table refetch on open/close, lazy data loading, skeleton while loading, mutually exclusive.
- 发票反提 OA is a future confirmed workflow. Its design and contracts must reference the ETC management page's create OA draft flow: create draft, save oaDraftId/oaDraftUrl, detect OA in progress, allow local draft revoke/release, use expectedVersion, idempotencyKey and audit.
- Do not fake OA draft creation or rule saving in the first version.
- First version must implement a real read-only oa-reverse preview endpoint if the drawer shows candidate counts/totals/groups; the frontend must not calculate or fake those values locally.
- If real export is not implemented, do not add a clickable fake export entry.
- Preserve unrelated user changes. Do not revert any modified files you did not change.

Execution order:
1. Serial preparation: inspect current git status and relevant existing frontend/backend patterns.
2. Parallel batch A:
   - Worker 1: backend query service and API.
   - Worker 2: frontend API/types/table page.
   - Worker 3: drawer/detail/filter UI components.
3. Serial integration: wire routes/menu/server handlers, reconcile DTO names, run tests.
4. Verification: run backend focused unittest, frontend tests, and build.
5. Report changed files, tests, remaining risks and any contracts intentionally left for the future OA write phase.
```

## Shared Constraints For Every Worker

- You are not alone in the codebase. Other agents may be editing disjoint files. Do not revert or overwrite unrelated changes.
- Use TDD. Write focused failing tests first, run them and confirm they fail for the expected reason, implement minimal production code, then rerun tests.
- Follow repository instructions in `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, and the approved spec.
- Do not add dependencies.
- Keep diffs scoped to your owned files.
- Use MUI native components only on the frontend. Do not use `DataGrid`.
- Use existing helper patterns before creating new abstractions.
- Do not guess unknown API fields, database columns, response shapes, IDs, or status values. Inspect source of truth or keep fields unavailable.
- Return status, changed files, tests run, blockers and integration notes.

## Frontend Integration Contract

- `InputInvoiceUsagePage.tsx` owns list rows, query state, filter state, sort state, pagination, active workflow drawer and detail target state.
- `web/src/features/inputInvoiceUsage/api.ts` owns every API function: rows, filter options, invoice/bank/OA detail, row relation detail, payment status rules and read-only OA reverse preview.
- `InputInvoiceUsageTable` receives rows/config and emits only callbacks: `onFilterMenuOpen(field)`, `onSortChange(field, direction)`, `onOpenDetail(target)`, `onToggleCellExpand(rowId, cellId)`.
- `InputInvoiceUsageFilterMenu` receives `fieldConfig`, `currentFilter`, `options`, `onApply(filter)`, `onClear(field)`, `onSort(direction)`.
- `InputInvoiceUsageDetailDrawer` receives `target`, `open`, `loadDetail(target)`, `onClose()`.
- `OaReverseWorkspaceDrawer` receives `open`, `sourceFilters`, `selectedInvoiceIds`, `loadPreview(request)`, `onClose()` and has no submit/create-draft callback in v1.
- `PaymentStatusRulesDrawer` receives `open`, `loadRules()`, `onClose()` and has no save callback in v1.
- Shared state shapes:
  - `activeWorkflow: "oaReverse" | "paymentRules" | null`
  - `detailTarget: { kind: "invoice" | "bank" | "oa" | "relationList"; id: string; rowId?: string } | null`

## Worker 1: Backend Query Service And API

```text
/goal Implement the backend read-only query service and API for the 进项发票使用情况 page.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md
- backend/src/fin_ops_platform/services/imports.py
- backend/src/fin_ops_platform/services/tax_offset_service.py
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py
- backend/src/fin_ops_platform/services/oa_projection_sync.py
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/app/routes_tax.py
- tests/test_pending_invoice_service.py
- tests/test_live_workbench_service.py

Owned write scope:
- backend/src/fin_ops_platform/services/input_invoice_usage_service.py
- tests/test_input_invoice_usage_service.py
- tests/test_input_invoice_usage_api.py
- backend/src/fin_ops_platform/app/server.py only for thin /api/input-invoice-usage route wiring and service construction

Do not edit:
- ETC service implementation
- Tax offset calculation behavior
- Existing pending invoice behavior
- Frontend files

Required behavior:
1. Add InputInvoiceUsageQueryService with read-only responsibilities only.
2. List rows one row per input invoice.
3. Aggregate repeated invoice line items by stable invoice identity:
   - prefer digital_invoice_no
   - else invoice_code + invoice_no
   - else stable invoice id fallback
4. Preserve line items in detail payload.
5. Resolve related OA and bank transaction summaries from existing relation facts only.
6. Before implementation, document in test names or service comments which existing source of truth is used for invoices, bank transactions, OA projection and active relations. Use WorkbenchPairRelationService active relations (`row_ids`, `row_types`, `relation_mode`, active/non-withdrawn state) where available.
7. Represent one-to-many OA and bank relations without dropping data:
   - deterministic primary summary
   - relationCount
   - hasMultiple
   - detailMode single|list|none
   - summaries array
8. Calculate conservative payment status on the backend using the spec's priority order:
   - 现金往来 陈秀云 + OA + bank + fully matched
   - 已付款 + OA + bank + fully matched
   - 冲 周洁莹 + OA + no bank + amount matched
   - 冲 刘树刚不付 + OA + no bank
   - 冲 韦代连 + OA + no bank
   - 待付款 + OA + no bank
   - otherwise 待处理 with reason
   Fully matched means the active relation proves invoice+OA+bank are in one relation and invoice/OA/bank amounts match within 0.01. If not provable, return 待处理.
9. Implement GET /api/input-invoice-usage/rows with page, page_size, keyword, invoice_date_from, invoice_date_to, month, filters, sort_field, sort_direction.
10. Implement canonical filter parsing exactly as the spec defines: URL-encoded JSON array, whitelisted fields, operator validation and single-sort whitelist.
11. Implement GET /api/input-invoice-usage/filter-options with context-aware options.
12. Implement detail endpoints:
   - GET /api/input-invoice-usage/invoices/{invoiceId}/detail
   - GET /api/input-invoice-usage/bank-transactions/{bankTransactionId}/detail
   - GET /api/input-invoice-usage/oa/{oaId}/detail
   - GET /api/input-invoice-usage/rows/{rowId}/relation-details?kind=oa|bank
13. Implement GET /api/input-invoice-usage/payment-status-rules as read-only rule projection.
14. Implement POST /api/input-invoice-usage/oa-reverse/preview as a real read-only preview endpoint returning candidate counts, total amount, target applicant grouping and rejected invoices/reasons. It must not create drafts or persist batches.
15. Do not implement fake write endpoints for OA draft creation or rule saving. If route contracts are documented only, leave them out or explicitly unavailable according to existing API conventions.
16. Return structured validation errors for invalid paging, invalid sort field, invalid filter field and not found details.

TDD requirements:
- Add failing tests for one row per invoice with multiple line items.
- Add failing tests for server pagination/filter/sort.
- Add failing tests for payment status calculation.
- Add failing tests for rule priority and conservative fallback when fully matched cannot be proven.
- Add failing tests for one-to-many OA/bank relation DTO shape.
- Add failing tests for detail payload completeness.
- Add failing tests for filter-options shape.
- Add failing tests for canonical filter operator/field validation.
- Add failing tests for read-only OA reverse preview and that it performs no writes.
- Add failing API tests for route wiring and validation errors.

Run:
- PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service tests.test_input_invoice_usage_api -v

Expected final status:
- DONE if tests pass and route contract is documented in code/tests.
- DONE_WITH_CONCERNS if OA detail source is unavailable and correctly represented as detailAvailable=false.
```

## Worker 2: Frontend Page, API And Main Table

```text
/goal Implement the 进项发票使用情况 frontend page, route, menu entry, API client, types and MUI Table main layout.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md
- web/src/README.md
- web/src/app/router.tsx
- web/src/components/shell/sidebarItems.ts
- web/src/components/common/PageScaffold.tsx
- web/src/contexts/PageSessionStateContext.tsx
- web/src/pages/TaxOffsetPage.tsx
- web/src/pages/NoOaBankBatchPage.tsx
- web/src/pages/EtcTicketManagementPage.tsx
- web/src/features/apiClient.ts
- web/src/test/renderHelpers.tsx
- web/src/test/apiMock.ts

Owned write scope:
- web/src/features/inputInvoiceUsage/types.ts
- web/src/features/inputInvoiceUsage/api.ts
- web/src/pages/InputInvoiceUsagePage.tsx
- web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx
- web/src/components/inputInvoiceUsage/ExpandableCellText.tsx
- web/src/app/router.tsx
- web/src/components/shell/sidebarItems.ts
- web/src/test/InputInvoiceUsagePage.test.tsx

Do not edit:
- Backend files
- DataGrid hooks
- Existing bank details, tax offset or ETC page behavior except imports needed for route/menu patterns

Required behavior:
1. Add sidebar item 进项发票使用情况 and route /input-invoice-usage.
2. Add typed API client for rows, filter options, row relation detail, details, payment status rules and read-only OA reverse preview.
3. Use MUI Table components only; no DataGrid import and no .MuiDataGrid-root surface.
4. Render 4 big columns:
   - 进项发票
   - 支付状态
   - OA
   - 流水
5. Use small columns inside each big column exactly as approved:
   - 发票号码, 销方, 价税合计, 不含税/税率税额, 业务/货物劳务
   - 支付状态
   - OA申请人, 项目名称
   - 对方户名, 金额, 摘要/备注
6. Table header shows small-column labels once. Row cells do not repeat labels.
7. Keep layout within page width. Use fixed layout, responsive widths and no horizontal page scroll.
8. Long text wraps up to two lines and then exposes expand/collapse.
9. 发票号码 cell shows date tag and detail button next to date.
10. 对方户名 cell shows trade date tag and detail button next to date.
11. 支付状态 column has distinct background.
12. Big-column separators and small-column separators are visually distinct.
13. Persist query/page/filter/sort/drawer state with existing page session patterns where appropriate.
14. Do not add a clickable fake export button if real export is not implemented.

TDD requirements:
- Add failing test that route/menu render page.
- Add failing test that no DataGrid is rendered.
- Add failing test that headers render once and row cells do not duplicate labels.
- Add failing test for four big column groups and expected small columns.
- Add failing test for long text expand button.
- Add failing test for invoice and bank detail buttons.
- Add failing test for server-side pagination/sort callback behavior.
- Add failing test that export is absent or disabled when no real export API is implemented.

Run:
- npm test -- InputInvoiceUsagePage
- npm run build

Expected final status:
- DONE if tests pass and page uses backend API DTOs.
- DONE_WITH_CONCERNS if final backend field names need integration adjustment.
```

## Worker 3: Filters, Details And Workflow Drawers

```text
/goal Implement filter menus, detail drawer and the two right-side workflow drawers for 进项发票使用情况.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md
- web/src/components/common/AppDrawer.tsx
- web/src/components/workbench/DetailDrawer.tsx
- web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx
- web/src/pages/EtcTicketManagementPage.tsx
- web/src/features/etc/api.ts
- web/src/features/etc/types.ts
- web/src/test/DetailDrawer.test.tsx
- web/src/test/EtcTicketManagementPage.test.tsx

Owned write scope:
- web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx
- web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx
- web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx
- web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx
- web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx
- Narrow edits to web/src/pages/InputInvoiceUsagePage.tsx only to integrate callbacks/state with Worker 2

Do not edit:
- Backend files
- ETC page behavior
- Sidebar/router except if Worker 2 has not yet wired and orchestrator asks you explicitly

Required behavior:
1. Every small-column header uses InputInvoiceUsageFilterMenu.
2. Menu supports field-appropriate single select, multi select, select all, clear, ascending sort and descending sort.
3. Menu options come from API/filter-options state, not hardcoded complete business lists.
4. Detail drawer supports invoice, bank transaction and OA detail types.
5. Detail drawer lazy-loads full detail after opening and shows skeleton/loading state.
6. If OA detail is unavailable, do not show fake full detail.
7. Implement OaReverseWorkspaceDrawer as a right-side drawer, not a dialog:
   - Calls the backend read-only preview API through the `loadPreview` prop after opening.
   - Shows candidate invoice count, total amount, applicant/account grouping and un-submittable reasons when provided.
   - Does not calculate candidate count, total amount, grouping or rejection reasons locally.
   - Does not fake successful OA draft creation.
   - Its visible copy and component structure must make later create-draft integration straightforward.
8. Implement PaymentStatusRulesDrawer as a right-side drawer, not a dialog:
   - Shows Sheet4 rule matrix.
   - Shows pending dropdown directions.
   - Reads from backend payment-status-rules API if available.
   - Is read-only in v1. Do not render editable controls, save button or saved-success state unless the PUT API is implemented with versioning/idempotency/audit/tests.
9. Drawers are mutually exclusive.
10. Drawer open/close uses MUI Drawer anchor=right, transform-based animation and does not trigger main rows refetch.
11. Desktop drawer width is large enough for workflow content; mobile full-screen.

TDD requirements:
- Add failing tests for filter menu select all, clear, asc, desc and multi-select behavior.
- Add failing tests for invoice/bank/OA detail lazy loading.
- Add failing tests that both workflow buttons open right-side drawers and not dialogs.
- Add failing tests that drawers are mutually exclusive.
- Add failing test that opening/closing a drawer does not call rows API again.
- Add failing test that OA reverse preview calls loadPreview and does not compute totals from visible table rows.
- Add failing tests that OA reverse drawer does not expose a fake successful submit/draft path in first version.
- Add failing test that payment rules drawer is read-only and has no save button in v1.

Run:
- npm test -- InputInvoiceUsageFiltersAndDrawers
- npm run build

Expected final status:
- DONE if tests pass and drawers integrate with the page.
- DONE_WITH_CONCERNS if backend preview/rules APIs are not yet merged and mocks need final DTO names.
```

## Serial Integration Prompt

```text
/goal Integrate the backend and frontend worker outputs for 进项发票使用情况 and verify the complete first-version workflow.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md
- All changed files from Worker 1, Worker 2 and Worker 3

Tasks:
1. Inspect git status and make sure no unrelated user edits are reverted.
2. Reconcile DTO field names between backend and frontend.
3. Ensure /input-invoice-usage loads through the sidebar.
4. Ensure rows, filter options, details and payment-status-rules use the same API contract.
5. Ensure no DataGrid is imported by the new feature.
6. Ensure OA reverse and payment rules use right-side drawers, not dialogs.
7. Ensure first version does not fake OA draft creation or fake rule saving.
8. Ensure first version uses backend read-only preview for OA reverse and does not compute preview totals on the frontend.
9. Ensure export is absent or disabled if no real export API is implemented.
10. Run focused backend tests:
   PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service tests.test_input_invoice_usage_api -v
11. Run focused frontend tests:
   npm test -- InputInvoiceUsage
12. Run frontend build:
   npm run build
13. If a local dev server is needed, start it and visually verify the page in the in-app browser at the running localhost URL.

Return:
- Status
- Changed files
- Tests run and results
- Any remaining risks
- Any deferred future contracts, especially 发票反提 OA create-draft implementation
```
