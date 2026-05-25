# 银行明细表格排版与导出多任务执行 Prompt

This prompt is intended for Codex workers implementing the approved bank details layout and export feature.

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Primary spec:

```text
docs/superpowers/specs/2026-05-25-bank-details-layout-export-design.md
```

Implementation plan:

```text
docs/superpowers/plans/2026-05-25-bank-details-layout-export.md
```

## Orchestrator Prompt

```text
/goal Implement the production-grade bank details table visual polish and professional Excel export, using the approved MUI Table layout, current-filter full-result export, all-bank plus per-bank sheets, current-account export, existing auth/audit patterns, and real bank field mappings.

You are working in /Users/yu/Desktop/fin-ops-platform.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/product-specs/bank-details.md
- docs/product-specs/settings-and-access-control.md
- docs/superpowers/specs/2026-05-25-bank-details-layout-export-design.md
- docs/superpowers/plans/2026-05-25-bank-details-layout-export.md

Hard requirements:
- This is not a temporary/rescue implementation. Produce integrated production-grade code aligned with the existing architecture.
- Do not restore manual bank transaction categorization.
- Keep MUI Table. Do not reintroduce MUI X DataGrid.
- Add subtle vertical separators between table columns.
- Improve row alignment and amount/source visual rhythm without adding horizontal scroll as the primary solution.
- Export must use current page filters across all matched rows, not just the current page.
- Export collection must page through the existing bank details service with its supported page size; do not rely on a single large page size because the service caps it.
- Export must not replicate UI chip/tag styling. Excel should be professional, with data columns, frozen header, filters, widths, wrapped text and numeric money columns.
- Export modes:
  - all: one `全部流水` sheet plus per-bank sheets.
  - account: one sheet for the selected account's bank, containing only that account.
- Current-account export requires `account_key`.
- Current-account export must validate `account_key` against account metadata before exporting, so invalid account and valid empty filtered result are distinguishable.
- Sync export row limit is 20000. Exceeding it returns `bank_detail_export_row_limit_exceeded`.
- Use existing `AuditTrailService.record_action()` for `bank_detail_export_downloaded`; do not create a parallel audit store.
- Real bank field mappings must remain:
  - 交行: 摘要
  - 工行: 用途、摘要、附言
  - 光大: 摘要
  - 建行: 摘要、备注
  - 民生: 客户附言
  - 平安: 摘要、交易用途
- Preserve unrelated dirty work. Do not revert files you did not change.

Execution order:
1. Serial setup: inspect git status, docs, current bank detail service/page/API tests.
2. Serial backend export service:
   - write failing service workbook tests;
   - implement `bank_details_export_service.py`;
   - page through all filtered rows despite existing page-size caps;
   - validate current-account metadata through accounts loader;
   - run service tests.
3. Serial backend API:
   - write failing API/audit/permission/error tests;
   - wire route and audit in `server.py`;
   - run backend focused tests.
4. Parallel frontend-safe batch after backend contract is stable:
   - frontend API/download helper and tests;
   - page toolbar/menu interaction and tests;
   - table CSS polish and structural tests.
5. Serial docs and integration:
   - update `docs/product-specs/bank-details.md`;
   - reconcile mock API;
   - run focused backend tests;
   - run frontend tests and build.
6. Final review:
   - run `git diff --check`;
   - inspect changed files;
   - report tests, changed files, residual risks.
```

## Worker 1: Backend Export Service

```text
/goal Implement bank details Excel export service with workbook generation and row-limit enforcement.

Owned files:
- backend/src/fin_ops_platform/services/bank_details_export_service.py
- tests/test_bank_details_export_service.py

Read:
- docs/superpowers/specs/2026-05-25-bank-details-layout-export-design.md
- docs/superpowers/plans/2026-05-25-bank-details-layout-export.md
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/turnover_ledger_export_service.py

Requirements:
- TDD first.
- Export columns exactly as spec.
- Use openpyxl and professional workbook formatting.
- Enforce 20000 row limit.
- Page through the transaction loader with a supported page size, so exports over 500 rows but under 20000 are complete.
- Accept an accounts loader and validate mode=account account_key before row collection.
- Do not implement HTTP route here.
- Return changed files and tests run.
```

## Worker 2: Backend API, Auth, Audit

```text
/goal Add /api/bank-details/transactions/export route using the export service, existing auth, existing AuditTrailService, and XLSX response headers.

Owned files:
- backend/src/fin_ops_platform/app/server.py
- tests/test_workbench_v2_api.py

Read:
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/app/auth.py
- backend/src/fin_ops_platform/services/audit.py
- tests/test_workbench_v2_api.py
- docs/superpowers/specs/2026-05-25-bank-details-layout-export-design.md

Requirements:
- TDD first.
- Route must return XLSX for allowed/read-export-only sessions.
- Denied session returns 403.
- Audit action: bank_detail_export_downloaded.
- Readiness summary includes /api/bank-details/transactions/export.
- Map row-limit/account/mode errors to specified 400 errors.
- Do not change unrelated routes.
- Return changed files and tests run.
```

## Worker 3: Frontend Export API and Interaction

```text
/goal Add bank details frontend export API helper and toolbar menu downloads for all-bank/current-account exports.

Owned files:
- web/src/features/bankDetails/types.ts
- web/src/features/bankDetails/api.ts
- web/src/pages/BankDetailsPage.tsx
- web/src/test/BankDetailsApi.test.ts
- web/src/test/BankDetailsPage.test.tsx
- web/src/test/apiMock.ts

Read:
- docs/superpowers/specs/2026-05-25-bank-details-layout-export-design.md
- web/src/pages/BankDetailsPage.tsx
- web/src/features/bankDetails/api.ts
- web/src/test/BankDetailsPage.test.tsx

Requirements:
- TDD first.
- Use backend filename from Content-Disposition.
- All-bank export omits account_key.
- Current-account export requires selected account and sends account_key.
- Show loading and failure feedback.
- Do not alter business classification behavior.
- Return changed files and tests run.
```

## Worker 4: Table Visual Polish

```text
/goal Improve bank details MUI Table visual rhythm with subtle column separators, stable amount/source layout, and cleaner row alignment.

Owned files:
- web/src/pages/BankDetailsPage.tsx
- web/src/app/styles.css
- web/src/test/BankDetailsPage.test.tsx

Read:
- docs/superpowers/specs/2026-05-25-bank-details-layout-export-design.md
- web/src/pages/BankDetailsPage.tsx
- web/src/app/styles.css

Requirements:
- TDD/structural tests where practical.
- Do not use DataGrid.
- Add subtle vertical separators between columns.
- Keep time and relation tags in separate rows.
- Keep type column narrow.
- Preserve no-horizontal-scroll intent.
- Return changed files and tests run.
```

## Final Verification Prompt

```text
/goal Review and verify the complete bank details layout/export implementation against the approved spec.

Check:
- No manual bank tagging UI returned.
- Export uses current filters, not current page.
- All-bank and current-account workbook structures match spec.
- Audit, permissions and row limit are implemented.
- Table has subtle separators and cleaner amount/source layout.
- Existing field mappings are preserved.

Run:
- PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service tests.test_bank_details_service tests.test_bank_details_sql_runtime tests.test_workbench_v2_api.WorkbenchV2ApiTests -v
- cd web && npm test -- --run BankDetailsApi.test.ts BankDetailsPage.test.tsx && npm run build
- git diff --check
```
