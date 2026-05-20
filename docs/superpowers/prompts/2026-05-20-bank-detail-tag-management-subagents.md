# 银行明细标签管理多任务子代理 Prompts

## Worker 1: Frontend Settings Boundary

```text
/goal Implement the frontend settings boundary for bank detail tag management.

Repository: /Users/yu/Desktop/fin-ops-platform
Spec: docs/superpowers/specs/2026-05-20-bank-detail-tag-management-design.md
Plan: docs/superpowers/plans/2026-05-20-bank-detail-tag-management.md

Scope:
- Modify only settings UI/type/test files unless blocked:
  - web/src/components/settings/SettingsPageContent.tsx
  - web/src/components/settings/SettingsBankTransactionTagsSection.tsx
  - web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx
  - web/src/components/settings/types.ts
  - web/src/test/SettingsPage.test.tsx
- You are not alone in the codebase. Do not revert edits made by others. Do not touch backend files.

Requirements:
1. Settings navigation must show 银行明细标签管理, not 银行流水标签.
2. The navigation description must communicate that this is the full-app bank detail tag dictionary.
3. The bank tag section heading must be 银行明细标签管理.
4. 待找发票筛选 must not allow quick tag creation.
5. Remove the 新标签 input and 新建并加入 button from 待找发票筛选.
6. 待找发票筛选 must only allow selecting existing active tags.
7. Empty state copy must tell users to create tags in 银行明细标签管理.
8. Keep MUI native components. Do not introduce DataGrid.
9. Keep internal IDs and API fields as bank_transaction_tags unless a test forces otherwise.

TDD:
- First update/add SettingsPage.test.tsx assertions for the renamed entry and removed quick-create controls.
- Run `cd web && npm test -- --run SettingsPage.test.tsx` and observe failure.
- Implement the minimal UI/type changes.
- Rerun `cd web && npm test -- --run SettingsPage.test.tsx`.

Return:
- Status: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED.
- Files changed.
- Test commands and results.
- Any concerns about copy, accessibility, or coupling.
```

## Worker 2: Settings API Contract and Error Mapping

```text
/goal Harden the settings API contract and user-facing error mapping for bank detail tags and pending invoice mappings.

Repository: /Users/yu/Desktop/fin-ops-platform
Spec: docs/superpowers/specs/2026-05-20-bank-detail-tag-management-design.md
Plan: docs/superpowers/plans/2026-05-20-bank-detail-tag-management.md

Scope:
- Modify only these files unless blocked:
  - web/src/features/workbench/api.ts
  - web/src/pages/SettingsPage.tsx
  - web/src/test/SettingsPage.test.tsx
  - tests/test_app_settings_service.py
  - backend/src/fin_ops_platform/services/app_settings_service.py
  - backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- You are not alone in the codebase. Do not revert edits made by others. Coordinate with UI changes by preserving current component contracts where possible.

Requirements:
1. Frontend save payload must send `bank_transaction_tags.definitions`, not `bank_transaction_tags.tags`.
2. Backend must continue to accept `tags` as a compatibility alias when normalizing tag dictionaries.
3. Backend validation must remain strict:
   - unknown mapped tag -> `unknown_bank_transaction_tag`
   - archived mapped tag -> `archived_bank_transaction_tag`
   - tag mapped to multiple groups -> `duplicate_pending_invoice_tag_mapping`
4. Frontend must translate these error codes to Chinese actionable messages:
   - unknown -> 待找发票筛选引用了不存在的银行明细标签，请刷新后重新选择。
   - archived -> 该银行明细标签已停用，不能用于新的待找发票筛选。
   - duplicate -> 同一个银行明细标签不能同时归入多个待找发票筛选。
5. Do not relax backend constraints and do not silently drop invalid mappings.

TDD:
- Add/update backend tests in tests/test_app_settings_service.py for `tags` alias + pending invoice mapping validation.
- Add/update frontend tests in SettingsPage.test.tsx for `definitions` payload and Chinese error mapping.
- Run:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_bank_transaction_category_service -v`
  - `cd web && npm test -- --run SettingsPage.test.tsx`

Return:
- Status.
- Root cause addressed.
- Files changed.
- Test commands and results.
- Any remaining risks.
```

## Worker 3: Cross-Page Sync Regression

```text
/goal Verify and, if needed, strengthen full-app synchronization after bank detail tag changes.

Repository: /Users/yu/Desktop/fin-ops-platform
Spec: docs/superpowers/specs/2026-05-20-bank-detail-tag-management-design.md
Plan: docs/superpowers/plans/2026-05-20-bank-detail-tag-management.md

Scope:
- Prefer tests and mocks. Modify production page sync only if a concrete gap is found.
- Candidate files:
  - web/src/pages/BankDetailsPage.tsx
  - web/src/pages/PendingInvoicesPage.tsx
  - web/src/test/BankDetailsPage.test.tsx
  - web/src/test/PendingInvoicesPage.test.tsx
  - web/src/test/apiMock.ts
- You are not alone in the codebase. Do not revert edits made by others.

Requirements:
1. Bank details page must consume the unified bank detail tag dictionary from the backend.
2. Pending invoices page must consume the same tag dictionary and pending invoice mapping from the backend.
3. After Settings saves bank detail tags and broadcasts `finops:bank-transaction-tags-updated`, relevant pages must refetch instead of relying on stale local state.
4. Focus fallback must still recover from missed events.
5. Do not add another tag store or duplicate taxonomy.

Process:
1. Inspect existing sync tests first.
2. If coverage exists and is sufficient, do not modify production code; report evidence.
3. If coverage is missing, add the smallest regression test for the missing sync path.
4. Run:
   - `cd web && npm test -- --run BankDetailsPage.test.tsx PendingInvoicesPage.test.tsx SettingsPage.test.tsx`

Return:
- Status.
- Whether production code changed.
- Test evidence.
- Any sync risks that remain.
```

## Final Review Agent

```text
/goal Review the completed bank detail tag management consolidation for correctness, integration quality, and test coverage.

Repository: /Users/yu/Desktop/fin-ops-platform
Spec: docs/superpowers/specs/2026-05-20-bank-detail-tag-management-design.md

Review scope:
- Confirm Settings shows 银行明细标签管理 and no longer presents 银行流水标签 as product copy.
- Confirm 待找发票筛选 cannot create tags and only maps existing active tags.
- Confirm tag creation/edit/disable remains centralized.
- Confirm backend strict validation remains.
- Confirm frontend uses definitions payload and maps relevant backend errors to Chinese messages.
- Confirm sync behavior is tested or covered by existing tests.
- Confirm no DataGrid was introduced in this workflow.

Return:
- APPROVED if no blocking issues.
- CHANGES_REQUESTED with numbered findings, file paths, and exact required fixes.
```

