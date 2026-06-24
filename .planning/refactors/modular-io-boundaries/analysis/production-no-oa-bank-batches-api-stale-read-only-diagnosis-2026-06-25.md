# Production No-OA Bank Batches API Stale Read-Only Diagnosis - 2026-06-25

**Boundary:** `production:no-oa-bank-batches-api-stale-read-only-diagnosis`
**Status:** `production-diagnosis-closed`
**Module closure:** `not-module-closed`
**Production mutation:** forbidden
**Worker threads created:** none
**Previous boundary:** `production:read-model-focused-user-scope-api-metadata-resmoke-runbook`

## Goal

Diagnose why user-scope `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200` still reports `read_model_status=stale` after:

- Row278 proved the bounded no-OA row category source-version mismatch was gone;
- Row280's GET-triggered no-OA refresh converged to done;
- App Status readiness, dirty scopes, outbox and dead-letter aggregates were clean.

This boundary is read-only. It must not call production API endpoints, enqueue refreshes, rebuild read models, mutate PostgreSQL, restart/deploy services, replay workers, or print payload rows.

## Code Path Facts

- `NoOaBankBatchApplicationService.list_batches_payload(...)` reads `summary_read_model_batches` with `{month, account_key}` and `read_model_batches` with `{month, type, status, bucket, account_key}`.
- API freshness compares `summary_read_model_batches + read_model_batches` through `no_oa_bank_batch_stale_reasons(...)`.
- The stale check calls `no_oa_bank_batch_source_versions()` before `resolve_labels(...)`, so the list path does not populate `BankTransactionTagReadFacade.last_source_versions` or `WorkbenchRelationReadFacade.last_source_versions` during the same request.
- Refresh worker `refresh_batches(...)` reads bank detail tags and workbench relation rows before writing no-OA row `source_versions`, so persisted rows may include optional `bank_detail_source_versions` and `workbench_relation_source_versions`.
- `source_version_mismatch_reasons(...)` only checks keys present in expected; extra actual keys do not make a row stale.

## Allowed Operations

- `ssh finops-prod-root` with bounded read-only commands.
- Local `/health/ready` summary.
- Sourcing deployed env files with `set +x`, without printing env values.
- Direct PostgreSQL read-only SQL through deployed `PostgresConnection`.
- Deployed pure helpers/constants:
  - `BankTransactionCategoryService.from_snapshot(...).snapshot()`
  - `WorkbenchReadModelService.snapshot_version(...)`
  - `source_version_mismatch_reasons(...)`
  - no-OA/workbench source-version constants and runtime worker source-version helper.
- Sanitized output only: hashes, key names, mismatch reason names, row counts, status counts, scope keys, release names and timestamps.

## Forbidden Operations

- Production API endpoint calls.
- Broad `Application` startup.
- Calling no-OA API/list methods that can enqueue refresh on stale rows.
- Any `insert`, `update`, `delete`, `truncate`, `alter`, `create`, `drop`, repair, refresh, rebuild, deploy, restart, browser session, worker drain, queue replay, direct readiness mutation, manual mark-done, or queue mutation.
- Printing env values, DSNs, passwords, tokens, cookies, private keys, payload rows, batch ids, transaction ids, account names, counterparties or other business values.

## Stop Gates

- Stop before running if the command would print a secret or business payload row.
- Stop before running if exact expected source-version construction would require broad `Application` startup or guessing unknown contracts.
- Stop after running if `/health/ready` changes from ready to non-ready.
- Stop without mutation if diagnosis shows rows are stale but the next action would require refresh/rebuild; that needs a separate controlled runbook.
- Do not claim module/global closure from this diagnosis.

## Step 1 - Read-Only Production Precheck

Use a local heredoc piped to `ssh finops-prod-root 'bash -s'` to avoid shell quote loss.

Expected evidence:

- active release name and commit are printed;
- `/health/ready` reports `ready`;
- dirty scopes are done, readiness is fresh, read-model outbox is done, and read-model dead letters are empty.

Rollback/cleanup: none. This is read-only.

## Step 2 - Read-Only API Stale Diagnosis

The command must:

- reconstruct deployed no-OA base expected source versions without `Application` startup;
- read sanitized source-version metadata for both API comparison scopes:
  - summary scope: `month=2026-06`;
  - detail scope: `month=2026-06,bucket=unsubmitted`;
- compare row source versions to base expected and to optional downstream variants when the optional nested versions can be derived from persisted row/source metadata;
- inspect whether stale reasons appear only in summary rows, only in detail rows, or both;
- summarize dirty/outbox/readiness/dead-letter metadata after Row280's GET-triggered refresh;
- print no payload rows, ids, account names, counterparties or env values.

Rollback/cleanup: none. This is read-only.

## Step 3 - Read-Only Production Postcheck

Repeat `/health/ready` and the sanitized dirty/outbox/readiness/dead-letter aggregate summary.

Expected evidence:

- `/health/ready` remains `ready`;
- aggregates remain clean.

## Production Evidence

Executed by T0 through `ssh finops-prod-root` after writing this runbook.

Precheck:

- Active release: `dev-pending-invoice-source-17d13466-20260625`.
- `/health/ready`: `ready`.

Read-only command attempts:

- First attempt stopped before DB access because `PostgresStateStore` was constructed without the deployed required `data_dir` keyword.
- Second attempt stopped before DB access because the deployed release exposes `default_data_dir` from `fin_ops_platform.services.state_store`, not `fin_ops_platform.config`.
- Third attempt stopped before DB access because `AppSettingsService` in the deployed release requires `project_costing_service`; T0 switched to `PostgresStateStore.load_app_settings()` plus deployed constants instead of broad service construction.
- Fourth attempt completed the source-version query but used an incorrect App Status readiness column (`domain` instead of `scope_type`); no write occurred.
- Fifth attempt completed with the corrected readiness aggregate but used an over-simplified pair-relation snapshot reconstruction. It incorrectly reported `pair_relation_snapshot_version_mismatch`; T0 rejected that result after inspecting `NoOaPairRelationSnapshotPort.snapshot_version()`.
- Final verification used `WorkbenchPairRelationService.from_snapshot(store.load_workbench_pair_relations()).snapshot()` to match the deployed application contract exactly and completed successfully.

Postcheck:

- `/health/ready`: `ready`.

No production API endpoint, response body, payload row, batch id, transaction id, account name, counterparty, secret, env value, DB mutation, queue mutation, readiness mutation, deploy, restart, requeue, repair, refresh command or worker replay occurred in this boundary.

## Diagnosis Result

Probe scope: `month=2026-06`, `bucket=unsubmitted`.

Current no-OA row source-version evidence after Row280's GET-triggered refresh:

- summary scope row count: `8`.
- detail scope row count: `8`.
- status distribution: `draft/unsubmitted=8`.
- detail row source-version hash: `36cab6e37ef9aede`.
- detail row key count: `15`.
- generated range: `2026-06-25 06:11:29.601474+08:00` to `2026-06-25 06:11:29.619570+08:00`.
- updated at: `2026-06-25 06:11:29.748983+08:00`.

Expected source-version evidence:

- exact base expected hash: `12a6a240c94fcc71`.
- exact base expected key count: `13`.
- exact expected `pair_relation_snapshot_version` prefix: `d35b81698abdd031`.
- optional-detail expected hash: `36cab6e37ef9aede`.
- optional-detail expected key count: `15`.
- optional `bank_detail_source_versions` hash: `0673e51b28166cb9`.
- optional `workbench_relation_source_versions` hash: `18ffe677bd6f1aa2`.

Mismatch evidence:

- Base expected vs summary rows: `0` rows with mismatch.
- Base expected vs detail rows: `0` rows with mismatch.
- Base expected vs combined API comparison rows: `0` rows with mismatch across `16` compared row entries.
- Optional-detail expected vs summary rows: `0` rows with mismatch.
- Optional-detail expected vs detail rows: `0` rows with mismatch.
- Optional-detail expected vs combined API comparison rows: `0` rows with mismatch across `16` compared row entries.

Freshness/worker metadata after Row280 refresh:

- Dirty `no_oa_bank_batch:2026-06`: `done`, count `1`, latest `2026-06-19 00:45:40.128449+08`.
- Dirty `no_oa_bank_batch:all`: `done`, count `28068`, latest `2026-06-25 06:11:30.097589+08`.
- Outbox `no_oa_bank_batch.read_model.refresh` in last 24h: `done`, count `3`, latest `2026-06-25 06:11:30.105523+08`.
- App Status readiness `no_oa_bank_batch:all`: `fresh`, latest `2026-06-25 06:11:30.101741+08`.
- Read-model dead letters in last 7d: none.

Root cause classification:

- Row280's `no_oa_bank_batches` API stale result was consistent with stale persisted rows before its GET-triggered refresh.
- The GET-triggered no-OA refresh completed and published new rows at `2026-06-25 06:11:29+08`; current persisted rows match both the exact deployed base contract and the optional downstream-key contract.
- The stale blocker is not currently reproduced in read-only metadata. No code fix, repair, rebuild, requeue or manual refresh is justified from current evidence.
- The next safe boundary is a focused authenticated API metadata recheck for `no_oa_bank_batches` only. That boundary may use the same controlled GET probe style as Row280 and must stop if the endpoint is still stale.

Next safe action:

- Reconcile Row281 as `production-diagnosis-closed`.
- Select `production:no-oa-bank-batches-focused-api-freshness-recheck` to prove the user-scope API now returns `read_model_status=fresh` after the completed refresh, before returning to broader user-scope/browser/admin/write evidence.
