# 进项发票使用情况 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production version of `进项发票使用情况`: a real read-only query page with MUI Table UI, server-side filtering/sorting/pagination, details, right-side workflow drawers, and production contracts for later reverse-OA draft creation.

**Architecture:** Add a cohesive `inputInvoiceUsage` vertical slice. The backend owns invoice aggregation, relation resolution, payment-status computation, filter options and read-only reverse-OA preview under `/api/input-invoice-usage`; the frontend owns typed API access, MUI Table presentation, filter menus, lazy detail drawer and two read-only workflow drawers. The implementation must preserve existing facts and relations, avoid DataGrid, avoid fake write paths, and leave future OA draft writes behind explicit contracts.

**Tech Stack:** Python unittest backend under `backend/src/fin_ops_platform`, React + TypeScript + Vite frontend under `web`, MUI Material native `Table`/`Drawer` components, existing app router/sidebar/session patterns.

---

## Source Documents

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `DESIGN.md`
- `docs/product-specs/workbench.md`
- `docs/product-specs/tax-offset-and-etc.md`
- `docs/dev/etc-business-batches-api.md`
- Spec: `docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md`
- Execution prompt: `docs/superpowers/prompts/2026-05-24-input-invoice-usage-subagents.md`
- Frontend docs: `web/README.md`, `docs/dev/frontend.md`
- Existing patterns: `web/src/pages/PendingInvoicesPage.tsx`, `web/src/pages/NoOaBankBatchPage.tsx`, `web/src/pages/EtcTicketManagementPage.tsx`
- Backend patterns: `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/pending_invoice_service.py`, `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`

## File Structure

Backend:

- Create `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`
  - Owns read-only aggregation, filters, sorting, detail payloads, rule projection and reverse-OA preview.
- Modify `backend/src/fin_ops_platform/app/server.py`
  - Thin route dispatch only for `/api/input-invoice-usage/*`.
- Create `tests/test_input_invoice_usage_service.py`
  - Service tests for aggregation, relation shape, filters, status rules and preview.
- Create `tests/test_input_invoice_usage_api.py`
  - Route and validation tests.

Frontend:

- Create `web/src/features/inputInvoiceUsage/types.ts`
  - DTOs, filter/sort types, drawer state types.
- Create `web/src/features/inputInvoiceUsage/api.ts`
  - All `/api/input-invoice-usage` calls.
- Create `web/src/pages/InputInvoiceUsagePage.tsx`
  - Page state, route-level orchestration, session state, drawers.
- Create `web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx`
  - MUI Table layout and cell composition.
- Create `web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx`
  - Header menu for filtering and sorting.
- Create `web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx`
  - Lazy detail viewer for invoice/bank/OA/relation-list targets.
- Create `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`
  - Read-only reverse-OA preview drawer.
- Create `web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx`
  - Read-only payment rule drawer.
- Create `web/src/components/inputInvoiceUsage/ExpandableCellText.tsx`
  - Two-line clamp and row-local expand/collapse.
- Modify `web/src/app/router.tsx`
  - Add `/input-invoice-usage`.
- Modify `web/src/components/shell/sidebarItems.ts`
  - Add `进项发票使用情况`.
- Create `web/src/test/InputInvoiceUsagePage.test.tsx`
  - Route, page, table and pagination tests.
- Create `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`
  - Filter menu, detail drawer and workflow drawer tests.

Do not edit the existing unrelated dirty files unless explicitly required:

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/test/WorkbenchPaneFilter.test.ts`

## Task 0: Serial Preparation

**Files:**
- Read: `AGENTS.md`
- Read: `README.md`
- Read: `ARCHITECTURE.md`
- Read: `DESIGN.md`
- Read: `docs/dev/frontend.md`
- Read: `docs/product-specs/workbench.md`
- Read: `docs/product-specs/tax-offset-and-etc.md`
- Read: `docs/dev/etc-business-batches-api.md`
- Read: `docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md`
- Read: `docs/superpowers/prompts/2026-05-24-input-invoice-usage-subagents.md`

- [ ] **Step 1: Inspect git status**

Run:

```bash
git status --short
```

Expected: record and preserve current dirty files. At plan creation time those are:

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/test/WorkbenchPaneFilter.test.ts`
- `docs/superpowers/plans/2026-05-24-input-invoice-usage.md`

- [ ] **Step 2: Read required architecture and product docs**

Confirm page and API work remain aligned with repository boundaries, frontend patterns, workbench relations, and ETC OA draft behavior.

- [ ] **Step 3: Inspect existing implementation patterns**

Read:

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `web/src/app/router.tsx`
- `web/src/components/shell/sidebarItems.ts`
- `web/src/pages/PendingInvoicesPage.tsx`
- `web/src/pages/EtcTicketManagementPage.tsx`
- `web/src/features/apiClient.ts`
- `web/src/test/renderHelpers.tsx`
- `web/src/test/apiMock.ts`

- [ ] **Step 4: Confirm worker write scopes**

Backend worker owns backend service/API/tests. Frontend page worker owns route/menu/types/api/table/page. Drawer worker owns filter/detail/workflow drawers and only narrow page integration. No worker may edit unrelated dirty files.

## Parallel Execution Strategy

Run three independent workers in parallel, then integrate serially:

- Worker 1: backend query service and API.
- Worker 2: frontend page, route, typed API and main table.
- Worker 3: filter menu, detail drawer and workflow drawers.

Workers must keep their write scopes disjoint except Worker 3 may make narrow integration edits to `InputInvoiceUsagePage.tsx` after Worker 2 creates it. If conflicts occur, integration owner resolves against the spec and frontend integration contract.

## Task 1: Backend Query Service And API

**Files:**
- Create: `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`
- Create: `tests/test_input_invoice_usage_service.py`
- Create: `tests/test_input_invoice_usage_api.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`

- [ ] **Step 1: Write failing service tests**

Cover:

- one row per input invoice when duplicate line items share `digital_invoice_no`;
- fallback identity by `invoice_code + invoice_no`;
- one-to-many OA/bank relation DTO shape;
- deterministic primary relation selection;
- rule priority and conservative fallback when full match cannot be proven;
- canonical filter field/operator validation;
- filter-options response shape;
- detail payloads and `detailAvailable=false` for unavailable OA projection;
- read-only `oa-reverse/preview` returns counts/totals/groups/rejections and performs no writes.

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service -v
```

Expected: fails because `input_invoice_usage_service.py` does not exist or methods are missing.

- [ ] **Step 2: Write failing API tests**

Cover:

- `GET /api/input-invoice-usage/rows`;
- `GET /api/input-invoice-usage/filter-options`;
- invoice/bank/OA detail endpoints;
- row relation details endpoint;
- `GET /api/input-invoice-usage/payment-status-rules`;
- `POST /api/input-invoice-usage/oa-reverse/preview`;
- structured `400` for invalid sort/filter/page and `404` for missing detail.

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v
```

Expected: fails because routes are not wired.

- [ ] **Step 3: Implement minimal read-only service**

Implement a focused service that accepts injected invoice/bank/OA/relation data sources where possible, so tests can exercise behavior without broad app bootstrapping. Use existing dataclasses from `imports.py` and relation shape from `WorkbenchPairRelationService`. Keep OA detail unavailable when no stable projection is supplied.

Backend implementation criteria:

- Source of truth must be documented before code in service comments or focused tests:
  - invoices from `Invoice`/`ImportNormalizationService` or existing repository;
  - bank transactions from `BankTransaction`/`ImportNormalizationService` or existing repository;
  - active relations from `WorkbenchPairRelationService.active_relations_for_row_ids` and relation snapshots (`row_ids`, `row_types`, `relation_mode`, active/non-withdrawn status);
  - OA projection from existing OA projection/manual import/workbench row only when stable; otherwise `detailAvailable=false`.
- Deterministic primary OA/bank summary selection:
  1. same active relation with highest completeness;
  2. closest amount to invoice `total_with_tax`;
  3. business time descending;
  4. stable ID ascending.
- Payment status priority:
  1. `现金往来（自动识别陈秀云oa，有流水）`
  2. `已付款（自动识别有oa有流水）`
  3. `冲（自动识别周洁莹oa，无流水）`
  4. `冲（自动识别刘树刚不付oa，无流水）`
  5. `冲（自动识别韦代连oa，无流水）`
  6. `待付款（自动识别有oa无流水）`
  7. `待处理`
- Fully matched means one active relation proves invoice + OA + bank are together, no withdrawn/conflict mark exists, and invoice/OA/bank amounts match within `0.01`. If not provable, return `待处理` with `reason`.
- Canonical filters must use URL-encoded JSON array and validate field/operator pairs. Allowed fields/operators:
  - `invoice_no`: `contains`, `equals`
  - `invoice_date`: `between`, `equals`
  - `seller_name`: `in`, `contains`
  - `seller_tax_no`: `contains`, `equals`
  - `total_with_tax`: `between`, `equals`
  - `amount`: `between`, `equals`
  - `tax_rate`: `in`
  - `tax_amount`: `between`, `equals`
  - `specific_business_type`: `in`
  - `taxable_item_name`: `in`, `contains`
  - `payment_status`: `in`
  - `oa_applicant`: `in`
  - `oa_application_type`: `in`, `equals`
  - `oa_project_name`: `in`, `contains`
  - `bank_counterparty_name`: `in`, `contains`
  - `bank_trade_time`: `between`, `equals`
  - `bank_amount`: `between`, `equals`
  - `bank_name`: `in`
  - `bank_summary`: `contains`

- [ ] **Step 4: Implement thin server routes**

Add dispatch in `backend/src/fin_ops_platform/app/server.py` for `/api/input-invoice-usage/*`. Route handlers parse params/body, call `InputInvoiceUsageQueryService`, and serialize structured responses. Do not add OA draft creation or rule save routes.

- [ ] **Step 5: Run backend focused verification**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service tests.test_input_invoice_usage_api -v
```

Expected: pass.

## Task 2: Frontend Page, API And Main Table

**Files:**
- Create: `web/src/features/inputInvoiceUsage/types.ts`
- Create: `web/src/features/inputInvoiceUsage/api.ts`
- Create: `web/src/pages/InputInvoiceUsagePage.tsx`
- Create: `web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx`
- Create: `web/src/components/inputInvoiceUsage/ExpandableCellText.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/components/shell/sidebarItems.ts`
- Create: `web/src/test/InputInvoiceUsagePage.test.tsx`

- [ ] **Step 1: Write failing page tests**

Cover:

- sidebar link `进项发票使用情况` navigates to `/input-invoice-usage`;
- route renders page;
- no `.MuiDataGrid-root`;
- four big columns and approved small column labels render once in header;
- row cells do not repeat header labels;
- invoice date and bank trade date have detail buttons;
- long text shows expand/collapse;
- pagination/sort/filter changes call backend rows API;
- fake export is absent or disabled.

Run:

```bash
cd web && npm test -- InputInvoiceUsagePage
```

Expected: fails because route/page/components do not exist.

- [ ] **Step 2: Implement typed DTOs and API**

Add typed functions for rows, filter options, invoice/bank/OA detail, row relation details, payment status rules and read-only OA reverse preview. Encode filters as URL-encoded JSON array matching the spec.

- [ ] **Step 3: Implement route, sidebar and page state**

Wire route/menu. Page owns query, filters, sort, pagination, detail target and `activeWorkflow`. Use existing `PageScaffold` and page session state patterns where appropriate.

- [ ] **Step 4: Implement MUI Table layout**

Use native MUI Table components only. Implement fixed-layout table, four visual groups, distinct big/small separators, payment-status background and responsive no-horizontal-scroll layout.

- [ ] **Step 5: Run frontend page verification**

```bash
cd web && npm test -- InputInvoiceUsagePage
```

Expected: pass.

## Task 3: Filter Menus, Details And Workflow Drawers

**Files:**
- Create: `web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx`
- Create: `web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx`
- Create: `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`
- Create: `web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx`
- Create: `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`
- Modify narrowly: `web/src/pages/InputInvoiceUsagePage.tsx`

- [ ] **Step 1: Write failing drawer/menu tests**

Cover:

- filter menu supports multi-select, select all, clear, asc and desc;
- menu options come from API state;
- detail drawer lazy-loads invoice/bank/OA/relation-list detail and shows loading state;
- both workflow buttons open right-side drawers, not dialogs;
- drawers are mutually exclusive;
- opening/closing drawers does not call rows API again;
- OA preview drawer calls `loadPreview` and does not compute totals from visible rows;
- no fake submit/create-draft success path;
- payment rules drawer is read-only and has no save button.

Run:

```bash
cd web && npm test -- InputInvoiceUsageFiltersAndDrawers
```

Expected: fails because components do not exist.

- [ ] **Step 2: Implement filter menu**

Use MUI `Menu`, `Checkbox`, `Radio`/menu items and `TableSortLabel`-compatible callbacks. Do not hardcode business option lists beyond field labels/modes.

- [ ] **Step 3: Implement detail drawer**

Use right-side `Drawer`/`AppDrawer` pattern. Lazy-load details after opening. Support `invoice`, `bank`, `oa`, and `relationList` targets.

- [ ] **Step 4: Implement workflow drawers**

Use `Drawer anchor="right"` with transform-based transitions. `OaReverseWorkspaceDrawer` calls backend preview through props and stays read-only. `PaymentStatusRulesDrawer` reads rules and stays read-only. No dialogs, no save, no fake submit.

- [ ] **Step 5: Run drawer/menu verification**

```bash
cd web && npm test -- InputInvoiceUsageFiltersAndDrawers
```

Expected: pass.

## Task 4: Serial Integration

**Files:**
- Modify only files touched by Tasks 1-3 as needed.

- [ ] **Step 1: Inspect git status**

```bash
git status --short
```

Confirm unrelated dirty files remain preserved.

- [ ] **Step 2: Reconcile DTO names**

Ensure backend response fields exactly match `web/src/features/inputInvoiceUsage/types.ts` and API tests/mocks.

- [ ] **Step 3: Run focused backend tests**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service tests.test_input_invoice_usage_api -v
```

- [ ] **Step 4: Run focused frontend tests**

```bash
cd web && npm test -- InputInvoiceUsage
```

- [ ] **Step 5: Run frontend build**

```bash
cd web && npm run build
```

- [ ] **Step 6: Browser smoke**

Start the dev server if needed and verify `/input-invoice-usage` visually in the in-app browser. Confirm no horizontal scroll, no DataGrid, right-side drawers, and no fake export/save/submit paths.

- [ ] **Step 7: Report deferred OA write contracts**

Report that future write endpoints are intentionally deferred in v1. Confirm no fake write routes/UI callbacks exist. Mention expected future write contract fields and behavior: `expectedVersion`, `idempotencyKey`, `oaDraftId`, `oaDraftUrl`, local revoke/release, audit, and OA status detection.

## Acceptance Checklist

- [ ] Left menu has `进项发票使用情况`.
- [ ] Route `/input-invoice-usage` loads.
- [ ] Backend rows API returns real read-only invoice rows.
- [ ] One row equals one invoice; line items are preserved in detail.
- [ ] Server-side filters/sort/page are canonical and validated.
- [ ] Filter options are context-aware.
- [ ] Details are lazy-loaded and complete where data exists.
- [ ] OA unavailable detail is explicit, not faked.
- [ ] Payment status is computed by backend with conservative fallback.
- [ ] Reverse-OA preview is backend read-only and no draft is created.
- [ ] Payment rules drawer is read-only in v1.
- [ ] No DataGrid is used by the new feature.
- [ ] No fake export, save, submit, or OA draft success path exists.
- [ ] Future reverse-OA write contracts are explicitly reported as deferred.
- [ ] Focused backend tests pass.
- [ ] Focused frontend tests pass.
- [ ] `npm run build` passes.
