# Bank Details Layout Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the bank details table layout and add professional filtered Excel export for all banks or the current account.

**Architecture:** Keep the existing MUI Table and existing bank details read/query pipeline. Add a focused backend export service that pages through `BankDetailsService.list_transactions()` with the service's supported page size until all filtered rows are collected or the export limit is exceeded, then expose it through `/api/bank-details/transactions/export`. Add frontend download helpers and a toolbar menu; visual polish stays in the bank details page/styles only.

**Tech Stack:** Python stdlib HTTP server layer, `openpyxl`, existing `AuditTrailService`, React + MUI, Vitest, Python `unittest`.

---

## File Map

- Create `backend/src/fin_ops_platform/services/bank_details_export_service.py`: build filtered export rows and professional workbook bytes.
- Modify `backend/src/fin_ops_platform/app/server.py`: route `/api/bank-details/transactions/export`, permission/session resolution, audit, response headers, health entrypoint.
- Modify `tests/test_bank_details_service.py` or create `tests/test_bank_details_export_service.py`: service-level workbook tests.
- Modify `tests/test_workbench_v2_api.py`: API route, permission, audit, row-limit tests.
- Modify `web/src/features/bankDetails/types.ts`: export request/result types.
- Modify `web/src/features/bankDetails/api.ts`: `downloadBankDetailTransactionsExport()`.
- Modify `web/src/pages/BankDetailsPage.tsx`: toolbar export button/menu and download state.
- Modify `web/src/app/styles.css`: table column separators, row alignment, amount/source layout polish.
- Modify `web/src/test/BankDetailsApi.test.ts`, `web/src/test/BankDetailsPage.test.tsx`, `web/src/test/apiMock.ts`: API and UI tests.
- Modify `docs/product-specs/bank-details.md`: document export behavior.

## Task 1: Backend Export Service

**Files:**
- Create: `backend/src/fin_ops_platform/services/bank_details_export_service.py`
- Test: `tests/test_bank_details_export_service.py`

- [ ] **Step 1: Write failing tests**

Cover:
- `mode=all` creates `全部流水` plus per-bank sheets.
- `mode=account` creates only one sheet and only current account rows.
- Exporting more than the existing bank detail page cap but fewer than `20000` rows includes every matched row.
- Workbook headers match the spec columns.
- Amount columns are numeric where populated.
- Field mapping respects: 交行摘要 only, 工行用途/摘要/附言, 光大摘要, 建行摘要/备注, 民生客户附言, 平安摘要/交易用途.
- More than `20000` rows raises `BankDetailsExportError("bank_detail_export_row_limit_exceeded")`.

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service -v
```

Expected: fail because service does not exist.

- [ ] **Step 2: Implement minimal service**

Create:

- `BANK_DETAIL_EXPORT_ROW_LIMIT = 20000`
- `BANK_DETAIL_EXPORT_COLUMNS`
- `BankDetailsExportError`
- `BankDetailsExportService`

Service constructor accepts callables compatible with:

- `BankDetailsService.list_transactions`
- `BankDetailsService.list_accounts`

Export strategy:

- Validate `mode=account` by calling the accounts loader with the same date range, finding `account_key` in the returned accounts. If absent, raise `bank_detail_export_account_not_found` before collecting transaction rows.
- Collect transaction rows by paging through the list loader with `page_size=500`, because the existing service deliberately caps page size. Continue until collected rows reach `pagination.total`.
- If `pagination.total > BANK_DETAIL_EXPORT_ROW_LIMIT`, raise row-limit error before collecting all pages.
- Transform rows into formal export rows.
- Build workbook with frozen first row, filter, header style, wrapped text, widths, numeric amount cells.
- `mode=all`: Sheet 1 `全部流水`, then per bank sheet.
- `mode=account`: one sheet named from bank/account.

- [ ] **Step 3: Run service tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service -v
```

Expected: pass.

## Task 2: Backend API Route, Permissions, Audit

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_workbench_v2_api.py`

- [ ] **Step 1: Write failing API tests**

Cover:
- `GET /api/bank-details/transactions/export?mode=all&date_from=...&date_to=...&keyword=...` returns XLSX content type and encoded filename.
- `mode=account` without `account_key` returns `bank_detail_export_account_required`.
- `mode=account` with no matching account returns `bank_detail_export_account_not_found`.
- Row limit maps to `bank_detail_export_row_limit_exceeded`.
- Export writes `AuditTrailService` action `bank_detail_export_downloaded` with actor, mode, filters, row count, sheet names and filename.
- Denied session returns 403; read-export-only is allowed.
- Readiness summary includes `/api/bank-details/transactions/export`.

Run focused tests:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests -v
```

Expected: new tests fail.

- [ ] **Step 2: Implement API route**

In `server.py`:

- Add route before `/api/bank-details/transactions`.
- Resolve read session using existing OA access helpers.
- Parse `mode`, `account_key`, `date_from`, `date_to`, `keyword`.
- Validate `mode in {"all", "account"}`.
- For `mode=account`, require `account_key`.
- Call export service with both transaction and account loaders so the service can validate current-account metadata and build the filename even if filtered rows are empty.
- Record audit through existing `self._audit_service.record_action()`.
- Return `XLSX_MIME_TYPE`, `_build_content_disposition(filename)`.
- Add route to readiness entrypoints if that list is maintained.

- [ ] **Step 3: Run backend API tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service tests.test_workbench_v2_api.WorkbenchV2ApiTests -v
```

Expected: pass.

## Task 3: Frontend Export API and Toolbar Interaction

**Files:**
- Modify: `web/src/features/bankDetails/types.ts`
- Modify: `web/src/features/bankDetails/api.ts`
- Modify: `web/src/pages/BankDetailsPage.tsx`
- Modify: `web/src/test/BankDetailsApi.test.ts`
- Modify: `web/src/test/BankDetailsPage.test.tsx`
- Modify: `web/src/test/apiMock.ts`

- [ ] **Step 1: Write failing frontend tests**

Cover:
- `downloadBankDetailTransactionsExport()` builds correct URL and extracts backend filename.
- Toolbar shows `导出` button.
- All-bank export sends current `date_from`, `date_to`, `keyword`, `mode=all`, without `account_key`.
- Current-account export is disabled while all accounts are selected.
- After selecting a bank account, current-account export sends `mode=account` and `account_key`.
- Failed export displays user-facing error.

Run:

```bash
cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx
```

Expected: new tests fail.

- [ ] **Step 2: Implement frontend export**

Add:

- `BankDetailExportMode = "all" | "account"`.
- `downloadBankDetailTransactionsExport(request)`.
- `extractFileNameFromContentDisposition()` if no shared helper exists.
- Toolbar props for export callbacks/state.
- MUI `Menu`/`MenuItem` from the `导出` button.
- Download via object URL and backend filename.
- Loading/feedback state.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx
```

Expected: pass.

## Task 4: Table Visual Polish

**Files:**
- Modify: `web/src/pages/BankDetailsPage.tsx`
- Modify: `web/src/app/styles.css`
- Test: `web/src/test/BankDetailsPage.test.tsx`

- [ ] **Step 1: Add failing/structural tests**

Cover:
- Table has classes for column separators.
- Amount cell preserves two-line structure.
- Time row and relation row remain separated.

- [ ] **Step 2: Implement styles**

Add/adjust:

- `table-layout: fixed`.
- Header/cell vertical rhythm.
- Subtle right borders on cells except the last column.
- Text columns top alignment.
- Amount cell two-line alignment with stable grid.
- Smaller source chip and relation tags.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd web && npm test -- --run BankDetailsPage.test.tsx
```

Expected: pass.

## Task 5: Docs and Final Verification

**Files:**
- Modify: `docs/product-specs/bank-details.md`

- [ ] **Step 1: Update product docs before final code review**

Document:

- Export current filters, all matched rows not current page.
- All-bank workbook structure.
- Current-account workbook structure.
- 20000 row sync limit.

- [ ] **Step 2: Run focused backend verification**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service tests.test_bank_details_service tests.test_bank_details_sql_runtime tests.test_workbench_v2_api.WorkbenchV2ApiTests -v
```

- [ ] **Step 3: Run frontend verification**

Run:

```bash
cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx && npm run build
```

- [ ] **Step 4: Final diff review**

Run:

```bash
git diff --check
git status --short
```

Confirm no unrelated files changed and no whitespace errors.
