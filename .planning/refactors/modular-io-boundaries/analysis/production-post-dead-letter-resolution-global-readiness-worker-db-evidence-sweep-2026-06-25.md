# Production Post Dead Letter Resolution Global Readiness Worker DB Evidence Sweep 2026-06-25

**Boundary:** `production:post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep`
**Final status:** `production-controlled`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `861f83a9f8c7bfe5618732484a6e65d8aa4e39d3`
**Production release for checks:** `dev-workbench-matching-port-20260625020818`

## Target

Collect a non-secret read-only production baseline after the historical read-model dead-letter cleanup. This boundary establishes whether current production health, worker status, queue state, dirty scopes and App Status readiness are clean enough to select module-specific production closure audits next.

This boundary must not mutate production.

## Allowed Operations

- Public `/health` and `/health/ready` checks.
- Root SSH read-only `systemctl show` and `journalctl` sampling for API, dispatcher and worker units.
- Deployed-runtime read-only PostgreSQL aggregate checks through existing production configuration without printing secrets.
- Read-only dry-run of `runtime_queue_ops resolve-covered-dead-letters --limit 100 --dry-run` if needed to confirm no covered residue remains.

## Forbidden Operations

- Deploy, restart, reload, stop, start or kill production services.
- Requeue, republish, repair, resolve, worker replay or broad queue consume.
- Direct SQL `insert`, `update`, `delete`, DDL or readiness/dirty-scope mutation.
- Printing env files, DSNs, passwords, tokens, cookies, private keys or secret env values.

## Evidence Plan

1. Summarize `/health` and `/health/ready` without storing sensitive payloads.
2. Capture selected `systemctl show` fields for:
   - `fin-ops.service`;
   - `fin-ops-rabbitmq-dispatcher.service`;
   - all active `fin-ops-worker@*.service` units.
3. Query deployed-runtime aggregate tables:
   - `job.outbox_events` status counts and read-model dead-letter groups;
   - `job.read_model_dirty_scopes` status counts and non-done samples;
   - `read_model.app_status_readiness` status counts and non-fresh samples.
4. Grep recent required worker logs for `Traceback`, `TypeError`, `PoolTimeout`, shared-memory errors, dead-letter failures and failed main process exits.

## Stop Gates

Classify the boundary precisely and stop if:

- `/health/ready` is not ready or times out.
- Any active dirty scope or non-fresh readiness row appears.
- Dead-letter groups return.
- Required worker units are missing, stale, mismatched or actively restarting.
- Evidence collection would require printing secrets or mutating production.

## Execution Results

Executed non-secret read-only production evidence collection against release `dev-workbench-matching-port-20260625020818`.

### Health And Release Identity

`/health` returned:

- `status=ready`;
- release `dev-workbench-matching-port-20260625020818`;
- git commit `b256db3a8fc370ce93e7b51bf62b1cd33176475d`;
- release metadata `consistent=True`;
- production runtime guard `consistent=True`;
- storage backend `postgres`;
- bootstrap mode `production`.

`/health/ready` returned:

- `status=ready`;
- release `dev-workbench-matching-port-20260625020818`;
- git commit `b256db3a8fc370ce93e7b51bf62b1cd33176475d`;
- release metadata `consistent=True`;
- production runtime guard `consistent=True`;
- `queue_backlog={}`;
- `dirty_scopes={"done": 187007}`;
- `failed_jobs=0`;
- `stale_dirty_scope_count=0`;
- required worker missing/stale/mismatch counts all `0`;
- RabbitMQ queue depth, unacked and DLQ counts all `0`;
- `worker_status_counts={"available": 21}`;
- `read_model_refresh_failure_rate=0.0`;
- pending outbox, dirty scope and stale dirty summaries all had `count=0`.

`/health/ready` still reports two old non-required worker problem samples:

- `operator-cost-statistics-drain-after-deploy-20260606`;
- `codex-oa-pending-payment-refresh-2`.

Both samples are `required=False` and `current_effective=False`; they are not current required-worker blockers.

### Systemd Status And Stability

Initial `systemctl show` sampled:

- `fin-ops.service`;
- `fin-ops-rabbitmq-dispatcher.service`;
- 20 active `fin-ops-worker@*.service` units.

All sampled API, dispatcher and worker units were:

- `LoadState=loaded`;
- `ActiveState=active`;
- `SubState=running`;
- `Result=success`;
- `NRestarts=0`;
- `ExecMainCode=0`;
- `ExecMainStatus=0`;
- `WorkingDirectory=/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src`.

The worker units sampled were:

- `fin-ops-worker@bank-account-balance.service`;
- `fin-ops-worker@bank-detail.service`;
- `fin-ops-worker@cost-statistics.service`;
- `fin-ops-worker@cost-tax.service`;
- `fin-ops-worker@import.service`;
- `fin-ops-worker@invoice-lifecycle-secondary.service`;
- `fin-ops-worker@invoice-lifecycle.service`;
- `fin-ops-worker@invoice-usage-collection.service`;
- `fin-ops-worker@no-oa-bank-batch.service`;
- `fin-ops-worker@oa-sync.service`;
- `fin-ops-worker@pending-invoice.service`;
- `fin-ops-worker@search-pending.service`;
- `fin-ops-worker@search-secondary.service`;
- `fin-ops-worker@search-tertiary.service`;
- `fin-ops-worker@search.service`;
- `fin-ops-worker@tax-offset.service`;
- `fin-ops-worker@turnover-ledger.service`;
- `fin-ops-worker@workbench-matching.service`;
- `fin-ops-worker@workbench-relation.service`;
- `fin-ops-worker@workbench.service`.

A 15-second stability recheck showed the same API, dispatcher and worker units still `active/running` with `NRestarts=0`, `ExecMainStatus=0` and stable `MainPID` values.

### Deployed-Runtime PostgreSQL Aggregate

Read-only deployed-runtime aggregate:

- `job.outbox_events`: `done=203169`.
- Read-model dead-letter groups: `[]`.
- `job.read_model_dirty_scopes`: `done=187007`.
- Active dirty scope samples: `[]`.
- `read_model.app_status_readiness`: `fresh=498`.
- Non-fresh readiness samples: `[]`.

Readiness by read model:

| Read model | Fresh rows |
| --- | ---: |
| `bank_account_balance` | 1 |
| `bank_detail` | 41 |
| `cost_statistics` | 66 |
| `input_invoice_usage` | 33 |
| `invoice_lifecycle` | 32 |
| `no_oa_bank_batch` | 8 |
| `oa_pending_payment` | 34 |
| `output_invoice_collection` | 33 |
| `pending_invoice` | 126 |
| `search` | 33 |
| `tax_offset` | 19 |
| `turnover_ledger` | 1 |
| `workbench` | 33 |
| `workbench_relation` | 38 |

### Covered Dead-Letter Dry-Run

`runtime_queue_ops resolve-covered-dead-letters --limit 100 --dry-run` returned:

- `mode=dry-run`;
- `candidate_count=0`;
- `eligible_count=0`;
- `events=[]`;
- `resolved_count=0`.

### Recent Worker Log Sampling

Recent logs since `2026-06-25 02:24:00` were sampled for all active `fin-ops-worker@*.service` units with:

- `Traceback`;
- `TypeError`;
- `PoolTimeout`;
- PostgreSQL shared-memory errors;
- `dead_letter` / `dead-letter`;
- `Failed with result`;
- `Main process exited`;
- `FATAL`.

The grep returned only unit headers and no matching error lines.

## Conclusion

Decision: `production-controlled`.

The post-dead-letter cleanup global production baseline is clean:

- `/health` and `/health/ready` are ready and release-consistent.
- Required worker missing/stale/mismatch counts are all `0`.
- All sampled API, dispatcher and worker units are active/running with `NRestarts=0`.
- Queue backlog is empty.
- No read-model dead-letter groups remain.
- Dirty scopes are all done.
- App Status readiness rows are all fresh.
- Recent required-worker log grep found no matching error lines.

This evidence supports selecting module-specific production closure/evidence reconciliation next. It does not by itself prove global modular IO closure, browser/high-row closure or Go admission.

## Docs Impact

No long-term docs update is expected unless the sweep finds a new persistent production fact that changes runtime governance. This boundary collects evidence only and does not change runtime behavior, API contracts, worker state definitions, read model scope policy, permissions or UI behavior.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business logic changed. |
| 2. Service-layer tests | Not applicable | No service/repository/worker code changed. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Covered by production read-only evidence | This boundary inspects queue, dirty scope, readiness and worker status in production. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No cross-module business flow changed. |
| 7. Existing feature regression tests | Covered by production read-only evidence | Safety regression is `/health/ready` stays ready with no queue/readiness/worker residue after cleanup. |

## Verification Plan

- Production read-only health/status/DB/log checks listed above.
- Local repository checks before commit:
  - `bash scripts/verify.sh docs`
  - `git diff --check`
  - `git diff --cached --check`
