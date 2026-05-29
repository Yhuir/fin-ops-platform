# 银行明细自动标签规则表格化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the production-grade bank auto-tag table drawer, file-backed rule replacement, multi-match candidate confirmation, durable manual confirmation, and read model consistency.

**Architecture:** Keep `bank_transaction_tags` as the only rule fact source and update the real auto-category evaluator to return 0/1/many candidate states. Store manual confirmations in durable app-schema/snapshot facts, project them into bank detail read models, and expose candidate-only confirmation through bank details APIs and UI.

**Tech Stack:** Python backend with custom HTTP server and PostgreSQL migrations/repositories; React + TypeScript + MUI frontend; unittest and Vitest test suites.

---

## File Structure

Backend rule parsing and replacement:

- Modify `backend/src/fin_ops_platform/services/bank_transaction_category_service.py` for file-rule normalization/replacement, code reuse, archived old rules, and validation.
- Modify `tests/test_bank_transaction_category_service.py` and `tests/test_bank_auto_tag_rules_api.py`.
- Create a small fixture or normalized test helper only if needed under an existing fixture/test path.

Backend evaluator and confirmation:

- Modify `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py` to produce candidate states instead of first ordinary match.
- Modify `backend/src/fin_ops_platform/services/bank_transaction_effective_category_provider.py` so final category resolution can consume candidate/confirmation state consistently.
- Modify or add repository code in `backend/src/fin_ops_platform/services/postgres_repositories/core.py` or a focused repository module for confirmation facts.
- Add migration `backend/src/fin_ops_platform/postgres/migrations/0041_bank_transaction_category_confirmations.sql` unless the current max migration changes before implementation.
- Modify `backend/src/fin_ops_platform/services/state_store_protocol.py`, `backend/src/fin_ops_platform/services/state_store.py`, `backend/src/fin_ops_platform/services/postgres_state_store.py`, and relevant dual/shadow store wiring for legacy/local confirmation persistence.
- Modify `backend/src/fin_ops_platform/app/server.py` for confirm/revoke routes.
- Modify `backend/src/fin_ops_platform/services/bank_details_service.py` for row payloads and dirty-scope integration.
- Modify tests: `tests/test_bank_transaction_auto_category_service.py`, `tests/test_bank_details_service.py`, `tests/test_bank_details_sql_runtime.py`, `tests/test_workbench_v2_api.py`, `tests/test_postgres_migrations.py`, and state-store contract tests.

Read model:

- Modify `backend/src/fin_ops_platform/services/bank_detail_sql_projection.py`.
- Modify `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`.
- Add migration `backend/src/fin_ops_platform/postgres/migrations/0042_bank_detail_candidate_projection.sql` if read model columns are separated from confirmation migration.
- Update source version expectations in `tests/test_bank_details_sql_runtime.py` and related backend tests.

Frontend:

- Modify `web/src/features/bankDetails/types.ts` and `web/src/features/bankDetails/api.ts` for candidate/status/confirm APIs.
- Modify `web/src/features/bankDetails/AutoTagRulesDrawer.tsx` to become the widened table-form editor.
- Modify `web/src/pages/BankDetailsPage.tsx` for category state rendering and candidate-only confirmation UI.
- Modify `web/src/features/bankDetails/BankCategoryTag.tsx` only if display state belongs in the shared tag component.
- Modify `web/src/test/apiMock.ts`, `web/src/test/BankDetailsApi.test.ts`, `web/src/test/AutoTagRulesDrawer.test.tsx`, and `web/src/test/BankDetailsPage.test.tsx`.

Docs:

- Modify `docs/product-specs/bank-details.md`.
- Modify `docs/dev/api-contracts.md`.
- Modify `docs/dev/backend.md` if read model/source-version guidance changes.
- Modify `docs/operations/` only if a manual migration/rebuild command is introduced.

## Task 1: Baseline And Contract Check

**Files:**
- Read: `docs/superpowers/specs/2026-05-29-bank-auto-tag-rules-table-redesign.md`
- Read: `docs/superpowers/prompts/2026-05-29-bank-auto-tag-rules-table-redesign-execution.md`
- Read: all backend/frontend files listed above

- [ ] **Step 1: Check worktree**

Run:

```bash
git status --short
```

Expected: only intentional plan/document changes before code edits.

- [ ] **Step 2: Run baseline backend tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_transaction_category_service tests.test_bank_transaction_auto_category_service tests.test_bank_details_service tests.test_bank_details_sql_runtime -v
```

Expected: PASS, or record existing failures before editing.

- [ ] **Step 3: Run baseline frontend tests**

Run:

```bash
cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsApi.test.ts BankDetailsPage.test.tsx
```

Expected: PASS, or record existing failures before editing.

- [ ] **Step 4: Confirm real evaluator and persistence boundaries**

Inspect:

```bash
rg -n "suggest_for_rows|_text_suggestion|_rule_match" backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py
rg -n "bank_transaction_categories|save_bank_transaction_categories|load_bank_transaction_categories" backend/src/fin_ops_platform/services backend/src/fin_ops_platform/postgres/migrations
```

Expected: implementation extends `bank_transaction_auto_category_service.py`, not a parallel evaluator.

## Task 2: Rule File Parser And Replacement

**Files:**
- Modify: `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Create: `fixtures/bank_auto_tag_rules/bank_flow_tag_rules_ui2.normalized.json`
- Create: `backend/src/fin_ops_platform/tools/normalize_bank_auto_tag_rules_file.py` only if a reusable command is chosen over a pure service method
- Test: `tests/test_bank_transaction_category_service.py`
- Test: `tests/test_bank_auto_tag_rules_api.py`
- Test: `tests/test_app_settings_service.py`

- [ ] **Step 1: Write parser tests**

Add tests proving:

- normalized fixture `fixtures/bank_auto_tag_rules/bank_flow_tag_rules_ui2.normalized.json` can be parsed into the expected rule count;
- parser can also consume worksheet-like rows produced from exported `.xlsx`;
- comparison between normalized `ui2` rules and `银行流水标签ui.xlsx`-style rows ignores only known header/OA-type differences and fails with a structured diff for rule-content differences;
- source header `精准命重` and canonical `精准命中` both map to `exact_any`;
- `OA中的类型` is ignored;
- `用途/交易用途、摘要、备注/附言/客户附言` maps to `purpose_text`, `summary_text`, `note_text`, `detail_text`;
- `对方户` maps to `counterparty_name`;
- unknown field descriptions fail;
- `内部往来款` is skipped as ordinary rule;
- same primary/sub label path reuses an existing code;
- file-external old rules are archived.
- replacement audit metadata includes source file name/hash or fixture version, reused codes, added codes, archived codes, and field mapping version.

- [ ] **Step 2: Run parser tests and verify failure**

Run focused tests, for example:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service tests.test_bank_auto_tag_rules_api -v
```

Expected: new tests fail before implementation.

- [ ] **Step 3: Implement parser and replacement service**

Implement small, explicit functions:

- canonical executable source path: `fixtures/bank_auto_tag_rules/bank_flow_tag_rules_ui2.normalized.json`;
- parser entry point: a service function that accepts normalized rows/JSON and returns validated active ordinary rules plus archive decisions;
- optional tool entry point: `backend/src/fin_ops_platform/tools/normalize_bank_auto_tag_rules_file.py` for local conversion/preflight, never used by backend runtime;
- normalize worksheet rows from exported `.xlsx` or normalized row arrays;
- parse condition terms by newlines and common Chinese punctuation;
- map source columns to rule fields;
- produce active ordinary rules and archived old rules;
- reuse code by `(output_primary_label, output_sub_label)`;
- generate backend custom codes for new rules;
- keep `account_scope={"type":"any","values":[]}` and `regex_any=[]`;
- do not require Apple Numbers at runtime.
- return structured comparison errors with row/column/field details when `ui2` and `.xlsx` content diverge beyond approved differences.

- [ ] **Step 4: Run rule parser/replacement tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service tests.test_bank_auto_tag_rules_api -v
```

Expected: PASS.

## Task 2B: Archived Rule Downstream Reference Handling

**Files:**
- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Modify: `backend/src/fin_ops_platform/services/pending_invoice_service.py` only if display/query code needs explicit archived-code handling
- Modify: `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py` only if no-OA selected tag scopes need explicit cleanup hooks
- Test: `tests/test_app_settings_service.py`
- Test: `tests/test_pending_invoice_service.py`
- Test: `tests/test_no_oa_bank_batch_tag_selection_api.py`

- [ ] **Step 1: Write downstream-reference tests**

Add tests proving file-external archived codes are handled consistently:

- if an archived code is referenced by `pending_invoice_tag_groups`, replacement either removes it atomically or fails with a clear validation error;
- if an archived code is included in no-OA selected tag scope, replacement removes it from the selected scope and writes audit metadata;
- active file rules remain available to pending invoice/no-OA displays by stable code;
- stale archived codes are not presented as selectable active no-OA tags.

- [ ] **Step 2: Run downstream-reference tests and verify failure**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_pending_invoice_service tests.test_no_oa_bank_batch_tag_selection_api -v
```

Expected: new tests fail.

- [ ] **Step 3: Implement cleanup/blocking behavior**

Implement one explicit policy:

- preferred: file-rule replacement atomically removes newly archived codes from pending-invoice groups and no-OA selected tag scope, records removed references in audit metadata, and increments affected versions;
- fallback only if cleanup cannot be made safe: replacement fails before saving and returns exact reference locations.

- [ ] **Step 4: Run downstream-reference tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_pending_invoice_service tests.test_no_oa_bank_batch_tag_selection_api -v
```

Expected: PASS.

## Task 3: Candidate Evaluator

**Files:**
- Modify: `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py`
- Test: `tests/test_bank_transaction_auto_category_service.py`
- Possibly modify: `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`

- [ ] **Step 1: Write evaluator tests**

Add tests for:

- no ordinary match -> `category_resolution_status="unmatched"`;
- one ordinary match -> `auto_matched` and `auto_category_code`;
- multiple ordinary matches -> `needs_confirmation`, `auto_candidate_category_codes`, no `auto_category_code`;
- internal transfer suggestion still wins before ordinary candidates;
- candidate order follows rule/file order.

- [ ] **Step 2: Run evaluator tests and verify failure**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_auto_category_service -v
```

Expected: new candidate tests fail.

- [ ] **Step 3: Update evaluator**

Change `BankTransactionAutoCategoryService` so ordinary text rules are evaluated as a set after internal transfer detection:

- collect all matching active ordinary rules;
- return status metadata for 0/1/many;
- include candidate code list and evidence;
- preserve existing callers by retaining old fields where needed for single-match compatibility.

- [ ] **Step 4: Run evaluator tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_auto_category_service -v
```

Expected: PASS.

## Task 4: Durable Manual Confirmation And APIs

**Files:**
- Create: `backend/src/fin_ops_platform/postgres/migrations/0041_bank_transaction_category_confirmations.sql`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/core.py` or create a focused confirmation repository
- Modify: `backend/src/fin_ops_platform/services/state_store_protocol.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Modify: `backend/src/fin_ops_platform/services/dual_state_store.py` and `backend/src/fin_ops_platform/services/shadow_state_store.py` only if their protocol forwarding needs explicit methods
- Modify: `backend/src/fin_ops_platform/services/bank_details_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_postgres_migrations.py`
- Test: `tests/test_bank_details_service.py`
- Test: `tests/test_workbench_v2_api.py`
- Test: `tests/test_state_store_contract.py`
- Test: `tests/test_state_store.py`
- Test: `tests/test_postgres_state_store.py`

- [ ] **Step 1: Write persistence and API tests**

Add tests for:

- migration creates `app.bank_transaction_category_confirmations`;
- only one active confirmation per transaction;
- confirmation persists selected code, candidate codes, rule version, actor/time;
- non-Postgres snapshot persistence round-trips confirmations through `StateStoreProtocol`, `StateStore`, `PostgresStateStore`, and dual/shadow forwarding where applicable;
- POST confirm rejects non-candidate code;
- POST confirm recomputes candidates from latest rules, not stale read model;
- DELETE revoke clears active confirmation;
- permission denial returns 403;
- HTTP routes parse JSON, map errors, and enforce permissions in `tests/test_workbench_v2_api.py`;
- audit events are written.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_bank_details_service tests.test_workbench_v2_api tests.test_state_store_contract tests.test_state_store tests.test_postgres_state_store -v
```

Expected: new tests fail.

- [ ] **Step 3: Add migration and repository**

Implement:

- `app.bank_transaction_category_confirmations`;
- unique partial index for one active confirmation per tenant/transaction;
- repository methods to upsert active confirmation, revoke confirmation, get by transaction ids;
- grants consistent with nearby migrations.

- [ ] **Step 4: Add service and server routes**

Implement routes:

- `POST /api/bank-details/transactions/{transaction_id}/category-confirmation`;
- `DELETE /api/bank-details/transactions/{transaction_id}/category-confirmation`.

Server behavior:

- resolve actor/permissions using existing patterns;
- load source transaction facts;
- recompute latest candidates for that single transaction;
- accept only selected code in latest candidates;
- write confirmation fact and audit;
- mark dirty scopes/downstream refreshes.

- [ ] **Step 5: Run confirmation tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_bank_details_service tests.test_workbench_v2_api tests.test_state_store_contract tests.test_state_store tests.test_postgres_state_store tests.test_bank_transaction_auto_category_service -v
```

Expected: PASS.

## Task 5: Bank Detail Read Model Projection

**Files:**
- Modify: `backend/src/fin_ops_platform/services/bank_details_service.py`
- Modify: `backend/src/fin_ops_platform/services/bank_detail_sql_projection.py`
- Modify: `backend/src/fin_ops_platform/services/bank_transaction_effective_category_provider.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Create or modify migration for read model projection columns
- Test: `tests/test_bank_details_sql_runtime.py`
- Test: `tests/test_bank_details_service.py`

- [ ] **Step 1: Write projection tests**

Tests must prove:

- row payload includes `auto_candidate_category_codes`, `manual_confirmed_category_code`, `effective_category_code`, `category_resolution_status`, and `category_rule_version`;
- SQL projection builder loads confirmation facts and candidate suggestions when rebuilding read_model.bank_detail_rows;
- effective category provider resolves `manual_confirmed > internal_transfer > single_auto_match > null`;
- manual confirmation wins over auto result;
- multi-candidate unconfirmed rows are not treated as effective classified rows;
- source versions include auto-tag rule version;
- rule change, confirm, and revoke mark dirty scopes;
- stale read model returns last projection and does not clear rows.

- [ ] **Step 2: Run projection tests and verify failure**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_details_sql_runtime -v
```

Expected: new tests fail.

- [ ] **Step 3: Add projection fields and mapping**

Implement read model schema/repository changes and service mapping:

- project candidate codes and confirmation fields;
- derive `effective_*` fields from `manual_confirmed > internal_transfer > single_auto_match > null`;
- preserve existing category aliases for downstream compatibility;
- do not use Redis or read model as confirmation fact source.

- [ ] **Step 4: Run read model tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_details_sql_runtime -v
```

Expected: PASS.

## Task 6: Frontend API Mapping

**Files:**
- Modify: `web/src/features/bankDetails/types.ts`
- Modify: `web/src/features/bankDetails/api.ts`
- Modify: `web/src/test/apiMock.ts`
- Test: `web/src/test/BankDetailsApi.test.ts`

- [ ] **Step 1: Write frontend API tests**

Add tests for mapping:

- `category_resolution_status`;
- candidate tag objects/codes and labels;
- manual confirmation code;
- confirm API payload;
- revoke API call;
- error mapping for invalid candidate and permission denial.

- [ ] **Step 2: Run frontend API tests and verify failure**

Run:

```bash
cd web && npm test -- --run BankDetailsApi.test.ts
```

Expected: new tests fail.

- [ ] **Step 3: Implement API mappings**

Implement explicit snake_case to camelCase mapping and helpers:

- `confirmBankDetailCategory(transactionId, categoryCode)`;
- `revokeBankDetailCategoryConfirmation(transactionId)`;
- row status/candidate fields.

- [ ] **Step 4: Run frontend API tests**

Run:

```bash
cd web && npm test -- --run BankDetailsApi.test.ts
```

Expected: PASS.

## Task 7: Table Drawer UI And Candidate Confirmation UI

**Files:**
- Modify: `web/src/features/bankDetails/AutoTagRulesDrawer.tsx`
- Modify: `web/src/pages/BankDetailsPage.tsx`
- Modify: `web/src/features/bankDetails/BankCategoryTag.tsx` only if needed
- Modify: `web/src/test/AutoTagRulesDrawer.test.tsx`
- Modify: `web/src/test/BankDetailsPage.test.tsx`

- [ ] **Step 1: Write UI tests**

Tests must cover:

- drawer paper widened to near full workspace;
- table columns render: `流水类型`, `主标签`, `子标签`, `选择查询的项`, `包含`, `必须同时包含`, `精准命中`, `不包含字样`, `优先级`, `操作`;
- no `OA中的类型`;
- internal transfer first row is read-only;
- condition cells collapse long term lists with `共 N 项`;
- condition editor accepts one term per line;
- save submits full active/archived rules;
- bank details rows render `-`, auto tag, `待确认`, and manual confirmation state;
- candidate picker offers only matched candidates;
- revoke action calls the revoke API.

- [ ] **Step 2: Run UI tests and verify failure**

Run:

```bash
cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsPage.test.tsx
```

Expected: new tests fail.

- [ ] **Step 3: Implement table drawer**

Refactor `AutoTagRulesDrawer`:

- keep existing load/save contract;
- replace card editors with MUI table layout;
- use sticky header and fixed action bar;
- set desktop drawer width to `min(1280px, 92vw)` or equivalent;
- implement term summary/editor component;
- keep active/archived toggle;
- keep read-only mode.

- [ ] **Step 4: Implement candidate confirmation UI**

Update `BankDetailsPage`:

- render category state from API status;
- show candidate-only menu/popover for `needs_confirmation`;
- call confirm/revoke APIs;
- refresh current list/row after mutation;
- never expose all-tag manual selection.

- [ ] **Step 5: Run UI tests**

Run:

```bash
cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsPage.test.tsx
```

Expected: PASS.

## Task 8: Documentation And Final Verification

**Files:**
- Modify: `docs/product-specs/bank-details.md`
- Modify: `docs/dev/api-contracts.md`
- Modify: `docs/dev/backend.md` if needed
- Modify: `docs/operations/` if a migration command/runbook is added

- [ ] **Step 1: Update docs**

Document:

- table drawer;
- file-backed replacement;
- internal transfer special rule;
- 0/1/many candidate semantics;
- candidate-only confirmation;
- manual confirmation priority/revoke;
- read model fields/source versions;
- RabbitMQ/Redis boundaries;
- migration command if created.

- [ ] **Step 2: Run full backend verification**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_transaction_category_service tests.test_bank_transaction_auto_category_service tests.test_bank_details_service tests.test_bank_details_sql_runtime tests.test_app_settings_service tests.test_pending_invoice_service tests.test_no_oa_bank_batch_tag_selection_api tests.test_no_oa_bank_batch_api tests.test_postgres_migrations -v
```

Expected: PASS.

- [ ] **Step 3: Run full frontend verification**

Run:

```bash
cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsApi.test.ts BankDetailsPage.test.tsx NoOaBankBatchApi.test.ts PendingInvoicesApi.test.ts
cd web && npm run build
```

Expected: PASS.

- [ ] **Step 4: Run repository checks**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 5: Manual visual verification if practical**

Start documented dev servers and inspect:

- `自动标签规则` drawer is widened and table-form;
- term cell editor works;
- multi-candidate row only offers candidate labels;
- confirm/revoke updates row state.

Record the URL and any limitations.
