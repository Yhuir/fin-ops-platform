# Next Prompt

Continue after `production:pending-invoice-no-oa-api-freshness-mismatch-read-only-diagnosis`.

## Current State

- Branch: `dev`.
- Row274 used root SSH and direct deployed PostgreSQL read repositories only.
- Row274 did not call production API endpoints and did not call service methods that enqueue refreshes.
- Row274 `/health/ready` was ready before and after.
- Pending invoice Row273 probe scope was `expense:all`.
- Pending invoice repository payload for `expense:all` was present, `refresh_status=fresh`, `row_count=50`, `total=683`.
- Pending invoice active refresh count for `expense:all` was `0`.
- Pending invoice dirty summary for `expense:all` was all `done` with count `551`, latest update `2026-06-25 05:02:07.183806+08`.
- Pending invoice recent refresh outbox had `done=38`, latest processed `2026-06-25 05:02:08.175592+08`.
- Pending invoice App Status readiness had no `expense:all` row.
- Pending invoice API expected-source gate reported mismatches:
  - `bank_auto_tag_rules_version_mismatch`
  - `bank_detail_source_versions_mismatch`
  - `oa_projection_sync_version_mismatch`
  - `pending_invoice_read_model_schema_version_mismatch`
  - `pending_invoice_tag_groups_version_mismatch`
- This explains Row273:
  - `pending_invoices_rows` returned HTTP `200` because the route maps `refreshing` plus non-empty rows to `200`;
  - `pending_invoices_filter_options` returned HTTP `202` because it gates through rows and returns accepted for any non-fresh gate payload.
- no-OA Row273 probe scope was current month `2026-06` plus `all`.
- no-OA current-month summary/filter row counts were both `8`.
- no-OA active refresh counts for `2026-06` and `all` were both `0`.
- no-OA dirty summary was clean:
  - `2026-06`: `done=1`, latest update `2026-06-19 00:45:40.128449+08`;
  - `all`: `done=28067`, latest update `2026-06-25 05:02:09.049344+08`.
- no-OA recent refresh outbox had `done=2`, latest processed `2026-06-25 05:02:09.054545+08`.
- no-OA App Status readiness was `all/fresh`, updated `2026-06-25 05:02:09.052821+08`, but readiness source metadata only exposed aggregate key `source_version`.
- no-OA row-level source versions for the 8 rows expose 15 keys, including bank detail, tag selection, pair relation, workbench and workbench relation source versions.
- This explains why App Status can be fresh while API returns `read_model_status=stale`: `NoOaBankBatchApplicationService.list_batches_payload(...)` compares row-level source versions through `no_oa_bank_batch_stale_reasons(...)`, not only aggregate App Status readiness.
- Exact no-OA expected-vs-row mismatch keys were not computed in Row274 because doing so without starting broad production `Application` runtime requires deeper dependency/source-version contract inspection.
- Browser/admin/write closure remains open. Module/global closure remains open.

## Next Boundary

`production:pending-invoice-no-oa-source-version-contract-deep-diagnosis`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/production-pending-invoice-no-oa-api-freshness-mismatch-read-only-diagnosis-2026-06-25.md`
   - `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/no-oa-bank-batches/README.md`
5. Write a read-only production diagnosis runbook/evidence file under `analysis/` before running any production command.
6. Use only source-version keys, mismatch reason names, counts, hashes and scope metadata. Do not print payload rows or business values.
7. Update controller files with result and next boundary.

## Diagnosis Scope

- Determine why completed pending invoice refreshes still leave `expense:all` source versions mismatching current API expected source versions.
- Compare projection writer source-version contract in `SearchPendingSqlProjectionBuilder` with `PendingInvoiceReadModelService` expected-source contract.
- Determine whether Row273-triggered refresh rebuilt `expense:all`, month/filter shards, or both.
- Determine exact no-OA expected-vs-row mismatch keys without starting broad production `Application` runtime or printing business payloads.
- Decide the next safe action: code contract fix, bounded explicit-scope refresh/rebuild runbook, or precise production-evidence defer.

## Stop Gates

- Any command would print secrets, tokens, cookies, DSNs, passwords or business payload rows.
- Any command would mutate DB, queue, readiness, files, workers, services, browser state or business data.
- Diagnosis requires guessing expected source-version contracts instead of reading source code.
- Diagnosis requires starting broad production `Application` runtime with possible startup side effects.
- Do not claim module/global closure from this diagnosis.
