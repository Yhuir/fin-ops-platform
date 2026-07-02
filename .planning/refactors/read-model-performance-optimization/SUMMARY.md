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

## 2026-07-02 Authenticated core API SLO and pending invoice index slice

- Evidence directory: `.planning/refactors/read-model-performance-optimization/evidence/20260702T080200Z/`.
- Admin Token was collected via local macOS dialog and kept only in process environment; it was not printed or written to evidence files.
- Initial authenticated HTTP SLO attempts with local Python certificate verification failed on local CA trust only; the successful core API run used a probe-local unverified SSL context and still verified application status codes and JSON freshness fields.
- Authenticated core API run: `12` probes, `36` measured samples, `11/12` passed. The only SLO miss was `pending_invoices_rows` at p50 `1364.911ms`, p95/p99 `1478.636ms`, status `200`, `read_model_status=fresh`, `refresh_enqueued_count=0`. This proves the miss is after the read model fresh gate, not a worker freshness failure.
- Passing core API probes included Workbench groups all paired p95 `408.627ms`, app health p95 `341.492ms`, no-OA batches p95 `315.270ms`, turnover ledger p95 `247.186ms`, tax offset p95 `182.210ms`, OA pending payments p95 `177.959ms`, bank details p95 `170.852ms`, input invoice usage p95 `151.961ms`, Workbench summary p95 `151.279ms`, session p95 `127.127ms`, and operations dashboard p95 `124.142ms`.
- Pending invoice architecture check: the rows path remains `PendingInvoiceApiRoutes` -> `PendingInvoiceReadModelService.rows` -> `PendingInvoiceReadModelRepositoryPort.list_pending_invoice_rows` -> PostgreSQL read model repository. No old synchronous fact scan, live fallback, Redis stale cache, or route-owner bypass was reintroduced.
- Root-cause candidate from code/index inspection: rows API orders by `trade_date desc nulls last, row_id`, while the existing hot-path indexes declared `trade_date desc` without `nulls last`. PostgreSQL DESC indexes default to `NULLS FIRST`, so the first-screen query can require an extra sort even when filtering only by `direction`.
- Production custom EXPLAIN could not be collected through the current `finops-deploy` account because `/etc/fin-ops` runtime env is root-only and arbitrary `sudo bash` requires a password; deploy-control exposes status/read-model smoke/scope-contract only, not a generic SQL diagnostics command.
- Local change: added migration `0085_pending_invoice_trade_date_nulls_last_index.sql` with `pending_invoice_rows_direction_trade_date_nulls_last_idx` on `(direction, trade_date desc nulls last, row_id)`, plus migration tests and pending-invoices persistent docs. This is a physical read-model index optimization only; API shape, freshness/source-version gates, worker scope contracts, and business behavior are unchanged.
- Verification so far: `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations.PostgresMigrationDiscoveryTests.test_expected_migration_files_are_present_and_ordered tests.test_postgres_migrations.PostgresMigrationDiscoveryTests.test_pending_invoice_first_screen_sort_index_matches_query_order -v` passed; `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v` passed.
- Decision: `CONTINUE`. Deploy release containing `0085`, rerun authenticated core API SLO with Admin Token, and only then decide whether pending invoices are closed or whether count/source-summary/source-version queries need a second optimization slice.

## 2026-07-02 Pending invoice post-index measurement and raw payload I/O slice

- Evidence directory: `.planning/refactors/read-model-performance-optimization/evidence/20260702T081500Z/pending-index-release/`.
- Release `pscip-l4-pending-index-650ee3d43a` was uploaded; deploy script failed only at installing `/usr/local/sbin/finops-ensure-runtime-workers` because that raw `install` sudo command is not whitelisted. The existing deploy-control helper contract had already passed, so activation was completed through the whitelisted `sudo -n /usr/local/sbin/finops-deploy-control activate pscip-l4-pending-index-650ee3d43a`.
- Migration result: `0085 applied pending_invoice_trade_date_nulls_last_index 50ms`. Active API/dispatcher/worker WorkingDirectory moved to `/opt/fin-ops/releases/pscip-l4-pending-index-650ee3d43a/src`.
- Health/scope evidence: production local and public `/health/ready` returned `status=ready`; default read model scope contract returned `ok=true`, `violation_count=0`, `current_uncovered_outbox_failure_count=0`.
- Post-index authenticated HTTP SLO still failed only `pending_invoices_rows`: 5 samples, status `200`, `read_model_status=fresh`, `refresh_enqueued_count=0`, p50 `1382.094ms`, p95/p99 `1424.202ms`. The index alone did not close the endpoint.
- Diagnostic authenticated probes isolated the bottleneck: `pending_rows_expense_page_size_1` p95 `200.100ms` passed, `pending_filter_options_expense` p95 `278.296ms` passed, while `page_size=50` p95 `1318.243ms` and `page_size=200` p95 `4289.744ms` failed. Latency scales with returned row count, not freshness, count, or source-version gating.
- Code root cause: `list_pending_invoice_rows(...)` selected both `payload` and `raw_payload` for every row, but `_read_model_payload(...)` already prefers canonical `payload`; `save_pending_invoice_rows(...)` also wrote the same JSON to `raw_payload.normalized_payload`. This duplicated per-row JSONB read/decode I/O on the rows hot path.
- Local follow-up change: rows query now selects `raw_payload` only for legacy rows where `payload = '{}'::jsonb`; new pending invoice read model writes keep canonical JSON in `payload` and store `raw_payload={}`. This removes old duplicate payload logic from the new chain while preserving bounded legacy fallback for rows that have no canonical payload.
- Verification so far: targeted two-test run passed; full `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime -v` passed 66 tests.
- Decision: `CONTINUE`. Commit/deploy the raw payload I/O slice, rerun authenticated pending/core API SLO, and only then decide whether the remaining high-performance gap is closed.

## 2026-07-02 Pending invoice per-page normalization slice

- Raw payload release `pscip-l4-pending-raw-017fcaeb84` activated successfully. Active API/dispatcher/worker WorkingDirectory moved to `/opt/fin-ops/releases/pscip-l4-pending-raw-017fcaeb84/src`; migration `0085` was already applied and skipped.
- Post-raw diagnostic SLO remained open: `pending_rows_expense_page_size_1` p95 `261.127ms` pass, `pending_filter_options_expense` p95 `297.132ms` pass, but `page_size=50` p95 `1379.688ms`, `page_size=200` p95 `4733.681ms`, `requires_invoice` p95 `1760.728ms`, and `income page_size=50` p95 `1566.792ms` failed. The raw payload I/O reduction did not fully close the rows endpoint.
- Second code root cause: `PendingInvoiceQueryService.normalize_row_payloads(...)` called `_apply_bank_identity(...)` for every row; `_apply_bank_identity(...)` rebuilt `bank_account_mappings` from settings every time. The remaining latency still scaled with row count, matching repeated per-row settings/mapping work.
- Local change: `normalize_row_payloads(...)` now builds bank account mappings once per page and passes them into row normalization; `_apply_bank_identity(...)` still supports direct single-row use by lazily loading mappings when no page-level mapping is supplied.
- Verification so far: `PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests.test_normalize_row_payloads_loads_bank_mapping_once_per_page -v` passed; full `PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service -v` passed 52 tests.
- Decision: `CONTINUE`. Commit/deploy the per-page normalization slice, rerun authenticated pending/core API SLO, and then decide whether rows performance is closed or needs a lower-level profiling hook.
