# Next Prompt

Continue after `production:pending-invoice-no-oa-source-version-contract-deep-diagnosis`.

## Current State

- Branch: `dev`.
- Row275 used root SSH and direct deployed PostgreSQL read-only metadata only.
- Row275 did not call production API endpoints and did not mutate production DB, queue, readiness, files, workers, services, browser state or business data.
- `/health/ready` was `ready` before and after the Row275 production command.
- Pending invoice expected source versions for `expense:all`:
  - hash `8ecc010b5db0bd95`;
  - 8 keys: `bank_auto_tag_rules_version`, `bank_detail_source_versions`, `oa_attachment_invoice_parser_version`, `oa_projection_sync_version`, `pending_invoice_read_model_schema_version`, `pending_invoice_tag_groups_version`, `pending_output_invoice_tag_groups_version`, `workbench_relation_source_versions`.
- Pending invoice actual aggregate source versions for `expense:all`:
  - hash `ffdfe1c6e3e27b01`;
  - 9 keys: expected keys plus `invoice_lifecycle_policy_schema_version`.
- Pending invoice stale reasons remain:
  - `bank_auto_tag_rules_version_mismatch`
  - `bank_detail_source_versions_mismatch`
  - `oa_projection_sync_version_mismatch`
  - `pending_invoice_read_model_schema_version_mismatch`
  - `pending_invoice_tag_groups_version_mismatch`
- Pending invoice scope evidence:
  - `read_model.pending_invoice_scopes` had 32 `expense:all:%` month shard rows.
  - Recent six-hour outbox included completed refreshes for aggregate `expense:all` and month shards `expense:all:2026-01` through `expense:all:2026-06`.
  - Dirty scopes for aggregate and listed shards were `done`; no active non-done blocker was observed.
  - `SearchPendingSqlProjectionBuilder.rebuild_pending_invoice_read_model_scope(...)` rejects aggregate scope keys and rebuilds only month shards.
  - `PostgresReadModelRepository._pending_invoice_scope_row("expense:all")` aggregates from all `expense:all:%` rows, including zero-row historical shards not rebuilt in the recent 2026 refresh window.
- no-OA source-version evidence:
  - base expected hash `65e9060b8cee23f2`;
  - row hash `6d33251a850b453d`;
  - row count `8` for `month=2026-06,bucket=unsubmitted`;
  - exact base mismatch reason: `bank_transaction_category_snapshot_version_mismatch`;
  - App Status readiness was `all/fresh` with only aggregate `source_version`, which is coarser than row-level API source-version freshness.
- Module/global closure remains open.

## Next Boundary

`read-models:pending-invoice-source-version-contract-alignment`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/production-pending-invoice-no-oa-source-version-contract-deep-diagnosis-2026-06-25.md`
   - `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - existing tests around pending invoice read model/service/projection/repository contracts
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/tests.md`
5. Use CodeGraph for pending invoice source-version symbols/callers before implementation if available.

## Implementation Scope

- Align pending invoice writer/API expected source-version contracts so both sides intentionally include or intentionally exclude `invoice_lifecycle_policy_schema_version`.
- Fix aggregate `direction:filter` source-version derivation so `expense:all` freshness is not poisoned by stale zero-row historical shards when the row query's effective data lives in current non-empty shards.
- Preserve month-shard rebuild semantics and do not add aggregate rebuild writes unless the contract explicitly requires it and tests prove it.
- Add or update focused tests for:
  - source-version contract parity between writer and API expected helper;
  - aggregate pending invoice scope source-version derivation from multiple month shards with zero-row historical shards;
  - existing pending invoice stale-reason behavior.
- Update pending invoice module docs/tests if the contract or verification matrix changes.

## Stop Gates

- Do not run production mutation in this boundary.
- Do not guess source-version fields; read the helper contracts and tests.
- Do not broaden into no-OA rebuild/repair in this boundary.
- Do not claim module/global closure from local tests.
