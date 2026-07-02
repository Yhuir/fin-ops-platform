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

## 2026-07-02 Workbench raw payload write amplification slice

- Evidence directory: `.planning/refactors/read-model-performance-optimization/evidence/20260702T071757Z/workbench-profile/`.
- Production profile on release `pscip-l4-workbench-insert-5f530d1b5`: recent `workbench:all` aggregate handlers were `7.7s-16.3s`; `workbench:2026-02` month shard handlers were usually `1.1s-3.5s`.
- Active all generation size: `1701` workbench rows, `960` groups, `1941` group_rows. Table stats showed no dead tuple blocker; active detail count queries were millisecond-level.
- Shadow profile without writes: all aggregate read+CPU path took `3309.583ms` (`consistency_check=375.700ms`, `fetch_active_month_groups=239.949ms`, `normalize_groups=420.521ms`, `aggregate_payload=1104.259ms`, `iter_rows_and_groups=687.310ms`, `build_group_row_records=454.940ms`). Remaining production latency is write amplification plus runtime variance.
- Local change: new Workbench generation writes keep canonical `payload` unchanged but stop duplicating the same JSON into `raw_payload.normalized_payload`; `raw_payload` is written as `{}` for Workbench snapshot, summary, rows, groups, and group_rows. Old data fallback remains in `_read_model_payload(...)`; new chain no longer carries the duplicate raw payload branch.
- Local verification: `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py -q` passed `178`; `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py tests/test_runtime_worker.py tests/test_read_model_slo_smoke.py tests/test_postgres_connection.py -q` passed `211`.
- Decision: `CONTINUE`. This is a bounded persistence I/O reduction, not a full high-performance closure. It must be released and measured with Workbench targeted SLO and critical grouped SLO before claiming improvement.

## 2026-07-02 Workbench raw payload release evidence

- Evidence directory: `.planning/refactors/read-model-performance-optimization/evidence/20260702T075500Z/workbench-raw-release/`.
- Release `pscip-l4-workbench-raw-51cba11e8` deployed from commit `51cba11e82d5b439da72633dbcc92ea48c350b79`; `/health/ready` returned `status=ready` and runtime metadata pointed to `/opt/fin-ops/releases/pscip-l4-workbench-raw-51cba11e8/src`.
- Scope contract default and invalid-scope checks both passed: default `ok=true`, `violation_count=0`, current uncovered outbox failures `0`; invalid read model scopes `0`.
- Critical read model 5s SLO passed `16/16`: max enqueue-to-fresh `3581.490ms`, p50 `568.217ms`, p95 `3581.490ms`; max handler duration `3391.024ms`.
- Targeted `workbench:all` 1s SLO passed: enqueue-to-fresh `397.159ms`, handler `352.381ms`.
- Production raw payload proof: active `workbench:all` generation has `1701` rows, `960` groups, `1941` group_rows, and snapshot/summary/details all have `raw_payload={}` with `raw_has_normalized=0` while canonical `payload` remains non-empty. Active `workbench:2026-02` generation shows the same contract.
- Write-operation audit since release activation (`2026-07-02T07:39:48+00:00`) still failed because all selected confirm/withdraw/no-OA withdraw expectations are `missing` (`51/51`). There is no current-release real write sample proving association withdraw or cross-page fan-out latency.
- Decision: `CONTINUE`. The read model and Workbench persistence performance slice is production-verified; full PSCIP-L4/high-performance closure still needs authenticated page/API evidence or approved controlled real write samples for confirm/withdraw/no-OA withdraw.

## 2026-07-02 Write-operation readonly re-audit

- Evidence directory: `.planning/refactors/read-model-performance-optimization/evidence/20260702T075056Z/write-operation-readonly/`.
- Current-release audit since `2026-07-02T07:39:48+00:00`: `event_sample_count=97`, `expectation_count=51`, `failed_expectation_count=51`, `missing_expectation_count=51`, non-missing result count `0`. This confirms no real confirm/withdraw/no-OA withdraw sample has occurred on release `pscip-l4-workbench-raw-51cba11e8`.
- 24h audit for the same operation set: `event_sample_count=4000`, `expectation_count=51`, non-missing result count `46`, `failed_expectation_count=51`, `missing_expectation_count=5`. Slowest historical p95s remain in cross-page downstream scopes: `input_invoice_usage` p95 `64829.108ms`, `invoice_lifecycle` p95 `53546.114ms`, and `workbench` p95 `45572.779ms`.
- Read-only scenario discovery found candidate controlled-withdraw contexts: `5` turnover manual relations, `5` Workbench pair relations, and `3` no-OA submitted batches. The discovery tool reports `mutates_data=false` and `requires_manual_approval_before_apply=true`.
- Decision: `CONTINUE but externally gated`. There is no safe smaller code change to prove write-operation closure without a real post-release sample. The next bounded action must be either approved authenticated HTTP/API smoke with Admin Token, or explicit approval to run one reviewed reversible scenario; otherwise the goal remains open with the write-operation evidence gap.
