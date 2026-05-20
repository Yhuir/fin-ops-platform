# 待找发票多任务子代理 Prompts

These prompts are intended for worker subagents in the isolated worktree:

```text
/Users/yu/Desktop/fin-ops-platform/.worktrees/pending-invoices
```

Shared constraints for every worker:

- You are not alone in the codebase. Other agents may be editing disjoint files. Do not revert or overwrite unrelated changes.
- Use TDD. Write focused failing tests first, run them and confirm they fail for the expected reason, then implement minimal production code, then rerun tests.
- Follow repository instructions in `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, and the approved spec.
- Do not add dependencies.
- Keep diffs scoped to your owned files.
- Use MUI native components only on the frontend. Do not use `DataGrid` for the pending invoice page.
- Return changed file paths, tests run, and any blockers.

## Worker 1: Backend Dynamic Bank Tags And Settings

```text
/goal Implement server-owned bank transaction tag definitions and pending invoice tag-group settings for the approved 待找发票 workflow.

Workspace: /Users/yu/Desktop/fin-ops-platform/.worktrees/pending-invoices

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-20-pending-invoices-design.md
- docs/superpowers/plans/2026-05-20-pending-invoices.md
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/app/server.py
- tests/test_bank_transaction_category_service.py
- tests/test_app_settings_service.py
- tests/test_bank_details_service.py

Owned write scope:
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/app/server.py ONLY for settings and bank-details route/payload changes
- tests/test_bank_transaction_category_service.py
- tests/test_app_settings_service.py
- tests/test_bank_details_service.py

Do not edit:
- pending_invoice_service.py
- pending invoice API routes
- frontend files

Required behavior:
1. Existing hardcoded bank transaction category codes become system seed tag definitions.
2. App settings payload includes:
   - bank_transaction_tags with version and definitions
   - pending_invoice_tag_groups with fixed groups:
     - requires_invoice
     - bank_statement_as_invoice
     - no_invoice_required
3. Tags have stable code, label, path, source=system|custom, status=active|archived.
4. Settings normalization validates:
   - unknown tag references rejected
   - archived tags cannot be mapped
   - same tag cannot be in multiple pending invoice groups
5. Version increments when tags or pending invoice mappings change.
6. Bank details can expose server-owned tag definitions/version so frontend no longer treats hardcoded categoryOptions as production fact source.
7. Preserve backward compatibility for existing category codes and existing tests.
8. Record audit entries for bank transaction tag dictionary and pending invoice tag-group changes, including actor, before/after summary, affected groups, and new version.
9. After a successful tag or mapping save, clear/refresh backend caches or read models that depend on bank_transaction_tags or pending_invoice_tag_groups, including bank details tag options/classification counts and pending invoice filter/query results.
10. Failed validation must not trigger backend invalidation or audit writes.

TDD requirements:
- Add failing tests for tag dictionary payload and versioning.
- Add failing tests for invalid pending invoice group mappings.
- Add failing tests that bank details response or helper exposes tag definitions/version.
- Add failing tests that tag and mapping changes produce audit entries.
- Add failing tests that successful tag or mapping saves invoke backend invalidation/finalization.
- Add failing tests that failed validation does not invalidate caches/read models and does not write audit.
- Run:
  PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service tests.test_app_settings_service tests.test_bank_details_service -v

Expected final status:
- DONE if all owned tests pass.
- DONE_WITH_CONCERNS if you completed the scope but found integration assumptions Worker 2/3 must know.
- NEEDS_CONTEXT only if a contract is impossible to infer from the spec.

Return:
- Status
- Changed files
- Tests run with pass/fail
- Notes for integration
```

## Worker 2: Backend Pending Invoice Services And API

```text
/goal Implement pending invoice query, manual invoice preview/confirm, canonical formal invoice creation, idempotency, pair relation integration, and backend API routes.

Workspace: /Users/yu/Desktop/fin-ops-platform/.worktrees/pending-invoices

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-20-pending-invoices-design.md
- docs/superpowers/plans/2026-05-20-pending-invoices.md
- backend/src/fin_ops_platform/services/imports.py
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py
- backend/src/fin_ops_platform/services/bank_details_relation_tag_projection_service.py
- backend/src/fin_ops_platform/services/invoice_inventory_stats_service.py
- backend/src/fin_ops_platform/app/server.py
- tests/test_workbench_pair_relation_service.py
- tests/test_import_service.py
- tests/test_invoice_inventory_stats_service.py

Owned write scope:
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/services/imports.py for a narrow public helper only if needed to create a canonical manual invoice through existing import logic
- backend/src/fin_ops_platform/services/state_store.py for pending invoice command log persistence and to persist Worker 1 settings fields bank_transaction_tags/pending_invoice_tag_groups in both JSON-file and Mongo app-settings storage
- backend/src/fin_ops_platform/app/server.py ONLY for /api/pending-invoices routes, service construction, persistence, and invalidation
- tests/test_pending_invoice_service.py
- tests/test_pending_invoice_api.py
- tests/test_invoice_inventory_stats_service.py if source-link visibility requires coverage
- tests/test_app_settings_service.py ONLY for focused persistence/reload coverage of bank_transaction_tags and pending_invoice_tag_groups if Worker 1's tests do not already fail without the state_store.py fix

Do not edit:
- settings tag normalization owned by Worker 1 except to consume its public payload
- frontend files

Required behavior:
0. Resolve Worker 1 integration concern: ApplicationStateStore.load_app_settings() and save_app_settings() must round-trip bank_transaction_tags and pending_invoice_tag_groups for file and Mongo payload paths, with focused regression coverage.
1. GET /api/pending-invoices/rows supports:
   - direction=expense|income
   - filter=all|requires_invoice|bank_statement_as_invoice|no_invoice_required
   - date_from/date_to/keyword/page/page_size
2. Income rejects three-category filters with structured 400 invalid_filter_for_income.
3. Rows are one bank transaction per row.
4. Multiple related invoices render in one row DTO.
5. Expense row invoice side is input invoices; income side is output invoices.
6. OA applicant is derived only from existing OA/workbench relation context; no relation returns —.
7. can_create_invoice rules:
   - expense + no_invoice_required + no invoice => false
   - expense + requires_invoice + no invoice => true
   - expense + bank_statement_as_invoice + no invoice => true
   - expense + all/unmapped + no invoice => true
   - income + no invoice => true
8. POST /api/pending-invoices/manual-invoices/preview:
   - validates without writes
   - returns preview_id, request_key, target_invoice_type, bank summary, invoice identity, duplicate status, relation impact, warnings
9. POST /api/pending-invoices/manual-invoices:
   - requires preview_id and request_id
   - reruns preview validation
   - creates formal invoice through ImportNormalizationService preview_import/confirm_import or a narrow equivalent preserving identity/source_links
   - uses BatchType.INPUT_INVOICE for expense, OUTPUT_INVOICE for income
   - uses source_type manual_invoice_import so existing inventory stats count it
   - creates active WorkbenchPairRelationService relation_mode pending_invoice_manual_invoice with row_types ["bank", "invoice"]
   - is idempotent using request_id and deterministic request_key
   - supports command statuses started, invoice_created, relation_created, completed, failed_recoverable, failed_terminal
   - can recover retry after invoice-created-before-relation-created partial failure
   - can recover retry after relation-created-before-response/audit/cache-finalization partial failure
   - detects an existing invoice with manual_invoice_import source link and same request_key but no relation, then creates the missing relation or returns a repair-required error without creating another invoice
   - writes audit for manual invoice confirm with actor, transaction id, invoice id, relation case id, request id/key, and affected months
   - invalidates or refreshes pending invoice row data, workbench read models, bank relation tag projection, search cache, and tax/writeoff affected-month state
10. Returns structured errors:
   - invalid_direction
   - invalid_filter_for_income
   - bank_transaction_not_found
   - invalid_invoice_payload
   - duplicate_invoice
   - relation_conflict
   - permission_denied

TDD requirements:
- Add tests for query behavior before service implementation.
- Add tests for preview behavior before preview implementation.
- Add tests for confirm/idempotency/recovery before confirm implementation.
- Add tests for all command statuses and both invoice_created and relation_created recovery paths.
- Add tests for request_key/source-link orphan invoice recovery without duplicate invoice creation.
- Add tests for manual invoice audit and full invalidation/finalization calls.
- Run:
  PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_pending_invoice_api tests.test_invoice_inventory_stats_service -v

Expected final status:
- DONE if owned tests pass.
- DONE_WITH_CONCERNS if route wiring depends on Worker 1 settings shape.
- NEEDS_CONTEXT only if current persistence APIs make idempotent recovery impossible without broader refactor.

Return:
- Status
- Changed files
- Tests run with pass/fail
- API shape notes
- Any integration notes for frontend
```

## Worker 3: Frontend Pending Invoice Page And Settings UI

```text
/goal Implement the 待找发票 frontend page using MUI native Table, settings UI for dynamic bank tags and pending invoice mappings, and real-time tag sync with bank details.

Workspace: /Users/yu/Desktop/fin-ops-platform/.worktrees/pending-invoices

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-20-pending-invoices-design.md
- docs/superpowers/plans/2026-05-20-pending-invoices.md
- web/src/README.md
- web/src/app/router.tsx
- web/src/components/shell/sidebarItems.ts
- web/src/pages/BankDetailsPage.tsx
- web/src/pages/SettingsPage.tsx
- web/src/components/settings/SettingsPageContent.tsx
- web/src/features/workbench/api.ts
- web/src/features/workbench/types.ts
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/test/renderHelpers.tsx
- web/src/test/apiMock.ts

Owned write scope:
- web/src/features/pendingInvoices/types.ts
- web/src/features/pendingInvoices/api.ts
- web/src/pages/PendingInvoicesPage.tsx
- web/src/components/pendingInvoices/PendingInvoicesTable.tsx
- web/src/components/pendingInvoices/ManualInvoiceDialog.tsx
- web/src/components/settings/SettingsBankTransactionTagsSection.tsx
- web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx
- web/src/app/router.tsx
- web/src/components/shell/sidebarItems.ts
- web/src/features/workbench/types.ts
- web/src/features/workbench/api.ts
- web/src/features/bankDetails/types.ts
- web/src/features/bankDetails/api.ts
- web/src/pages/BankDetailsPage.tsx
- web/src/components/settings/SettingsPageContent.tsx
- web/src/components/settings/types.ts
- web/src/components/settings/SettingsTreeNav.tsx
- web/src/test/PendingInvoicesApi.test.ts
- web/src/test/PendingInvoicesPage.test.tsx
- web/src/test/SettingsPage.test.tsx
- web/src/test/BankDetailsPage.test.tsx

Do not edit:
- Backend files
- Do not introduce DataGrid into PendingInvoicesPage
- Do not add dependencies

Required behavior:
1. Left sidebar has 待找发票 under 财务业务 near 银行明细/关联台.
2. Route /pending-invoices renders PendingInvoicesPage.
3. Page top-left has ToggleButtonGroup with 支出流水 and 收入流水.
4. Expense mode shows filter menu options:
   - 全部
   - 需要开票
   - 流水代替发票
   - 无需开票
5. Income mode hides three-category filter.
6. Main page uses MUI native Table components only:
   - Table
   - TableHead
   - TableBody
   - TableRow
   - TableCell
   - TablePagination
7. Three columns:
   - 支出流水/收入流水
   - 进项发票/销项发票
   - OA申请人
8. Bank transaction cell shows:
   - counterparty + time Chip second line
   - amount + bank/last4 Chip second line
9. Invoice cell shows:
   - multiple invoices vertically inside one row
   - invoice number + issue date Chip
   - gross amount
   - seller for expense, buyer for income
10. + icon rules:
   - use server canCreateInvoice
   - expense no_invoice_required missing invoice has no +
   - expense requires_invoice/bank_statement_as_invoice missing invoice has +
   - income missing output invoice has +
11. ManualInvoiceDialog:
   - collects invoice number/digital number, issue date, total with tax, seller/buyer names and optional tax fields
   - calls preview first
   - displays preview summary
   - confirm calls write endpoint with same request_id
12. Settings:
   - Add 银行流水标签 section
   - Add 待找发票筛选 section
   - Use two-column structure: left fixed groups, right tag items
   - + can select existing tag or create new tag
   - - removes tag from selected group
13. Real-time sync:
   - After settings save, broadcast finops:bank-transaction-tags-updated with version
   - BankDetailsPage listens and refetches tag options/current rows
   - PendingInvoicesPage listens and refetches filters/current rows
   - Use BroadcastChannel for cross-tab propagation when available
   - Add window-focus version comparison/refetch fallback when BroadcastChannel is unavailable or an event was missed

TDD requirements:
- Add API mapping tests first.
- Add page render/interaction tests first.
- Add settings UI tests first.
- Add tests for BroadcastChannel propagation or focus-time version fallback refetch.
- Run:
  cd web && npm test -- --run PendingInvoicesApi.test.ts PendingInvoicesPage.test.tsx SettingsPage.test.tsx BankDetailsPage.test.tsx
- Run:
  cd web && npm run build

Important environment note:
- If this worktree lacks node_modules, run `npm install` inside `web/` before frontend tests.

Expected final status:
- DONE if owned tests/build pass.
- DONE_WITH_CONCERNS if backend endpoint shape had to be assumed; clearly list assumptions.
- NEEDS_CONTEXT only if API shape conflicts with the spec.

Return:
- Status
- Changed files
- Tests run with pass/fail
- UI/API assumptions
```

## Integration Reviewer Prompt

```text
/goal Review the completed 待找发票 implementation for spec compliance, integration quality, and regressions.

Workspace: /Users/yu/Desktop/fin-ops-platform/.worktrees/pending-invoices

Read:
- docs/superpowers/specs/2026-05-20-pending-invoices-design.md
- docs/superpowers/plans/2026-05-20-pending-invoices.md
- git diff from main

Review requirements:
- Findings first, ordered by severity.
- Include exact file/line references.
- Focus on correctness, persistence, idempotency, official invoice inventory visibility, permission checks, cache invalidation, tests, and MUI Table/no DataGrid compliance.
- If no issues, say approved and list residual verification risk.

Do not modify files.
```
