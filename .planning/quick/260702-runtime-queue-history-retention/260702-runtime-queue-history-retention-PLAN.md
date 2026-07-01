# Quick Task 260702: Runtime queue history retention

## Objective

为 `job.outbox_events` 与 `job.read_model_dirty_scopes` 增加受控 retention，避免完成态历史无限增长占满磁盘，同时不影响当前 App 使用、read model freshness、worker 重试和 dead-letter 诊断。

## Modular Boundary / I/O

- Owner boundary: `RuntimeQueueRepository` owns retention SQL for job queue tables.
- CLI boundary: `fin_ops_platform.tools.runtime_queue_ops prune-history` exposes dry-run and execute only through repository methods.
- Deploy boundary: versioned helper/timer is installed by `finops-deploy-control activate`; production helper uses the root-only migrator DB env for delete permission.
- Input: `keep_days`, `keep_recent_per_type`, `limit`, `dry-run|execute`.
- Output: JSON/log counts by table and event/scope type, candidate/deleted count, cutoff policy.
- Safety invariant: delete only `status = 'done'` history, keep pending/processing/failed/dead-lettered, preserve recent samples per type, and avoid deleting done proof for unresolved failed/dead-lettered same-scope events.

## Tasks

1. Add repository retention methods and CLI subcommand with tests.
2. Add migration indexes and migrator delete grant for bounded high-performance delete.
3. Add versioned deploy helper, service, timer, and deploy-control contract checks.
4. Update module/operations docs.
5. Run local verification, deploy to production, run dry-run then execute smoke.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_queue_ops tests.test_deploy_runtime_examples tests.test_deploy_oa_script -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`
- `git diff --check`
- Production: deploy release, check timer/helper installed, dry-run retention, execute one or more bounded batches, verify `/health/ready`, queue status, table sizes.
