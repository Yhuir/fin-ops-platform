# 待找发票规则派生与层级抽屉多任务执行 Prompt

This prompt is intended for Codex workers implementing the approved production-grade `待找发票规则设置` drawer refactor.

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Primary spec:

```text
docs/superpowers/specs/2026-05-31-pending-invoice-derived-rules-design.md
```

Long-term sources:

```text
AGENTS.md
README.md
ARCHITECTURE.md
backend/README.md
docs/index.md
docs/dev/backend.md
docs/architecture/backend-refactor/README.md
docs/architecture/backend-refactor/target-architecture.md
docs/architecture/backend-refactor/architecture-inventory.md
docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
docs/architecture/backend-refactor/read-model-and-external-services.md
docs/product-specs/pending-invoices.md
docs/product-specs/bank-details.md
docs/dev/pending-invoices-api.md
docs/dev/api-contracts.md
```

## Orchestrator Prompt

```text
/goal Implement the production-grade 待找发票规则设置 refactor: users edit only 流水代替发票 and 无需开票 tag groups; 需要开票 is derived by the backend from all active 银行明细自动标签 minus those two groups; the drawer shows the tags as a compact primary/child hierarchy with primary labels never selectable.

You are working in /Users/yu/Desktop/fin-ops-platform on main.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/dev/backend.md
- docs/architecture/backend-refactor/README.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/architecture-inventory.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/read-model-and-external-services.md
- docs/product-specs/pending-invoices.md
- docs/product-specs/bank-details.md
- docs/dev/pending-invoices-api.md
- docs/dev/api-contracts.md
- docs/superpowers/specs/2026-05-31-pending-invoice-derived-rules-design.md
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/search_pending_sql_projection.py
- web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx
- web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx
- web/src/features/pendingInvoices/types.ts
- web/src/features/pendingInvoices/api.ts
- web/src/pages/PendingInvoicesPage.tsx
- tests/test_pending_invoice_api.py
- tests/test_pending_invoice_service.py
- tests/test_bank_auto_tag_rules_api.py
- web/src/test/PendingInvoicesApi.test.ts
- web/src/test/PendingInvoicesPage.test.tsx

Architecture constraints:
- This is not a rescue patch. Implement the integrated production solution.
- Follow the existing Python-first backend refactor direction. Do not create a new backend, new rule table, or parallel rule store.
- Keep HTTP handlers thin. Reuse AppSettingsService and existing pending invoice read model invalidation.
- Continue using `pending_invoice_tag_groups` as the settings fact source.
- Do not expand legacy snapshot paths or add direct Redis/RabbitMQ/OA Mongo dependencies.
- Do not add dependencies.
- Preserve unrelated dirty work. Do not revert files you did not change.

Functional requirements:
- GET /api/pending-invoices/rules returns three groups:
  - `bank_statement_as_invoice`: editable, persisted.
  - `no_invoice_required`: editable, persisted.
  - `requires_invoice`: read-only, derived by backend.
- The active tag universe is all `status=active` tags from the bank detail auto-tag dictionary (`bank_transaction_tags.definitions` or compatible `tags`).
- `requires_invoice = active tags - bank_statement_as_invoice - no_invoice_required`.
- Tag identity is only `code`.
- Display hierarchy uses `output_primary_label` and `output_sub_label`.
- Primary labels are never selectable.
- Child labels are selectable in the first two blocks.
- Tags without a sub label render as a same-name child under their primary label.
- PUT /api/pending-invoices/rules only trusts/saves `bank_statement_as_invoice` and `no_invoice_required`.
- If legacy request payload contains `requires_invoice`, accept it but ignore and recompute it.
- Pending invoice list filtering and read-model projection for `filter=requires_invoice` must also use the same complement rule, not a persisted `requires_invoice.tag_codes` array.
- Unknown and archived tags in the two editable groups must fail with existing validation errors; ignored legacy `requires_invoice` content must not block saves.
- Duplicate tag selection across the two editable groups must fail.
- Save success must continue to write settings audit/version and enqueue pending invoice read model refresh scopes through existing paths.
- Frontend save request must not send `requires_invoice`.
- The drawer must be narrower and denser than the current implementation.
- The drawer must show two editable blocks and one read-only block in this order: 流水代替发票, 无需开票, 需要开票.

Execution order:
1. Serial discovery:
   - inspect `git status --short`;
   - read the docs and current code listed above;
   - use CodeGraph for structural backend call-chain questions before grep-based symbol discovery;
   - identify any existing dirty changes in touched files and work with them.
2. Serial backend contract implementation:
   - implement derived `requires_invoice` in existing settings/rules response path;
   - update PUT normalization so legacy `requires_invoice` input is ignored/recomputed;
   - preserve existing validation and read model invalidation.
3. Parallel-safe frontend work after backend response contract is stable:
   - Worker 2 can update `web/src/features/pendingInvoices/types.ts` and `api.ts`.
   - Worker 3 can update `PendingInvoiceRulesDrawer.tsx`.
   - If both workers need the same file, serialize that file.
4. Serial docs and integration:
   - update product/API docs;
   - reconcile frontend tests and mocks;
   - run focused backend/frontend verification.
5. Final review:
   - run the reviewer prompt below;
   - fix any issues;
   - rerun impacted tests;
   - report changed files, tests, and residual risk.

Expected final report:
- backend contract changes;
- frontend drawer behavior;
- docs changed;
- exact tests run and result;
- any tests not run and why;
- residual risks.
```

## Worker 1: Backend Rules Contract

```text
/goal Refactor the pending invoice rules backend contract so `requires_invoice` is derived from active bank detail auto-tag definitions while only `bank_statement_as_invoice` and `no_invoice_required` remain editable inputs.

Workspace: /Users/yu/Desktop/fin-ops-platform
Branch/worktree: main. Do not create a branch unless explicitly told.

You are not alone in the codebase. Preserve unrelated dirty work and do not revert files you did not change.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/dev/backend.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/superpowers/specs/2026-05-31-pending-invoice-derived-rules-design.md
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/services/search_pending_sql_projection.py
- tests/test_pending_invoice_api.py
- tests/test_pending_invoice_service.py
- tests/test_app_settings_service.py
- tests/test_search_pending_sql_runtime.py if SQL read-model projection behavior is touched
- tests/test_bank_auto_tag_rules_api.py

Owned write scope:
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/pending_invoice_service.py if legacy fallback/filter behavior needs updating
- backend/src/fin_ops_platform/services/search_pending_sql_projection.py if SQL read model filter/projection behavior needs updating
- tests/test_pending_invoice_api.py
- tests/test_pending_invoice_service.py if query behavior needs a characterization test
- tests/test_app_settings_service.py
- tests/test_search_pending_sql_runtime.py if SQL read-model projection behavior is updated
- tests/test_bank_auto_tag_rules_api.py only if archive/tag dictionary compatibility expectations need updating

Do not edit:
- Frontend files
- PostgreSQL migrations unless you discover an unavoidable schema requirement; this task should not need one
- Runtime queue/Redis/RabbitMQ adapters

Required behavior:
1. GET /api/pending-invoices/rules:
   - returns `bank_transaction_tags`;
   - returns `groups.requires_invoice`, `groups.bank_statement_as_invoice`, and `groups.no_invoice_required`;
   - enriches every returned group tag with `code`, `label`, `status`, `output_primary_label`, and `output_sub_label`;
   - derives `requires_invoice` from active tag universe minus the two editable groups.
2. Active tag universe:
   - supports `bank_transaction_tags.definitions` and compatible `tags`;
   - includes only `status=active`;
   - uses non-empty `code`;
   - uses `output_primary_label`, `output_sub_label`, then `label` fallback for display fields.
3. PUT /api/pending-invoices/rules:
   - accepts payload with `groups.bank_statement_as_invoice.tag_codes` and `groups.no_invoice_required.tag_codes`;
   - accepts legacy payload containing `requires_invoice` but ignores it;
   - validates only the two editable persisted groups as user input;
   - still rejects unknown or archived tags in editable groups;
   - does not reject invalid unknown/archived codes that appear only in ignored legacy `requires_invoice` input;
   - still rejects duplicates across editable groups;
   - returns recomputed `requires_invoice`.
4. Persistence:
   - continue using `AppSettingsService.update_settings`;
   - do not add a new fact source;
   - preserve audit/version behavior;
   - preserve `_invalidate_pending_invoice_read_model_scopes(reason=...)`.
   - if GET returns compatibility `pending_invoice_tag_groups`, mirror the derived `requires_invoice` in that response payload without making it an editable persisted fact.
5. Pending invoice query/read model behavior:
   - `filter=requires_invoice` remains supported;
   - it must match effective active tag codes not assigned to `bank_statement_as_invoice` or `no_invoice_required`;
   - it must not read old persisted `requires_invoice.tag_codes` as the source of truth;
   - SQL read model projection, legacy query fallback, export and filter-options must use the same complement semantics;
   - unclassified/no-effective-tag/unknown-tag/non-active-tag rows are not forced into a tag-derived requires group solely because they are not in the two editable groups.
6. Tests:
   - add a backend test proving old `requires_invoice` input is ignored and recomputed;
   - add a backend test proving duplicate editable tag mappings fail;
   - add a backend test proving derived group includes active tags not in editable groups and excludes archived tags;
   - add a backend test proving `filter=requires_invoice` follows the complement rule;
   - add AppSettingsService-level tests for version/audit/validation preservation if AppSettingsService is edited;
   - add SQL read-model projection tests if `search_pending_sql_projection.py` is edited;
   - add or update assertions for `output_primary_label` and `output_sub_label`.

Suggested verification:
```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_pending_invoice_service tests.test_app_settings_service tests.test_bank_auto_tag_rules_api -v
git diff --check
```

Expected final report:
- backend files changed;
- exact behavior of legacy `requires_invoice` input;
- tests run;
- any remaining risks.
```

## Worker 2: Frontend API Mapping

```text
/goal Update the pending invoice frontend API/type mapping so rules saving sends only the two editable groups while GET still maps the three backend groups, including derived read-only `requires_invoice` tags with primary/child display fields.

Workspace: /Users/yu/Desktop/fin-ops-platform
Branch/worktree: main. Do not create a branch unless explicitly told.

You are not alone in the codebase. Preserve unrelated dirty work and do not revert files you did not change.

Read first:
- AGENTS.md
- web/README.md
- docs/superpowers/specs/2026-05-31-pending-invoice-derived-rules-design.md
- docs/dev/pending-invoices-api.md
- web/src/features/pendingInvoices/types.ts
- web/src/features/pendingInvoices/api.ts
- web/src/test/PendingInvoicesApi.test.ts

Owned write scope:
- web/src/features/pendingInvoices/types.ts
- web/src/features/pendingInvoices/api.ts
- web/src/test/PendingInvoicesApi.test.ts

Do not edit:
- `PendingInvoiceRulesDrawer.tsx` unless the orchestrator serializes Worker 3 after you
- Backend files

Required behavior:
1. Keep frontend type support for all three groups:
   - `requiresInvoice`
   - `bankStatementAsInvoice`
   - `noInvoiceRequired`
2. Add an explicit way for UI code to know `requiresInvoice` is read-only if useful, without changing backend facts unless backend already returns such a flag.
3. `mapRulesPayload`:
   - maps group tags with `code`, `label`, `status`, `outputPrimaryLabel`, `outputSubLabel`;
   - maps `availableTags` from active `bank_transaction_tags.definitions` or compatible `tags`;
   - includes only `status=active` tags in `availableTags`; do not include future non-active statuses just because they are not `archived`.
4. `rulesRequestBody`:
   - sends only:
     - `groups.bank_statement_as_invoice.tag_codes`
     - `groups.no_invoice_required.tag_codes`
   - does not send `requires_invoice`.
5. Tests:
   - prove GET maps three groups;
   - prove derived `requiresInvoice.tags` maps hierarchy fields;
   - prove PUT body omits `requires_invoice`;
   - prove active available tags come from `bank_transaction_tags`.
   - prove a non-active, non-archived tag status is excluded from `availableTags`.

Suggested verification:
```bash
cd web && npm test -- --run PendingInvoicesApi.test.ts
git diff --check
```

Expected final report:
- frontend API/type files changed;
- PUT body shape;
- tests run.
```

## Worker 3: Frontend Rules Drawer UI

```text
/goal Replace the pending invoice rules drawer UI with a compact hierarchical rules drawer: two editable no-invoice blocks and one read-only derived requires-invoice block.

Workspace: /Users/yu/Desktop/fin-ops-platform
Branch/worktree: main. Do not create a branch unless explicitly told.

You are not alone in the codebase. Preserve unrelated dirty work and do not revert files you did not change.

Read first:
- AGENTS.md
- web/README.md
- docs/superpowers/specs/2026-05-31-pending-invoice-derived-rules-design.md
- web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx
- web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx
- web/src/features/pendingInvoices/types.ts
- web/src/pages/BankDetailsPage.tsx around existing category hierarchy helpers
- web/src/pages/PendingInvoicesPage.tsx
- web/src/test/PendingInvoicesPage.test.tsx

Owned write scope:
- web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx
- web/src/pages/PendingInvoicesPage.tsx only if refresh/save wiring needs a small adjustment
- web/src/test/PendingInvoicesPage.test.tsx
- web/src/test/apiMock.ts only for pending invoice rules mock payload

Do not edit:
- Backend files
- web/src/features/pendingInvoices/api.ts unless Worker 2 has completed and the orchestrator asks you to integrate

Required behavior:
1. Drawer layout:
   - use existing `PendingInvoiceDrawerFrame`;
   - pass a narrower width such as 560 or 600;
   - reduce vertical spacing, row height, block padding and title margins.
2. Blocks:
   - first: `流水代替发票`, editable;
   - second: `无需开票`, editable;
   - third: `需要开票`, read-only.
3. Hierarchy:
   - group tags by `outputPrimaryLabel` fallback `label`/`code`;
   - primary rows are not selectable and do not include checkbox;
   - child rows are indented;
   - if `outputSubLabel` is empty, render a same-name child row under the primary row.
4. Editable interactions:
   - child rows in the first two blocks have checkboxes;
   - selecting a tag in one editable block disables that tag in the other editable block;
   - canceling selection returns it to the read-only derived block;
   - `requiresInvoice` block has no checkbox and no click handler.
5. State:
   - maintain only the two editable tag code arrays;
   - derive read-only `requiresInvoice` display from payload available tags and the two editable sets, but replace local payload with backend response after save;
   - preserve read-only permission behavior.
6. Accessibility:
   - primary rows can be text/group headings, not buttons;
   - checkbox labels must include child tag display name and group context when useful;
   - save and close buttons keep existing labels.
7. Tests:
   - drawer shows all three blocks;
   - primary label is not a checkbox/menuitem/button;
   - no-sub-label tag is rendered as same-name child;
   - selecting in `流水代替发票` disables same tag in `无需开票`;
   - selected tag disappears from `需要开票`;
   - `需要开票` block has no checkbox;
   - save still triggers PUT and row refresh behavior.

Suggested verification:
```bash
cd web && npm test -- --run PendingInvoicesPage.test.tsx
git diff --check
```

Expected final report:
- drawer files changed;
- hierarchy/interaction behavior;
- tests run.
```

## Worker 4: Docs And Integration Verification

```text
/goal Update long-term docs and run final integration checks for the pending invoice derived-rules refactor.

Workspace: /Users/yu/Desktop/fin-ops-platform
Branch/worktree: main. Do not create a branch unless explicitly told.

You are not alone in the codebase. Preserve unrelated dirty work and do not revert files you did not change.

Read first:
- docs/superpowers/specs/2026-05-31-pending-invoice-derived-rules-design.md
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- docs/dev/api-contracts.md
- final diffs from Workers 1-3

Owned write scope:
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- docs/dev/api-contracts.md only if the implementation changes shared API contract wording
- web/src/test/apiMock.ts if final integration mock data needs alignment

Required behavior:
1. Product spec:
   - say users edit only `流水代替发票` and `无需开票`;
   - say `需要开票` is backend-derived from all active bank detail auto-tag definitions;
   - say primary labels are non-selectable and child tags are selectable.
2. API doc:
   - `GET /api/pending-invoices/rules` returns three groups;
   - `PUT /api/pending-invoices/rules` accepts/saves only two editable groups;
   - legacy `requires_invoice` input is accepted but ignored/recomputed;
   - unknown/archived/duplicate validation remains.
3. Verification:
   - run focused backend tests;
   - run focused frontend tests;
   - run `git diff --check`;
   - if frontend changes are broad, run `cd web && npm run build`.

Suggested verification:
```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_pending_invoice_service tests.test_app_settings_service tests.test_bank_auto_tag_rules_api -v
cd web && npm test -- --run PendingInvoicesApi.test.ts PendingInvoicesPage.test.tsx
git diff --check
```

Expected final report:
- docs changed;
- verification results;
- any integration mismatches found and fixed.
```

## Reviewer Prompt

```text
/goal Review the completed pending invoice derived-rules implementation for production readiness against docs/superpowers/specs/2026-05-31-pending-invoice-derived-rules-design.md. Find blocking issues before merge.

Workspace: /Users/yu/Desktop/fin-ops-platform

Read:
- AGENTS.md
- docs/superpowers/specs/2026-05-31-pending-invoice-derived-rules-design.md
- docs/product-specs/pending-invoices.md
- docs/dev/pending-invoices-api.md
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/pending_invoice_service.py
- backend/src/fin_ops_platform/services/search_pending_sql_projection.py
- web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx
- web/src/features/pendingInvoices/api.ts
- tests and frontend tests changed by implementation
- `git diff`

Review checklist:
1. Backend contract:
   - `requires_invoice` is derived, not trusted from request input.
   - PUT omits or ignores legacy `requires_invoice`.
   - Active tag universe uses all active bank detail auto-tag definitions.
   - Unknown/archived/duplicate validation remains.
   - Settings audit/version/read model invalidation remain intact.
   - `filter=requires_invoice` uses complement semantics across legacy query fallback, SQL projection, export, and filter-options; it does not read persisted `requires_invoice.tag_codes` as source of truth.
2. Architecture:
   - no new rule table/fact source;
   - no direct Redis/RabbitMQ/OA Mongo dependency;
   - no expansion of legacy snapshot paths;
   - handlers remain thin enough for the current app/server transitional architecture.
3. Frontend:
   - drawer shows exactly two editable blocks plus one read-only block;
   - primary labels are never selectable;
   - no-sub-label tags appear as same-name children;
   - mutual exclusion works;
   - save request does not send `requires_invoice`;
   - read-only users cannot save.
4. Tests:
   - backend tests cover derived `requires_invoice`, ignored legacy input, duplicate validation, and hierarchy fields;
   - frontend tests cover hierarchy, disabled duplicate selection, read-only derived block, and PUT body shape.
5. Docs:
   - product and API docs match implemented behavior.

Output:
- Findings first, ordered by severity, each with file/line reference.
- If no blocking issue remains, say `APPROVED`.
- Include any non-blocking follow-up separately.
```
