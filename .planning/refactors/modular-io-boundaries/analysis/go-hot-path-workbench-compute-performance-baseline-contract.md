# Go Hot Path Workbench Compute Performance Baseline Contract

**Date:** 2026-06-24
**Boundary:** `go-hot-path:workbench-compute-performance-baseline-contract`
**Slice status:** `planning-closed`
**Module closure:** `go-admission-not-started`

## Goal

Define the candidate-specific Python reference IO, minimum performance evidence, shadow-run comparison, rollback gates and forbidden-write contract for `workbench:matching-grouping-check` before any Go, Go Fiber or Go Worker implementation can enter admission.

This slice does not change Python runtime behavior and does not approve Go implementation.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-performance-baseline-and-admission-reconciliation.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/reconciliation-workbench/implementation-notes.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `docs/operations/runtime-worker-governance.md`
- `backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_worker.py`
- `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`
- `backend/src/fin_ops_platform/services/workbench_matching_rules.py`
- `backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`
- `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`
- `backend/src/fin_ops_platform/services/workbench_amount_check_service.py`
- `backend/src/fin_ops_platform/tools/http_slo_probe.py`
- `backend/src/fin_ops_platform/tools/sync_slo_baseline.py`
- `backend/src/fin_ops_platform/tools/read_model_slo_smoke.py`
- `backend/src/fin_ops_platform/tools/write_operation_slo_audit.py`
- Existing Workbench matching, dirty queue, amount check, reconciliation engine, SLO and write-operation SLO tests.
- CodeGraph context for Workbench matching/grouping/check entry points.

## Python Reference Boundary

`workbench:matching-grouping-check` is not a single pure function today. The production Python reference spans three layers:

1. Worker lifecycle boundary:
   - `WorkbenchMatchingDirtyScopeWorker.run_once()`
   - Claims due scope months from `job.workbench_matching_dirty_scopes`.
   - Requeues completed scopes whose `source_versions` lag the current matching versions.
   - Calls the matching orchestrator once per claimed month.
   - Completes or fails the dirty scope and records worker heartbeat.

2. Compute/orchestration boundary:
   - `WorkbenchMatchingOrchestrator.run(...)`
   - Normalizes changed months.
   - Loads OA, bank and invoice rows for the scope/window.
   - Reads active relations through `WorkbenchMatchingRelationReadPort`.
   - Excludes rows occupied by canonical active relations, except allowed two-pane completion cases.
   - Runs either legacy candidate mode or decision-store mode.
   - Persists candidates/decisions and invalidates `workbench` / `workbench_relation` read models.
   - Emits deterministic run summary counts and duration.

3. Deterministic compute sub-boundaries:
   - `WorkbenchMatchingRules.generate_candidates(...)` for legacy candidate dictionaries.
   - `WorkbenchFreeMatchingEngine.generate_decisions(...)` plus special adapter for SQL decision mode.
   - `WorkbenchReconciliationEngine.run_scope(...)` for decision expiration/upsert and optional two-pane relation auto-completion.
   - `WorkbenchAmountCheckService.check(...)` for relation amount/direction validation.

The Go candidate may target deterministic compute first, but the Python reference remains the whole worker/orchestrator behavior until shadow output proves equivalence and state writes are explicitly migrated.

## Candidate Input Contract

A shadow or future Go compute implementation must receive the same normalized input the Python reference uses:

- `scope_month`: exact `YYYY-MM` month being processed.
- Expanded scope window: months returned by the Python `expand_scope_month_window(...)` contract.
- OA rows, bank rows and invoice rows after Python row-provider normalization, including stable row id, row type, amount/reconciliation amount, dates, direction, counterparty/name/tax evidence, attachment/source metadata, detail fields and source month hints.
- Active relation snapshot from `WorkbenchMatchingRelationReadPort`, including `status`, `case_id`, `row_ids`, `row_types`, `relation_mode`, `month_scope`, `amount_check` and `special_metadata`.
- Settings payload used by matching rules.
- Source-version payload including at least `workbench_matching_rules_version`, `workbench_special_rules_version`, `workbench_exception_rules_version` and Workbench builder/parser/source versions supplied by the current provider.
- Exception/special-rule suppression inputs where the current orchestrator or special adapters use them.

The input must be captured after Python normalization and relation occupancy filtering if the target is compute-only comparison. If Go is later admitted at the orchestrator level, the input contract must also include row-provider and relation-read-port semantics.

## Candidate Output Contract

The Python reference output is the combination of:

- Candidate dictionaries from legacy mode:
  - `scope_month`
  - `rule_code`
  - `row_ids`
  - row type lists / pane-specific row ids
  - `status` such as open/conflict/auto-closed where produced by the candidate service
  - evidence, warning/skipped-rule metadata and source versions.
- `WorkbenchDecision` rows from decision mode:
  - decision key
  - scope month
  - row ids and row types
  - match domain, match shape, rule code and rule version
  - decision status and display state
  - evidence, amount check and source versions.
- Run summary from `WorkbenchMatchingOrchestrator.run(...)`:
  - `request_id`
  - `reason`
  - `scope_months`
  - `processed_months`
  - `candidate_count`
  - `decision_count`
  - `paired_decision_count`
  - `open_decision_count`
  - `expired_decision_count`
  - `suppressed_by_pair_relation_count`
  - `auto_completed_relation_count`
  - `conflict_count`
  - `skipped_rule_count`
  - `duration_ms`

For shadow comparison, ordering must be canonicalized before diffing. The canonical key should include scope month, row-id set, row-type set, rule code/match domain/status and source-version signature. Differences in ordering alone are not acceptable evidence of a mismatch, but row membership, grouping, status, amount check, stale/source versions and summary counts must match.

## State, Events And Read Model Dependencies

Canonical state touched by the Python reference:

- `job.workbench_matching_dirty_scopes`: claim, stale-completed requeue, complete and fail.
- Runtime heartbeat / App Status worker facts for `workbench-matching`.
- Candidate/decision persistence owned by the Python candidate service / decision store.
- `app.workbench_pair_relations` only through `WorkbenchRelationCommandService.confirm_relation(...)` during allowed two-pane auto-completion.
- Downstream read model invalidation for `workbench` and `workbench_relation`.
- Active generation freshness via the normal Workbench read model refresh path after invalidation.

Read model dependencies:

- `workbench` keeps active generation atomic publish semantics.
- `workbench_relation` remains the canonical relation read model boundary for cross-page relation consumers.
- `workbench:all` must aggregate matching rules source versions from month shards.
- Redis may only cache fresh-gated Workbench query payloads and is outside the matching compute boundary.

## Permissions And Audit Assumptions

The matching dirty worker runs as system background work. It does not consume user HTTP session, cookies, request headers or frontend permission state. It must not weaken:

- Python facade API response shape.
- Workbench relation command audit behavior.
- Idempotency keys and actor IDs used by relation command auto-completion.
- App Health/readiness semantics.

Any future Go implementation that can cause canonical writes must preserve the Python audit actor, reason, idempotency and relation command contract. Shadow mode is read/compare only and must not write audit events.

## Forbidden Writes In Go Shadow Mode

Shadow Go code must not:

- Claim, ack, complete, fail or requeue `job.workbench_matching_dirty_scopes`.
- Write `job.outbox_events` or `job.read_model_dirty_scopes`.
- Write `read_model.app_status_readiness`.
- Publish or retire Workbench active generations.
- Write Redis cache.
- Write candidate or decision stores.
- Write or mutate `app.workbench_pair_relations`.
- Call relation command service or emit relation audit.
- Mark Workbench worker heartbeat as authoritative.
- Return HTTP/API payloads to the frontend.
- Mark stale payloads as fresh.

Allowed shadow behavior:

- Read the same normalized input snapshot as Python.
- Produce non-authoritative candidate/decision output.
- Persist shadow comparison artifacts only in a dedicated non-authoritative artifact/log location if a later implementation slice adds that storage explicitly.
- Emit metrics/logs that cannot affect readiness, cache, dirty scopes, outbox or active generation.

## Minimum Performance Evidence Before Admission

`go-hot-path:workbench-compute-admission` must remain blocked until at least the following candidate-specific evidence exists:

- Workbench matching worker p95/p99 `duration_ms` per scope and per claimed batch.
- Claimed scope counts, processed scope counts, failed scope counts and stale-completed requeue counts.
- Row counts per processed scope: OA rows, bank rows, invoice rows, active relation rows, filtered held rows.
- Candidate/decision counts per scope, including paired/open/conflict/expired/suppressed/auto-completed counts.
- Dirty-scope queue lag and worker heartbeat for `workbench-matching`.
- SQL/query timing evidence for row provider, active relation reads, decision store expire/upsert and candidate upsert.
- Workbench active generation enqueue-to-fresh p95/p99 after matching invalidation.
- Authenticated HTTP p95/p99 for Workbench summary/groups first screen and non-fresh response detection.
- CPU and memory evidence for high-row Workbench months.
- Shadow diff result on representative high-row months, including row membership/grouping/status/amount/source-version comparison.

Existing generic SLO tools are useful but insufficient by themselves: they cover HTTP first response, read model enqueue-to-fresh, write-operation scope convergence and sync baseline. They do not currently capture Workbench matching compute row counts, decision counts or CPU/memory per scope.

## Evidence Without Local PGSQL_URL Or Staging

Available locally:

- Static IO contract inspection.
- Unit and integration tests for Workbench matching rules, free matching, orchestrator, dirty queue, amount check and SQL runtime behavior.
- Unit tests for SLO tool fail-closed semantics.
- Documentation of production-only probes and required output fields.
- Dry-run-only planning where tools support configuration-missing reports.

Not available locally without real PostgreSQL or deployed runtime:

- Real `pg_stat_statements`, query timings and table-size baselines.
- Real `workbench-matching` heartbeat and dirty-scope lag.
- Real enqueue-to-fresh p95/p99.
- Real authenticated HTTP p95/p99.
- Real high-row month row counts and CPU/memory.
- Real shadow-run equivalence on production-shaped months.

These gaps are not blockers for this planning slice, but they are blockers for Go admission.

## Rollback Gates

Before any Go implementation can publish or own output:

- Python remains the reference implementation.
- A per-worker/per-service switch must disable Go and route work back to Python without data repair.
- Python facade API/auth/audit behavior must stay unchanged.
- Dirty scope ownership must be single-writer: either Python owns authoritative ack/publish, or Go owns it after explicit migration. Shadow never owns ack/publish.
- Read model freshness, source-version proof and operation barrier behavior must be identical or explicitly migrated with tests.
- Rollback must not require deleting canonical facts or manual DB edits.

## Admission Decision

`go-hot-path:workbench-compute-admission` cannot become the next pending boundary yet.

Reason: candidate-specific Python reference IO is now documented, but the repository does not yet contain an executable guard/harness that freezes the reference input/output contract for shadow comparison, and the real performance evidence is still missing.

The next executable boundary should add local reference-contract guards and a non-authoritative evidence plan for Workbench compute before an admission review is allowed.

## State Machine Impact

- `go-hot-path:workbench-compute-performance-baseline-contract` transitions to `planning-closed`.
- Insert `go-hot-path:workbench-compute-python-reference-contract-guards` as the next pending boundary.
- Keep `go-hot-path:workbench-compute-admission` blocked by prerequisite evidence.
- Keep all other Go hot-path candidates blocked.
- No Python runtime behavior changes are made in this slice.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable for this slice | No matching rule or amount logic changed. Existing tests are evidence only. |
| 2. Service-layer tests | Applicable as evidence review | Existing dirty worker/orchestrator/engine tests define the reference boundary; no new runtime behavior was added. |
| 3. API contract tests | Not applicable | No HTTP/API contract changed. |
| 4. Read model/cache/background job tests | Applicable as evidence review | Workbench dirty queue/read model tests remain required evidence; no new runtime behavior was added. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Deferred | Real shadow-run and deployed Workbench performance evidence are prerequisites for admission, not for this planning slice. |
| 7. Existing feature regression tests | Applicable as planning guard | Targeted existing Workbench and SLO tests should be run to prove the documented reference remains intact. |

## Next Boundary

`go-hot-path:workbench-compute-python-reference-contract-guards`

This next slice should:

- Add or tighten tests/guards that freeze the Workbench compute reference IO and shadow-forbidden-write contract.
- Prefer existing Workbench tests and static boundary guards before adding new abstractions.
- Define the exact artifact shape for future shadow diff output without implementing Go.
- Keep `go-hot-path:workbench-compute-admission` blocked unless the local guard and evidence prerequisites are satisfied.
