# Read Model Performance Optimization Summary

## Result

Wave 1 completed.

Implemented a narrow PostgreSQL index migration for read model refresh metric sampling:

- `outbox_events_read_model_refresh_metric_attention_idx`
- covers `event_type, updated_at desc`
- partial predicate covers both completed duration samples and failed/dead-lettered refresh rows

This keeps `RuntimeMonitoringRepository.health_summary()` / dashboard read-model metric sampling on a bounded index path when the query includes `status='done' OR status in ('failed','dead_lettered')`.

## Files Changed

- `backend/src/fin_ops_platform/postgres/migrations/0076_outbox_read_model_refresh_metric_attention.sql`
- `tests/test_postgres_migrations.py`
- `tests/postgres_test_utils.py`
- `docs/operations/monitoring.md`
- `.planning/refactors/read-model-performance-optimization/PLAN.md`

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_runtime_monitoring -v
bash scripts/verify.sh docs
```

## Deferred

- No business read model projection code was changed.
- No production migration/deploy was applied.
- No mutating production write or forced refresh was executed.

## Master Goal Prompt

Added `.planning/refactors/read-model-performance-optimization/GOAL_PROMPT.md` as the Codex `/goal` controller prompt for closing production deploy, before/after metrics, targeted second-wave optimization, docs, and final risk reporting.

## 2026-06-28 Goal Loop 1 Current-State Analysis

- Current branch/worktree: `main` is dirty with many unrelated changes. Release/deploy must not run from this mixed tree.
- Intended read-model-performance changes currently identified:
  - `backend/src/fin_ops_platform/postgres/migrations/0076_outbox_read_model_refresh_metric_attention.sql`
  - `tests/test_postgres_migrations.py`
  - `tests/postgres_test_utils.py`
  - `docs/operations/monitoring.md`
  - `.planning/refactors/read-model-performance-optimization/*`
- Code evidence: `RuntimeMonitoringRepository.health_summary()` samples each read-model refresh event type through lateral queries ordered by `updated_at desc limit 512`; the metric and slow-event queries include `status in ('failed', 'dead_lettered') or (status = 'done' and runtime_result.duration_ms exists)`.
- Index evidence: migration `0068` only covers completed duration rows; migration `0076` adds `outbox_events_read_model_refresh_metric_attention_idx` on `(event_type, updated_at desc)` with the full completed-or-failed predicate.
- Migration risk: `backend/src/fin_ops_platform/postgres/migrate.py` wraps every migration body in `begin; ... commit;`, so production apply of a new index on `job.outbox_events` must first inspect table size/write rate/lock risk. Do not deploy/apply blindly.
- Production state: not yet checked in this goal run. No production baseline, migration apply, or post-change metrics have been collected in this loop.
- Decision: `CONTINUE` to local verification and clean release isolation; production baseline and lock-risk decision remain required before deployment.

## Next Step

Deploy/apply the migration in a controlled release, then compare production full `/health` or operations dashboard runtime metric latency before/after. If read model refresh handler p95 remains high after the metrics query is fixed, optimize the specific projection handler with fresh `EXPLAIN` evidence.

## 2026-07-02 Goal Continuation - Current Production Revalidation

- Evidence directory: `.planning/refactors/read-model-performance-optimization/evidence/20260702T070901Z/current-production/`.
- Active release: `/opt/fin-ops/releases/pscip-l4-workbench-insert-5f530d1b5/src`; backend cwd matches release; 21 worker template units active, 0 failed.
- `/health/ready`: `status=ready`, worker missing/stale/mismatched `0/0/0`.
- Scope contract: default check exit `0`; invalid read model scope check exit `0`, invalid counts `0` for `job.outbox_events`, `job.read_model_dirty_scopes`, and `read_model.app_status_readiness`.
- Critical read model SLO 5s grouped run: `14/16 pass`, max enqueue-to-fresh `5591.378ms`; failures were `turnover_ledger:all` `5591.378ms` and `bank_flow_rule_batch:2026-02` `5445.482ms`.
- Targeted retry: `turnover_ledger:all` pass `993.910ms`; `bank_flow_rule_batch:2026-02` pass `455.961ms`. Current evidence points to grouped-run tail latency, not a stable handler-specific blocker for those two keys.
- Workbench 1s targeted: still fail, `enqueue_to_fresh_ms=1485.007`, `handler_duration_ms=1181.262`.
- Write operation audit since the release activation time (`2026-07-02T06:57:41+00:00`): fail because required confirm/withdraw/no-OA withdraw samples are missing, not because current release samples are slow.
- Decision: `CONTINUE`. Full PSCIP-L4/high-performance closure is not proven. Next useful step is either authenticated HTTP/page SLO with Admin Token, or a controlled reversible real write sample for confirm/withdraw/no-OA withdraw; without that, only read model worker convergence is evidenced.
