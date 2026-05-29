# 银行明细自动标签规则表格化与候选确认多任务执行 Prompt

This prompt is intended for Codex workers implementing the approved production-grade bank auto-tag rule table redesign and candidate confirmation workflow.

Workspace:

```text
/Users/yu/Desktop/fin-ops-platform
```

Primary spec:

```text
docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
```

Source files to inspect:

```text
/Users/yu/Desktop/sy/财务运营平台/银行明细标签/银行流水标签ui2.numbers
/Users/yu/Desktop/sy/财务运营平台/银行明细标签/银行流水标签ui.xlsx
```

## Orchestrator Prompt

```text
/goal Implement the production-grade 银行明细 自动标签规则 table redesign, file-backed rule replacement, multi-match candidate confirmation, and read model consistency described in docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md.

You are working in /Users/yu/Desktop/fin-ops-platform.

Read first:
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/product-specs/bank-details.md
- docs/dev/api-contracts.md
- docs/dev/backend.md
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- backend/README.md
- web/README.md
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- backend/src/fin_ops_platform/services/postgres_repositories/core.py
- backend/src/fin_ops_platform/services/audit.py
- backend/src/fin_ops_platform/postgres/migrations/
- backend/src/fin_ops_platform/app/server.py
- web/src/features/bankDetails/AutoTagRulesDrawer.tsx
- web/src/features/bankDetails/api.ts
- web/src/features/bankDetails/types.ts
- web/src/pages/BankDetailsPage.tsx
- tests/test_bank_auto_tag_rules_api.py
- tests/test_bank_transaction_category_service.py
- tests/test_bank_details_service.py
- tests/test_bank_details_sql_runtime.py
- web/src/test/AutoTagRulesDrawer.test.tsx
- web/src/test/BankDetailsApi.test.ts
- web/src/test/BankDetailsPage.test.tsx
- web/src/test/apiMock.ts

Hard requirements:
- This is not a temporary UI patch. Implement the integrated production design.
- Continue using `bank_transaction_tags` as the only auto-tag rule fact source. Do not create a parallel rule table.
- Replace current app ordinary auto-tag rules with the file rule set from `银行流水标签ui2.numbers`, validated against `银行流水标签ui.xlsx`.
- Do not make backend/server runtime depend on Apple Numbers, GUI automation, or local desktop apps. Use exported `.xlsx`, a repository fixture, or normalized JSON for executable migration; `.numbers` conversion is only a local preflight/validation step.
- Ignore `OA中的类型`; do not introduce OA type mapping in this task.
- Preserve the existing `内部往来款` system special rule. It must remain fixed first, read-only, and outside ordinary text-rule migration.
- Reuse old `code` for rules with the same primary/sub label path. File rules overwrite conditions.
- Archive file-external old ordinary rules instead of keeping them active.
- Ordinary file rules are same-level priority 2 candidate rules. Do not silently choose the first ordinary match when several match.
- Evaluate ordinary rules into 0/1/many states: unmatched, auto_matched, needs_confirmation.
- Bank detail rows with many ordinary matches must expose only the matched candidate tags for user confirmation.
- User confirmation must be a structured, audited fact. It overrides automatic results until explicitly revoked or changed.
- Manual confirmation must have a durable fact source. Do not persist it only in read models, cached payloads, or frontend state.
- PostgreSQL runtime must add a migration-backed app schema table/repository for confirmations, such as `app.bank_transaction_category_confirmations`, plus legacy snapshot parity for non-Postgres tests/runtime.
- Rules changes must not silently overwrite manual confirmations.
- Recompute historical bank details under the new rules through background read model/lifecycle refresh. Do not synchronously full-scan history inside rule save/migration requests.
- Read model is the consistency boundary for candidates, manual confirmation, effective label, status, and rule version.
- RabbitMQ may only be used through existing lifecycle/queue abstractions. Do not directly bind business logic to RabbitMQ APIs.
- Redis must not store rule facts, candidates, or manual confirmations. It may only be a short-TTL derived query cache after read model versioning.
- Do not restore the old all-tags manual classification dropdown.
- Do not convert the bank details main MUI Table to DataGrid.
- Preserve unrelated dirty work. Do not revert files you did not change.

Execution order:
1. Serial setup and baseline:
   - inspect `git status --short`;
   - read the spec and current bank auto-tag/rule/read-model code;
   - run focused existing tests if practical:
     `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_transaction_category_service tests.test_bank_details_service tests.test_bank_details_sql_runtime -v`
     and
     `cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsApi.test.ts BankDetailsPage.test.tsx`.
2. Serial contract and persistence design in code:
   - define exact backend field names for candidate codes, manual confirmation, effective code, and resolution status;
   - define the manual confirmation durable fact table/repository/snapshot shape before any feature worker starts;
   - add or plan the PostgreSQL migration file for confirmation facts and read-model columns before workers depend on those fields;
   - inspect existing category provider/read model paths so the implementation extends current boundaries instead of creating parallel paths;
   - inspect `bank_transaction_auto_category_service.py`; it is the current evaluator and must be updated rather than bypassed;
   - decide whether rule-file migration is a backend service method, management route, script, or testable fixture loader, then keep that choice documented and test-covered.
3. Serial backend foundation:
   - complete Worker 1 and Worker 2 changes around parser, evaluator, confirmation persistence, server routes, and backend tests first because they share core backend files;
   - then complete Worker 3 read-model/migration integration against the finalized backend contract.
4. Parallel-safe frontend/docs after backend contract is stable:
   - Worker 4: AutoTagRulesDrawer table UI and bank detail candidate confirmation UI;
   - Worker 5: frontend API mapping, mocks, and tests;
   - Worker 6: docs and operations/dev notes.
   Coordinate Worker 4 and Worker 5 around `types.ts`, `api.ts`, `apiMock.ts`, and shared tests. If both need the same file, serialize those edits.
5. Serial integration:
   - reconcile shared backend files, especially `server.py`, `bank_transaction_category_service.py`, `bank_details_service.py`, and read model repositories;
   - ensure file parser service and API payloads use the same field names;
   - ensure candidate confirmation updates read model dirty scopes and UI refresh behavior;
   - ensure archived old rules do not remain active;
   - ensure pending-invoice/no-OA references to archived codes are cleaned or blocked consistently with existing policy.
6. Verification:
   - `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_transaction_category_service tests.test_bank_transaction_auto_category_service tests.test_bank_details_service tests.test_bank_details_sql_runtime tests.test_app_settings_service tests.test_pending_invoice_service tests.test_no_oa_bank_batch_tag_selection_api tests.test_no_oa_bank_batch_api -v` if those modules exist; omit only nonexistent test files and state so.
   - `cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsApi.test.ts BankDetailsPage.test.tsx NoOaBankBatchApi.test.ts PendingInvoicesApi.test.ts`.
   - `cd web && npm run build`.
   - `git diff --check`.
   - If a dev server is practical, visually inspect the widened drawer and candidate confirmation UI in browser.

Expected final report:
- changed files;
- migration/file parser behavior;
- exact backend fields added;
- how old rules are archived and code reuse works;
- how multi-match candidate confirmation is persisted and audited;
- read model/dirty scope behavior;
- exact tests run and results;
- residual risks.
```

## Worker 1: Rule File Parser And Replacement Service

```text
/goal Implement a testable parser and replacement path that converts `银行流水标签ui2.numbers` / `银行流水标签ui.xlsx` into the bank auto-tag rule model, replacing current ordinary app rules while preserving code identity where possible.

Owned files:
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py only if existing settings persistence needs a small extension
- tests/test_bank_transaction_category_service.py
- tests/test_bank_auto_tag_rules_api.py
- fixture/helper files only if the repository already has a suitable fixture location
- docs/dev/api-contracts.md only for parser/contract wording if Worker 6 is not active

Read:
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- docs/product-specs/bank-details.md
- docs/dev/api-contracts.md
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- tests/test_bank_transaction_category_service.py
- tests/test_bank_auto_tag_rules_api.py

Requirements:
- Keep `bank_transaction_tags` as the only rule fact source.
- Provide a deterministic parser/normalizer for the file columns:
  - 流水类型;
  - 主标签;
  - 子标签;
  - 选择查询的项（可全选/清空） / 选择查询的项;
  - 包含;
  - 必须同时包含;
  - 精准命重 / 精准命中;
  - 不包含字样;
  - 优先级.
- Ignore `OA中的类型`.
- Do not require Apple Numbers or GUI automation in backend tests/runtime. If `.numbers` must be compared, treat conversion as a local preflight step and feed the parser exported `.xlsx` or normalized fixture data.
- Treat source header `精准命重` as a file typo alias. Parser accepts both `精准命重` and canonical `精准命中`; UI/docs/tests display `精准命中`.
- Treat `内部往来款` as a system display row only. Do not include it in ordinary active rules.
- Map fields exactly:
  - `用途/交易用途、摘要、备注/附言/客户附言` -> `purpose_text`, `summary_text`, `note_text`, `detail_text`;
  - `对方户` -> `counterparty_name`.
- Unknown field descriptions must fail validation.
- Split condition cells on newlines and common Chinese punctuation where appropriate; trim, de-duplicate, and drop empty values.
- Convert:
  - 包含 -> `contains_any`;
  - 必须同时包含 -> `contains_all`;
  - 精准命重 / 精准命中 -> `exact_any`;
  - 不包含字样 -> `none_of`.
- Require active ordinary file rules to have a non-empty primary label, a query field mapping, and at least one positive condition.
- Reuse existing rule `code` when the existing active or archived rule has the same `output_primary_label` + `output_sub_label`.
- Generate stable backend custom codes for file rules without a reusable code.
- Move file-external old ordinary rules to archived, preserving code and audit trace.
- Preserve current API response shape for active/archived rules unless the orchestrator defines explicit additive fields.
- Write tests for parsing, code reuse, code generation, archive behavior, invalid field descriptions, and validation failures.
- Return changed files and tests run.
```

## Worker 2: Candidate Evaluation, Confirmation Persistence, And Manual Confirmation APIs

```text
/goal Extend the real bank transaction auto-category evaluator so ordinary rules produce candidate states, add durable confirmation persistence, and add audited APIs for confirming or revoking a candidate category on a bank transaction.

Owned files:
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/core.py or a new focused repository file if that matches local patterns better
- backend/src/fin_ops_platform/postgres/migrations/<next>_bank_transaction_category_confirmations.sql
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/audit.py only if existing audit helper cannot record required metadata
- tests/test_bank_transaction_category_service.py
- tests/test_bank_transaction_auto_category_service.py
- tests/test_bank_details_service.py
- tests/test_bank_auto_tag_rules_api.py
- tests/test_postgres_migrations.py or repository migration tests if schema checks live elsewhere

Read:
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- backend/src/fin_ops_platform/services/bank_transaction_category_service.py
- backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/core.py
- backend/src/fin_ops_platform/app/server.py
- tests/test_bank_transaction_category_service.py
- tests/test_bank_transaction_auto_category_service.py
- tests/test_bank_details_service.py

Requirements:
- Update `bank_transaction_auto_category_service.py`; do not create a parallel evaluator that leaves first-match behavior in the real path.
- Preserve internal transfer special-rule priority. If internal transfer matches, effective category is internal transfer and ordinary candidates do not override it.
- Evaluate ordinary active file rules in parallel for each transaction:
  - 0 matches -> `category_resolution_status=unmatched`;
  - 1 match -> `category_resolution_status=auto_matched`, `auto_category_code=<match>`;
  - many matches -> `category_resolution_status=needs_confirmation`, `auto_candidate_category_codes=[...]`, `auto_category_code=null`.
- Preserve stable order of candidates using file/rule display order.
- Add a structured manual confirmation fact. It must be durable outside read models.
- PostgreSQL runtime should use an app schema fact table such as `app.bank_transaction_category_confirmations` with one active confirmation per transaction, candidate codes, selected code, rule version, actor/time, revoke fields, version, and raw payload.
- Add the required migration file and repository methods.
- Non-Postgres/local snapshot runtime must have equivalent snapshot persistence so tests and rollback observation do not lose confirmations.
- Read model rows project confirmation facts, but read model rows are not the confirmation source of truth.
- Add confirmation endpoint, for example:
  `POST /api/bank-details/transactions/{transaction_id}/category-confirmation`.
- Add revoke endpoint, for example:
  `DELETE /api/bank-details/transactions/{transaction_id}/category-confirmation`.
- Confirmation endpoint accepts only `category_code`.
- Backend must reject a category code that is not in the current candidate list with a 400 error.
- "Current candidate list" means candidates recomputed for that single transaction from the latest rule version and source transaction facts. Do not validate confirmation solely against a stale read model row.
- If the read model is stale but the selected code is still in the latest recomputed candidate set, accept and record the latest rule version; if not, return a conflict/validation error that tells the user to refresh.
- Confirmation must require write permission; read/export users receive 403.
- Confirmation writes audit metadata: transaction id, rule version, candidate codes, selected code, actor, timestamp.
- Revoke writes audit metadata and returns the row to automatic/candidate state.
- Manual confirmation must override automatic results until explicitly revoked or changed.
- Rule changes must not silently overwrite manual confirmations.
- Trigger derived data dirty/lifecycle events after confirm/revoke.
- Add tests for 0/1/many matches, internal transfer priority, confirm candidate, reject non-candidate, stale read-model confirmation validation against latest rules, revoke, permission denial, audit, migration/repository persistence, and dirty event.
- Return changed files and tests run.
```

## Worker 3: Read Model, Source Versions, Dirty Scopes, Cache Boundaries

```text
/goal Make bank detail read models carry candidate categories, manual confirmation, final effective category, resolution status, and rule version, with correct dirty-scope behavior and no business facts in Redis.

Owned files:
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- backend/src/fin_ops_platform/postgres/migrations/<next>_bank_detail_candidates_and_confirmation_projection.sql if read model columns require schema changes
- backend/src/fin_ops_platform/services/postgres_repositories/runtime_queue.py only if an event list must include an existing refresh type
- backend/src/fin_ops_platform/services/bank_detail_read_model_builder.py or equivalent builder file if present
- tests/test_bank_details_sql_runtime.py
- tests/test_bank_details_service.py
- tests/test_app_settings_service.py only if source version expectations live there
- docs/dev/backend.md only if Worker 6 is not active

Read:
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- docs/dev/backend.md
- backend/src/fin_ops_platform/services/bank_details_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- backend/src/fin_ops_platform/services/postgres_repositories/runtime_queue.py
- tests/test_bank_details_sql_runtime.py
- tests/test_bank_details_service.py

Requirements:
- Read model rows must include enough data to render:
  - auto single match;
  - multi-match candidates;
  - manual confirmation;
  - final effective code;
  - resolution status;
  - rule version/source version.
- Read model rows project manual confirmation facts from the durable confirmation store. Do not make read model rows the source of truth for confirmations.
- API hot paths must not perform full historical auto-category scans to answer list pages.
- Confirmation APIs are the exception to read-model-only validation: they must recompute a single transaction's latest candidates from source facts/latest rules before accepting a selected candidate.
- Rule replacement/save publishes `bank_auto_tag_rules_changed` with scope `all` or equivalent month-sharded dirty scopes.
- Manual confirm/revoke marks the affected bank-detail scope and downstream scopes dirty.
- Refreshing/stale/schema_mismatch states return the last usable projection and do not clear account or transaction lists.
- Existing lifecycle/queue abstraction may use RabbitMQ in production, but business code must not call RabbitMQ directly.
- Redis, if present, may only cache derived query results keyed by read model/source version. Do not store rules, candidates, or confirmations in Redis.
- Add tests that source versions include the bank auto-tag rule version, dirty scopes are marked on rule change/confirm/revoke, stale refresh behavior preserves last projection, and stale read model rows are not trusted as final confirmation validation.
- Return changed files and tests run.
```

## Worker 4: AutoTagRulesDrawer Table UI And Bank Detail Candidate UI

```text
/goal Replace the current card-based `自动标签规则` drawer with a widened table-form rule editor, and add bank detail row UI for candidate confirmation without restoring all-tags manual classification.

Owned files:
- web/src/features/bankDetails/AutoTagRulesDrawer.tsx
- web/src/pages/BankDetailsPage.tsx
- web/src/app/styles.css only if small scoped style adjustments are unavoidable
- web/src/features/bankDetails/BankCategoryTag.tsx only if the tag component must display resolution states
- web/src/test/AutoTagRulesDrawer.test.tsx
- web/src/test/BankDetailsPage.test.tsx

Read:
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- web/src/features/bankDetails/AutoTagRulesDrawer.tsx
- web/src/pages/BankDetailsPage.tsx
- web/src/features/bankDetails/BankCategoryTag.tsx
- web/src/test/AutoTagRulesDrawer.test.tsx
- web/src/test/BankDetailsPage.test.tsx

Requirements:
- Keep the `自动标签规则` button on the bank details page.
- Keep a right-side drawer, but widen desktop paper to an effective rule workspace, such as `min(1280px, 92vw)` or equivalent.
- Mobile remains full width.
- Replace the card/accordion-like rule editor with a table-form editor.
- Table columns:
  - 流水类型;
  - 主标签;
  - 子标签;
  - 选择查询的项;
  - 包含;
  - 必须同时包含;
  - 精准命中;
  - 不包含字样;
  - 优先级;
  - 操作.
- Do not render `OA中的类型`.
- `内部往来款` appears as first read-only system row.
- Ordinary rows show priority `2` / same-level candidate semantics.
- Use sticky table header and fixed save/action bar.
- Avoid horizontal scrolling for the main columns on normal desktop. Use wrapping, compact cell summaries, and editor popovers/dialogs instead.
- Condition cells show up to 3-5 terms and `共 N 项` for larger lists.
- Clicking a condition cell opens an editor where terms are maintained one per line.
- Main/sub labels are editable.
- Query fields are editable through a semantic-field multi-select, displayed with file-friendly labels.
- Active/archived rules remain reachable in the same drawer.
- Save submits complete active/archived rules and expected version.
- Read-only users can view but cannot edit/save.
- Bank detail category cell states:
  - unmatched -> `-`;
  - auto_matched -> tag label;
  - needs_confirmation -> `待确认` action showing only candidate labels;
  - manually_confirmed -> confirmed tag with a confirmation marker and revoke/change action.
- Candidate confirmation UI must never offer all labels.
- Add/update tests for table columns, no OA type, widened drawer class/sx, condensed condition terms, term editor, read-only behavior, candidate-only selection, confirm and revoke controls.
- Return changed files and tests run.
```

## Worker 5: Frontend API Mapping, Mocks, And Tests

```text
/goal Update bank details frontend API types, serialization, mocks, and tests for rule table editing plus candidate confirmation states and endpoints.

Owned files:
- web/src/features/bankDetails/types.ts
- web/src/features/bankDetails/api.ts
- web/src/test/apiMock.ts
- web/src/test/BankDetailsApi.test.ts
- web/src/test/AutoTagRulesDrawer.test.tsx
- web/src/test/BankDetailsPage.test.tsx

Read:
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- web/src/features/bankDetails/types.ts
- web/src/features/bankDetails/api.ts
- web/src/test/apiMock.ts
- web/src/test/BankDetailsApi.test.ts

Requirements:
- Add frontend types for:
  - `categoryResolutionStatus`;
  - `autoCandidateCategoryCodes` or richer candidate objects;
  - `manualConfirmedCategoryCode`;
  - current rule version/status if returned.
- Map backend snake_case fields explicitly.
- Add API helpers for confirmation and revoke endpoints.
- Keep save auto-tag rules payload compatible with existing `active_rules`, `archived_rules`, and `expected_version`.
- Update mocks to produce rows for unmatched, auto matched, needs confirmation, and manually confirmed cases.
- Add tests for API mapping and endpoint payloads.
- Ensure error messages for invalid candidate, permission denial, version conflict, and validation remain user-readable.
- Return changed files and tests run.
```

## Worker 6: Product, API, And Operations Documentation

```text
/goal Update long-lived documentation so the new bank auto-tag table rules, candidate confirmation, read model consistency, and migration behavior are the source of truth.

Owned files:
- docs/product-specs/bank-details.md
- docs/dev/api-contracts.md
- docs/dev/backend.md if read model/source version guidance changes
- docs/operations/ only if a manual migration/rebuild runbook is introduced

Read:
- docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md
- docs/product-specs/bank-details.md
- docs/dev/api-contracts.md
- docs/dev/backend.md

Requirements:
- Update bank details product spec:
  - rule table drawer;
  - file-backed replacement;
  - internal transfer special rule;
  - ordinary rule candidate semantics;
  - user confirmation from candidates only;
  - manual confirmation priority and revoke behavior;
  - no all-tags manual classification.
- Update API contracts:
  - transaction row candidate/status fields;
  - confirmation endpoint;
  - revoke endpoint;
  - auto-tag rule table fields if the response shape changes.
- Update backend/read model docs:
  - read model carries candidates, confirmation, effective category, rule version;
  - RabbitMQ through lifecycle abstraction only;
  - Redis cache boundary and invalidation;
  - no request-thread historical full scan.
- If implementation creates a migration command or script, document exact command, expected output, rollback/check behavior, and verification.
- Keep documentation in Chinese, matching repository convention.
- Return changed files.
```

## Serial Integration Prompt

```text
/goal Integrate all bank auto-tag table redesign work into one coherent implementation, resolving shared-file conflicts and proving the production behavior end to end.

You are working in /Users/yu/Desktop/fin-ops-platform.

Before editing:
- inspect `git status --short`;
- read docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md;
- inspect all worker outputs if this is a multi-agent run.

Integration checklist:
- There is one rule fact source: `bank_transaction_tags`.
- `银行流水标签ui2.numbers` and `银行流水标签ui.xlsx` comparison is deterministic and test-covered.
- Runtime migration does not depend on Apple Numbers or GUI automation.
- `OA中的类型` is ignored.
- Source header typo `精准命重` is accepted as an alias, while UI/docs use `精准命中`.
- `内部往来款` remains system-only and fixed first.
- File rules replace ordinary app rules.
- Same primary/sub label paths reuse old code.
- File-external old rules are archived, not active.
- Ordinary rules produce 0/1/many candidate states.
- Multi-match rows expose candidates only.
- Candidate confirmation rejects non-candidate code.
- Candidate confirmation validates against latest single-row recomputation, not stale read model candidates.
- Confirmation and revoke are audited and permission-checked.
- Manual confirmation facts are durable in app schema/snapshot storage and only projected into read models.
- Manual confirmation wins over automatic rules until revoked/changed.
- Rule changes do not erase manual confirmations.
- Read model rows carry candidate, manual, effective, status, and rule version fields.
- Rules/confirm/revoke mark dirty scopes and downstream refreshes.
- Refreshing/stale read model states do not clear existing lists.
- Redis/RabbitMQ boundaries comply with the spec.
- AutoTagRulesDrawer is table-form, widened, and does not show OA type.
- BankDetailsPage does not expose an all-label manual classification picker.
- Frontend mocks and tests cover all row states.
- Long-lived docs are updated.

Verification commands:
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_transaction_category_service tests.test_bank_transaction_auto_category_service tests.test_bank_details_service tests.test_bank_details_sql_runtime tests.test_app_settings_service tests.test_pending_invoice_service tests.test_no_oa_bank_batch_tag_selection_api tests.test_no_oa_bank_batch_api tests.test_postgres_migrations -v`
- `cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsApi.test.ts BankDetailsPage.test.tsx NoOaBankBatchApi.test.ts PendingInvoicesApi.test.ts`
- `cd web && npm run build`
- `git diff --check`

Browser/manual verification if practical:
- start the app using documented commands;
- open bank details page;
- verify the `自动标签规则` drawer is widened and table-form;
- verify condition cell editor behavior;
- verify a multi-candidate row only offers matched candidate labels;
- verify confirm/revoke updates the row state without offering all labels.

Final report:
- changed files grouped by backend/frontend/docs/tests;
- exact tests run and pass/fail results;
- any skipped tests and why;
- migration command or path used;
- residual risk list.
```
