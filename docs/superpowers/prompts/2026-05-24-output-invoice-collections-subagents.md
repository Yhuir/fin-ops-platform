# 销项发票收款情况页面多任务执行 Prompt

This prompt is intended for Codex workers implementing the approved `销项发票收款情况` feature.

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Primary spec:

```text
docs/superpowers/specs/2026-05-24-output-invoice-collections-design.md
```

Source workbook:

```text
/Users/yu/Desktop/sy/财务运营平台/界面.xlsx
```

Relevant workbook sheets:

```text
（待收款）销项发票和收款流水
Sheet6
Sheet7
```

## Orchestrator Prompt

```text
/goal Implement the production-grade 销项发票收款情况 page as a real read-only query workflow with Sheet6 status-rule visibility, Sheet7 receipt preview, and production service boundaries for later editable status rules and formal receipt lifecycle.

You are working in /Users/yu/Desktop/fin-ops-platform.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- DESIGN.md
- docs/dev/frontend.md
- docs/dev/backend.md
- docs/product-specs/reconciliation.md
- docs/product-specs/workbench.md
- docs/product-specs/exception-handling.md
- docs/product-specs/imports.md
- docs/superpowers/specs/2026-05-24-output-invoice-collections-design.md
- docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md
- web/src/pages/InputInvoiceUsagePage.tsx if present
- web/src/components/inputInvoiceUsage/ if present
- backend/src/fin_ops_platform/services/input_invoice_usage_service.py if present

Hard requirements:
- This is not a temporary/rescue implementation. Produce integrated production-grade code aligned with the existing architecture.
- Use the same table design pattern as 进项发票使用情况: big grouped columns, small columns, MUI native Table components, server-side pagination/filtering/sorting, right-side drawers.
- Add a left-sidebar page named 销项发票收款情况. Recommended route: /output-invoice-collections.
- Main row contract: one row = one formal output invoice.
- Red and blue invoices remain separate rows; red/blue relationships are shown as relation summaries and details, not by merging rows.
- First phase scope is real read-only query + receipt preview contracts only.
- Do not save status rules.
- Do not create formal receipt numbers.
- Do not save receipt history.
- Do not implement receipt void/reissue.
- Do not add a persistent read model table in this phase.
- Do not add a fake export button if no real export API exists.
- Use MUI native high-performance components. Follow the existing InputInvoiceUsage MUI Table pattern. Do not introduce a new table library.
- Keep all key information in one page width without horizontal scrolling.
- Use 4 big columns: 销项发票, 收款状态, 收入流水, 收据.
- Header labels appear in the header only. Do not repeat small-column labels inside every row.
- Every small-column header has a field-appropriate filter/sort menu. Enum menus support select all and clear; all sortable fields support ascending and descending sort; filtering/sorting/pagination are server-side.
- Long cell content may wrap to two lines. If still too long, show an expand button.
- Every detail button must lazy-load complete information for that item, not just repeat visible row summary.
- Big-column separators and small-column separators must be visually distinct.
- 收款状态 column must have a distinct low-saturation background/tone.
- The three workflow buttons open right-side workflow drawers, not dialogs and not new sidebar pages:
  - 销项发票收款情况类型设置
  - 已出收据
  - 待出收据
- Sheet6 drawer is read-only in phase 1. It shows status rules, recognition mode, required facts, linked workbench matching requirements and priority. It has no save/edit controls.
- Sheet7 drawer is a receipt preview. Receipt preview amount defaults to the selected income bank transaction amount.
- If one output invoice has one income transaction, use that transaction by default for receipt preview.
- If one output invoice has multiple income transactions, require the user to select one transaction inside the drawer, then preview with that transaction amount.
- If there is no linked income transaction, do not render a generated receipt template; show the reason and pending amount reference.
- Red/refund status rows must not auto-generate receipt preview in phase 1; show a blocked reason.
- Receipt history drawer must not fake data. If there is no formal history source, show an empty state backed by an API response such as sourceAvailable=false.
- Preserve unrelated user changes. Do not revert or overwrite modified files you did not create.

Execution order:
1. Serial preparation:
   - inspect current git status;
   - inspect existing 进项发票使用情况 implementation and tests if present;
   - inspect existing workbench pair relation, invoice and bank transaction source models;
   - confirm no implementation will depend on the Excel file at runtime.
2. Parallel batch A:
   - Worker 1: backend query service, status-rule service, receipt preview service and API routes.
   - Worker 2: frontend API/types/page/table/menu route.
   - Worker 3: detail drawer and three right-side workflow drawers.
3. Serial integration:
   - reconcile DTO field names;
   - extract only safe shared UI utilities if it reduces duplication with 进项发票使用情况;
   - verify route/menu/server handlers;
   - ensure no fake write paths exist.
4. Verification:
   - run focused backend tests;
   - run focused frontend tests;
   - run frontend build;
   - if practical, visually inspect in browser that there is no horizontal scroll and drawers do not refetch the main table.
5. Report changed files, tests, remaining risks and deferred future contracts for editable rules and formal receipt lifecycle.
```

## Shared Constraints For Every Worker

- You are not alone in the codebase. Other agents may be editing disjoint files. Do not revert or overwrite unrelated changes.
- Use TDD. Write focused failing tests first, run them and confirm they fail for the expected reason, implement minimal production code, then rerun tests.
- Follow repository instructions in `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, `DESIGN.md`, and the approved spec.
- Do not add dependencies.
- Keep diffs scoped to owned files.
- Reuse existing code patterns and helper APIs before adding abstractions.
- Do not guess unknown API fields, database columns, response shapes, IDs or status values. Inspect source of truth or represent data as unavailable.
- Do not make a read model table in this phase.
- Do not implement fake write operations.
- Return status, changed files, tests run, blockers and integration notes.

## Backend API Contract

API group:

```text
/api/output-invoice-collections
```

Required endpoints:

```text
GET /api/output-invoice-collections/rows
GET /api/output-invoice-collections/filter-options
GET /api/output-invoice-collections/invoices/{invoice_id}/detail
GET /api/output-invoice-collections/bank-transactions/{bank_transaction_id}/detail
GET /api/output-invoice-collections/rows/{row_id}/relation-details?kind=bank|red_invoice|receipt
GET /api/output-invoice-collections/status-rules
POST /api/output-invoice-collections/receipt-preview
GET /api/output-invoice-collections/receipts/history?invoice_id=...
```

Rows query parameters:

```text
page=1
page_size=50
keyword=...
invoice_date_from=YYYY-MM-DD
invoice_date_to=YYYY-MM-DD
month=YYYY-MM or all
filters=<URL encoded JSON array>
sort_field=invoice_date
sort_direction=asc|desc
```

Read-model-shaped response should include:

```text
rows
pagination
summary
filterConfig
readModelStatus
generatedAt
sourceVersion
```

For phase 1, `readModelStatus` may be `live_query`.

## Frontend Integration Contract

- `OutputInvoiceCollectionsPage.tsx` owns list rows, query state, filter state, sort state, pagination, active workflow drawer and detail target state.
- `web/src/features/outputInvoiceCollections/api.ts` owns every API function: rows, filter options, invoice detail, bank detail, row relation detail, status rules, receipt preview and receipt history.
- `OutputInvoiceCollectionsTable` receives rows/config and emits callbacks only:
  - `onFilterApply(filter)`
  - `onFilterClear(field)`
  - `onSortChange(field, direction?)`
  - `onOpenDetail(target)`
  - `onOpenWorkflow(target)`
  - `onToggleCellExpand(rowId, cellId)`
- `CollectionStatusRulesDrawer` receives `open`, `loadRules()`, `onClose()`.
- `ReceiptHistoryDrawer` receives `open`, `invoiceId`, `loadHistory(invoiceId)`, `onClose()`.
- `ReceiptPreviewDrawer` receives `open`, `row`, `loadPreview(request)`, `onClose()`.
- Shared state shapes:
  - `activeWorkflow: { kind: "statusRules" } | { kind: "receiptHistory"; invoiceId: string; rowId: string } | { kind: "receiptPreview"; rowId: string } | null`
  - `detailTarget: { kind: "invoice" | "bank" | "relationList"; id: string; rowId?: string; relationKind?: "bank" | "red_invoice" | "receipt" } | null`

## Worker 1: Backend Query Service, Status Rules, Receipt Preview And API

```text
/goal Implement the backend read-only query service and API for the 销项发票收款情况 page, including Sheet6 status rules and Sheet7 receipt preview contracts.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-24-output-invoice-collections-design.md
- docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md
- backend/src/fin_ops_platform/domain/enums.py
- backend/src/fin_ops_platform/domain/models.py
- backend/src/fin_ops_platform/services/imports.py
- backend/src/fin_ops_platform/services/input_invoice_usage_service.py if present
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py
- backend/src/fin_ops_platform/services/workbench_amount_check_service.py
- backend/src/fin_ops_platform/services/reconciliation.py
- backend/src/fin_ops_platform/app/server.py
- tests/test_input_invoice_usage_service.py if present
- tests/test_input_invoice_usage_api.py if present

Owned write scope:
- backend/src/fin_ops_platform/services/output_invoice_collection_service.py
- tests/test_output_invoice_collection_service.py
- tests/test_output_invoice_collection_api.py
- backend/src/fin_ops_platform/app/server.py only for thin /api/output-invoice-collections route wiring and service construction

Do not edit:
- Frontend files
- ETC service implementation
- Existing input invoice usage behavior except reading patterns
- Workbench matching behavior except using existing public service APIs

Required behavior:
1. Add `OutputInvoiceCollectionQueryService` with read-only responsibilities only.
2. Add `OutputInvoiceCollectionStatusRuleService` as a distinct service boundary:
   - phase 1 returns static Sheet6 rules;
   - exposes classification logic used by query service;
   - no save/update route.
3. Add `OutputInvoiceReceiptPreviewService` as a distinct service boundary:
   - phase 1 returns Sheet7 preview DTO;
   - no formal receipt creation route.
4. List rows one row per output invoice.
5. Aggregate repeated invoice line items by stable output invoice identity:
   - prefer digital_invoice_no;
   - else invoice_code + invoice_no;
   - else stable invoice id fallback.
6. Preserve line items in invoice detail payload.
7. Resolve related income bank transaction summaries from existing active relation facts only.
8. Only income bank transactions (`TransactionDirection.INFLOW`) count as receipt/collection transactions.
9. Red and blue invoices remain separate rows. Expose red/blue relation summary and detail links when conservatively provable.
10. Red invoice relation conservative proof for phase 1:
    - positive/negative output invoice amount absolute values match within 0.01;
    - and digital invoice number, invoice code/number or remark text links the pair.
    If not provable, do not mark as confirmed.
11. Calculate `collectionStatus` on the backend using this priority:
    - 开票已收款，冲红并退款: positive invoice has income collection, linked red invoice exists, and corresponding outflow refund transaction is provable.
    - 开票后冲红: linked red/blue output invoice relation exists and no income/refund flow is present.
    - 已收款: output invoice + active income bank relations + received total equals invoice total within 0.01 + relation amount check can prove match.
    - 待收款，已收部分款: output invoice + active income bank relations + received total is less than invoice total.
    - 待收款: output invoice has no income bank transaction.
    - 待处理: relationship is ambiguous or cannot be proven.
12. Phase 1 must not show 主表 `待冲红` from user action, because there is no manual status-write path. Include `待冲红` only in status rules.
13. Implement `GET /api/output-invoice-collections/rows` with page, page_size, keyword, invoice_date_from, invoice_date_to, month, filters, sort_field, sort_direction.
14. Implement canonical filter parsing: URL-encoded JSON array, whitelisted fields, operator validation and sort whitelist.
15. Implement `GET /api/output-invoice-collections/filter-options` with context-aware options.
16. Implement detail endpoints:
    - invoice detail;
    - bank transaction detail;
    - row relation details for bank, red_invoice, receipt.
17. Implement `GET /api/output-invoice-collections/status-rules` as read-only Sheet6 projection.
18. Implement `POST /api/output-invoice-collections/receipt-preview`:
    - request identifies invoice row and selected bank transaction id;
    - if no eligible income transaction, return `canPreview=false` and reason;
    - if multiple income transactions and no selected transaction is provided, return candidates and require selection;
    - preview amount equals selected income bank transaction amount;
    - returns Chinese uppercase amount from backend;
    - red/refund rows return blocked preview reason in phase 1.
19. Implement `GET /api/output-invoice-collections/receipts/history?invoice_id=...`:
    - phase 1 returns `sourceAvailable=false` and an empty history array unless a real source already exists.
20. Return structured validation errors for invalid paging, invalid sort field, invalid filter field, invalid preview selection and not found details.
21. Do not add persistent read model tables. Return read-model-shaped metadata such as `readModelStatus: "live_query"` if useful.

TDD requirements:
- Add failing tests for one row per output invoice with multiple line items.
- Add failing tests for server pagination/filter/sort.
- Add failing tests for collection status calculation:
  - 已收款;
  - 待收款，已收部分款;
  - 待收款;
  - 开票后冲红;
  - 开票已收款，冲红并退款;
  - ambiguous fallback.
- Add failing tests that `待冲红` is present in rules but not emitted by automatic phase-1 row classification.
- Add failing tests for income-only bank relation counting; outflow refund should not count as collection.
- Add failing tests for one-to-many income bank relation DTO shape.
- Add failing tests for invoice detail payload completeness and red/blue relation details.
- Add failing tests for status rules endpoint shape.
- Add failing tests for receipt preview:
  - selected income transaction amount is used;
  - multiple transactions require selection;
  - no transaction blocks preview;
  - red/refund blocks preview;
  - uppercase amount returned by backend.
- Add failing tests for receipt history empty sourceAvailable=false response.
- Add failing API tests for route wiring and validation errors.

Run:
- PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_service tests.test_output_invoice_collection_api -v

Expected final status:
- DONE if tests pass and no write/fake receipt/rule endpoints exist.
- DONE_WITH_CONCERNS if a real receipt history source is unavailable and correctly represented as sourceAvailable=false.
```

## Worker 2: Frontend Page, API, Route, Menu And Main Table

```text
/goal Implement the 销项发票收款情况 frontend page, route, menu entry, API client, types and MUI Table main layout.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-24-output-invoice-collections-design.md
- docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md
- web/src/README.md
- web/src/app/router.tsx
- web/src/components/shell/sidebarItems.ts
- web/src/components/common/PageScaffold.tsx
- web/src/contexts/PageSessionStateContext.tsx
- web/src/pages/InputInvoiceUsagePage.tsx if present
- web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx if present
- web/src/features/inputInvoiceUsage/api.ts if present
- web/src/features/apiClient.ts
- web/src/test/renderHelpers.tsx
- web/src/test/apiMock.ts

Owned write scope:
- web/src/features/outputInvoiceCollections/types.ts
- web/src/features/outputInvoiceCollections/api.ts
- web/src/pages/OutputInvoiceCollectionsPage.tsx
- web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx
- web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx
- web/src/components/outputInvoiceCollections/ExpandableCellText.tsx if not safely shared
- web/src/components/invoiceRelations/* only if extracting small shared utilities is clearly beneficial
- web/src/app/router.tsx
- web/src/components/shell/sidebarItems.ts
- web/src/test/OutputInvoiceCollectionsPage.test.tsx
- narrow additions to web/src/test/apiMock.ts for the new API mocks

Do not edit:
- Backend files
- Existing input invoice usage behavior except extracting truly shared UI helpers with compatibility preserved
- DataGrid-related code
- Existing bank details, tax offset, turnover ledger or pending invoice behavior

Required behavior:
1. Add sidebar item `销项发票收款情况` and route `/output-invoice-collections`.
2. Add typed API client for rows, filter options, invoice detail, bank detail, relation details, status rules, receipt preview and receipt history.
3. Use MUI Table components only; no DataGrid import and no `.MuiDataGrid-root` surface.
4. Render 4 big columns:
   - 销项发票
   - 收款状态
   - 收入流水
   - 收据
5. Render small columns:
   - 销项发票: 发票号码, 购方, 价税合计, 税额/税率, 业务/货物劳务
   - 收款状态: 状态/依据/已收待收
   - 收入流水: 付款方/日期, 收款金额, 银行/摘要
   - 收据: 收据情况/操作
6. Header shows small-column labels once. Row cells do not repeat labels.
7. Keep layout within page width. Use fixed table layout, responsive widths and no horizontal page scroll.
8. Long text wraps up to two lines and then exposes expand/collapse.
9. 发票号码 cell shows date tag and detail button next to date.
10. 收入流水 付款方/日期 cell shows collection date tag and detail button next to date when a primary bank transaction exists.
11. 收款状态 column has distinct low-saturation background and status tone.
12. Big-column separators and small-column separators are visually distinct.
13. 收据 column conditionally shows:
    - 已出收据 button when receipt.statusCode is issued;
    - 待出收据 button when receipt.statusCode is pending;
    - reason text for not_available or blocked.
14. Top toolbar includes:
    - keyword search;
    - invoice date/month filters if consistent with existing patterns;
    - status filter entry;
    - 销项发票收款情况类型设置 button;
    - refresh button.
15. Do not add a clickable fake export button.
16. Persist query/page/filter/sort/drawer state with existing page session patterns where appropriate.
17. Keep drawer open/close state separate from row loading so opening drawers does not refetch rows.
18. Every small-column header uses `OutputInvoiceCollectionFilterMenu` or a compatible shared filter menu.
19. Menu options come from `/api/output-invoice-collections/filter-options`, not hardcoded complete business lists.
20. Field modes:
    - text: contains/search and sort;
    - enum_single or enum_multi: select all where applicable, clear, ascending sort and descending sort;
    - date: range and sort;
    - money: min/max range and sort.

TDD requirements:
- Add failing test that route/menu render page.
- Add failing test that no DataGrid is rendered.
- Add failing test that four big column groups and expected small columns render.
- Add failing test that row cells do not duplicate header labels.
- Add failing test for long text expand button.
- Add failing test for invoice and bank detail buttons.
- Add failing test for receipt status buttons and blocked/no-flow reason states.
- Add failing test for server-side pagination/sort/filter callback behavior.
- Add failing test for filter menu select all, clear, ascending sort and descending sort behavior.
- Add failing test that export is absent when no real export API is implemented.

Run:
- cd web && npm test -- OutputInvoiceCollectionsPage
- cd web && npm run build

Expected final status:
- DONE if tests pass and page uses backend API DTOs.
- DONE_WITH_CONCERNS if final backend field names need integration adjustment.
```

## Worker 3: Details, Status Rules, Receipt History And Receipt Preview Drawers

```text
/goal Implement detail drawer and the three right-side workflow drawers for 销项发票收款情况.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-24-output-invoice-collections-design.md
- docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md
- web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx if present
- web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx if present
- web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx if present
- web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx
- web/src/pages/EtcTicketManagementPage.tsx
- web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx if present

Owned write scope:
- web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx
- web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx
- web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx
- web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx
- web/src/test/OutputInvoiceCollectionsDrawers.test.tsx
- narrow additions to web/src/pages/OutputInvoiceCollectionsPage.tsx only to integrate drawer state/callbacks
- narrow additions to web/src/test/apiMock.ts for drawer endpoint mocks

Do not edit:
- Backend files
- Sidebar/router except if the orchestrator explicitly asks
- Existing input invoice usage drawer behavior except extracting a shared shell with compatibility preserved

Required behavior:
1. Implement `OutputInvoiceCollectionDetailDrawer`:
   - supports invoice, bank and relation-list targets;
   - lazy-loads after opening;
   - shows skeleton/loading state;
   - does not fake unavailable details.
2. Implement `CollectionStatusRulesDrawer` as a right-side drawer, not a dialog:
   - loads status rules from backend;
   - displays Sheet6 status matrix;
   - shows status, recognition mode, description, required facts, workbench matching requirement and priority;
   - is read-only in phase 1;
   - no save button, editable controls or saved-success state.
3. Implement `ReceiptHistoryDrawer` as a right-side drawer:
   - loads history from backend;
   - if `sourceAvailable=false`, shows `暂无系统内历史收据事实`;
   - does not invent history records;
   - if real records exist later, renders receipt number, date, amount, summary, handler, status and source.
4. Implement `ReceiptPreviewDrawer` as a right-side drawer:
   - loads preview from backend;
   - if one eligible income bank transaction exists, shows Sheet7-style receipt preview using that amount;
   - if multiple eligible income transactions exist, shows a MUI radio/list selector and reloads preview for selected transaction;
   - if no eligible income transaction exists, shows blocked reason and pending amount reference;
   - if red/refund row is blocked, shows blocked reason;
   - displays backend-provided uppercase amount;
   - no create/save/issue receipt button in phase 1.
5. Drawers are mutually exclusive.
6. Drawer open/close uses MUI Drawer anchor=right or a compatible existing drawer shell.
7. Drawer open/close must not trigger main rows API refetch.
8. Desktop drawer is wide enough for Sheet7 preview; mobile full-screen.
9. Sheet7 preview should be visually close to the workbook template while staying within app design constraints:
   - company title;
   - `收 据`;
   - date;
   - `兹收到 ... 交来下列款项`;
   - summary / amount / remark;
   - total uppercase and numeric amount;
   - supervisor / handler placeholders.

TDD requirements:
- Add failing tests for invoice/bank/relation detail lazy loading.
- Add failing tests that the three workflow buttons open right-side drawers and not dialogs.
- Add failing tests that drawers are mutually exclusive.
- Add failing test that opening/closing drawers does not call rows API again.
- Add failing test that status rules drawer is read-only and has no save button.
- Add failing test that receipt history empty sourceAvailable=false state does not fake records.
- Add failing test that receipt preview uses backend amount and uppercase amount.
- Add failing test that multiple income transactions require selection and reload preview with selected bank transaction id.
- Add failing test that no-flow and red/refund rows block template preview.
- Add failing test that receipt preview has no create/save/issue button in phase 1.

Run:
- cd web && npm test -- OutputInvoiceCollectionsDrawers
- cd web && npm run build

Expected final status:
- DONE if tests pass and drawers integrate with page state.
- DONE_WITH_CONCERNS if backend preview/history APIs are not yet merged and mocks need final DTO names.
```

## Serial Integration Prompt

```text
/goal Integrate the backend and frontend worker outputs for 销项发票收款情况 and verify the complete first-version workflow.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- docs/superpowers/specs/2026-05-24-output-invoice-collections-design.md
- docs/superpowers/prompts/2026-05-24-output-invoice-collections-subagents.md
- All changed files from Worker 1, Worker 2 and Worker 3

Tasks:
1. Inspect git status and make sure no unrelated user edits are reverted.
2. Reconcile DTO field names between backend and frontend.
3. Ensure `/output-invoice-collections` loads through the sidebar.
4. Ensure rows, filter options, details, status rules, receipt preview and receipt history use the same API contract.
5. Ensure no DataGrid is imported by the new feature.
6. Ensure the table uses 4 big column groups and does not require horizontal scrolling at common desktop widths.
7. Ensure one row equals one output invoice.
8. Ensure red/blue invoices remain separate rows with relation summaries/details.
9. Ensure status rules, receipt history and receipt preview use right-side drawers, not dialogs.
10. Ensure first version does not fake status-rule saving, receipt creation, receipt history or export.
11. Ensure receipt preview amount comes from selected income bank transaction and not from invoice total or pending amount.
12. Ensure no persistent read model table was introduced in this phase.
13. Run focused backend tests:
    PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_service tests.test_output_invoice_collection_api -v
14. Run focused frontend tests:
    cd web && npm test -- OutputInvoiceCollections
15. Run frontend build:
    cd web && npm run build
16. If practical, start the local backend and web server and visually verify in the in-app browser:
    - page opens from sidebar;
    - table has no horizontal scroll;
    - drawers open smoothly;
    - opening/closing drawers does not refetch the main table;
    - long text does not overlap or break layout.

Return:
- Status
- Changed files
- Tests run and results
- Any remaining risks
- Deferred future contracts:
  - editable status rules;
  - formal receipt creation/history/void/reissue;
  - persistent read model if production performance requires it.
```

## Prompt Review Checklist

Before execution, the orchestrator should confirm:

- Requirements are grounded in `docs/superpowers/specs/2026-05-24-output-invoice-collections-design.md`.
- Worker write scopes are disjoint enough for parallel work.
- Backend worker owns server route changes; frontend workers do not edit backend files.
- Frontend table/page worker and drawer worker have only narrow shared integration points.
- Phase 1 read-only/previews are enforced.
- There is no fake write path.
- There is no persistent read model work in phase 1.
- Receipt preview amount is explicitly selected-income-transaction based.
- Red/refund statuses have priority over generic paid/pending statuses.
- Every small-column header filter/sort menu is specified.
- Sheet6 and Sheet7 meanings are explicit.
- Tests cover the highest-risk product rules.
