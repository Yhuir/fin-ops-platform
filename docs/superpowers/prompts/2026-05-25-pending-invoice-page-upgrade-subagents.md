# 待找发票页面升级多任务执行 Prompt

This prompt is intended for Codex workers implementing the approved `待找发票` page upgrade.

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Primary spec:

```text
docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md
```

Long-term product/API sources:

```text
docs/product-specs/pending-invoices.md
docs/dev/pending-invoices-api.md
```

## Orchestrator Prompt

```text
/goal Implement the production-grade 待找发票 page upgrade in place at /pending-invoices, using the approved four-zone MUI Table layout, upgraded pending invoice DTO/read model, right-side workflows, server-side export, permissions, audit, and no Redis dependency in v1.

You are working in /Users/yu/Desktop/fin-ops-platform.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- DESIGN.md
- SECURITY.md
- docs/dev/frontend.md
- docs/dev/backend.md
- docs/architecture/persistence-and-read-models.md
- docs/product-specs/pending-invoices.md
- docs/product-specs/workbench.md
- docs/product-specs/settings-and-access-control.md
- docs/dev/pending-invoices-api.md
- docs/superpowers/specs/2026-05-20-pending-invoices-design.md
- docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md

Hard requirements:
- This is not a temporary/rescue implementation. Produce integrated production-grade code aligned with the existing architecture.
- Upgrade the existing 待找发票 menu and /pending-invoices route in place. Do not add a second similar sidebar page.
- Use MUI Table components for the main table. Do not use MUI X DataGrid.
- Main table uses four big zones: 支出流水, 发票获取状态, 进项发票, OA.
- Target one page width with no horizontal scroll on common desktop widths.
- One row = one expense bank transaction. Multiple invoices/OA/payment records render as primary summary +N and open details in drawers.
- Sheet1 entry belongs in the 发票获取状态 column. Object columns only open object details.
- The rule button should be labeled 待找发票规则设置 or equivalent and must manage all three groups: 需要开票, 流水代替发票, 无需开票.
- The rules drawer saves the same backend pending_invoice_tag_groups fact. Do not create a parallel rule store.
- 发票获取状态 is calculated by backend facts/rules/relations. The frontend does not manually compute or directly mutate status.
- Implement 筛选的内容可以导出 as server-side export of the full filtered/sorted result, not just current page.
- First version does not add Redis dependency. PostgreSQL read_model.pending_invoice_rows + durable refresh queue is the correctness path.
- Redis may only be documented as future short-TTL optimization. Do not store rules, workflow state, Sheet1 detail, or export state in Redis.
- read model fresh empty must return 200/read_model_status=fresh with rows=[]. Only missing/stale scopes return 202/read_model_status=refreshing and enqueue pending_invoice.read_model.refresh. Do not synchronously scan all facts in API hot path when SQL read model exists.
- Write operations must enforce backend permission checks and audit/structured operation records.
- Read-export-only users can view/filter/detail/export; they cannot save rules,补票, attach existing invoice, or create relations.
- Preserve unrelated dirty work. Do not revert or overwrite files you did not change.

Execution order:
1. Serial preparation: inspect git status, docs, current pending invoice implementation, read model repository, settings and export patterns.
2. Serial contract prep: run the Contract Preparation Prompt below to verify/update long-term docs and freeze API/type contracts before implementation.
3. Serial backend read/export: Worker 1.
4. Serial backend rules/attach workflow: Worker 2. Backend workers are intentionally serial because they share pending invoice service/server files.
5. Parallel frontend component batch after the contract is stable:
   - Worker 3: four-zone table component and table-only tests.
   - Worker 4: right-side drawer components and drawer-only tests.
6. Serial integration:
   - reconcile DTO names;
   - wire API routes and frontend api mappings;
   - update mocks/tests;
   - ensure existing pending invoice/manual补票 behavior still passes.
7. Verification:
   - focused backend tests;
   - full backend unittest if practical;
   - frontend tests;
   - frontend build;
   - browser smoke for /pending-invoices if local app can run.
8. Final review:
   - run the reviewer prompt in this document;
   - fix issues;
   - rerun impacted tests;
   - report changed files, tests, residual risks.
```

## Shared Constraints For Every Worker

- You are not alone in the codebase. Other agents may be editing disjoint files. Do not revert or overwrite unrelated changes.
- Use TDD. Write focused failing tests first, run them and confirm they fail for the expected reason, implement production code, then rerun tests.
- Follow repository instructions in `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, and the approved spec.
- Do not add dependencies.
- Keep diffs scoped to your owned files.
- Do not use DataGrid in the pending invoice main table.
- Do not guess unknown API fields, database columns, response shapes, IDs, or status values. Inspect source of truth or return unavailable details explicitly.
- The backend owns business status and relationship facts; frontend owns rendering and interaction state only.
- Writes must be transactional or use the existing recoverable command pattern. Do not create half-state where relation, audit, command record and read-model invalidation disagree.
- Prefer cohesive service/component boundaries over adding generic abstractions. If a file must be split, keep the split local to pending invoice responsibilities.
- Return status, changed files, tests run, blockers, and integration notes.

## Frontend Integration Contract

- `PendingInvoicesPage.tsx` owns query state, pagination, sorting, active drawer/dialog state, selected row ids, and refresh orchestration.
- `web/src/features/pendingInvoices/api.ts` owns every backend mapping: rows, filter options, rules, relation detail, object details, attach-existing preview/confirm, manual invoice preview/confirm and export.
- `PendingInvoicesTable` receives rows/config and emits callbacks only: `onSortChange`, `onOpenRelation`, `onOpenInvoicePicker`, `onOpenManualInvoice`, `onOpenObjectDetail`, `onOpenRules`, `onOpenExport`, `onToggleCellExpand`.
- Drawer components load their own detail payloads after open and do not mutate table business state directly.
- Shared frontend state shape should stay explicit:
  - `activeDrawer: "rules" | "relation" | "invoicePicker" | "detail" | "export" | null`
  - `detailTarget: { kind: "bankTransaction" | "invoice" | "oa"; id: string; rowId?: string } | null`
  - `relationTarget: { transactionId: string } | null`
- The frontend must keep mapped `invoiceAcquisitionStatus` immutable except for display and action routing.
- Performance constraints: server-side pagination/filter/sort, fixed table layout, no per-row eager detail fetch, memoized row rendering helpers, no layout shift from expanding long text.

## Contract Preparation Prompt

```text
/goal Freeze the 待找发票 product/API/type contract before implementation so backend and frontend workers do not guess fields or collide on shared files.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md
- web/src/features/pendingInvoices/types.ts
- web/src/features/pendingInvoices/api.ts
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py

Owned write scope:
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md only for confirmed contract corrections
- docs/superpowers/prompts/2026-05-25-pending-invoice-page-upgrade-subagents.md only if worker scopes need tightening before dispatch

Required behavior:
1. Confirm the product spec and API doc contain:
   - existing /pending-invoices route upgrade;
   - MUI Table only;
   - four-zone layout and column merges;
   - Sheet1 status-column entry;
   - three-group pending_invoice_tag_groups rules;
   - seven backend statuses with priority;
   - filters JSON shape, field/operator whitelist, sort whitelist and error shape;
   - invoice-candidates endpoint contract;
   - fresh empty vs missing/stale read model behavior;
   - export full filtered result plus permission/audit behavior;
   - attach-existing preview/confirm, idempotency and recovery.
2. Do not implement code in this prep step.
3. If a contract is still ambiguous, stop and report the exact unresolved field/endpoint instead of inventing code.

Expected final status:
- DONE if product/API docs and execution prompt are internally consistent and ready for implementation workers.
```

## Worker 1: Backend Read Model, Query, Status, Filter, Export

```text
/goal Upgrade the pending invoice backend read path so /api/pending-invoices/rows, filter-options, relation-detail, object details, export-preview, and export support the approved four-zone 待找发票 page without adding Redis dependency.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-20-pending-invoices-design.md
- docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- docs/dev/backend.md
- docs/architecture/persistence-and-read-models.md
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py
- backend/src/fin_ops_platform/services/imports.py
- backend/src/fin_ops_platform/services/postgres_state_store.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- backend/src/fin_ops_platform/postgres/migrations/ (inspect latest pending invoice/read model migrations)
- tests/test_pending_invoice_service.py
- tests/test_pending_invoice_api.py if present
- tests/test_postgres_state_store.py
- tests/test_postgres_migrations.py

Owned write scope:
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/app/server.py only for thin /api/pending-invoices read/export route wiring
- backend/src/fin_ops_platform/services/postgres_state_store.py and `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` only for pending invoice read model row/query changes
- Create the next numbered SQL migration under `backend/src/fin_ops_platform/postgres/migrations/` after inspecting the current highest migration number. Do not guess or reuse an existing migration number.
- tests/test_pending_invoice_service.py
- tests/test_pending_invoice_api.py or create focused route tests if absent
- tests/test_postgres_state_store.py or focused read model repository tests
- tests/test_postgres_migrations.py if migration expectations need updating

Do not edit:
- Frontend files
- Settings normalization/rules save logic owned by Worker 2 except to consume its public settings payload
- Existing unrelated workbench pages

Required behavior:
1. Keep existing /api/pending-invoices/rows route but upgrade the expense DTO for the four-zone page.
2. Preserve old income behavior enough that existing tests pass. Do not expand income into the new complex workflow in this task.
3. Use read_model.pending_invoice_rows as production hot path when SQL read repository is available.
4. API miss/stale:
   - return 200 OK, rows=[] and read_model_status=fresh for a fresh scope with no matching rows;
   - return 202 Accepted and read_model_status=refreshing only for missing or stale/dirty scopes;
   - enqueue pending_invoice.read_model.refresh only for missing/stale scopes;
   - do not synchronously scan all facts in the SQL hot path.
5. Keep legacy/in-memory fallback only for local/test modes where no SQL read repository exists, following existing repository patterns.
6. Upgrade backend source row DTO for expense using snake_case API fields:
   - bank_transaction with Excel fields: counterparty_name, counterparty_account_no, counterparty_bank_name, trade_time, booked_date, debit_amount, credit_amount, balance, currency, bank_name, account_name, account_last4, summary, remark, statement_serial_no, enterprise_serial_no, voucher_type, voucher_no.
   - invoice_acquisition_status: code, label, reason, severity, primary_action, matched_rule.
   - input_invoices: primary, relation_count, has_multiple, summaries, payment_summary.
   - oa: primary, relation_count, has_multiple, detail_available, summaries.
7. Implement the 7 approved status classes with this exact priority:
   - invoice_not_fully_paid / 未支付完已开票 when an active bank+input invoice relation exists and invoice total is greater than paid total.
   - paid_invoiced / 已支付已开票 when an active bank+input invoice relation exists and amount/relation facts are closed.
   - no_invoice_required / 无需开票 when the no_invoice_required rule group matches and no formal invoice relation exists.
   - bank_statement_as_invoice / 流水代替发票 when the bank_statement_as_invoice rule group matches and no formal invoice relation exists.
   - paid_pending_future_invoice / 已支付待后期集中开票 only when a stable backend fact proves future consolidated invoicing. Do not infer it from UI guesses or ordinary similar rows.
   - paid_pending_invoice / 已支付待开票 when no invoice exists and no exemption/statement-as-invoice rule applies.
   - pending / 待处理 when facts cannot reliably prove one of the above.
8. The status code enum must include:
   - paid_invoiced / 已支付已开票
   - paid_pending_invoice / 已支付待开票
   - paid_pending_future_invoice / 已支付待后期集中开票
   - invoice_not_fully_paid / 未支付完已开票
   - no_invoice_required / 无需开票
   - bank_statement_as_invoice / 流水代替发票
   - pending / 待处理
9. Status is derived only from rules, active pair relations, invoice/bank/OA facts, and payment totals. The frontend must not have to recalculate it.
10. Payment totals for Sheet1 detail must be derived from relations. Do not persist page-private payment summaries.
11. Upgrade read_model.pending_invoice_rows schema/query support:
    - add or populate query columns for status_code, seller_name, invoice_total, oa_applicant, project_name and other approved filter/sort fields;
    - add targeted indexes for common filters/sorts;
    - keep existing direction/filter/date/keyword pagination behavior compatible;
    - if a field cannot be columnized yet, document the reason and do not fall back to full API hot-path scans in production SQL mode.
12. Add GET /api/pending-invoices/filter-options for current query context. It must return field configs/options/counts for transaction date, bank, counterparty, amount, summary/remark, status, rule group, seller, invoice amount, OA applicant and project.
13. Add GET /api/pending-invoices/rows/{transactionId}/relation-detail for Sheet1 relation/payment detail:
    - selected/current transaction;
    - related invoice summaries;
    - historical payment rows;
    - paid_total, invoice_total, remaining_amount, difference_amount;
    - action availability.
14. Add GET /api/pending-invoices/invoice-candidates exactly as documented in docs/dev/pending-invoices-api.md:
    - supports transaction_id, keyword, seller_name, issue_date_from, issue_date_to, amount_min, amount_max, sort_field, sort_direction, page, page_size;
    - returns existing input invoice candidates only;
    - includes available/already_related/conflict status and conflict reason;
    - uses the documented stable default ordering;
    - does not write relations or workflow state.
15. Add object detail endpoints:
    - GET /api/pending-invoices/bank-transactions/{id}/detail
    - GET /api/pending-invoices/invoices/{id}/detail
    - GET /api/pending-invoices/oa/{id}/detail
16. Add export-preview and export endpoints:
    - GET /api/pending-invoices/export-preview
    - GET /api/pending-invoices/export
17. Export uses the same query parameters and server-side semantics as list rows, including filters and sort.
18. Export returns all filtered/sorted rows, not only current page.
19. Export should follow existing platform export patterns and produce xlsx unless an existing pending-invoice export convention says otherwise.
20. Export includes fields hidden by main table: full bank voucher/serial fields, invoice fields, OA fields, status reason and payment relation amounts.
21. Export permission behavior:
    - users without view/export permission receive 403;
    - read-export-only users can call export-preview/export;
    - download writes export audit or structured operation record.
22. No Redis implementation in this worker. If a cache abstraction already exists, do not wire pending invoice to it unless the spec is amended.
23. Return structured validation errors for invalid filters/sort/page and not found details.

TDD requirements:
- Add failing tests for upgraded expense DTO shape.
- Add failing tests for all 7 statuses and priority/edge cases.
- Add failing tests for payment summary derived from multiple bank+invoice relations.
- Add failing tests for filter-options context and field config.
- Add failing tests for relation-detail Sheet1 payload.
- Add failing tests for invoice-candidates search, pagination, available/already_related/conflict statuses and read-only behavior.
- Add failing tests for object details.
- Add failing tests for export-preview/export using same filters/sort and exporting all rows.
- Add failing tests for export no-view 403, read-export-only allowed and export audit/operation record.
- Add failing tests for SQL read model fresh empty, missing scope, stale/dirty scope and queue enqueue behavior.
- Add failing tests or migration assertions for new pending_invoice_rows query columns/indexes.
- Add failing tests for filters JSON field/operator whitelist, sort whitelist and structured 400 errors.
- Add regression tests that income old behavior still works.

Run:
- PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service -v
- PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v
- PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store -v

Expected final status:
- DONE if focused tests pass and DTO/export/read model contract is implemented.
- DONE_WITH_CONCERNS if existing repository abstractions expose a narrower pending invoice read model than expected; document exact follow-up for integration.
```

## Worker 2: Backend Rules, Attach Existing Invoice, Permissions, Audit

```text
/goal Implement production-grade pending invoice rules endpoints and attach-existing-invoice preview/confirm workflow, preserving the existing pending_invoice_tag_groups fact source and enforcing permissions, idempotency, audit, and read model invalidation.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- SECURITY.md
- docs/superpowers/specs/2026-05-20-pending-invoices-design.md
- docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- docs/product-specs/settings-and-access-control.md
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py
- backend/src/fin_ops_platform/services/access_control_service.py
- backend/src/fin_ops_platform/app/server.py
- tests/test_app_settings_service.py
- tests/test_pending_invoice_service.py
- tests/test_workbench_pair_relation_service.py
- tests/test_session_api.py or existing access-control tests

Owned write scope:
- backend/src/fin_ops_platform/services/pending_invoice_service.py for attach-existing-invoice application service methods
- backend/src/fin_ops_platform/services/app_settings_service.py only if existing pending_invoice_tag_groups API cannot support rules endpoint
- backend/src/fin_ops_platform/app/server.py only for /api/pending-invoices/rules and attach-existing-invoice routes/permission checks
- tests/test_app_settings_service.py
- tests/test_pending_invoice_service.py
- tests/test_pending_invoice_api.py or focused route tests

Do not edit:
- Main read/export query logic owned by Worker 1 except shared service contracts
- Frontend files

Required behavior:
1. Add GET /api/pending-invoices/rules returning:
   - bank_transaction_tags dictionary/version;
   - three groups: requires_invoice, bank_statement_as_invoice, no_invoice_required;
   - each group's tag codes and resolved active labels;
   - read_only/can_save flags based on access tier if existing API patterns expose them.
2. Add PUT /api/pending-invoices/rules:
   - save the same AppSettingsService pending_invoice_tag_groups fact;
   - do not create a second rules store;
   - validate unknown tags, archived tags, duplicate group assignment;
   - write settings audit;
   - mark pending_invoice read model dirty;
   - notify any existing settings/tag invalidation mechanisms.
3. Read-export-only users must receive 403 for PUT rules.
4. Add attach-existing-invoice preview:
   - POST /api/pending-invoices/rows/{transactionId}/attach-existing-invoice/preview
   - request body uses invoice_id and optional request_id;
   - validates transaction exists, direction is expense, invoice exists and is input invoice;
   - detects active relation conflicts;
   - returns preview_id, request_key, transaction_summary, invoice_summary, payment_impact, affected_months, warnings, conflicts, expires_at and can_confirm.
5. Add attach-existing-invoice confirm:
   - POST /api/pending-invoices/rows/{transactionId}/attach-existing-invoice
   - request body uses preview_id, invoice_id and request_id;
   - request_id is the confirm idempotency key;
   - reruns validation;
   - creates active bank+invoice pair relation through WorkbenchPairRelationService;
   - relation_mode should be stable and explicit, for example pending_invoice_attach_existing_invoice;
   - handles duplicate retry idempotently;
   - uses a stable request key and either a command record or deterministic relation case lookup so retries recover the same result;
   - returns status, request_id, request_key, transaction_id, invoice_id, affected_transaction_ids, affected_invoice_ids, affected_months, relation_case_id and optionally updated row DTO.
6. Confirm must enforce backend write permissions. Read-export-only users get 403.
7. Confirm must audit actor, transaction id, invoice id, relation case id, request id/key, affected months.
8. Confirm must invalidate/refresh pending invoice read model, workbench/search read models where existing lifecycle requires it.
9. Do not implement fake manual state mutation for status. Status will change by relation facts and read model refresh.
10. Existing manual补票 preview/confirm behavior must continue to pass.
11. If confirm writes any relation/command/audit state, it must use existing transaction or recoverable command conventions. On failure, it must either roll back fully or leave enough command state for recovery.
12. Recovery cases must be explicit:
    - retry after relation already exists returns the existing relation_case_id;
    - retry after relation exists but audit/dirty enqueue failed must补齐 audit/dirty scope when possible;
    - retry must not create a duplicate relation or mark a different status directly.

TDD requirements:
- Add failing tests for GET rules shape.
- Add failing tests for PUT rules validation, audit, invalidation and permission denial.
- Add failing tests for attach-existing preview success and validation failures.
- Add failing tests for attach-existing confirm idempotency and relation conflict.
- Add failing tests for retry after relation already exists and retry after audit/dirty enqueue failure.
- Add failing tests for audit and dirty scope/refresh enqueue after confirm.
- Add regression tests for existing manual pending invoice confirm if touched.

Run:
- PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_pending_invoice_service -v
- PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v

Expected final status:
- DONE if rules and attach-existing workflow pass focused tests and preserve existing manual补票 behavior.
- DONE_WITH_CONCERNS if access-control plumbing lacks an existing route helper; document exact integration point.
```

## Worker 3: Frontend Four-Zone Table Component

```text
/goal Build the approved four-zone PendingInvoicesTable component with MUI Table, merged columns, stable callbacks, responsive no-horizontal-scroll layout, and table-only tests.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-20-pending-invoices-design.md
- docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md
- docs/product-specs/pending-invoices.md
- web/src/README.md
- web/src/pages/PendingInvoicesPage.tsx
- web/src/components/pendingInvoices/PendingInvoicesTable.tsx
- web/src/features/pendingInvoices/types.ts
- web/src/components/common/PageScaffold.tsx
- web/src/contexts/PageSessionStateContext.tsx
- web/src/test/PendingInvoicesPage.test.tsx
- web/src/test/apiMock.ts

Owned write scope:
- web/src/components/pendingInvoices/PendingInvoicesTable.tsx
- web/src/components/pendingInvoices/ExpandableCellText.tsx if needed
- web/src/test/PendingInvoicesTable.test.tsx or table-focused additions to web/src/test/PendingInvoicesPage.test.tsx

Do not edit:
- web/src/pages/PendingInvoicesPage.tsx except if the orchestrator explicitly reassigns page wiring during integration
- web/src/features/pendingInvoices/api.ts
- web/src/features/pendingInvoices/types.ts except if the contract-prep/integration step has already assigned the change
- web/src/test/apiMock.ts
- Sidebar route/menu unless current files need no changes; this is an in-place upgrade and existing menu/route should remain.
- Backend files
- DataGrid code/hooks

Required behavior:
1. Main table uses MUI Table component family only. No DataGrid import and no .MuiDataGrid-root surface.
2. Render four big zone headers:
   - 支出流水
   - 发票获取状态
   - 进项发票
   - OA
3. Render small columns:
   - 支出流水: 对方/时间, 金额/银行账户, 摘要/凭证
   - 发票获取状态: 状态/依据/主操作
   - 进项发票: 发票号码/开票日期, 销方/识别号, 金额/支付差额
   - OA: 申请人/类型, 项目/详情
4. Fit common desktop widths without horizontal page scroll. Use fixed table layout and responsive percentages from the spec.
5. Do not repeat small-column labels inside data rows.
6. Long text uses two-line clamp and row-local expand/collapse.
7. One row per expense bank transaction.
8. Multiple invoices/OA/payment rows render primary summary and +N.
9. Status column displays backend invoiceAcquisitionStatus code/label/reason/primaryAction. Do not compute status in frontend.
10. Status column buttons emit callbacks only:
    - open relation drawer;
    - open invoice picker drawer;
    - open manual补票 dialog if existing flow remains in scope;
    - open rules drawer;
    - open export drawer.
11. Object detail buttons in bank/invoice/OA cells only emit object-detail callbacks.
12. The component receives data and access/action availability through props; it does not fetch rows and does not own server query state.
13. Support a refreshing/empty state prop so integration can display 202 read model refresh without treating it as a hard failure.
14. Preserve read-export-only UX through disabled/hidden action props supplied by the page.

TDD requirements:
- Add failing tests for four zone headers and key merged cell content.
- Add failing test that DataGrid is not rendered/imported for pending invoices.
- Add failing tests for status column actions opening correct drawer callbacks/state.
- Add failing tests that table renders refreshing/empty state from props.
- Add failing tests for read-export-only disabling write actions.

Run:
- cd web && npm test -- PendingInvoicesTable.test.tsx PendingInvoicesPage.test.tsx
- cd web && npm run build

Expected final status:
- DONE if table-focused tests and build pass.
- DONE_WITH_CONCERNS if shared frontend types are not yet available; document exact prop contract expected by integration.
```

## Worker 4: Frontend Drawers, Rules, Relation/Sheet1, Picker, Details, Export

```text
/goal Implement the 待找发票 right-side drawer workflows for rules, Sheet1 relation/payment details, existing invoice selection, object details, and filtered export.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- web/src/pages/PendingInvoicesPage.tsx
- web/src/components/pendingInvoices/PendingInvoicesTable.tsx
- web/src/components/common/AppDrawer.tsx
- web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx
- web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx
- web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx
- web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx
- web/src/components/cost-statistics/ExportCenterModal.tsx
- web/src/features/pendingInvoices/api.ts
- web/src/test/PendingInvoicesPage.test.tsx
- web/src/test/SettingsPage.test.tsx
- web/src/test/TurnoverLedgerPage.test.tsx
- web/src/test/CostStatisticsPage.test.tsx

Owned write scope:
- web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx
- web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx
- web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx
- web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx
- web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx
- web/src/components/pendingInvoices/PendingInvoiceDrawerTypes.ts if needed for local drawer prop contracts
- web/src/test/PendingInvoicesDrawers.test.tsx or extend PendingInvoicesPage tests

Do not edit:
- web/src/pages/PendingInvoicesPage.tsx except if the orchestrator explicitly reassigns page wiring during integration
- web/src/features/pendingInvoices/api.ts
- web/src/features/pendingInvoices/types.ts except if the contract-prep/integration step has already assigned the change
- web/src/test/apiMock.ts
- Backend files
- Settings page implementation except reuse ideas, unless orchestrator explicitly assigns shared component extraction

Required behavior:
1. All drawers anchor right, use MUI Drawer/AppDrawer patterns, and do not trigger main table refetch merely by opening/closing.
2. Drawers are mutually exclusive.
3. Drawer content lazy-loads after open and shows skeleton/progress state.
4. Drawer components should receive typed loader/action props. The serial integration step wires those props to `web/src/features/pendingInvoices/api.ts`.
5. Rules drawer:
   - loads GET /api/pending-invoices/rules;
   - manages three groups: 需要开票, 流水代替发票, 无需开票;
   - can only select existing active bank detail tags;
   - does not create new tags;
   - saves via PUT /api/pending-invoices/rules;
   - after save, refreshes current list/filter options and emits existing tag/settings update events if applicable;
   - disables save for read-export-only users.
6. Relation/Sheet1 drawer:
   - loads GET /api/pending-invoices/rows/{transactionId}/relation-detail;
   - shows related invoice summary, historical payment rows, current transaction, paid total, invoice total, remaining amount, difference amount;
   - actions route to invoice picker or object details as needed.
7. Existing invoice picker drawer:
   - supports search/filter for existing input invoices through GET /api/pending-invoices/invoice-candidates as documented in docs/dev/pending-invoices-api.md;
   - previews attach-existing-invoice before confirm;
   - confirms with preview_id + request_id, then maps API response to frontend camelCase;
   - shows conflicts/warnings from backend;
   - refreshes affected current row/list after success.
8. Object detail drawer:
   - supports bank transaction, invoice and OA detail targets;
   - shows all sections returned by backend;
   - handles detail_available=false after frontend mapping for OA without stable projection.
9. Export drawer:
   - calls export-preview with current filters/sort;
   - shows expected row count and file name;
   - downloads export endpoint result;
   - exports full filtered result, not current page;
   - remains available to read-export-only users.
10. Existing manual补票 dialog should remain available where the status action requires 补票, unless orchestrator decides to move it into drawer. Do not break existing manual invoice tests.
11. All buttons use icons when appropriate and accessible labels.

TDD requirements:
- Add failing tests for each drawer opening from status/object/export actions.
- Add failing tests for rules drawer load/save/permission disabled.
- Add failing tests for relation drawer totals and historical payment rows.
- Add failing tests for invoice picker candidate search request shape, conflict rendering, preview/confirm and request_id request shape.
- Add failing tests for detail drawer sections and unavailable OA detail.
- Add failing tests for export preview/download request including current filters/sort.
- Add regression test that opening/closing drawers does not refetch rows.

Run:
- cd web && npm test -- PendingInvoicesPage.test.tsx PendingInvoicesApi.test.ts PendingInvoicesDrawers.test.tsx
- cd web && npm run build

Expected final status:
- DONE if drawer tests and build pass.
- DONE_WITH_CONCERNS only if the frozen invoice-candidates contract changed during backend implementation; document exact contract mismatch for serial integration.
```

## Serial Integration Prompt

```text
/goal Integrate the 待找发票 backend and frontend worker outputs into one coherent production implementation, reconcile contracts, run verification, and fix regressions.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md
- docs/superpowers/prompts/2026-05-25-pending-invoice-page-upgrade-subagents.md
- all worker final reports
- git diff --stat
- git diff for changed files

Required work:
1. Inspect git status and identify changes by worker.
2. Own the shared frontend integration files:
   - web/src/pages/PendingInvoicesPage.tsx
   - web/src/features/pendingInvoices/types.ts
   - web/src/features/pendingInvoices/api.ts
   - web/src/test/apiMock.ts for pending invoice endpoints
   - web/src/test/PendingInvoicesPage.test.tsx and PendingInvoicesApi.test.ts as needed
3. Reconcile DTO naming: backend API stays snake_case; frontend mapper exposes camelCase.
4. Ensure /api/pending-invoices/rows works for upgraded expense page and existing income behavior remains sane.
5. Ensure filters JSON, field/operator whitelist, sort whitelist and structured 400 errors match docs/dev/pending-invoices-api.md.
6. Ensure filter-options, relation-detail, invoice-candidates, object details, rules, attach-existing-invoice, export-preview and export endpoints are wired in server and frontend API.
7. Ensure read-export-only permissions are enforced by backend and reflected in frontend.
8. Ensure pending invoice read model projection writes fields required for filtering/sorting/export.
9. Ensure fresh empty returns 200/read_model_status=fresh and rows=[], while stale/miss returns 202/refreshing without synchronous full rebuild.
10. Ensure no Redis dependency was introduced.
11. Ensure no DataGrid is used for pending invoice main table.
12. Update docs if implementation changed API details:
    - docs/product-specs/pending-invoices.md
    - docs/dev/pending-invoices-api.md
    - docs/dev/api-contracts.md if endpoint grouping changed
    - docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md if a confirmed detail changed
13. Run focused tests after each integration fix.
14. Run final verification:
    - PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service -v
    - PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service -v
    - PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store -v
    - cd web && npm test -- PendingInvoicesPage.test.tsx PendingInvoicesApi.test.ts PendingInvoicesDrawers.test.tsx
    - cd web && npm run build
15. UI/browser verification:
    - start the existing web dev server according to `web/README.md`;
    - open `/pending-invoices`;
    - verify common desktop widths have no horizontal page scroll;
    - verify drawer open/close does not refetch the main row list;
    - verify no `.MuiDataGrid-root` exists on the page.
16. If practical, run broader:
    - PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
    - cd web && npm test
17. Report exact verification results and any remaining risk.
```

## Reviewer Prompt

```text
/goal Review the completed 待找发票 page upgrade for requirement coverage, architecture fit, correctness, tests, permissions, and production-readiness.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read first:
- AGENTS.md
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md
- docs/superpowers/prompts/2026-05-25-pending-invoice-page-upgrade-subagents.md
- git diff --stat
- git diff for all changed files
- latest test output from implementer

Review stance:
- Findings first, ordered by severity.
- Ground findings in exact file/line references.
- Prioritize bugs, missed requirements, permission gaps, data consistency, read model correctness, test gaps, and UI regressions.
- Do not praise or summarize before findings.

Must check:
1. Existing /pending-invoices route/menu was upgraded in place; no duplicate similar page was added.
2. Main table uses MUI Table, not DataGrid.
3. Four-zone layout and approved column merges are implemented.
4. Page has no horizontal scroll at common desktop widths.
5. One row equals one expense bank transaction; multi relations show primary +N and details in drawers.
6. Sheet1 entry is in status column; object columns only open object details.
7. 7 status classes are backend-calculated and covered by tests.
8. Frontend does not calculate or mutate business status.
9. Rules drawer manages the same pending_invoice_tag_groups fact and supports all three groups.
10. Rules drawer cannot create tags.
11. Attach-existing-invoice flow uses preview/confirm, idempotency, permission checks and audit.
12. Invoice-candidates endpoint exists, is read-only and powers Sheet1 selection.
13. Export exports full filtered/sorted result, not current page.
14. Read-export-only users can view/export but cannot write.
15. filters JSON, field/operator whitelist and sort whitelist match docs/dev/pending-invoices-api.md.
16. read_model.pending_invoice_rows supports required fields/filter/sort/status.
17. Fresh empty read model result is 200/fresh/rows=[], while miss/stale is 202/refreshing.
18. API miss/stale path does not synchronously rebuild or scan all facts when SQL read model exists.
19. No Redis dependency was introduced.
20. Existing manual补票 behavior and income-side pending invoice behavior did not regress.
21. Writes are transactional or recoverable, with audit and read-model invalidation aligned.
22. PostgreSQL read_model.pending_invoice_rows has required query columns/indexes or a clearly documented approved exception.
23. Product/API long-term docs are updated if implementation changed the contract.
24. Tests cover backend query/status/read model, rules, attach existing invoice, export, frontend table, drawers and permissions.
25. No unrelated dirty files were reverted.

Return:
- Findings with severity P0/P1/P2/P3.
- Open questions.
- Verification gaps.
- Concise change summary only after findings.
- Verdict: APPROVED or NEEDS_FIXES.
```

## Prompt Self-Review Checklist

Use this checklist before dispatching implementation:

- [x] Prompts reference `docs/superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md`.
- [x] Prompts reference long-term docs `docs/product-specs/pending-invoices.md` and `docs/dev/pending-invoices-api.md`.
- [x] Prompts say upgrade existing `/pending-invoices`, not add a new page.
- [x] Prompts explicitly forbid DataGrid.
- [x] Prompts include the four approved zones and column merges.
- [x] Prompts include Sheet1 status-column entry.
- [x] Prompts include three-group rules drawer and same `pending_invoice_tag_groups` fact source.
- [x] Prompts include all 7 backend status classes.
- [x] Prompts include server-side full filtered export.
- [x] Prompts include read-export-only permission behavior.
- [x] Prompts include filters JSON, field/operator whitelist, sort whitelist and structured 400 behavior.
- [x] Prompts include invoice-candidates endpoint for Sheet1 selection.
- [x] Prompts include read model fresh empty versus miss/stale behavior.
- [x] Prompts include PostgreSQL pending_invoice_rows column/index migration work.
- [x] Prompts explicitly say no Redis dependency in v1.
- [x] Prompts include relation-detail and attach-existing-invoice preview/confirm.
- [x] Prompts include object detail endpoints.
- [x] Prompts include frontend drawer no-refetch behavior.
- [x] Prompts include transactional/recoverable writes, audit and read-model invalidation.
- [x] Prompts include focused backend/frontend tests and final verification commands.
- [x] Prompts include browser/layout verification for no horizontal scroll and no DataGrid surface.
