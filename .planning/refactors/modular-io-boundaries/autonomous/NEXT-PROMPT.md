# Next Prompt

Continue after `read-models:pending-invoice-source-version-contract-alignment`.

## Current State

- Branch: `dev`.
- Row276 implemented the pending invoice source-version contract alignment locally.
- Row276 did not run production commands and did not mutate production.
- `pending_invoice_source_versions(...)` now matches SQL projection writer source-version shape:
  - includes `invoice_lifecycle_policy_schema_version`;
  - always includes stable `bank_detail_source_versions` and `workbench_relation_source_versions` dict keys.
- `PostgresReadModelRepository._pending_invoice_scope_row(...)` now selects `row_count` from `read_model.pending_invoice_scopes`.
- `_pending_invoice_scope_source_versions_row(...)` now derives aggregate source-version proof from non-empty month shards (`row_count > 0`) when any exist, so zero-row historical shards do not poison aggregate `expense:all` freshness.
- Added local regressions:
  - `test_pending_invoice_writer_and_api_source_version_contracts_match`
  - `test_pending_invoice_repository_ignores_zero_row_historical_shards_for_aggregate_source_versions`
- Verification passed:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime -v`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`
  - `python3 -m py_compile backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_search_pending_sql_runtime.py`
- Pending invoice module docs were updated.
- Module/global closure remains open because production deploy/rebuild/API convergence is not yet proven.
- no-OA `bank_transaction_category_snapshot_version_mismatch` remains a separate open production issue after pending invoice convergence.

## Next Boundary

`production:pending-invoice-source-version-contract-deploy-and-convergence-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/read-models-pending-invoice-source-version-contract-alignment-2026-06-25.md`
   - `analysis/production-pending-invoice-no-oa-source-version-contract-deep-diagnosis-2026-06-25.md`
   - `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `docs/operations/runtime-worker-governance.md`
   - `deploy/oa/README.md`
5. Write a production controlled-operation runbook/evidence file under `analysis/` before any production command.

## Production Runbook Scope

- Deploy current `dev` through the documented production deploy path only if the runbook proves prechecks and rollback/cleanup safety.
- Use only root SSH controlled production operations authorized by the T0 goal.
- Refresh/rebuild only explicit pending invoice scopes needed to prove `expense:all` convergence.
- Prefer the least invasive operation:
  - precheck `/health/ready`, release, current git commit, dirty/outbox/readiness summaries;
  - deploy current dev if production is not already at the fix commit;
  - enqueue or run bounded explicit-scope pending invoice refresh for `expense:all` and relevant month shards;
  - wait boundedly for dirty/outbox/readiness convergence;
  - run sanitized authenticated API metadata probe for pending invoice rows/filter-options only, without printing response bodies or payload rows.
- Post-check `/health/ready`, dirty scopes, outbox, readiness, dead letters and sanitized pending invoice source-version mismatch metadata.

## Stop Gates

- Any command would print secrets, tokens, cookies, DSNs, passwords, private keys or business payload rows.
- Any operation would require broad DB mutation, unbounded worker replay/consume, manual mark-done, broad repair, or unclear rollback/cleanup.
- The explicit pending invoice scope list cannot be derived from source/read-model metadata without guessing.
- Deploy prechecks are not clean or rollback path is not documented in the runbook.
- Do not broaden into no-OA repair/rebuild in this boundary.
- Do not claim module/global closure from pending invoice convergence alone.
