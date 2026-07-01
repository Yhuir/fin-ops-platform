# P002 Independent Storage Cutover Report

Date: 2026-07-01

## Scope

P002 implemented the first backend storage/read-model cutover slice for `bank-flow-rule-batches`.

Included:

- PostgreSQL physical storage for bank-flow batches.
- PostgreSQL read model row table for bank-flow batch queries.
- Backfill migration from historical no-OA physical tables where `relation_mode=bank_flow_rule_batch`.
- Runtime repository/state-store/read-model query cutover.
- Focused tests and long-lived module docs.

Excluded by design:

- Tag-rule persistence family migration.
- Frontend component/page-state split.
- API response shape changes.

## Implemented Boundary

New physical tables:

- `app.bank_flow_rule_batches`
- `app.bank_flow_rule_batch_events`
- `read_model.bank_flow_rule_batch_rows`

Runtime I/O after this slice:

- `PostgresStateStore.load_bank_flow_rule_batches()` calls `PostgresWorkbenchRepository.load_bank_flow_rule_batches()`.
- `PostgresStateStore.save_bank_flow_rule_batches()` calls `PostgresWorkbenchRepository.save_bank_flow_rule_batches()`.
- `PostgresStateStore.save_bank_flow_rule_batches_scope()` calls `PostgresWorkbenchRepository.save_bank_flow_rule_batches_scope()`.
- `PostgresReadModelRepository.list_bank_flow_rule_batch_rows()` reads `read_model.bank_flow_rule_batch_rows`.
- `PostgresReadModelRepository.bank_flow_rule_batch_source_versions_summary()` reads `read_model.bank_flow_rule_batch_rows`.

No-OA legacy I/O remains on:

- `app.no_oa_bank_batches`
- `app.no_oa_bank_batch_events`
- `read_model.no_oa_bank_batch_rows`

## Old Logic Removed From The Bank-Flow Runtime Path

The bank-flow PostgreSQL runtime path no longer delegates to:

- `PostgresStateStore.load_no_oa_bank_batches()`
- `PostgresWorkbenchRepository.save_no_oa_bank_batches(..., relation_mode="bank_flow_rule_batch")`
- `PostgresWorkbenchRepository.save_no_oa_bank_batches_scope(..., relation_mode="bank_flow_rule_batch")`
- `read_model.no_oa_bank_batch_rows` for bank-flow list/source-summary queries.

The migration uses no-OA physical tables only as historical backfill source. That is not a runtime fallback.

## Performance Impact

Before P002:

- Bank-flow list/source-summary queries scanned `read_model.no_oa_bank_batch_rows` with a `payload->>'relation_mode'` expression predicate.
- The hot-path guard was the expression index from `0080_no_oa_bank_batch_relation_mode_filter.sql`.

After P002:

- Bank-flow list/source-summary queries read `read_model.bank_flow_rule_batch_rows`.
- The table has direct filter/sort indexes:
  - `bank_flow_rule_batch_rows_filters_idx`
  - `bank_flow_rule_batch_rows_generated_idx`
  - `bank_flow_rule_batch_rows_source_versions_gin`
- Query predicates no longer need a relation-mode expression filter on the bank-flow path.

Remaining performance risk:

- `BankFlowRuleBatchApplicationService._refresh_bank_flow_rule_batch_runtime_snapshot()` still does an `all` refresh before detail/withdraw/reset. This should be addressed after rule persistence is independent, because refresh behavior depends on final source-version contracts.

## Tests Added Or Updated

- `tests/test_postgres_migrations.py`
  - Registers `0082_bank_flow_rule_batch_storage.sql`.
  - Adds bank-flow physical/read-model tables to expected table contracts.
  - Changes `READ_MODEL_STORAGE_CONTRACTS["bank_flow_rule_batch"]` to `read_model.bank_flow_rule_batch_rows`.
  - Adds migration/backfill/index/grant assertions.
- `tests/test_postgres_repositories_boundaries.py`
  - Verifies bank-flow writes use dedicated physical tables.
  - Verifies no-OA writes do not touch bank-flow physical tables.
  - Verifies bank-flow read-model list/source-summary query the dedicated table and do not use relation-mode payload predicates.
- `tests/test_bank_flow_rule_batch_backend_boundary.py`
  - Verifies `PostgresStateStore` bank-flow storage methods use dedicated repository I/O names.
- `tests/test_state_store.py`
  - Verifies local pickle mode uses a separate `bank_flow_rule_batches.pkl` file.

## Verification

```bash
PYTHONPATH=backend/src:. python3 -m pytest tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_application_service.py -q
```

Result: 99 passed, 15 subtests passed.

```bash
PYTHONPATH=backend/src:. python3 -m pytest tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_application_service.py tests/test_state_store.py -q
```

Result: 140 passed, 15 subtests passed.

```bash
git diff --check -- backend/src/fin_ops_platform/postgres/migrations backend/src/fin_ops_platform/services tests docs .planning/quick/20260701-bank-flow-rule-batches-full-closure-goal
```

Result: passed.

## Seven-Category Coverage

1. Business core unit tests: not changed in P002; no business rules changed.
2. Service-layer tests: covered by storage boundary and state-store tests.
3. API contract tests: existing bank-flow route tests rerun; no API shape changed.
4. Read model/cache/background job tests: covered by migration storage contract, read-model table query assertions, and producer tests.
5. Frontend component and interaction tests: not applicable to P002; frontend behavior unchanged.
6. End-to-end business-flow integration tests: not run in P002; physical storage cutover is protected by repository/migration contract tests, but browser E2E remains a later final regression gate.
7. Existing feature regression tests: covered for no-OA service/application and no-OA write non-contamination.

## Remaining Gaps

- `BankFlowRuleBatchApplicationService.update_tag_selection()` still persists bank-flow rules through `AppSettingsService.update_no_oa_bank_batch_tag_selection(...)`.
- Rule source version/audit family is still no-OA-named.
- `BankFlowRuleBatchPage.tsx` still owns list/detail/rules/mutation state in one large page component.
- The runtime snapshot refresh still has an `all` hot path before detail/withdraw/reset.

## Next Single Prompt

Run exactly one next prompt:

- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/P003_RULE_FAMILY_CUTOVER.md`
