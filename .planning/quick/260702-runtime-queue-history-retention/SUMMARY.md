---
status: complete
slug: runtime-queue-history-retention
completed_at: 2026-07-02
---

# Runtime queue history retention summary

## Delivered

- Added controlled retention for `job.outbox_events` and `job.read_model_dirty_scopes` through `RuntimeQueueRepository`.
- Added `python -m fin_ops_platform.tools.runtime_queue_ops prune-history --dry-run|--execute`.
- Added PostgreSQL migration `0084_runtime_queue_history_retention.sql` with done-history retention indexes and delete permission only for the migrator role.
- Added production helper and systemd timer examples installed by `finops-deploy-control activate`.
- Updated runtime worker/read model boundary docs and operations docs.

## Boundary / I/O Decisions

- Repository owns queue-history SQL and is the only application code boundary allowed to compute candidates or delete rows.
- CLI input is limited to `keep_days`, `keep_recent_per_type`, `limit`, and `--dry-run|--execute`; output is JSON with policy, candidates, deleted counts, and grouped summaries.
- Production execution uses root-owned scripts plus the PostgreSQL migrator DSN; API and worker roles do not get delete permission.
- Retention deletes only `status = 'done'`.
- Dirty scope retention preserves the latest done row per exact `(tenant_id, scope_type, scope_key)` so future enqueue operations retain source-version monotonicity.
- Done outbox rows are not deleted when they are the same-scope proof for unresolved failed or dead-lettered events.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_queue_ops tests.test_deploy_runtime_examples tests.test_deploy_oa_script tests.test_postgres_migrations -v`
- `bash -n deploy/oa/bin/finops-prune-runtime-queue-history.sh deploy/oa/bin/finops-deploy-control.sh`
- `git diff --check`

## Production Follow-up

- Deploy the committed release.
- Run production dry-run first.
- Execute bounded batches only after dry-run confirms candidates are done-history rows.
- Run `VACUUM (ANALYZE)` after deletion to refresh planner statistics; do not use `VACUUM FULL` unless an explicit OS-space reclaim maintenance window is approved.
