# Fix Input Invoice Usage All-Scope Refresh Loop Plan

## Goal

Fix `/input-invoice-usage` so the default all-scope query can converge to `read_model_status=fresh` after read model refresh, even when old month shards remain from months that no longer exist in the current input invoice fact set.

## Closed-Loop Prompt

Implement a minimal, production-safe read model fix for the diagnosed `input_invoice_usage:all` refreshing loop.

Root cause from investigation:

- API all-scope rows call reads SQL read model payload and then compares expected source versions.
- `read_model.input_invoice_usage_scopes` contains orphan month scopes/rows for months no longer present in `app.invoices`.
- The all-scope source version proof is calculated from all non-empty month scopes, including orphan scopes.
- Old orphan scopes carry stale `oa_projection_sync_version`, so `_common_source_versions(...)` drops the key and API returns `read_model_status=refreshing` with `oa_projection_sync_version_missing`.
- `input_invoice_usage:all` refresh fan-outs only current invoice months, but does not remove stale orphan scopes, so the loop repeats.

Implement the fix by pruning stale invoice relation month scopes/rows when a parent all-scope refresh discovers the current shard set. Preserve fail-closed freshness semantics; do not make API ignore missing source versions.

## Implementation Tasks

1. Add backend regression coverage first.
   - In `tests/test_invoice_usage_collection_sql_runtime.py`, cover `input_invoice_usage:all` refresh where old month scopes exist but current input invoice facts only include a subset of months.
   - Assert all refresh prunes orphan input usage scope rows/read model rows.
   - Assert subsequent `/api/input-invoice-usage/rows` returns fresh rows instead of `oa_projection_sync_version_missing`.

2. Implement shared repository pruning.
   - Add a repository method that prunes invoice relation read model rows/scopes for a specific read model table pair to a supplied current month shard set.
   - Keep it scoped to the target table and month scopes; do not touch `all` rows or unrelated read models.
   - Use one transaction for row and scope cleanup.

3. Wire pruning into all-scope fan-out.
   - In `InvoiceUsageCollectionReadModelRefreshService._enqueue_scope_shards(...)`, after shard discovery and before completing the parent dirty scope, call an optional projection-builder method to prune stale shards.
   - Add builder methods for `input_invoice_usage`, `output_invoice_collection`, and `oa_pending_payment` if the shared service path needs them; at minimum the input usage path must be fixed.
   - Preserve existing empty-scope behavior.

4. Update module docs.
   - Update `docs/modules/input-invoice-usage/state-machine.md` and `tests.md` with this historical bug and regression coverage.
   - If the shared read model boundary changes materially, update `docs/modules/read-models/README.md` or related module docs.

5. Verification.
   - Run targeted backend tests for invoice usage SQL runtime and freshness.
   - Run a local PostgreSQL read-only/probe check if practical to confirm source version mismatch no longer reproduces after a refresh.

## Acceptance Criteria

- `input_invoice_usage:all` refresh removes month scopes/rows that are no longer current input invoice months.
- The all-scope source version proof retains required base keys including `oa_projection_sync_version` after refresh.
- `/api/input-invoice-usage/rows` returns `read_model_status=fresh` for the default query after worker drain.
- Existing behavior remains: all-scope must not compare against global `workbench_relation:all` source versions.
- No live-scan fallback is introduced in production PostgreSQL runtime.

## Seven Test Categories

- Business core unit tests: not directly applicable; this fix does not change payment/status business rules.
- Service-layer tests: applicable through refresh service/projection builder/repository orchestration.
- API contract tests: applicable for rows returning fresh after refresh rather than 202 refreshing.
- Read model/cache/background job tests: primary category; covers all-scope fan-out, pruning, and source-version freshness.
- Frontend component and interaction tests: not applicable unless UI behavior changes; current UI correctly reflects backend status.
- End-to-end business-flow integration tests: not required for this narrow read model maintenance bug; existing import/relation flows remain unchanged.
- Existing feature regression tests: applicable; preserve old all-scope month relation version tests and no live-scan fallback behavior.

## Verification Commands

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_read_model_freshness -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v
bash scripts/verify.sh docs
```

## Out of Scope

- Manual production data repair outside the test/local diagnostic environment.
- Changing frontend loading or polling behavior.
- Changing workbench relation distribution semantics.
- Relaxing source version freshness guards.
