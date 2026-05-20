# Pending Invoices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved `待找发票` workflow: dynamic bank transaction tags, expense invoice filters, a MUI Table page, and official manual invoice creation with preview/confirm and pair relation integration.

**Architecture:** Add a small server-owned bank transaction tag dictionary and pending invoice tag-group settings, then build an independent pending-invoice query/application service that reads existing bank transactions, invoices, OA/workbench relations, and pair relations. Manual invoice creation uses the canonical import service path, creates a formal invoice, and writes a bank+invoice pair relation through one idempotent backend command.

**Tech Stack:** Python backend under `backend/src/fin_ops_platform`, custom HTTP routing in `app/server.py`, React 18 + TypeScript + Vite frontend, MUI Material Table components, Vitest and Python unittest.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-20-pending-invoices-design.md`
- Existing docs: `docs/product-specs/bank-details.md`, `docs/product-specs/workbench.md`, `docs/dev/api-contracts.md`, `DESIGN.md`

## File Map

Backend tag/settings work:

- Modify: `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
  - Introduce server-owned tag dictionary normalization and payload helpers.
  - Preserve existing system codes as seeds.
- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Persist `bank_transaction_tags` and `pending_invoice_tag_groups` with versioning.
- Validate active tag references and duplicate mappings.
- Record audit entries for tag dictionary and pending invoice tag-group changes.
- Modify: `backend/src/fin_ops_platform/services/bank_details_service.py`
  - Return tag dictionary/version to bank details clients or provide options through a new method.
- Modify: `backend/src/fin_ops_platform/app/server.py`
  - Accept and return new settings fields.
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
  - Persist `bank_transaction_tags` and `pending_invoice_tag_groups` in both file and Mongo app-settings storage.
- Test: `tests/test_bank_transaction_category_service.py`
- Test: `tests/test_app_settings_service.py`
- Test: `tests/test_bank_details_service.py`

Backend pending invoice work:

- Create: `backend/src/fin_ops_platform/services/pending_invoice_service.py`
  - `PendingInvoiceQueryService`
  - `PendingInvoiceApplicationService`
  - preview/confirm DTO helpers
  - idempotent command log model in snapshot-compatible form
- Modify: `backend/src/fin_ops_platform/services/imports.py`
  - Add a focused public method if needed for canonical manual invoice import from a normalized row.
  - Do not bypass existing identity/source-link behavior.
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
  - Persist pending invoice command logs if current app snapshot needs a dedicated slot.
- Modify: `backend/src/fin_ops_platform/app/server.py`
  - Add `/api/pending-invoices/rows`
- Add `/api/pending-invoices/manual-invoices/preview`
- Add `/api/pending-invoices/manual-invoices`
- Wire service construction, persistence, audit, and full read-model/cache invalidation.
- Test: `tests/test_pending_invoice_service.py`
- Test: `tests/test_pending_invoice_api.py`
- Test: `tests/test_invoice_inventory_stats_service.py` if source-link visibility needs coverage.

Frontend work:

- Create: `web/src/features/pendingInvoices/types.ts`
- Create: `web/src/features/pendingInvoices/api.ts`
- Create: `web/src/pages/PendingInvoicesPage.tsx`
- Create: `web/src/components/pendingInvoices/PendingInvoicesTable.tsx`
- Create: `web/src/components/pendingInvoices/ManualInvoiceDialog.tsx`
- Create: `web/src/components/settings/SettingsBankTransactionTagsSection.tsx`
- Create: `web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/components/shell/sidebarItems.ts`
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/features/bankDetails/types.ts`
- Modify: `web/src/features/bankDetails/api.ts`
- Modify: `web/src/pages/BankDetailsPage.tsx`
- Modify: `web/src/components/settings/SettingsPageContent.tsx`
- Modify: `web/src/components/settings/types.ts`
- Modify: `web/src/components/settings/SettingsTreeNav.tsx`
- Test: `web/src/test/PendingInvoicesPage.test.tsx`
- Test: `web/src/test/PendingInvoicesApi.test.ts`
- Test: `web/src/test/SettingsPage.test.tsx`
- Test: `web/src/test/BankDetailsPage.test.tsx`

Prompt artifact:

- Create: `docs/superpowers/prompts/2026-05-20-pending-invoices-subagents.md`

## Task 1: Backend Dynamic Tags And Settings

**Files:**
- Modify: `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Modify: `backend/src/fin_ops_platform/services/bank_details_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_bank_transaction_category_service.py`
- Test: `tests/test_app_settings_service.py`
- Test: `tests/test_bank_details_service.py`

- [ ] **Step 1: Write failing tests for tag dictionary payload**

Add tests proving:

- Existing system category codes are exposed as active `system` tag definitions.
- Custom tags are normalized with `source=custom`, `status=active`, stable code, label, path.
- Tag dictionary `version` increments when tags or pending invoice mappings change.
- Archived tags remain resolvable for historical rows but are not selectable.
- Tag dictionary or pending invoice mapping changes record an audit entry with actor, before/after summary, and version.

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service tests.test_app_settings_service -v
```

Expected: FAIL because the tag dictionary/settings fields do not exist.

- [ ] **Step 2: Implement tag dictionary and settings normalization**

Implement:

- A payload builder in `bank_transaction_category_service.py` that converts current category definitions and auto categories into tag definitions.
- App settings fields:
  - `bank_transaction_tags`
  - `pending_invoice_tag_groups`
  - `bank_transaction_tags.version`
- Validation:
  - Unknown tag code rejected.
  - Archived tag cannot be referenced by pending invoice groups.
  - Same tag cannot be mapped to multiple pending invoice groups.

- [ ] **Step 3: Extend settings API**

Modify `server.py` settings handlers to:

- Return the new fields from `GET /api/workbench/settings`.
- Accept and validate them in `POST /api/workbench/settings`.
- After a successful tag or mapping save, clear/refresh server-side caches and read models that depend on `bank_transaction_tags` or `pending_invoice_tag_groups`, including bank details tag options/classification counts and pending invoice filter/query results.
- Failed validation must not trigger invalidation.
- Record settings audit for bank tag and pending invoice mapping changes.
- Persist the new settings fields through `ApplicationStateStore.load_app_settings()` and `save_app_settings()` for both JSON-file and Mongo-backed storage so tag mappings survive process restarts.

- [ ] **Step 4: Extend bank details DTO**

Add tag dictionary/version to bank details responses or a server-owned options response. Frontend must not need the hardcoded category list for production rendering.

- [ ] **Step 5: Verify tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service tests.test_app_settings_service tests.test_bank_details_service -v
```

Expected: PASS.

## Task 2: Backend Pending Invoice Query And Manual Invoice Command

**Files:**
- Create: `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- Modify: `backend/src/fin_ops_platform/services/imports.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_pending_invoice_service.py`
- Test: `tests/test_pending_invoice_api.py`
- Possibly modify: `tests/test_invoice_inventory_stats_service.py`

- [ ] **Step 1: Write failing query service tests**

Cover:

- Expense rows include input invoices.
- Income rows include output invoices.
- One bank transaction with multiple invoices returns one row.
- Expense `no_invoice_required` rows with no invoice return `can_create_invoice=false`.
- Expense `requires_invoice` and `bank_statement_as_invoice` rows with no invoice return `can_create_invoice=true`.
- Income rows with no invoice return `can_create_invoice=true`.
- OA applicant comes only from existing relation context; missing relation returns `—`.

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service -v
```

Expected: FAIL because the service does not exist.

- [ ] **Step 2: Implement `PendingInvoiceQueryService`**

Implement a read-only service that accepts:

- import service
- pair relation service
- app settings/tag provider
- optional OA/applicant row lookup provider

Output DTO exactly shaped for the frontend. Do not mutate invoices, bank transactions, or pair relations.

- [ ] **Step 3: Write failing preview/confirm tests**

Cover:

- Preview returns target invoice type, identity, duplicate status, affected months.
- Confirm requires `request_id` and valid preview.
- Confirm creates a formal invoice through the import service canonical path.
- Confirm creates bank+invoice pair relation with `relation_mode=pending_invoice_manual_invoice`.
- Duplicate submit with same `request_id` returns the original result.
- Command log supports statuses `started`, `invoice_created`, `relation_created`, `completed`, `failed_recoverable`, and `failed_terminal`.
- Failure after invoice creation can be retried and completes relation creation instead of creating a second invoice.
- Failure after relation creation but before response, audit, or cache invalidation can be retried and completes finalization without creating a second relation.
- Recovery detects an existing invoice with `manual_invoice_import` source link and the same `request_key` but no relation, then creates the missing relation or returns a repair-required error without creating another invoice.
- Duplicate invoice identity returns `409 duplicate_invoice` semantics.

- [ ] **Step 4: Implement `PendingInvoiceApplicationService`**

Implement:

- Preview validation with no writes.
- Confirm validation reusing preview logic.
- Idempotent command log with `request_id` and deterministic `request_key`.
- Canonical invoice creation via `ImportNormalizationService.preview_import()` / `confirm_import()` or a narrowly extracted equivalent method that preserves identity/source links.
- Pair relation creation through `WorkbenchPairRelationService`.
- Affected months calculation.
- Audit for manual invoice confirm, including actor, transaction id, invoice id, relation case id, request id/key, and affected months.
- Invalidation/finalization for pending invoice row data, workbench read models, bank relation tag projection, search cache, and tax/writeoff affected-month state.

- [ ] **Step 5: Add API routes**

Add routes:

- `GET /api/pending-invoices/rows`
- `POST /api/pending-invoices/manual-invoices/preview`
- `POST /api/pending-invoices/manual-invoices`

Return structured errors:

- `invalid_direction`
- `invalid_filter_for_income`
- `bank_transaction_not_found`
- `invalid_invoice_payload`
- `duplicate_invoice`
- `relation_conflict`
- `permission_denied`

Confirm route finalization must run after both initial success and idempotent recovery so retries leave the system in the same completed state.

- [ ] **Step 6: Verify backend pending invoice tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_pending_invoice_api tests.test_invoice_inventory_stats_service -v
```

Expected: PASS.

## Task 3: Frontend Pending Invoices Page, Settings UI, And Bank Details Sync

**Files:**
- Create: `web/src/features/pendingInvoices/types.ts`
- Create: `web/src/features/pendingInvoices/api.ts`
- Create: `web/src/pages/PendingInvoicesPage.tsx`
- Create: `web/src/components/pendingInvoices/PendingInvoicesTable.tsx`
- Create: `web/src/components/pendingInvoices/ManualInvoiceDialog.tsx`
- Create: `web/src/components/settings/SettingsBankTransactionTagsSection.tsx`
- Create: `web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/components/shell/sidebarItems.ts`
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/features/bankDetails/types.ts`
- Modify: `web/src/features/bankDetails/api.ts`
- Modify: `web/src/pages/BankDetailsPage.tsx`
- Modify: `web/src/components/settings/SettingsPageContent.tsx`
- Modify: `web/src/components/settings/types.ts`
- Modify: `web/src/components/settings/SettingsTreeNav.tsx`
- Test: `web/src/test/PendingInvoicesApi.test.ts`
- Test: `web/src/test/PendingInvoicesPage.test.tsx`
- Test: `web/src/test/SettingsPage.test.tsx`
- Test: `web/src/test/BankDetailsPage.test.tsx`

- [ ] **Step 1: Write failing API mapping tests**

Add tests for:

- `fetchPendingInvoiceRows()`
- `previewManualPendingInvoice()`
- `confirmManualPendingInvoice()`
- settings mapping for `bankTransactionTags` and `pendingInvoiceTagGroups`
- bank details tag dictionary mapping

Run:

```bash
cd web && npm test -- --run PendingInvoicesApi.test.ts WorkbenchApi.test.ts BankDetailsApi.test.ts
```

Expected: FAIL until API client/types exist.

- [ ] **Step 2: Implement frontend API/types**

Add typed mappers that translate snake_case backend DTOs to camelCase frontend DTOs. Keep all business facts server-owned.

- [ ] **Step 3: Write failing page tests**

Cover:

- Sidebar has `待找发票`.
- Route `/pending-invoices` renders page.
- MUI Table displays the three large columns.
- Expense/income toggle changes labels and API parameters.
- Expense filter menu appears only on expense mode.
- `无需开票` no-invoice row does not show `+`.
- `需要开票` and `流水代替发票` no-invoice rows show `+`.
- Income no-invoice rows show `+`.
- Multiple invoices render inside one table row.
- Dialog preview step appears before confirm.

- [ ] **Step 4: Implement page and table**

Use MUI native components only:

- `Table`
- `TableHead`
- `TableBody`
- `TableRow`
- `TableCell`
- `TablePagination`
- `ToggleButtonGroup`
- `Menu`
- `IconButton`
- `Chip`
- `Dialog`
- `TextField`
- `DatePicker`

Do not use `DataGrid`.

- [ ] **Step 5: Implement settings sections and tag sync**

Add:

- `银行流水标签` section.
- `待找发票筛选` section with left fixed groups and right tag items.
- Add/remove/create tag controls.
- Broadcast event `finops:bank-transaction-tags-updated` after settings save.
- Use `BroadcastChannel` for cross-tab propagation when available.
- Add a window-focus fallback that compares the latest server tag version and refetches when `BroadcastChannel` is unavailable or missed.
- BankDetailsPage listens and refetches tag dictionary/rows.
- PendingInvoicesPage listens and refetches filters/rows.

- [ ] **Step 6: Verify frontend tests and build**

Run:

```bash
cd web && npm test -- --run PendingInvoicesApi.test.ts PendingInvoicesPage.test.tsx SettingsPage.test.tsx BankDetailsPage.test.tsx
cd web && npm run build
```

Expected: PASS.

## Task 4: Integration Verification And Fixes

**Files:**
- Modify only files needed to fix integration failures found by full verification.

- [ ] **Step 1: Run backend verification**

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

- [ ] **Step 2: Run frontend verification**

```bash
cd web && npm test
cd web && npm run build
```

- [ ] **Step 3: Fix failures with TDD**

For any failure:

- Write or adjust the focused failing test first if missing.
- Verify failure.
- Implement minimal fix.
- Re-run focused check.
- Re-run full check.

- [ ] **Step 4: Final review**

Confirm:

- No production behavior exists only in frontend state.
- Manual invoice creation is official inventory and pair relation backed.
- No `DataGrid` is used in the pending invoice page.
- Settings tags are server-owned and sync without page reload.
- Tag sync works across tabs through `BroadcastChannel` or focus-time version comparison fallback.
- Read-only users cannot mutate.
