# Production Pending Invoice No-OA Source Version Contract Deep Diagnosis - 2026-06-25

**Boundary:** `production:pending-invoice-no-oa-source-version-contract-deep-diagnosis`
**Status:** `production-diagnosis-closed`
**Module closure:** `not-module-closed`
**Production mutation:** forbidden
**Worker threads created:** none
**Previous boundary:** `production:pending-invoice-no-oa-api-freshness-mismatch-read-only-diagnosis`
**Next boundary:** `read-models:pending-invoice-source-version-contract-alignment`

## Goal

Diagnose why completed production refreshes still leave:

- pending invoice `expense:all` source versions mismatching the current API expected source versions;
- no-OA row-level source versions mismatching the current application expected source versions even when App Status readiness is fresh.

This boundary is read-only. It must not call production APIs, enqueue refreshes, mutate DB/queue/readiness/files/workers/services/browser state, print secrets, or print business payload rows.

## Code Contract Findings Before Production Command

Pending invoice:

- `PendingInvoiceReadModelService.pending_invoice_source_versions(...)` expects:
  - `pending_invoice_read_model_schema_version`
  - `pending_invoice_tag_groups_version`
  - `pending_output_invoice_tag_groups_version`
  - `bank_auto_tag_rules_version`
  - `oa_attachment_invoice_parser_version`
  - `oa_projection_sync_version`
  - optional `bank_detail_source_versions`
  - optional `workbench_relation_source_versions`
- `SearchPendingSqlProjectionBuilder._pending_invoice_source_versions()` writes the same keys plus `invoice_lifecycle_policy_schema_version`.
- `SearchPendingSqlProjectionBuilder.rebuild_pending_invoice_read_model_scope(...)` rejects aggregate scope keys without a month shard. `expense:all` cannot be directly rebuilt through that method; month shards such as `expense:all:YYYY-MM` are the writer path.
- `PostgresReadModelRepository.list_pending_invoice_rows(...)` reads aggregate `expense:all` source versions through `_pending_invoice_scope_row("expense:all")`, which loads both `expense:all` and `expense:all:%` rows, then aggregates month-shard versions.
- `_pending_invoice_scope_source_versions_row(...)` starts from the first row's source_versions, then nests `bank_detail_source_versions` and `workbench_relation_source_versions` by month when multiple rows exist.

no-OA:

- `NoOaBankBatchApplicationService.no_oa_bank_batch_source_versions()` expects:
  - workbench matching source versions from `_workbench_matching_source_versions(...)`
  - `no_oa_bank_batch_schema_version`
  - `no_oa_bank_batch_tag_selection_version`
  - `bank_transaction_category_schema_version`
  - `pair_relation_snapshot_version`
  - `bank_transaction_category_snapshot_version`
  - optional `bank_detail_source_versions`
  - optional `workbench_relation_source_versions`
- `NoOaBankBatchApplicationService.no_oa_bank_batch_stale_reasons(...)` compares every returned row's `source_versions` against that expected contract. App Status readiness can therefore be fresh while row-level source versions are stale.

## Allowed Operations

- `ssh finops-prod-root` with bounded commands.
- Public local `/health/ready` summary.
- Source deployed env files with `set +x`, without printing env values.
- Direct PostgreSQL read-only SQL through deployed code's `PostgresConnection`.
- Pure source-version helper functions, constants, hashes, key names, mismatch reason names, row counts, scope keys and job/readiness metadata.

## Forbidden Operations

- Production API calls.
- Starting broad `Application` runtime.
- Calling service methods that enqueue refreshes or persist snapshots.
- Any `insert`, `update`, `delete`, `truncate`, `alter`, `create`, `drop`, repair, refresh, rebuild, deploy, restart, browser, worker drain, queue replay or readiness mutation.
- Printing env values, DSNs, passwords, tokens, cookies, private keys, payload rows, invoice identifiers, project names, counterparties, bank account names, transaction ids or other business values.

## Runbook Commands

### 1. Precheck release and health

```bash
ssh finops-prod-root 'set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; echo "release_src=$release_src"; echo "git_commit=$(cat "$release_src/.git_commit" 2>/dev/null || git -C "$release_src" rev-parse HEAD 2>/dev/null || true)"; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

Stop if health is unavailable or not ready.

### 2. Read-only source-version contract diagnosis

The command must:

- initialize only `PostgresConnection`, `PostgresReadModelRepository`, and `PostgresStateStore` read paths;
- compute pending invoice expected source versions using the same helper as `PendingInvoiceReadModelService`;
- read pending invoice scope source versions for `expense:all` and `expense:all:%` without payload rows;
- summarize recent `pending_invoice.read_model.refresh` jobs by payload scope key;
- compute no-OA expected source versions from SQL/settings/snapshots/constants without constructing `Application`;
- read no-OA row `source_versions` for `month=2026-06,bucket=unsubmitted` without payload rows;
- print only keys, hashes, mismatch reasons, row counts and scope/job/readiness metadata.

Rollback is not applicable because the command is read-only. Cleanup is not applicable because it creates no production files.

## Stop Gates

- Stop before running if the command would print a secret or business payload row.
- Stop before running if a required expected-source contract cannot be derived from source code.
- Stop before running if exact no-OA expected-source derivation would require broad `Application` startup.
- Stop after running if health changes from ready to non-ready.

## Production Evidence

Executed by T0 through `ssh finops-prod-root` after writing this runbook.

Precheck:

- Active release source path: `/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src`.
- `/health/ready`: `ready`.

Read-only command attempts:

- First attempt stopped before DB access because `MongoOAAdapter` was imported from the wrong module path.
- Second attempt stopped on a SQL quoting error before useful diagnosis.
- Third attempt used a local heredoc to preserve SQL quoting and completed successfully.

Post-check:

- `/health/ready`: `ready`.

No production API endpoint, response body, payload row, secret, env value, DB mutation, queue mutation, readiness mutation, deploy, restart, requeue, repair or worker replay occurred.

## Diagnosis Result

### Pending Invoice

Scope: `expense:all`.

Expected API source-version contract:

- key count: 8
- hash: `8ecc010b5db0bd95`
- keys: `bank_auto_tag_rules_version`, `bank_detail_source_versions`, `oa_attachment_invoice_parser_version`, `oa_projection_sync_version`, `pending_invoice_read_model_schema_version`, `pending_invoice_tag_groups_version`, `pending_output_invoice_tag_groups_version`, `workbench_relation_source_versions`

Actual aggregate read-model source-version contract:

- key count: 9
- hash: `ffdfe1c6e3e27b01`
- keys: expected keys plus `invoice_lifecycle_policy_schema_version`

Mismatch reasons:

- `bank_auto_tag_rules_version_mismatch`
- `bank_detail_source_versions_mismatch`
- `oa_projection_sync_version_mismatch`
- `pending_invoice_read_model_schema_version_mismatch`
- `pending_invoice_tag_groups_version_mismatch`

Refresh topology evidence:

- `read_model.pending_invoice_scopes` had 32 `expense:all:%` month shard rows.
- Recent six-hour outbox included completed refreshes for aggregate `expense:all` and month shards `expense:all:2026-01` through `expense:all:2026-06`.
- Dirty scopes for aggregate and all listed shards were `done`; there were no active non-done rows in this diagnosis output.
- `SearchPendingSqlProjectionBuilder.rebuild_pending_invoice_read_model_scope(...)` can rebuild only month shards. Aggregate `expense:all` jobs can mark scope metadata, but they do not rebuild the aggregate rows directly.

Root cause classification:

- This is not an active worker backlog problem: relevant dirty/outbox rows completed.
- The aggregate source-version proof is stale because `_pending_invoice_scope_source_versions_row("expense:all", rows)` builds the aggregate from every historical `expense:all:%` shard, including many zero-row historical shards that were not rebuilt in the recent 2026 refresh window.
- The projection writer and API expected contracts are also not byte-aligned: writer includes `invoice_lifecycle_policy_schema_version`, while API expected source versions omit it. That extra key alone does not cause current stale reasons because mismatch comparison ignores extra actual keys, but it is still a contract drift that should be aligned before any production rebuild is trusted.

Next safe action:

- Code contract fix first: align pending invoice source-version contracts and aggregate source-version derivation so aggregate `direction:filter` freshness is computed from effective/non-empty shard rows or from the same scoped row set used by the API query, rather than stale zero-row historical shards.
- After local tests prove the contract, run a separate bounded production deploy/rebuild/convergence runbook for explicit pending invoice scopes.

### no-OA

Probe scope: `month=2026-06`, `bucket=unsubmitted`.

Expected base source-version contract without broad `Application` startup:

- key count: 13
- hash: `65e9060b8cee23f2`
- keys: `bank_auto_tag_rules_version`, `bank_transaction_category_schema_version`, `bank_transaction_category_snapshot_version`, `no_oa_bank_batch_schema_version`, `no_oa_bank_batch_tag_selection_version`, `oa_attachment_invoice_parser_version`, `oa_projection_sync_version`, `pair_relation_snapshot_version`, `workbench_candidate_match_schema_version`, `workbench_exception_projection_version`, `workbench_exception_rules_version`, `workbench_matching_rules_version`, `workbench_read_model_schema_version`

Actual row source-version contract:

- row count: 8
- unique source-version hash count: 1
- hash: `6d33251a850b453d`
- key count: 15
- keys: expected base keys plus `bank_detail_source_versions` and `workbench_relation_source_versions`

Mismatch reasons against the exact base expected contract:

- `bank_transaction_category_snapshot_version_mismatch`

Readiness/dirty evidence:

- Dirty `no_oa_bank_batch:2026-06`: `done`, count `1`, latest `2026-06-19 00:45:40.128449+08`.
- Dirty `no_oa_bank_batch:all`: `done`, count `28067`, latest `2026-06-25 05:02:09.049344+08`.
- App Status readiness had only `all/fresh`; readiness source metadata exposed only aggregate key `source_version`.

Root cause classification:

- This is not an App Status readiness problem; App Status is coarser than row-level API source-version comparison.
- Against the safely reconstructable base expected contract, the stale row reason is exactly `bank_transaction_category_snapshot_version_mismatch`.
- The row actual versions include optional `bank_detail_source_versions` and `workbench_relation_source_versions`. `list_batches_payload(...)` calls `no_oa_bank_batch_stale_reasons(...)` before it calls category/relation providers in that request path, so a fresh service instance's expected contract does not include those optional keys. Reading whether the long-lived production service has provider `last_source_versions` pre-populated would require broad runtime state inspection; this boundary intentionally did not do that. Extra actual keys are ignored by `source_version_mismatch_reasons(...)`.

Next safe action:

- no-OA likely needs a bounded explicit-scope refresh/rebuild after confirming why `bank_transaction_category_snapshot_version` advanced without current row rebuild.
- Because pending invoice has a code-contract drift, fix pending invoice source-version alignment before production rebuild work. no-OA can be the following production convergence boundary if no additional code bug is found.
