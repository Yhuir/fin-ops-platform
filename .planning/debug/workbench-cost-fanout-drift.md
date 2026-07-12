---
status: fixing
trigger: "Production System Audit regressed from 16/16 to 15/16 because Workbench source versions advanced while cost statistics stayed fresh/drained on older upstream versions."
created: 2026-07-12
updated: 2026-07-12
---

# Workbench to Cost Statistics Fan-out Drift

## Symptoms

- Expected: after imports, relation confirm/withdraw, OA sync, or any legitimate Workbench generation change, affected read models converge asynchronously without manual refresh; stale downstream projections must not report fresh.
- Actual: Workbench refreshed through 19:54 while cost statistics last refreshed at 19:20; durable queue was drained and cost statistics still reported fresh.
- Error: production System Audit returned 15/16 with 38 `cost_statistics_upstream_source_versions_mismatch` issues.
- Timeline: a 19:20 production snapshot passed 16/16; by 19:56 Workbench source versions had advanced again and cost statistics no longer matched.
- Reproduction: allow normal production background Workbench refreshes after a passing snapshot, then run the read-only System Audit without manually refreshing cost statistics.

## Current Focus

- hypothesis: confirmed dual boundary failure: cost refresh was scheduled in parallel with Workbench rather than after active-generation publication, and the cost query expected-set omitted current Workbench source versions.
- test: Workbench month publication must enqueue active/all cost month scopes after projection commit and before completing the Workbench dirty scope; a cost API read built from an older Workbench generation must return refreshing and enqueue repair.
- expecting: normal asynchronous operation converges without a manual cost refresh, and stale cost data cannot report fresh.
- next_action: run architecture/lint/full regressions, deploy the exact commit, trigger only an upstream Workbench refresh, and prove cost automatically converges before a 16/16 read-only System Audit.
- reasoning_checkpoint: Workbench `source_version` is the durable dirty-scope commit sequence consumed by cost lineage; deleting it would hide a real ordering failure. The producer must sequence the dependent refresh instead.
- tdd_checkpoint: targeted cost-statistics and Workbench SQL runtime suites pass with publication-order and stale-fresh-gate regressions.

## Evidence

- 2026-07-12 19:56: System Audit `system-audit:1deeb8b8658d948dd279c6b3` passed 15/16; only cost statistics failed.
- 2026-07-12: cost scopes embedded Workbench versions such as 2504/334 while current versions were 2511/341.
- 2026-07-12: App Health runtime metrics showed Workbench last completed at 19:54:52 and cost statistics last completed at 19:20:29, with no current outbox backlog.
- 2026-07-12 production convergence proof: an operator enqueued only `workbench=all`; Workbench publication automatically created 38 cost-statistics events. Production then exposed a missing facade delegate: the narrow method existed on `PostgresSummaryReadModelRepository`, while the worker receives the composed `PostgresReadModelRepository`.

## Eliminated

- hypothesis: The failure is only a stale queue still being processed.
  reason: production Audit reported `freshness=fresh` and `queue=drained`, and the mismatch persisted across repeated read-only checks.
- hypothesis: A manual cost refresh permanently closes the issue.
  reason: a manual gateway refresh produced a passing snapshot, but later Workbench version advances recreated the mismatch.
- hypothesis: Filtering the exact Workbench `source_version` from cost lineage is a safe fix.
  reason: cost rows are derived from the Workbench active generation, and this version is the only durable commit sequence in that generation's source_versions. Filtering it would allow real upstream row changes to remain invisible.

## Resolution

- root_cause: Business lifecycle events enqueue Workbench and cost statistics independently, so cost can finish from the old active generation before Workbench publishes the new one. Workbench publication did not enqueue a dependent cost refresh. Separately, the cost API expected source versions omitted `workbench_source_versions`, so the query gateway could label that stale snapshot fresh even though Audit compared and rejected it.
- fix: Add a narrow repository port for current Workbench active-generation source versions; use it in both the cost projection builder and API expected-set. After a Workbench month shard publishes, enqueue normalized active/all cost month scopes through `ReadModelRefreshGateway` before completing the Workbench dirty scope. Do not fan out from the compatibility all aggregate.
- hardening: Preserve fail-closed behavior, durable queue ordering, tenant/priority/trace propagation, parent fan-out from cost shard completion, and remove the builder's duplicate raw SQL version reader.
- verification: initial targeted/full verification passed, but the production composed repository caught the missing delegate. A production-shaped facade/port regression and hotfix are in progress before rerunning the same upstream-only convergence proof.
- files_changed: `workbench_read_model_refresh.py`, `cost_statistics_read_model_repository.py`, `postgres_repositories/read_models.py`, `cost_tax_sql_projection.py`, `app/server.py`, tests, and boundary docs.
