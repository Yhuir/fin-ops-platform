# Go Hot Path Workbench Compute Performance Evidence Collector Contract

**Date:** 2026-06-24
**Boundary:** `go-hot-path:workbench-compute-performance-evidence-collector-contract`
**Slice status:** `implementation-closed`
**Module closure:** `go-admission-not-started`

## Goal

Add a read-only Workbench compute evidence collector that can gather the candidate-specific performance facts required before `workbench:matching-grouping-check` may enter Go admission review.

This slice does not implement Go, Go Fiber or Go Worker, and does not change canonical Python runtime behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-performance-baseline-and-admission-reconciliation.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-baseline-contract.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-python-reference-contract-guards.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/reconciliation-workbench/implementation-notes.md`
- `docs/operations/runtime-worker-governance.md`
- `backend/src/fin_ops_platform/tools/cli_reports.py`
- `backend/src/fin_ops_platform/tools/sync_slo_baseline.py`
- `backend/src/fin_ops_platform/tools/read_model_slo_smoke.py`
- PostgreSQL migrations defining Workbench active generation, group rows, candidate matches, reconciliation decisions, dirty scopes, worker heartbeats and outbox events.

## Changes

Added `backend/src/fin_ops_platform/tools/workbench_compute_evidence.py` and updated the Workbench compute admission guard to expect this collector slice as closed while `go-hot-path:workbench-compute-production-evidence-gate` becomes the next pending item.

The tool is read-only and reports:

- `matching_scope_durations`: completed/failed/processing scope counts and p50/p95/p99/max `duration_ms` from `job.workbench_matching_dirty_scopes`.
- `matching_scope_samples`: recent claimed/processed/failed/stale candidate scope samples including age, request id, attempt count, source versions and error summary.
- `worker_heartbeat`: latest `workbench-matching` heartbeat and lag from `job.runtime_worker_heartbeats`.
- `candidate_decision_counts`: candidate and decision counts by scope, including paired/open/conflict/expired/suppressed/consumed evidence.
- `active_generation_row_counts`: active generation row counts from `read_model.workbench_group_rows`, including OA, bank, invoice, active relation and held-row counts by scope.
- `workbench_refresh_after_matching`: Workbench refresh enqueue-to-done p50/p95/p99 for matching-originated refresh events.
- `query_timing_evidence`: relevant `pg_stat_statements` samples for Workbench dirty scope, decision, candidate, generation, row and relation queries.
- `explain_probes`: plain `EXPLAIN (FORMAT JSON)` for fixed Workbench compute evidence probes.

The CLI returns the shared structured `configuration_missing` report when no PostgreSQL URL is configured and marks `production_evidence_required=true`. Empty or partial evidence returns `status=partial`, `admission_status=blocked_by_missing_real_evidence` and `production_evidence_required=true`; it does not pass Go admission.

## Read-only And Legacy Isolation Contract

The collector only calls `fetch_all` and `fetch_one`; it does not call enqueue, claim, ack, complete, fail, requeue, publish, readiness mutation, Redis cache write, candidate/decision write, relation command or audit write APIs.

The collector does not become a new runtime fact source. It is a reporting tool only. It cannot mark evidence as fresh, cannot update App Status and cannot satisfy admission unless real PostgreSQL/runtime evidence is present in the report.

## State Machine Impact

- `go-hot-path:workbench-compute-performance-evidence-collector-contract` transitions to `implementation-closed`.
- `go-hot-path:workbench-compute-admission` remains `blocked-by-prerequisite`.
- Insert `go-hot-path:workbench-compute-production-evidence-gate` as the next pending boundary. That next slice may run the collector in an approved read-only runtime or record `production-evidence-deferred`; it still must not implement Go.
- Global state-machine definitions are unchanged. Reviewed `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`; existing Go candidate and state-accounting semantics already cover this transition.
- Module state-machine definitions are unchanged. This is Workbench performance evidence tooling, not a Workbench business state or UI/API contract change.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No matching, grouping, amount, relation or permission business rule changed. |
| 2. Service-layer tests | Not applicable | No service/repository runtime behavior changed. |
| 3. API contract tests | Not applicable | No HTTP/API contract changed. |
| 4. Read model/cache/background job tests | Applicable | Added fake-connection tests proving Workbench evidence sections combine dirty scope, heartbeat, active generation, candidate/decision, outbox and query timing evidence without writes; updated the Go admission guard to keep admission blocked behind production evidence. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Deferred | Real production/staging-like Workbench performance evidence remains the next gate, not this local tooling slice. |
| 7. Existing feature regression tests | Applicable | Existing SLO defaults and Workbench compute guard tests remain the surrounding regression evidence. |

## Verification

Targeted verification for this slice:

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/workbench_compute_evidence.py
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_compute_evidence -v
PYTHONPATH=backend/src python3 -m unittest tests.test_slo_tool_defaults tests.test_sync_slo_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_reference_state_writes_stay_in_python_boundaries tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- No local `PGSQL_URL` or staging database is assumed, so this slice cannot prove real Workbench p95/p99, heartbeat, high-row counts, `pg_stat_statements`, CPU/memory or active generation enqueue-to-fresh evidence.
- Production evidence must be collected through an approved read-only runtime path without writing credentials to files, logs, docs or prompts.
- Go/Fiber/Go Worker implementation remains blocked until performance evidence, shadow comparison and rollback gates are satisfied.
