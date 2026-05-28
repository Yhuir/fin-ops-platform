# 2026-05-28 银行明细主子标签生产级改造执行 Prompt

/goal Implement production-grade primary/sub-label support for bank detail automatic tags in `/Users/yu/Desktop/fin-ops-platform`. Make primary and sub labels first-class structured fields for bank details, automatic tag rules, bank detail search/filter/export, pending invoice rule display/matching context, no-OA/workbench bank-row display, and read-model projection. Preserve stable `category_code`/tag `code` as the durable identity. Do not change cost statistics aggregation: 成本统计 must continue to use OA `费用类型` / `费用内容` as its cost grouping source in this release.

## Workspace

```text
/Users/yu/Desktop/fin-ops-platform
```

## Must Read First

Read these before editing:

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/product-specs/bank-details.md`
- `docs/product-specs/pending-invoices.md`
- `docs/product-specs/no-oa-bank-batches.md`
- `docs/product-specs/workbench.md`
- `docs/product-specs/turnover-management.md`
- `docs/product-specs/cost-statistics.md`
- `docs/dev/api-contracts.md`
- `docs/dev/backend.md`
- `docs/dev/frontend.md`
- `docs/archive/prompts/2026-05-26-bank-auto-tag-rules-execution.md`
- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_effective_category_provider.py`
- `backend/src/fin_ops_platform/services/bank_details_service.py`
- `backend/src/fin_ops_platform/services/bank_detail_sql_projection.py`
- `backend/src/fin_ops_platform/services/bank_details_export_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/services/live_workbench_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `web/src/pages/BankDetailsPage.tsx`
- `web/src/features/bankDetails/api.ts`
- `web/src/features/bankDetails/types.ts`
- `web/src/features/bankDetails/AutoTagRulesDrawer.tsx`
- `web/src/features/pendingInvoices/api.ts`
- `web/src/features/pendingInvoices/types.ts`
- Existing tests around bank details, auto tag rules, settings, pending invoices, no-OA batches, turnover ledger, workbench bank rows, and exports.

## Hard Requirements

1. Use TDD. Write failing tests before production code for each behavior change.
2. Preserve unrelated dirty worktree changes. Inspect `git status --short` first and do not revert files you did not change.
3. This is not a temporary/rescue patch. Do not only concatenate labels in the UI.
4. Preserve stable `category_code` / tag dictionary `code` as the durable identity used by downstream services.
5. Do not make downstream services persist copied Chinese label names as facts for rule matching. Rules continue to store stable tag codes unless this prompt explicitly says otherwise.
6. Do not change `cost_statistics_service.py`, cost statistics API contracts, or cost statistics frontend grouping semantics except for tests proving no regression if necessary. Cost statistics remains grouped by OA `expense_type` / `expense_content`.
7. Do not let primary/sub labels replace existing single-label fields. Add structured fields while preserving old fields for compatibility.
8. Do not physically delete tags.
9. Do not allow users to edit the `内部往来款` system rule.
10. Do not add broad fallback behavior that hides invalid contracts. Validate missing/invalid label contracts and fail clearly.
11. Do not perform synchronous full-history read-model rebuilds inside normal API save/read requests.

## Current Code Facts To Verify

The implementation must verify these facts before editing:

- `BankTransactionCategoryService` already has partial `output_primary_label` / `output_sub_label` normalization, but the frontend does not map or save these fields.
- `BankTransactionAutoCategoryService._suggestion()` currently returns only `category_code`, `category_label`, and `category_path`.
- `resolve_effective_category()` currently returns only `effective_category_code`, `effective_category_label`, `effective_category_path`, and `effective_category_source`.
- `BankDetailsService._row_payload()` and `BankDetailSqlProjectionBuilder` currently expose single-label fields such as `auto_category_label` and `effective_category_label`.
- `read_model.bank_detail_rows` currently has no primary/sub label columns.
- `BankDetailsPage.TypeCell` currently renders a single `autoCategoryLabel`.
- `pending_invoice_tag_groups` currently stores tag codes and `PendingInvoiceQueryService` matches by `category_code`.
- `CostStatisticsService` builds cost grouping from OA rows, not bank labels. This must stay true.

## Target Contract

### Tag Rule Definition

Each editable automatic bank tag rule supports:

```json
{
  "code": "fee",
  "label": "手续费",
  "output_primary_label": "费用",
  "output_sub_label": "手续费",
  "direction": "expense",
  "account_scope": {"type": "any", "values": []},
  "rules": {
    "match_fields": ["counterparty_name", "summary_text", "note_text"],
    "exact_any": ["手续费", "短信服务费"],
    "contains_any": ["转账手续费"],
    "contains_all": [],
    "none_of": ["技术服务费"],
    "regex_any": []
  }
}
```

Rules:

- `output_primary_label` is required and non-empty for active editable automatic rules.
- `output_sub_label` is optional.
- Existing rules without explicit primary/sub labels migrate compatibly:
  - `output_primary_label = existing label`
  - `output_sub_label = ""`
- For rules with a sub label, keep the legacy `label` as the sub label unless the existing label is intentionally different. For example, `费用 / 手续费` should keep `label = 手续费`.
- The public rule payload must include `output_primary_label` and `output_sub_label`.
- Frontend camelCase fields must be `outputPrimaryLabel` and `outputSubLabel`.
- Save payload must send `output_primary_label` and `output_sub_label`.

### Category Suggestion / Effective Category

Automatic suggestions and effective category records must add structured fields:

```json
{
  "category_code": "fee",
  "category_label": "手续费",
  "category_primary_label": "费用",
  "category_sub_label": "手续费",
  "category_label_path": ["费用", "手续费"],
  "category_path": ["自动识别", "手续费"]
}
```

Rules:

- Existing `category_label` remains for compatibility and should continue to represent the leaf/default display label.
- New `category_primary_label` and `category_sub_label` are the structured dimensions.
- New `category_label_path` is a clean display hierarchy for primary/sub labels.
- Do not break existing `category_path` consumers unless a test proves an intentional additive adjustment is needed.
- Manual/legacy categories without output fields should derive safe defaults:
  - primary label from a known definition path/group when available;
  - otherwise from the existing `category_label`;
  - sub label may be empty.

### Bank Detail Row DTO

Rows returned by `/api/bank-details/transactions` must add:

```json
{
  "auto_category_primary_label": "费用",
  "auto_category_sub_label": "手续费",
  "auto_category_label_path": ["费用", "手续费"],
  "effective_category_primary_label": "费用",
  "effective_category_sub_label": "手续费",
  "effective_category_label_path": ["费用", "手续费"],
  "category_primary_label": "费用",
  "category_sub_label": "手续费",
  "category_label_path": ["费用", "手续费"]
}
```

Existing fields must remain:

- `auto_category_code`
- `auto_category_label`
- `auto_category_path`
- `effective_category_code`
- `effective_category_label`
- `effective_category_path`
- `category_code`
- `category_label`
- `category_path`

### Bank Detail Search And Filter

Bank detail search must include:

- primary label
- sub label
- label path
- legacy label

Add server-side filter support with additive query params:

```text
category_code=fee
category_primary_label=费用
category_sub_label=手续费
```

Rules:

- Filters apply to effective category fields.
- Empty params are ignored.
- `category_code` remains the preferred stable filter when available.
- Label filters exist for user-facing primary/sub browsing and must be exact normalized comparisons, not broad substring logic.
- SQL read-model path and legacy/local path must behave consistently.

### Bank Detail Export

Bank detail export must include structured columns:

- `自动分类`
- `自动分类主标签`
- `自动分类子标签`

If effective category is used in export today, keep the same effective/auto fallback policy and add primary/sub columns using the same policy. Do not remove existing columns.

### Frontend Bank Details Page

Frontend must:

- Map all new DTO fields.
- Display primary/sub labels in the bank detail type cell. A compact, stable display such as `费用 / 手续费` is acceptable, but do not store this composite as the only data model.
- Add category filtering UI that can filter by code and/or primary/sub label without overloading the global search input.
- Keep text inside chips/buttons from overflowing on desktop and mobile.
- Keep current server-side pagination/search behavior.
- Do not turn the page into a marketing or explanatory screen.

### Auto Tag Rules Drawer

The drawer must:

- Show editable fields for `输出主标签` and `输出子标签`.
- Keep `标签名称` as the legacy leaf/default label, or rename the UI copy if tests/docs clarify a better label.
- Validate active rules:
  - primary label required;
  - legacy label required;
  - existing matching condition validation remains.
- Show primary/sub labels in collapsed rule summaries.
- Preserve `内部往来款` as system-first and not editable.
- Preserve archive/re-enable behavior and version conflict behavior.

### Pending Invoice Rules And Rows

Pending invoice rules remain code-based:

- `pending_invoice_tag_groups.groups.*.tag_codes` remains the fact source.
- Matching remains by stable `category_code`.
- Do not introduce label-based pending invoice rule storage.

Add structured label participation:

- Public bank transaction tag definitions exposed to settings/pending-invoice UIs include primary/sub labels.
- Pending invoice row payload includes:
  - `effective_tag_primary_label`
  - `effective_tag_sub_label`
  - `effective_tag_label_path`
- `invoice_acquisition_status.matched_rule` includes:
  - `tag_primary_label`
  - `tag_sub_label`
  - `tag_label_path`
- Keyword search and table filters can find primary/sub labels.
- Rule settings UI/tag selectors display primary/sub labels so users can reason about rules by main/sub tag while the backend stores tag codes.

### Workbench / No-OA / Turnover Display

Bank rows projected into workbench/no-OA/turnover-related displays must carry structured labels additively:

- `category_primary_label`
- `category_sub_label`
- `category_label_path`

Display tags should include primary/sub information when available. Existing special-rule logic that checks `category_code` must remain code-based.

Do not change turnover business family/status rules in this task.

### Cost Statistics Explicit Non-Goal

Do not adapt cost statistics in this release.

Cost statistics must continue to:

- resolve cost grouping from OA `expense_type` / `expense_content`;
- group by existing cost `expense_type`;
- export existing cost columns;
- ignore bank primary/sub labels for grouping and filtering unless an existing row display already happens to show bank text.

Add a focused regression test only if implementation changes shared category helpers in a way that could accidentally alter cost statistics.

## Recommended Execution Model

Use one orchestrator and split implementation into serial and parallel phases. Workers are not alone in the codebase: there may be concurrent changes by other workers. They must not revert edits made by others and must keep edits inside their ownership scope.

### Serial Phase 0: Contract Freeze

Run before parallel workers.

```text
/goal Freeze the bank primary/sub tag contract before implementation. Inspect current code and update only docs/spec/API contract files needed to prevent backend/frontend workers from guessing field names. Do not implement production behavior yet.

Work in /Users/yu/Desktop/fin-ops-platform.

Read:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/product-specs/bank-details.md
- docs/product-specs/pending-invoices.md
- docs/product-specs/no-oa-bank-batches.md
- docs/product-specs/workbench.md
- docs/product-specs/cost-statistics.md
- docs/archive/prompts/2026-05-28-bank-detail-primary-sub-tags-execution.md

Deliver:
- Update product/dev docs only if they are the project’s current contract source for the changed fields.
- Define canonical snake_case and camelCase field names exactly as in the Target Contract.
- Explicitly document that cost statistics remains OA-based and out of scope.
- Do not change backend/frontend implementation in this phase.
- Run no broad tests unless docs tooling exists.
```

### Parallel Worker A: Backend Category Contract And Auto Tag Rules

Can run after Phase 0.

```text
/goal Implement backend category contract support for bank primary/sub labels and automatic tag rule persistence, using TDD, without touching frontend files or cost statistics.

Work in /Users/yu/Desktop/fin-ops-platform.

Owned files/modules:
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py
- backend/src/fin_ops_platform/services/bank_transaction_effective_category_provider.py
- backend/src/fin_ops_platform/services/app_settings_service.py only for public settings/tag payload support
- backend tests directly covering these services/API endpoints

Do not edit:
- web/
- backend/src/fin_ops_platform/services/cost_statistics_service.py

Requirements:
- Preserve existing `category_code` and `category_label`.
- Add `category_primary_label`, `category_sub_label`, and `category_label_path` to category records/suggestions/effective category records.
- Make `output_primary_label` required for active editable automatic rules.
- Preserve and return `output_primary_label` / `output_sub_label` in GET auto-tag rules.
- Accept and validate `output_primary_label` / `output_sub_label` in PUT auto-tag rules.
- Default old rules to primary=label, sub="".
- Keep `内部往来款` non-editable.
- Keep pending invoice tag group storage code-based.

Tests first:
- Add/modify tests in `tests/test_bank_transaction_auto_category_service.py`.
- Add/modify tests in `tests/test_bank_auto_tag_rules_api.py`.
- Add/modify tests in `tests/test_app_settings_service.py`.
- Watch each new test fail before implementation.

Verification:
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_auto_category_service tests.test_bank_auto_tag_rules_api tests.test_app_settings_service -v`
```

### Parallel Worker B: Backend Bank Detail Read Model, Search, Filter, Export

Can run after Phase 0. Coordinate with Worker A before final integration if helper names change.

```text
/goal Make bank detail API/read-model/export carry and query structured primary/sub labels end to end, using TDD, without changing frontend or cost statistics.

Work in /Users/yu/Desktop/fin-ops-platform.

Owned files/modules:
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/bank_detail_sql_projection.py
- backend/src/fin_ops_platform/services/bank_details_export_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- backend/src/fin_ops_platform/app/server.py only for `/api/bank-details/transactions` and export query-param parsing
- backend/src/fin_ops_platform/postgres/migrations/*
- backend tests for bank detail service, SQL runtime/projection, repository, export

Do not edit:
- web/
- backend/src/fin_ops_platform/services/cost_statistics_service.py

Requirements:
- Add row DTO fields for auto/effective/category primary/sub labels and label paths.
- Add SQL read-model columns for primary/sub labels and label paths where native filtering/search needs them.
- Bump bank detail read-model schema version if payload/native columns change.
- Add migration for new read-model columns and indexes needed for category_code/primary/sub filtering.
- Add `category_code`, `category_primary_label`, `category_sub_label` filters to SQL and legacy bank detail list paths.
- Parse and pass `category_code`, `category_primary_label`, and `category_sub_label` in bank detail list and export routes.
- Include primary/sub labels in keyword search text.
- Export `自动分类主标签` and `自动分类子标签`.
- Do not introduce request-time full rebuilds.

Tests first:
- Add/modify `tests/test_bank_details_service.py`.
- Add/modify `tests/test_bank_details_sql_runtime.py`.
- Add/modify `tests/test_bank_details_export_service.py`.
- Add/modify repository/migration tests if this repo has existing migration test patterns.
- Watch each new test fail before implementation.

Verification:
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_details_sql_runtime tests.test_bank_details_export_service -v`
```

### Parallel Worker C: Backend Pending Invoice, Workbench, No-OA Display

Can run after Phase 0. Coordinate with Worker A for helper output names.

```text
/goal Add structured bank primary/sub labels to pending invoice rows, matched rules, workbench/no-OA bank-row display, and related search payloads while keeping all business matching code-based.

Work in /Users/yu/Desktop/fin-ops-platform.

Owned files/modules:
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/services/live_workbench_service.py
- backend/src/fin_ops_platform/app/server.py only for narrow mapping/search payload changes
- tests covering pending invoice service/page API/workbench bank row payloads/no-OA display

Do not edit:
- web/
- backend/src/fin_ops_platform/services/cost_statistics_service.py

Requirements:
- Pending invoice filtering by `requires_invoice`, `bank_statement_as_invoice`, and `no_invoice_required` remains based on `category_code` in `pending_invoice_tag_groups`.
- Pending invoice row bank transaction payload includes primary/sub labels and label path.
- `matched_rule` includes primary/sub labels and label path.
- Pending invoice keyword search can find primary/sub labels.
- Workbench/no-OA bank rows carry category primary/sub labels and label path.
- Display tags include primary/sub information when available.
- Existing special detectors continue to check `category_code`.
- Turnover/no-OA behavior must not change except additive display/search fields.

Tests first:
- Add/modify `tests/test_pending_invoice_service.py`.
- Add/modify relevant workbench/no-OA tests such as `tests/test_workbench_v2_api.py` or focused service tests.
- Watch each new test fail before implementation.

Verification:
- `PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_workbench_v2_api -v`
```

### Parallel Worker D: Frontend Bank Details And Auto Tag Drawer

Can run after Phase 0 and after backend contract field names are frozen. Use backend contract from this prompt even before backend is merged.

```text
/goal Implement frontend support for bank primary/sub labels in bank details types/API mapping, auto-tag rules drawer editing/saving, display, and bank-detail filters.

Work in /Users/yu/Desktop/fin-ops-platform.

Owned files/modules:
- web/src/features/bankDetails/types.ts
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/AutoTagRulesDrawer.tsx
- web/src/pages/BankDetailsPage.tsx
- web/src/test/BankDetailsApi.test.ts
- web/src/test/BankDetailsPage.test.tsx
- web/src/test/apiMock.ts only for bank detail mock data

Do not edit:
- backend/
- cost statistics frontend files

Requirements:
- Map snake_case primary/sub fields to camelCase.
- Add `outputPrimaryLabel` and `outputSubLabel` to editable/save auto-tag rule types.
- Drawer shows and validates `输出主标签` and `输出子标签`.
- Drawer sends `output_primary_label` and `output_sub_label`.
- Bank details type cell displays primary/sub labels in a compact, non-overflowing way.
- Add category filter UI that sends `category_code`, `category_primary_label`, and/or `category_sub_label` query params through the API client.
- Global search remains global search and is not overloaded as the only category filter.
- Keep server-side pagination/search behavior.

Tests first:
- Add/modify `web/src/test/BankDetailsApi.test.ts`.
- Add/modify `web/src/test/BankDetailsPage.test.tsx`.
- Add drawer tests if an AutoTagRulesDrawer test file exists; otherwise add focused coverage where this project normally places component tests.
- Watch each new test fail before implementation.

Verification:
- `cd web && npm test -- BankDetailsApi.test.ts BankDetailsPage.test.tsx`
```

### Parallel Worker E: Frontend Pending Invoice / Settings Tag Display

Can run after Phase 0 and after backend contract field names are frozen.

```text
/goal Make pending invoice and settings-related frontend views display and search bank primary/sub labels while continuing to save pending invoice rules as tag codes.

Work in /Users/yu/Desktop/fin-ops-platform.

Owned files/modules:
- web/src/features/pendingInvoices/types.ts
- web/src/features/pendingInvoices/api.ts
- web/src/pages/PendingInvoicesPage.tsx
- settings page/tag selector files if they render `pending_invoice_tag_groups` or `bank_transaction_tags`
- web/src/test/PendingInvoicesPage.test.tsx
- web/src/test/SettingsPage.test.tsx
- web/src/test/apiMock.ts only for pending/settings mock data

Do not edit:
- backend/
- cost statistics frontend files

Requirements:
- Pending invoice row type maps effective tag primary/sub labels and label path.
- Matched rule type maps primary/sub labels and label path.
- Pending invoice UI displays primary/sub labels where tag labels are shown.
- Settings/pending invoice rule selectors show primary/sub labels to users but submit existing tag codes.
- Do not create a frontend-only label-based pending invoice rule model.
- Do not save primary/sub labels in `pending_invoice_tag_groups`; only `tag_codes` may be submitted.
- Keyword/filter behavior should include primary/sub labels when backend returns them.

Tests first:
- Add/modify `web/src/test/PendingInvoicesPage.test.tsx`.
- Add/modify `web/src/test/SettingsPage.test.tsx`.
- Watch each new test fail before implementation.

Verification:
- `cd web && npm test -- PendingInvoicesPage.test.tsx SettingsPage.test.tsx`
```

### Serial Phase F: Integration, Docs, Verification

Run after Workers A-E.

```text
/goal Integrate all bank primary/sub tag changes into one coherent production implementation, resolve contract mismatches, update docs, run verification, and fix regressions. Cost statistics must remain OA-based.

Work in /Users/yu/Desktop/fin-ops-platform.

Responsibilities:
- Inspect `git status --short` and review changed files from all workers.
- Reconcile snake_case/camelCase naming across backend, frontend, mocks, and tests.
- Ensure stable `category_code` remains the durable identity everywhere.
- Ensure pending invoice rule storage remains `tag_codes`.
- Ensure cost statistics files and behavior are unchanged except explicit no-regression tests/docs.
- Update product/dev docs:
  - `docs/product-specs/bank-details.md`
  - `docs/product-specs/pending-invoices.md`
  - `docs/product-specs/no-oa-bank-batches.md` if no-OA display/search changed
  - `docs/product-specs/workbench.md` if workbench bank display/search changed
  - `docs/dev/api-contracts.md` or a more specific API doc if this repo has one for bank details/pending invoices
- Do not add this prompt to main docs; keep it archived.

Verification:
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_auto_category_service tests.test_bank_auto_tag_rules_api tests.test_app_settings_service tests.test_bank_details_service tests.test_bank_details_sql_runtime tests.test_bank_details_export_service tests.test_pending_invoice_service -v`
- Run relevant workbench/no-OA tests selected by changed files.
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v` if practical.
- `cd web && npm test`
- `cd web && npm run build`
- Start local dev server and smoke test bank details/pending invoice pages if needed.

Final report:
- Changed files grouped by backend/frontend/docs/tests.
- Verification commands and results.
- Confirmation that cost statistics remains OA-based and was not adapted.
- Remaining risks or skipped checks.
```

### Reviewer Prompt

Run this after implementation, before final handoff.

```text
/goal Review the completed bank primary/sub tag implementation for correctness, architecture fit, requirement coverage, test quality, and regression risk. Do not implement broad rewrites; report findings first, then fix only confirmed issues if asked.

Work in /Users/yu/Desktop/fin-ops-platform.

Review against:
- docs/archive/prompts/2026-05-28-bank-detail-primary-sub-tags-execution.md
- AGENTS.md
- docs/product-specs/bank-details.md
- docs/product-specs/pending-invoices.md
- docs/product-specs/cost-statistics.md

Check:
- Primary/sub labels are structured fields, not only concatenated UI strings.
- Existing `category_code` remains the durable identity.
- Existing single-label fields remain backward compatible.
- Auto-tag rules GET/PUT preserve primary/sub labels.
- Bank detail API/read model/export/search/filter include primary/sub labels.
- Pending invoice rows/matched rules display and search primary/sub labels while rules still store tag codes.
- Workbench/no-OA bank display includes primary/sub labels additively.
- Cost statistics remains grouped by OA `expense_type` / `expense_content` and has no accidental bank-label grouping.
- SQL read-model schema/version/migrations are coherent.
- Frontend types/API/mocks/tests match backend snake_case fields.
- No unrelated dirty work was reverted.
- Tests were written before implementation and relevant verification passed.

Output:
- Findings first, ordered by severity with file/line references.
- Then missing tests or residual risks.
- Then concise approval only if no blocking issues remain.
```

## Acceptance Criteria

- Auto-tag drawer can edit and save `输出主标签=费用` and `输出子标签=手续费` for a fee rule.
- A matching bank transaction returns both legacy label and structured labels:
  - `auto_category_label = 手续费`
  - `auto_category_primary_label = 费用`
  - `auto_category_sub_label = 手续费`
- Bank details page displays primary/sub labels and can filter by them.
- Bank detail keyword search finds `费用` and `手续费`.
- Bank detail export contains primary/sub columns.
- Pending invoice rows and matched rules expose/display primary/sub labels while matching remains by tag code.
- Settings/pending invoice rule selectors display primary/sub labels but save tag codes.
- Workbench/no-OA bank rows carry primary/sub labels for display/search without changing special rule code matching.
- Cost statistics remains unchanged and OA-based.
- Full relevant backend/frontend tests pass, or skipped checks are explicitly reported with reasons.

## Prompt Self-Review Checklist

Reviewed on 2026-05-28 before handoff.

- [x] Contains `/goal`.
- [x] States cost statistics is out of scope and remains OA-based.
- [x] Keeps `category_code` as durable identity.
- [x] Requires structured fields instead of string concatenation only.
- [x] Covers auto-tag rule GET/PUT.
- [x] Covers automatic suggestions and effective category records.
- [x] Covers bank details DTO, read model, search, filter, export, and frontend.
- [x] Covers pending invoice rows/rules without changing tag-code storage.
- [x] Covers workbench/no-OA additive display fields.
- [x] Specifies tests and verification.
- [x] Splits work into safe serial/parallel phases.
- [x] Warns workers not to revert unrelated changes.
