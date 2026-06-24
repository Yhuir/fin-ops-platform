# Go Hot Path T7 Admission Evidence

**Date:** 2026-06-24
**Boundary:** `go-hot-path:t7-admission-evidence`
**Slice status:** `go-candidate-deferred`
**Module closure:** `go-admission-not-started`

## Goal

Prepare Go / Go Fiber / Go Worker admission evidence without implementing Go or changing Python runtime behavior.

This slice consolidates the current admission evidence for T7. It does not approve implementation.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-performance-baseline-and-admission-reconciliation.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-baseline-contract.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-python-reference-contract-guards.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-evidence-collector-contract.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-production-evidence-gate.md`
- `.planning/refactors/modular-io-boundaries/analysis/planning-post-workbench-compute-evidence-gate-next-boundary-selection.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `docs/modules/runtime-workers/README.md`
- `docs/modules/runtime-workers/state-machine.md`
- `docs/modules/runtime-workers/tests.md`
- `docs/modules/runtime-workers/implementation-notes.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/operations/postgresql-runtime.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `backend/src/fin_ops_platform/tools/workbench_compute_evidence.py`
- `tests/test_workbench_compute_evidence.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Candidate Membership

`workbench:matching-grouping-check` is listed in the approved candidate table as `P1-A`. The candidate may be evaluated for Go Worker or Go compute service shape, with optional Fiber only if an internal HTTP API is later justified.

The other queued admission rows remain blocked:

| Candidate | Queue state | T7 decision |
| --- | --- | --- |
| `workbench:matching-grouping-check` | `blocked-by-prerequisite` | `go-candidate-deferred` |
| `workbench:read-model-builder` | `blocked-by-prerequisite` | Not evaluated beyond global gate; still blocked. |
| `imports:parse-normalize-preview` | `blocked-by-prerequisite` | Not evaluated beyond global gate; still blocked. |
| `cost-statistics:summary-rollup` | `blocked-by-prerequisite` | Not evaluated beyond global gate; still blocked. |

## Gate Matrix

| Gate | Evidence | Result |
| --- | --- | --- |
| Candidate list membership | `P1-A workbench:matching-grouping-check` exists in `11-GO-HOT-PATH-CARVE-OUT.md`. | Pass |
| Performance evidence | Local `workbench_compute_evidence` can collect the required fields, but with no local PostgreSQL URL it returns `configuration_missing`; previous production gate also lacked deployed collector and DB connectivity. | Fail |
| IO contract completeness | Python reference input/output contract is documented for dirty worker, orchestrator, matching rules, free matching, reconciliation engine and amount check. Static guards protect Python reference ownership. | Partial |
| Legacy isolation | Shadow forbidden-write contract is documented and guarded. Legacy Python state writes still remain the authoritative implementation; no Go writer is isolated or available. | Partial |
| Freshness proof | Workbench active generation, dirty scope, outbox and readiness constraints are documented. No live enqueue-to-fresh p95/p99 after matching invalidation is available. | Fail |
| Shadow run feasibility | Shadow shape and forbidden writes are documented. No executable Python-vs-Go shadow diff exists because there is no Go implementation and no production-shaped output artifact. | Fail |
| Python-vs-Go equivalence test plan | Canonical comparison dimensions are documented: rows, counts, grouping, status, amount check, source versions, readiness metadata and error shape. | Partial |
| Rollback gate | Rollback requirement is documented: per-worker/per-service switch back to Python, single authoritative ack/publish owner, no manual DB repair. No implemented switch exists. | Fail |
| PostgreSQL dual queue constraints | Durable truth remains `job.outbox_events` plus `job.read_model_dirty_scopes`; RabbitMQ is wakeup/transport only. Shadow cannot ack, enqueue, mutate readiness or publish generations. | Pass |

## Local Execution Evidence

Read-only collector with no local database URL:

```bash
env -u FIN_OPS_POSTGRES_DATABASE_URL -u DATABASE_URL \
  PYTHONPATH=backend/src \
  python3 -m fin_ops_platform.tools.workbench_compute_evidence --json
```

Result:

- Exit code: `2`
- `status`: `configuration_missing`
- `blocking_condition`: `database_url_required`
- `production_evidence_required`: `true`
- Required env: `FIN_OPS_POSTGRES_DATABASE_URL`, `DATABASE_URL`

Targeted verification:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_compute_evidence -v
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_reference_state_writes_stay_in_python_boundaries \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded \
  -v
```

Result: all targeted tests passed.

## Admission Decision

`workbench:matching-grouping-check` is marked `go-candidate-deferred`.

Reasons:

- Real candidate-specific performance evidence is missing.
- Live freshness proof is missing.
- Shadow diff evidence is missing.
- Rollback switch proof is missing.
- Production/staging runtime evidence remains unavailable from the current local environment.

No Go, Go Fiber or Go Worker implementation may start from this evidence.

## Required Evidence To Reopen Admission

- Run `workbench_compute_evidence` against an approved runtime that contains the collector and can read PostgreSQL without printing secrets.
- Capture non-empty p95/p99 matching duration, scope sample, heartbeat, candidate/decision count, active generation row-count, query timing and matching-originated enqueue-to-fresh sections.
- Add a non-authoritative shadow diff artifact shape before any Go writer exists.
- Prove rollback can disable Go and restore Python ownership without DB edits.
- Keep Python facade auth/audit/API behavior unchanged.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No matching, grouping, relation, amount, classification or permission rule changed. |
| 2. Service-layer tests | Applicable as static guard evidence | Existing guard tests prove Python dirty worker/orchestrator/engine state-write ownership remains intact. |
| 3. API contract tests | Not applicable | No HTTP/API contract changed. |
| 4. Read model/cache/background job tests | Applicable | `tests.test_workbench_compute_evidence` proves the evidence collector is read-only and fails closed on missing evidence. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Deferred | Real shadow-run and production-shaped performance evidence are admission prerequisites and remain unavailable. |
| 7. Existing feature regression tests | Applicable | Platform guard keeps Go shadow/admission blocked behind documented prerequisites. |

## Remaining Risk

- This slice does not collect real production PostgreSQL evidence.
- It does not prove high-row Workbench compute performance.
- It does not prove Python-vs-Go equivalence because no Go implementation exists.
- It does not prove operational rollback beyond documented gates.
