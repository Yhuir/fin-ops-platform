# Production No-OA Bank Batch Category Source Version Mismatch Diagnosis - 2026-06-25

**Boundary:** `production:no-oa-bank-batch-category-source-version-mismatch-diagnosis`
**Status:** `production-diagnosis-closed`
**Module closure:** `not-module-closed`
**Production mutation:** forbidden
**Worker threads created:** none
**Previous boundary:** `production:pending-invoice-source-version-contract-deploy-and-convergence-runbook`

## Goal

Diagnose the remaining no-OA `bank_transaction_category_snapshot_version_mismatch` from Row275 after pending invoice production convergence:

- prove the current no-OA expected source-version contract from deployed code without broad `Application` startup;
- compare only sanitized source-version metadata for bounded no-OA rows;
- determine whether the mismatch is row data lag, code-contract drift, or an unsafe-to-refresh condition;
- collect dirty/outbox/readiness metadata needed to select the next bounded production boundary.

This boundary is read-only. It must not repair, refresh, rebuild, requeue, replay, deploy, restart, mark readiness, mutate DB rows, or call production APIs.

## Allowed Operations

- `ssh finops-prod-root` with bounded commands.
- Local `/health/ready` summary.
- Source deployed env files with `set +x`, without printing env values.
- Direct PostgreSQL read-only SQL through deployed `PostgresConnection`.
- Deployed pure helpers/constants:
  - `BankTransactionCategoryService.from_snapshot(...).snapshot()`
  - `WorkbenchReadModelService.snapshot_version(...)`
  - `source_version_mismatch_reasons(...)`
  - no-OA/workbench source-version constants and runtime worker source-version helper.
- Sanitized output only: hashes, key names, mismatch reason names, counts, statuses, scope keys, release names and timestamps.

## Forbidden Operations

- Production API endpoint calls.
- Broad `Application` startup.
- Calling no-OA list/query methods that can enqueue refresh on stale rows.
- Any `insert`, `update`, `delete`, `truncate`, `alter`, `create`, `drop`, repair, refresh, rebuild, deploy, restart, browser session, worker drain, queue replay, direct readiness mutation, manual mark-done, or queue mutation.
- Printing env values, DSNs, passwords, tokens, cookies, private keys, payload rows, batch ids, transaction ids, account names, counterparties or other business values.

## Stop Gates

- Stop before running if the command would print a secret or business payload row.
- Stop before running if exact expected source versions cannot be derived from deployed code without broad `Application`.
- Stop after running if `/health/ready` changes from ready to non-ready.
- Stop without mutation if diagnosis shows rows are stale but the next action would require a refresh/rebuild; that needs a separate controlled runbook.

## Step 1 - Read-Only Production Precheck

```bash
ssh finops-prod-root 'set -eu
release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"
if [ ! -d "$release_src/backend/src" ]; then
  release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"
fi
release_name="$(basename "$(dirname "$release_src")")"
git_commit="$(cat "$release_src/.git_commit" 2>/dev/null || true)"
echo "precheck_release_name=$release_name"
echo "precheck_git_commit=$git_commit"
curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready \
  | /opt/fin-ops/venv/bin/python -c '"'"'import json,sys; p=json.load(sys.stdin); print({"status":p.get("status"),"release":p.get("release")})'"'"'
'
```

Expected evidence:

- active release name and commit are printed;
- `/health/ready` reports `ready`.

Rollback/cleanup: none. This is read-only.

## Step 2 - Read-Only Category Source-Version Diagnosis

The command must:

- use only deployed code in the active release;
- initialize `PostgresConnection` and `PostgresStateStore` read paths;
- reconstruct expected no-OA source versions from deployed helpers/constants and snapshots;
- read bounded no-OA row source-version metadata for `month=2026-06,bucket=unsubmitted`;
- compare actual row versions to current expected versions;
- summarize category snapshot hash/current row category version distribution;
- summarize no-OA dirty/outbox/readiness/dead-letter metadata;
- print no payload rows, ids, account names, counterparties or env values.

Rollback/cleanup: none. This is read-only.

## Step 3 - Read-Only Production Postcheck

Repeat the `/health/ready` summary from Step 1.

Expected evidence:

- `/health/ready` remains `ready`.

## Production Evidence

Executed by T0 through `ssh finops-prod-root` after writing this runbook.

Precheck:

- Active release: `dev-pending-invoice-source-17d13466-20260625`.
- `/health/ready`: `ready`.

Read-only command attempts:

- First attempt stopped before DB access because `PostgresStateStore` was constructed with a positional `connection` argument instead of the deployed keyword-only signature.
- Second attempt stopped on a SQL quoting error at the first aggregate SELECT. No useful diagnosis was produced and no writes occurred.
- Third attempt used a local heredoc piped to `ssh finops-prod-root 'bash -s'` to preserve SQL quoting and completed successfully.

Post-check:

- `/health/ready`: `ready`.

No production API endpoint, response body, payload row, secret, env value, DB mutation, queue mutation, readiness mutation, deploy, restart, requeue, repair, refresh command or worker replay occurred in this boundary.

## Diagnosis Result

Probe scope: `month=2026-06`, `bucket=unsubmitted`.

Expected base no-OA source-version contract from deployed code and snapshots:

- key count: `13`
- hash: `12a6a240c94fcc71`
- category snapshot hash prefix: `b1533c3ad8c74afa`
- keys: `bank_auto_tag_rules_version`, `bank_transaction_category_schema_version`, `bank_transaction_category_snapshot_version`, `no_oa_bank_batch_schema_version`, `no_oa_bank_batch_tag_selection_version`, `oa_attachment_invoice_parser_version`, `oa_projection_sync_version`, `pair_relation_snapshot_version`, `workbench_candidate_match_schema_version`, `workbench_exception_projection_version`, `workbench_exception_rules_version`, `workbench_matching_rules_version`, `workbench_read_model_schema_version`

Actual bounded no-OA row source-version contract:

- row count: `8`
- unique source-version hash count: `1`
- row source-version hash: `6d33251a850b453d`
- key count: `15`
- actual category snapshot hash prefix: `b1533c3ad8c74afa`
- actual category snapshot equals expected: `true`
- mismatch reasons: none
- keys: expected base keys plus `bank_detail_source_versions` and `workbench_relation_source_versions`
- generated range: `2026-06-25 05:02:08.541922+08:00` to `2026-06-25 05:02:08.562119+08:00`
- updated at: `2026-06-25 05:02:08.743141+08:00`

Global top no-OA source-version distribution:

- top source-version group row count: `80`
- hash: `6d33251a850b453d`
- category snapshot equals expected: `true`
- mismatch reasons: none

Category snapshot metadata:

- category snapshot hash: `b1533c3ad8c74afa`
- `app.bank_transaction_categories` row count: `17`
- category rows latest update: `2026-06-23 20:30:47.661717+08:00`
- category event count: `315`
- category events latest occurred at: `2026-06-23 20:30:47.622593+08:00`
- active confirmation count: `110`
- active confirmations latest confirmed at: `2026-06-23 20:30:47.661717+08:00`

Dirty/outbox/readiness evidence:

- Dirty `no_oa_bank_batch:2026-06`: `done`, count `1`, latest `2026-06-19 00:45:40.128449+08:00`.
- Dirty `no_oa_bank_batch:all`: `done`, count `28067`, latest `2026-06-25 05:02:09.049344+08:00`.
- Outbox `no_oa_bank_batch.read_model.refresh` in last 48h: `done`, count `2729`, latest `2026-06-25 05:02:09.054545+08:00`.
- App Status readiness: `no_oa_bank_batch:all` is `fresh`, latest `2026-06-25 05:02:09.052821+08:00`.
- Dead letters in last 7d: none.

Root cause classification:

- Row275's `bank_transaction_category_snapshot_version_mismatch` is no longer present on the bounded no-OA probe scope after the Row277-era completed `no_oa_bank_batch:all` refreshes.
- This boundary found no no-OA code-contract drift for the current deployed expected base contract: extra downstream row keys are ignored by the mismatch helper, and the expected category snapshot now matches the actual row category snapshot.
- No bounded no-OA repair/rebuild is justified from current evidence. A future production API/browser smoke may still need to prove user-visible no-OA response status, but the specific category source-version mismatch is closed by read-only evidence.

Next safe action:

- Reconcile Row278 as `production-diagnosis-closed`.
- Select a planning boundary to choose the next remaining global closure gap instead of issuing a no-OA refresh/rebuild.
