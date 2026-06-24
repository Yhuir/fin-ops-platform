# Go Hot Path Workbench Compute Python Reference Contract Guards

**Date:** 2026-06-24
**Boundary:** `go-hot-path:workbench-compute-python-reference-contract-guards`
**Slice status:** `static-guard-closed`
**Module closure:** `go-admission-not-started`

## Goal

Add local executable guards that freeze the Workbench compute Python reference ownership and Go shadow forbidden-write/admission-blocking contract before any Go admission review can start.

This slice does not implement Go, Go Fiber or Go Worker, and does not change Python runtime behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-performance-baseline-and-admission-reconciliation.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-baseline-contract.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/reconciliation-workbench/implementation-notes.md`
- `docs/operations/runtime-worker-governance.md`
- `backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_worker.py`
- `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`
- `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Changes

Added two static guard tests in `tests/test_platform_runtime_boundary_guards.py`:

- `test_workbench_compute_reference_state_writes_stay_in_python_boundaries`
  - Guards that the Python reference still owns dirty-scope claim/stale-requeue/complete/fail and heartbeat recording.
  - Guards that `WorkbenchMatchingOrchestrator` still owns candidate upsert, scope processed marking, read model invalidation, reconciliation engine wiring and relation read port dependency.
  - Guards that `WorkbenchReconciliationEngine` still owns decision expiry/upsert, relation auto-completion through command service and decision consumption.

- `test_workbench_compute_go_shadow_admission_remains_guarded`
  - Guards that the Workbench compute baseline contract documents Go shadow forbidden writes.
  - Guards that shadow mode cannot claim/ack/complete/fail dirty scopes, write outbox/dirty scopes, publish active generations, mutate pair relations or bypass the canonical diff shape.
  - Guards that `go-hot-path:workbench-compute-python-reference-contract-guards` is the pending queue item while `go-hot-path:workbench-compute-admission` remains `blocked-by-prerequisite`.
  - Guards that the next prompt still forbids Go/Fiber/Go Worker implementation in this guard slice.

## Admission Decision

`go-hot-path:workbench-compute-admission` remains blocked.

The local Python reference and shadow-forbidden-write guard now exists, but admission still lacks candidate-specific production-shaped performance evidence:

- Workbench matching worker p95/p99 duration by scope and batch.
- Row counts per scope.
- Candidate/decision counts per scope.
- Dirty-scope lag and heartbeat.
- SQL timing for row provider, active relation reads and decision/candidate persistence.
- Workbench active generation enqueue-to-fresh p95/p99 after matching invalidation.
- CPU/memory and high-row representative evidence.
- Shadow diff output on production-shaped scopes.

The next safe boundary is a performance evidence collector contract/tooling slice, not Go implementation.

## State Machine Impact

- `go-hot-path:workbench-compute-python-reference-contract-guards` transitions to `static-guard-closed`.
- Insert `go-hot-path:workbench-compute-performance-evidence-collector-contract` as the next pending boundary.
- Keep `go-hot-path:workbench-compute-admission` blocked by missing evidence.
- Keep all other Go hot-path candidates blocked.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No matching or amount business behavior changed. |
| 2. Service-layer tests | Applicable as static guard | Added service boundary ownership guards for dirty worker, orchestrator and engine reference writes. |
| 3. API contract tests | Not applicable | No HTTP/API behavior changed. |
| 4. Read model/cache/background job tests | Applicable as static guard | Guard covers dirty-scope, read model invalidation and active-generation forbidden-write admission contract. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Deferred | Real shadow-run and production performance evidence remain admission prerequisites. |
| 7. Existing feature regression tests | Applicable | Existing Workbench dirty/orchestrator/engine tests were run with the new guard tests. |

## Next Boundary

`go-hot-path:workbench-compute-performance-evidence-collector-contract`

This next slice should define or add a read-only evidence collection contract/tooling path for Workbench compute p95/p99, row counts, candidate/decision counts, dirty-scope lag, worker heartbeat and query timing evidence. It must still not implement Go or change canonical Python runtime behavior.
