---
status: resolved
trigger: "After deploying the latest code, App Status still shows blocked with Workbench read model generation consistency failed for Jia Xiaohua turnover manual closure rows."
created: "2026-06-21"
updated: "2026-06-21"
---

# Debug Session: turnover-closure-workbench-paired-generation

## Symptoms

- Expected behavior: confirming an external turnover closure shows "收支闭环" in the turnover ledger rows and shows the same `turnover_manual_closure` active case in the reconciliation workbench paired area.
- Actual behavior: production App Status reports `Workbench read model generation consistency failed`; Workbench scopes `2026-02`, `2026-03`, and `all` stay refreshing/backlogged.
- Error/status: `active_relation_open_membership` consistency failures for `txn_imported_1277`, `txn_imported_1292`, and `txn_imported_1344`.

## Current Focus

- hypothesis: the write path is no longer the blocker; Workbench generation demotes already-written `turnover_manual_closure` active relation rows to open/temp because grouping still treats bank-only closure as incomplete.
- second_hypothesis: after the grouping fix and schema bump, monthly rebuild can still be skipped by the repository stale-source guard because it compares only numeric `source_version` and ignores builder/schema mismatches.
- test: Workbench grouping and SQL projection tests must require `turnover_manual_closure` multi-bank rows to publish as paired `case:*`, not open/temp.
- expecting: before the fix, SQL projection emits the three bank rows in open and production consistency checker reports `active_relation_open_membership`; after the fix, the rows are in paired and no open owner remains.
- third_hypothesis: production App Status may remain blocked even after Workbench scopes are fresh if the runtime readiness summary query itself fails while computing current-effective dirty scopes.
- fourth_hypothesis: production may still show refreshing/backlog if `workbench:all` aggregate-only events are rapidly deferred while parent month scopes wait behind them in RabbitMQ/Postgres queue order.
- next_action: closed; production release verified with clean App Status, clean raw outbox/dirty scopes, fresh Workbench scopes, and paired Jia Xiaohua rows.

## Evidence

- Production release was current (`main-3531b99e-20260621230102`), so the remaining blocker was not an old deployment.
- Production `get_workbench_refresh_status` showed active generation consistency failures for `2026-02`, `2026-03`, and `all`. Samples were the three Jia Xiaohua bank rows in the active case `turnover:turnover_rel_89e8fb47e3ffce91`.
- `app.workbench_pair_relations` already contained the `turnover_manual_closure` active relation, but Workbench generation published its rows to open/temp owners.
- Code inspection found SQL projection writes `relation_mode=turnover_manual_closure` and relation code `turnover_manual_closure`; `WorkbenchCandidateGroupingService._is_paired_row()` did not recognize that code and `_paired_group_has_enough_row_types()` demoted pure bank groups.
- Production deployment of the grouping fix loaded the new code, but `rehydrate-workbench-read-models.py` still saw old monthly active generation IDs. The month rebuild had been skipped because `save_workbench_read_models(...)` considered incoming `source_version` lower than the existing active generation, without comparing the changed builder schema.
- After the second deploy and targeted rehydrate, production placed the three rows in `zone=paired`, `group_id=case:turnover:turnover_rel_89e8fb47e3ffce91` for scopes `2026-02`, `2026-03`, and `all`.
- Direct production invocation of `RuntimeMonitoringRepository.ready_health_summary()` then failed with PostgreSQL `syntax error at or near "{"` because the ready summary dirty-scope query sent `{_current_effective_dirty_scope_predicate_sql()}` as literal SQL.
- After fixing/deploying the ready summary SQL, production still had `workbench` dirty scopes `2026-01`, `2026-02`, and `2026-04` pending. Non-done outbox rows showed many `workbench:all` aggregate-only events repeatedly deferred with `workbench_read_model_not_fresh: parent_scope_keys=2026-02`, while parent month dirty scopes were still pending.
- After fixing/deploying the same-scope parent backoff, production `ready_health_summary()` reported no backlog/dirty/failed jobs and Workbench scopes were fresh, but `app_status_runtime_snapshot()` still reported an old `oa.sync` failed row from 2026-05-28 even though direct `status <> 'done'` outbox SQL showed no current `oa.sync` rows.
- Final production release `main-3531b99e-20260621235050` reports `/health/ready status=ready`, `runtime_blockers=null`, `ready_health_summary.queue_backlog={}`, `failed_jobs=0`, no dirty scope backlog, and `app_status_runtime_snapshot()` has empty read_model/outbox/worker attention.
- Raw production `job.outbox_events where status <> 'done'` and `job.read_model_dirty_scopes where status <> 'done'` are both empty after covered Workbench dead-letters were resolved through `runtime_queue_ops resolve-covered-dead-letters --execute` with `fresh_readiness` and `later_done` proof.
- Production Workbench scopes `2026-01`, `2026-02`, `2026-03`, `2026-04`, and `all` are `read_model_status=fresh` and `consistency_status=fresh`.
- Jia Xiaohua rows `txn_imported_1277`, `txn_imported_1292`, and `txn_imported_1344` are in `zone=paired`, `payload_status=paired`, `relation_mode=turnover_manual_closure`, `group_id=case:turnover:turnover_rel_89e8fb47e3ffce91` for scopes `2026-02`, `2026-03`, and `all`.

## Eliminated

- Old release: eliminated by production systemd release path matching the latest deployed commit.
- Missing Workbench relation write: eliminated because production consistency samples came from an active `turnover_manual_closure` case.
- Queue cleanup alone: eliminated because the failed job would be retried into the same inconsistent generation until grouping is fixed.

## Resolution

- root_cause: current Workbench grouping still implemented the older "bank-only turnover closure stays open" rule. That rule conflicts with the current product contract and with generation consistency, because active relation rows cannot be published as non-canonical open/temp rows.
- root_cause_2: Workbench repository publish guard treated lower numeric `source_version` as stale even when the incoming builder/schema version changed. That let the API mark old generations stale/refreshing while the actual monthly generation write was skipped.
- root_cause_3: `ready_health_summary()` had a string interpolation bug in its dirty-scope current-effective predicate. The App Status/ready diagnostic path could fail independently from the Workbench generation path, so the UI still showed runtime blockers after the business read model was repaired.
- root_cause_4: same-scope parent dependency defer reused the global fast dependency retry delay. In RabbitMQ transport this rapidly republished `workbench:all` aggregate-only events, so all-scope retries could starve the actual month shard refreshes that would make the parent dependency fresh.
- root_cause_5: App Status outbox aggregation included rows with `publish_status in ('publishing','failed')` regardless of `status`. A historical `status='done'` `oa.sync` row with stale `publish_status='failed'` was mapped back to current failed, while ready summary correctly ignored it.
- fix: classify rows whose `relation_mode` and relation code are both `turnover_manual_closure` as paired rows, allow multi-bank `turnover_manual_closure` active relation groups to remain paired, bump Workbench SQL/legacy schema versions, require the stale-source write skip to compare source-version signatures before skipping, interpolate the ready summary current-effective dirty-scope SQL before sending it to PostgreSQL, make same-scope parent dependency events use retry-level defer delay so parent shards can drain first, and align App Status outbox SQL with current-effective ready summary semantics so done publish failures do not surface as current failures.
- verification: local targeted suites pass; docs check passes; production deploy/drain verified; App Status and raw runtime queues are clean.
- files_changed: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`, `backend/src/fin_ops_platform/services/workbench_sql_projection.py`, `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`, `backend/src/fin_ops_platform/services/runtime_monitoring.py`, `backend/src/fin_ops_platform/services/runtime_worker.py`, `backend/src/fin_ops_platform/app/server.py`, `tests/test_workbench_turnover_grouping.py`, `tests/test_workbench_sql_runtime.py`, `tests/test_turnover_workbench_integration.py`, `tests/test_runtime_monitoring.py`, `tests/test_runtime_worker.py`, docs, and this debug session.
