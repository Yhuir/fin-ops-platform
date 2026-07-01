# P002 Independent Storage Cutover

Use this as the next bounded execution prompt inside the `/goal` controller.

```text
Goal:
Implement the first backend storage/read-model cutover slice for `bank-flow-rule-batches`: create independent bank-flow physical tables and move bank-flow batch/read-model persistence and query methods away from no-OA physical tables. Do not move tag-rule persistence and do not split frontend in this slice.

Evidence to inspect first:
- `.planning/quick/20260701-bank-flow-rule-batches-full-closure-goal/BASELINE_AUDIT.md`
- `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0022_read_model_native_closeout.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0080_no_oa_bank_batch_relation_mode_filter.sql`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/state_store_protocol.py`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py`
- `backend/src/fin_ops_platform/services/bank_batch_read_model_refresh.py`
- `tests/test_postgres_migrations.py`
- `tests/test_postgres_repositories_boundaries.py`
- `tests/test_bank_flow_rule_batch_application_service.py`
- `tests/test_no_oa_bank_batch_application_service.py`

Allowed implementation scope:
- New PostgreSQL migration file only for bank-flow storage/read-model tables and backfill.
- `PostgresWorkbenchRepository` or a small existing repository-adjacent helper if needed; do not create speculative layers.
- `PostgresStateStore` bank-flow load/save/scope/mutation methods.
- `PostgresReadModelRepository` bank-flow list/source-version methods.
- `ApplicationStateStoreProtocol` only if method contracts need tightening.
- Local `ApplicationStateStore` only enough to keep local dev parity; no new production fallback.
- Focused backend tests for migration, repository boundaries, and bank-flow/no-OA non-contamination.
- Required docs if facts change: bank-flow boundary/tests/read-model-contracts/api-contracts.

Architecture constraints:
- Keep no-OA legacy paths on `app.no_oa_bank_batches`, `app.no_oa_bank_batch_events`, and `read_model.no_oa_bank_batch_rows`.
- Keep bank-flow paths on `app.bank_flow_rule_batches`, `app.bank_flow_rule_batch_events`, and `read_model.bank_flow_rule_batch_rows`.
- Preserve `relation_mode=bank_flow_rule_batch` in payload/metadata for Workbench and API compatibility, but do not use no-OA physical tables as the bank-flow source of truth.
- Preserve `WorkbenchRelationCommandService` as relation write owner.
- Do not alter public `/api/bank-flow-rule-batches` response shape except if tests prove a missing field from the existing contract.
- Do not move `update_no_oa_bank_batch_tag_selection(...)` in this slice.
- Do not split `BankFlowRuleBatchPage.tsx` in this slice.
- No broad dual-read fallback unless migration safety requires it; if temporary dual-read is used, add an explicit deletion condition and guard test.

Required edits:
1. Add migration:
   - `app.bank_flow_rule_batches`
   - `app.bank_flow_rule_batch_events`
   - `read_model.bank_flow_rule_batch_rows`
   - indexes matching current filter/sort hot paths:
     - scope_month, batch_type, status, status_bucket, account_key
     - generated_at desc, batch_id
     - any source/version lookup already used by current repository methods
   - grants consistent with no-OA equivalents.
   - backfill from no-OA tables where payload/raw_payload relation mode is `bank_flow_rule_batch`.
2. Add/switch repository persistence:
   - bank-flow load/save/scope save use bank-flow tables.
   - bank-flow read model list/source-summary use `read_model.bank_flow_rule_batch_rows`.
   - no-OA methods remain unchanged and continue relation-mode filtering where still needed for legacy data.
3. Add tests:
   - migration contains/creates required bank-flow tables and grants.
   - bank-flow repository writes do not execute SQL against `app.no_oa_bank_batches`, `app.no_oa_bank_batch_events`, or `read_model.no_oa_bank_batch_rows`.
   - no-OA repository writes do not touch bank-flow tables.
   - bank-flow list/source summary queries `read_model.bank_flow_rule_batch_rows`.
   - existing route/service tests still pass.
4. Update docs only for facts changed by this slice.

Verification to run:
- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_application_service.py -q`
- `git diff --check -- backend/src/fin_ops_platform/postgres/migrations backend/src/fin_ops_platform/services tests docs .planning/quick/20260701-bank-flow-rule-batches-full-closure-goal`

Stop condition:
- Bank-flow physical storage/read-model query no longer depends on no-OA physical tables in production PostgreSQL paths.
- No-OA legacy tests still pass.
- Tests and docs identify any temporary compatibility path that remains.
- Generate exactly one next prompt `P003_*` based on the resulting diff and tests, but do not create a backlog.
```

