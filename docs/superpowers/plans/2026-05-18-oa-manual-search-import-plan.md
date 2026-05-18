# OA Manual Search Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-grade OA full-range search and manual import flow under OA import settings, using existing OA import and attachment parsing services.

**Architecture:** Backend adds a focused manual OA import service that searches Mongo-backed OA records outside the global retention cutoff, records manually retained OA row ids, refreshes selected attachment parsing before import, and reuses `WorkbenchQueryService.sync_oa_row_ids()`. Frontend adds a MUI native `Table`-based data table under `SettingsOaRetentionSection`, with server-side paging, filters, multi-select, row expansion, attachment refresh, import and undo actions. No `@mui/x-data-grid` and no new `mui-datatables` dependency.

**Tech Stack:** Python standard-library HTTP app, `MongoOAAdapter`, `WorkbenchQueryService`, `ApplicationStateStore`; React 18, TypeScript, MUI Material Table components, Vitest, Python unittest.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-18-oa-manual-search-import-design.md`
- Repository guidance: `AGENTS.md`
- Existing settings UI: `web/src/components/settings/SettingsOaRetentionSection.tsx`
- Existing settings API client: `web/src/features/workbench/api.ts`
- Existing settings route handlers: `backend/src/fin_ops_platform/app/server.py`
- Existing OA adapter: `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- Existing workbench sync entrypoint: `backend/src/fin_ops_platform/services/workbench_query_service.py`
- Existing state store: `backend/src/fin_ops_platform/services/state_store.py`

## Work Ownership

Worker A owns backend service, state store methods, adapter refresh/search helpers, backend route handlers, and Python backend tests.

Worker B owns frontend API types/client, settings UI components, and frontend tests.

Worker C owns final integration review and verification only after A and B finish.

Workers are not alone in the codebase. Do not revert unrelated changes. Current main worktree already has unrelated dirty files from the batch-accounting work; ignore them unless directly touching the same file. If editing `backend/src/fin_ops_platform/app/server.py` or `web/src/components/settings/SettingsOaRetentionSection.tsx`, preserve existing changes and keep the diff scoped.

## API Contract

### Search

`GET /api/workbench/settings/oa/manual-search`

Query params:

- `q`: free text, optional.
- `form_types`: comma-separated values, optional. Supported values: `payment_request`, `expense_claim`.
- `statuses`: comma-separated values, optional. Supported values include `completed`, `in_progress`.
- `date_from`: `YYYY-MM-DD`, optional.
- `date_to`: `YYYY-MM-DD`, optional.
- `page`: 0-based integer.
- `page_size`: integer, default 20, max 100.

Response:

```json
{
  "rows": [
    {
      "row_id": "oa-exp-1981",
      "oa_no": "1981",
      "applicant": "陈雄兵",
      "application_date": "2025-12-23",
      "form_type": "expense_claim",
      "form_type_label": "日常报销",
      "status": "completed",
      "status_label": "已完成",
      "project_name": "大理卷烟厂动力车间中水处理系统升级改造项目",
      "reason": "去大理检修中水系统餐费",
      "amount": "135.00",
      "attachment_file_count": 2,
      "importable_invoice_count": 1,
      "unrecognized_attachment_count": 1,
      "import_status": "not_imported",
      "imported_at": null,
      "can_import": true,
      "disabled_reason": "",
      "items": [
        {
          "date": "2025-12-23",
          "amount": "135.00",
          "content": "餐费",
          "project_name": "大理卷烟厂动力车间中水处理系统升级改造项目",
          "reason": "去大理检修中水系统餐费",
          "attachment_file_count": 2,
          "importable_invoice_count": 1
        }
      ]
    }
  ],
  "total": 1,
  "page": 0,
  "page_size": 20
}
```

### Refresh Attachments

`POST /api/workbench/settings/oa/manual-search/refresh-attachments`

Request:

```json
{ "row_ids": ["oa-exp-1981"] }
```

Response:

```json
{
  "rows": [
    {
      "row_id": "oa-exp-1981",
      "attachment_file_count": 2,
      "importable_invoice_count": 1,
      "unrecognized_attachment_count": 1
    }
  ],
  "errors": []
}
```

### Import

`POST /api/workbench/settings/oa/manual-imports`

Request:

```json
{ "row_ids": ["oa-exp-1981"], "actor_id": "current_user_or_settings" }
```

Response:

```json
{
  "imported": ["oa-exp-1981"],
  "already_imported": [],
  "failed": [],
  "rows": [/* refreshed search row DTOs */]
}
```

### List Manual Imports

`GET /api/workbench/settings/oa/manual-imports`

Response:

```json
{ "row_ids": ["oa-exp-1981"], "entries": [] }
```

### Undo

`DELETE /api/workbench/settings/oa/manual-imports/{row_id}`

Response:

```json
{ "removed": true, "row_id": "oa-exp-1981" }
```

## Task 1: Backend Manual Import Service

**Files:**

- Create: `backend/src/fin_ops_platform/services/oa_manual_import_service.py`
- Modify: `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Test: `tests/test_oa_manual_import_service.py`
- Test: `tests/test_mongo_oa_adapter.py`
- Test: `tests/test_state_store.py`

- [ ] **Step 1: Write failing service tests**

Add tests covering:

- Search ignores global retention cutoff and filters records by query text, form type and status.
- In-progress records are returned but `can_import=false`.
- Completed records are importable.
- Import writes manual retained row ids idempotently.
- Import calls adapter row-id sync path and preserves original `record.month`.
- Refresh/import force attachment parsing for selected OA and returns updated attachment counts.
- Undo removes only the manual retained marker, not source OA data.

- [ ] **Step 2: Add state store persistence**

Add local JSON and Mongo-backed methods on `ApplicationStateStore`:

- `load_manual_oa_imports() -> dict[str, object]`
- `save_manual_oa_imports(payload: dict[str, object]) -> None`
- `add_manual_oa_imports(row_ids: list[str], actor_id: str, audit: dict[str, object]) -> dict[str, object]`
- `remove_manual_oa_import(row_id: str, actor_id: str) -> bool`

Use a new local file under the existing state root, e.g. `manual_oa_imports.json`, and a Mongo detailed collection key such as `manual_oa_imports`. Preserve existing storage-mode behavior and fail fast in `mongo_only` if Mongo is required.

- [ ] **Step 3: Add adapter helpers without bypassing import settings globally**

Add focused methods to `MongoOAAdapter`:

- `search_application_records(...)` for full-range search. It must not apply the global retention cutoff. It may use form/status filters passed to the method.
- `refresh_application_record_attachments(row_ids: list[str]) -> list[OAApplicationRecord]` or equivalent. It must force synchronous attachment parsing for selected row ids and invalidate selected record cache entries/months.

Do not change default `list_application_records()` semantics for normal app import.

- [ ] **Step 4: Implement `OAManualImportService`**

Responsibilities:

- Normalize search filters.
- Build search DTOs from `OAApplicationRecord`.
- Compute `attachment_file_count`, `importable_invoice_count`, `unrecognized_attachment_count`.
- Mark `import_status` from state store.
- Reject non-completed imports with structured `not_completed` errors.
- On import, force attachment refresh before writing row ids.
- Call `WorkbenchQueryService.sync_oa_row_ids(row_ids)` after state persistence.
- Expose `manual_retained_row_ids()` for app-level retained scope.

- [ ] **Step 5: Run backend unit tests**

Run:

```bash
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_oa_manual_import_service tests.test_mongo_oa_adapter tests.test_state_store -v
```

Expected: all tests pass.

## Task 2: Backend API and Retention Integration

**Files:**

- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_oa_manual_import_api.py`
- Test: `tests/test_workbench_v2_api.py`

- [ ] **Step 1: Write failing API tests**

Cover:

- `GET /api/workbench/settings/oa/manual-search` returns early OA rows even when global cutoff excludes them.
- Search supports page/page_size and validates bounds.
- `POST /api/workbench/settings/oa/manual-search/refresh-attachments` returns updated counts.
- `POST /api/workbench/settings/oa/manual-imports` imports completed rows and rejects in-progress rows.
- Repeated import is idempotent.
- `GET /api/workbench/settings/oa/manual-imports` returns retained ids.
- `DELETE /api/workbench/settings/oa/manual-imports/{row_id}` removes marker and invalidates read models.

- [ ] **Step 2: Wire service construction**

Instantiate `OAManualImportService` in `Application.__init__`, passing state store, `WorkbenchQueryService`, and the OA adapter when available.

- [ ] **Step 3: Add route dispatch**

Add routes near existing `/api/workbench/settings` handlers:

- `GET /api/workbench/settings/oa/manual-search`
- `POST /api/workbench/settings/oa/manual-search/refresh-attachments`
- `GET /api/workbench/settings/oa/manual-imports`
- `POST /api/workbench/settings/oa/manual-imports`
- `DELETE /api/workbench/settings/oa/manual-imports/{row_id}`

Use existing `_load_json_body`, `_json_response`, status code, and error payload patterns.

- [ ] **Step 4: Integrate retained all scope**

Update `_build_retained_all_oa_row_payload()` and `_raw_oa_payload_for_selected_scope()` so manual retained row ids are included alongside supplemental relation-derived row ids. Include OA attachment invoice rows whose `derived_from_oa_id` is manually retained.

- [ ] **Step 5: Invalidate derived state**

After import, refresh, or undo, invalidate relevant workbench read model scopes: affected original months plus `all`. Clear search cache. Use existing `_handle_oa_source_changed()` or scoped invalidation helpers where appropriate.

- [ ] **Step 6: Run API tests**

Run:

```bash
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_oa_manual_import_api tests.test_workbench_v2_api -v
```

Expected: all tests pass.

## Task 3: Frontend API Client and MUI Table UI

**Files:**

- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Create: `web/src/components/settings/OaManualSearchImportTable.tsx`
- Modify: `web/src/components/settings/SettingsOaRetentionSection.tsx`
- Modify: `web/src/components/settings/types.ts`
- Test: `web/src/test/SettingsOaManualSearchImportTable.test.tsx`
- Test: `web/src/test/WorkbenchSelection.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Cover:

- Renders `OA全量搜索导入` under `OA导入设置`.
- Uses table semantics, not DataGrid roles/classes.
- Can search and display rows.
- Multi-select updates selected count, amount total and invoice count.
- Expand row shows OA item details.
- In-progress rows cannot be selected and show disabled reason.
- Refresh attachments calls refresh API and updates counts.
- Import calls import API and updates row import status.
- Clear selection works.

- [ ] **Step 2: Add TypeScript API models**

Add types for:

- `OaManualSearchRow`
- `OaManualSearchItem`
- `OaManualSearchResult`
- `OaManualImportResult`
- `OaManualImportEntry`

Add API functions:

- `searchManualOaImports(filters)`
- `refreshManualOaImportAttachments(rowIds)`
- `importManualOaRows(rowIds)`
- `fetchManualOaImports()`
- `removeManualOaImport(rowId)`

- [ ] **Step 3: Build the MUI native Table component**

Use only MUI Material components. Do not import `@mui/x-data-grid` and do not add `mui-datatables`.

Component responsibilities:

- Local filter state: query, form type checkboxes, status checkboxes, optional date range.
- Server-side page and page size.
- Multi-select by `row_id`.
- Table header toolbar with selected count, amount sum and invoice count sum.
- Row expansion with `Collapse`.
- Inline status chips for completed/in-progress/imported.
- `刷新附件解析` per row.
- `导入已选OA项` button disabled when no importable selected rows.
- Error and loading states.

- [ ] **Step 4: Mount under settings section**

Render the table below the existing OA import settings block in `SettingsOaRetentionSection`. Keep existing import settings controls unchanged.

- [ ] **Step 5: Run frontend tests**

Run:

```bash
cd web && npm test -- --run src/test/SettingsOaManualSearchImportTable.test.tsx src/test/WorkbenchSelection.test.tsx
```

Expected: all tests pass.

## Task 4: Final Integration and Verification

**Files:**

- Modify only if needed after review.

- [ ] **Step 1: Run targeted backend test bundle**

```bash
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_oa_manual_import_service tests.test_oa_manual_import_api tests.test_mongo_oa_adapter tests.test_state_store tests.test_workbench_v2_api -v
```

- [ ] **Step 2: Run targeted frontend tests**

```bash
cd web && npm test -- --run src/test/SettingsOaManualSearchImportTable.test.tsx src/test/WorkbenchSelection.test.tsx
```

- [ ] **Step 3: Run frontend build**

```bash
cd web && npm run build
```

- [ ] **Step 4: Inspect final diff**

```bash
git diff --stat
git diff -- backend/src/fin_ops_platform/services/oa_manual_import_service.py backend/src/fin_ops_platform/app/server.py web/src/components/settings/SettingsOaRetentionSection.tsx
```

- [ ] **Step 5: Verify constraints**

Confirm:

- No new dependency in `web/package.json`.
- No `@mui/x-data-grid` import in new manual import component.
- Manual import does not copy OA source data.
- Import uses existing `sync_oa_row_ids()`.
- Attachment refresh is targeted, not global cache clear.

## Subagent Prompt A: Backend Service Worker

```text
/goal Implement backend manual OA search/import core on main for fin-ops-platform.

You are Worker A. Work in /Users/yu/Desktop/fin-ops-platform. You are not alone in the codebase. Do not revert unrelated changes. Own only:
- backend/src/fin_ops_platform/services/oa_manual_import_service.py
- backend/src/fin_ops_platform/services/mongo_oa_adapter.py
- backend/src/fin_ops_platform/services/state_store.py
- tests/test_oa_manual_import_service.py
- focused additions to tests/test_mongo_oa_adapter.py and tests/test_state_store.py

Read:
- AGENTS.md
- docs/superpowers/specs/2026-05-18-oa-manual-search-import-design.md
- docs/superpowers/plans/2026-05-18-oa-manual-search-import-plan.md
- backend/src/fin_ops_platform/services/mongo_oa_adapter.py
- backend/src/fin_ops_platform/services/workbench_query_service.py
- backend/src/fin_ops_platform/services/state_store.py
- backend/src/fin_ops_platform/services/oa_adapter.py

Implement Task 1 only. Requirements:
- Create OAManualImportService.
- Add state store persistence for manual OA imports with local and Mongo paths.
- Add targeted MongoOAAdapter helpers for full-range search and selected attachment refresh.
- Do not change normal automatic OA import behavior.
- Do not clear all attachment cache. Refresh selected row ids only.
- Import must be idempotent by OA row_id.
- Non-completed OA must be visible in search but not importable.
- Preserve original OA month.
- Reuse OAApplicationRecord and existing attachment parsing.

Write and run:
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_oa_manual_import_service tests.test_mongo_oa_adapter tests.test_state_store -v

Return status DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, list changed files, tests run, and any concerns.
```

## Subagent Prompt B: Backend API Worker

```text
/goal Wire manual OA search/import service into backend HTTP API and retained all-scope.

You are Worker B. Work in /Users/yu/Desktop/fin-ops-platform. You are not alone in the codebase. Do not revert unrelated changes. Own only:
- backend/src/fin_ops_platform/app/server.py
- tests/test_oa_manual_import_api.py
- focused additions to tests/test_workbench_v2_api.py

Read:
- AGENTS.md
- docs/superpowers/specs/2026-05-18-oa-manual-search-import-design.md
- docs/superpowers/plans/2026-05-18-oa-manual-search-import-plan.md
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/workbench_query_service.py

Implement Task 2 only. Assume Worker A provides OAManualImportService with search, refresh_attachments, import_row_ids, list_imports, remove_import, and manual_retained_row_ids methods. If Worker A methods differ, adapt minimally without changing Worker A-owned files.

Requirements:
- Add routes:
  GET /api/workbench/settings/oa/manual-search
  POST /api/workbench/settings/oa/manual-search/refresh-attachments
  GET /api/workbench/settings/oa/manual-imports
  POST /api/workbench/settings/oa/manual-imports
  DELETE /api/workbench/settings/oa/manual-imports/{row_id}
- Reuse existing JSON and validation patterns.
- Include manual retained row ids in retained all-scope alongside supplemental relation-derived row ids.
- Include OA attachment invoice rows derived from manually retained OA ids.
- After import/refresh/delete, invalidate affected scopes and clear search cache.
- Keep existing settings API behavior unchanged.

Write and run:
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_oa_manual_import_api tests.test_workbench_v2_api -v

Return status DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, list changed files, tests run, and any concerns.
```

## Subagent Prompt C: Frontend Worker

```text
/goal Implement the OA manual search/import settings UI using MUI native Table.

You are Worker C. Work in /Users/yu/Desktop/fin-ops-platform. You are not alone in the codebase. Do not revert unrelated changes. Own only:
- web/src/features/workbench/types.ts
- web/src/features/workbench/api.ts
- web/src/components/settings/OaManualSearchImportTable.tsx
- web/src/components/settings/SettingsOaRetentionSection.tsx
- web/src/components/settings/types.ts
- web/src/test/SettingsOaManualSearchImportTable.test.tsx
- focused additions to web/src/test/WorkbenchSelection.test.tsx

Read:
- AGENTS.md
- docs/superpowers/specs/2026-05-18-oa-manual-search-import-design.md
- docs/superpowers/plans/2026-05-18-oa-manual-search-import-plan.md
- web/src/components/settings/SettingsOaRetentionSection.tsx
- web/src/features/workbench/api.ts
- web/src/features/workbench/types.ts

Implement Task 3 only. Requirements:
- Use MUI Material Table components only. Do not import @mui/x-data-grid. Do not add mui-datatables.
- Add API client functions for the contract in the plan.
- Add a component under OA导入设置 named OA全量搜索导入.
- Filters: query, form types, statuses, optional date range.
- Server-side pagination.
- Multi-select importable rows, clear selection, all current-page importable rows.
- Header shows selected OA count, selected amount total, selected importable invoice count.
- Expand row with Collapse to show OA item details.
- Per-row refresh attachments button.
- Import selected button.
- Disabled rows show reason.
- Keep existing OA导入设置 controls unchanged.

Write and run:
cd web && npm test -- --run src/test/SettingsOaManualSearchImportTable.test.tsx src/test/WorkbenchSelection.test.tsx

Return status DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED, list changed files, tests run, and any concerns.
```

## Subagent Prompt D: Final Review Worker

```text
/goal Review integrated OA manual search/import implementation for spec compliance and production quality.

You are Worker D. Work in /Users/yu/Desktop/fin-ops-platform. Do not make broad edits. Review after Workers A/B/C have completed.

Read:
- docs/superpowers/specs/2026-05-18-oa-manual-search-import-design.md
- docs/superpowers/plans/2026-05-18-oa-manual-search-import-plan.md
- Final git diff.

Check:
- Search ignores global cutoff but has its own filters.
- Import only allows completed OA.
- Import preserves original OA month.
- Import reuses sync_oa_row_ids.
- Attachment refresh is selected-row targeted, not global clear.
- Manual retained OA ids affect all-scope retained payload and attachment invoice rows.
- UI uses MUI native Table, not DataGrid or new dependencies.
- Error handling is structured.
- Tests cover backend and frontend acceptance criteria.

Run if possible:
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_oa_manual_import_service tests.test_oa_manual_import_api tests.test_mongo_oa_adapter tests.test_state_store tests.test_workbench_v2_api -v
cd web && npm test -- --run src/test/SettingsOaManualSearchImportTable.test.tsx src/test/WorkbenchSelection.test.tsx
cd web && npm run build

Return findings first, ordered by severity, with file/line references. If no issues, say clearly. Include tests run.
```
