# Production Post-Convergence Readiness Worker DB Aggregate Evidence Sweep 2026-06-25

**Boundary:** `production:post-convergence-readiness-worker-db-aggregate-evidence-sweep`
**Final status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `d6583295c9f15c7ee78ddc7b713986b5cf6cf6d5`

## Scope

Collect non-secret read-only production aggregate evidence after the PostgreSQL, app/worker and no-OA convergence operations.

Allowed:

- root SSH identity;
- systemd status for API, dispatcher and required worker units;
- `/health` and `/health/ready` structured summaries;
- read-only PostgreSQL aggregate queries for queue, dirty scopes, readiness and no-OA exact scope.

Forbidden:

- DB writes;
- requeue, resolve, repair, deploy, restart, worker replay or readiness mutation;
- printing env files, DSNs, passwords, tokens, cookies, private keys or secret env values.

## Evidence Results

Executed as a non-secret read-only production sweep over systemd status, `/health`, `/health/ready`, PostgreSQL aggregate queries and selected worker logs.

### Release and Health

- Active release: `dev-no-oa-fk-20260625014906`.
- Active git commit: `cc43e262eeb13c1a459d0f96e991666d0db2f280`.
- API working directory: `/opt/fin-ops/releases/dev-no-oa-fk-20260625014906/src`.
- `/health`: HTTP 200, `status=ready`, release identity consistent, production runtime guard consistent.
- `/health/ready`: HTTP 200 in about 0.547s, `status=ready`.
- `/health/ready` summary:
  - `queue_backlog={}`;
  - `failed_jobs=0`;
  - `stale_dirty_scope_count=0`;
  - required worker missing/stale/mismatch counts all `0`;
  - RabbitMQ queue/unacked/dead-letter counts all `0`;
  - `worker_status_counts={"available": 21}`.

### Systemd Worker Evidence

- `fin-ops.service` and `fin-ops-rabbitmq-dispatcher.service` were `active/running` from the deployed release with `NRestarts=0`.
- Most required worker units were `active/running` with `NRestarts=0`.
- `fin-ops-worker@workbench-matching.service` was not stable:
  - initial check: `ActiveState=activating`, `SubState=auto-restart`, `Result=exit-code`, `NRestarts=68`;
  - stability recheck after about 15s: still `activating/auto-restart`, `NRestarts=72`, `ExecMainStatus=1`, `MainPID=0`.

### Database Aggregate Evidence

- `job.read_model_dirty_scopes`: only `done=187007`; no active non-done dirty scopes.
- `read_model.app_status_readiness`: `fresh=498`.
- `job.outbox_events`: `done=203145`, `dead_lettered=24`.
- Current dead-letter classification:
  - `no_oa_bank_batch.read_model.refresh no_oa_bank_batch all`: 13 historical dead-letter rows;
  - `pending_invoice.read_model.refresh pending_invoice expense:all:2026-05`: 1 historical dead-letter row;
  - Workbench read-model refresh rows for `2025-04`, `2025-09`, `2025-11`, `2025-12`, `2026-01`, `2026-02`, `2026-03`, `2026-04`, `2026-05`, `2026-06`: 10 historical dead-letter rows.
- Exact no-OA event `3bc506fd-5662-4902-a9b9-19b0d8fbe4a6` is `done`.
- `no_oa_bank_batch` readiness rows are all `fresh`.

### Readiness By Read Model

- `bank_account_balance`: 1 fresh.
- `bank_detail`: 41 fresh.
- `cost_statistics`: 66 fresh.
- `input_invoice_usage`: 33 fresh.
- `invoice_lifecycle`: 32 fresh.
- `no_oa_bank_batch`: 8 fresh.
- `oa_pending_payment`: 34 fresh.
- `output_invoice_collection`: 33 fresh.
- `pending_invoice`: 126 fresh.
- `search`: 33 fresh.
- `tax_offset`: 19 fresh.
- `turnover_ledger`: 1 fresh.
- `workbench`: 33 fresh.
- `workbench_relation`: 38 fresh.

### Worker Log Evidence

`fin-ops-worker@workbench-matching.service` logs show a deployed-code constructor mismatch:

```text
TypeError: WorkbenchMatchingOrchestrator.__init__() got an unexpected keyword argument 'pair_relation_service'
```

The traceback points to deployed `backend/src/fin_ops_platform/services/runtime_worker_handlers.py` in `build_dirty_scope_worker(...)` while constructing `WorkbenchMatchingOrchestrator(...)`.

## Conclusion

The post-convergence production DB/readiness aggregate is clean for active dirty scopes, no-OA readiness, exact no-OA convergence and `/health/ready`. However, the systemd-level `workbench-matching` worker is in an active restart loop caused by a local deployed code bug. This blocks production worker closure even though App Status currently reports required workers available.

No DB writes, requeue, resolve, repair, deploy, restart, worker replay, readiness mutation or secret output occurred in this boundary.

Next boundary: `runtime-workers:workbench-matching-orchestrator-constructor-fix`.
