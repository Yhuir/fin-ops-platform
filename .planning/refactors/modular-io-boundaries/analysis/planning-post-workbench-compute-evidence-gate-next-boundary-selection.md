# Post Workbench Compute Evidence Gate Next Boundary Selection

**Date:** 2026-06-24
**Boundary:** `planning:post-workbench-compute-evidence-gate-next-boundary-selection`
**Slice status:** `planning-closed`
**Module closure:** `not-applicable`

## Goal

Select the next safe non-blocked modular IO boundary after `go-hot-path:workbench-compute-production-evidence-gate` was deferred and all Go admission rows remained blocked.

This slice does not implement Go, Go Fiber, Go Worker or canonical Python runtime behavior.

## Evidence Reviewed

- `.planning/ROADMAP.md`
- `.planning/refactors/README.md`
- `.planning/refactors/modular-io-boundaries/README.md`
- `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`
- `.planning/refactors/modular-io-boundaries/01-CURRENT-STATE-AUDIT.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
- `.planning/refactors/modular-io-boundaries/06-PILOT-SELECTION.md`
- `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`
- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-production-evidence-gate.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `docs/modules/README.md`
- Current code metrics for `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` and `backend/src/fin_ops_platform/services/postgres_state_store.py`.

## Previous State

- First pending queue item was `planning:post-workbench-compute-evidence-gate-next-boundary-selection`.
- `go-hot-path:workbench-compute-production-evidence-gate` was `production-evidence-deferred`.
- Go admission rows 185-188 were `blocked-by-prerequisite`.
- Known non-Go read model pilots had local implementation support accounted for, but production evidence remained deferred.
- No module was globally closed.

## Why Go Rows Were Skipped

`11-GO-HOT-PATH-CARVE-OUT.md` requires candidate-specific performance evidence, IO contract closure, legacy isolation, freshness proof, shadow run and rollback proof before Go implementation or admission.

The Workbench compute production evidence gate did not provide the required evidence:

- No live p95/p99 Workbench matching duration evidence.
- No live candidate/decision and row-count evidence.
- No live Workbench active generation enqueue-to-fresh evidence after matching invalidation.
- No shadow diff evidence.
- No rollback proof.

Therefore `go-hot-path:workbench-compute-admission`, `go-hot-path:workbench-read-model-builder-admission`, `go-hot-path:import-parser-admission` and `go-hot-path:cost-summary-rollup-admission` remain blocked.

## Boundary Options Considered

### Option A: Continue Go Admission

Rejected. It would violate the admission gates and the user's requirement that old Python/read model boundaries be modularized before Go hot-path replacement.

### Option B: Start `read_models.py` Repository Split

Deferred. `read_models.py` remains large at about 11410 lines and is still a high-risk center, but the recent read model pilot series already introduced many narrow repository ports. A direct repository split now risks becoming mechanical file surgery unless a smaller owner/gap audit chooses one concrete method family first.

### Option C: Shared `server.py` Residual Handler Boundary Audit

Selected. `01-CURRENT-STATE-AUDIT.md` still lists `server.py` as the largest shared center. Current metrics show:

- `backend/src/fin_ops_platform/app/server.py`: 21519 lines.
- Function definitions in `server.py`: 1062.
- Private functions/methods in `server.py`: 1031.
- `server.py` still contains residual route/handler/dependency/helper surfaces even after previous route owner inventory and several extraction slices.

This is a safe next planning boundary because it can inspect and rank residual handler/helper ownership without changing behavior. It also aligns with Phase 6 shared boundary governance in `04-IMPLEMENTATION-ROADMAP.md`.

## Selected Next Boundary

`server-py:residual-route-handler-boundary-audit`

Purpose:

- Audit residual `server.py` route/handler/helper surfaces after prior route module work.
- Classify residual surfaces by module owner, caller evidence, write/read/read-model/worker risk and legacy contamination risk.
- Select exactly one next implementation or narrower audit boundary.
- Do not delete or move code in the audit slice.

Expected outputs for the next slice:

- Analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and master controller prompt.
- If a concrete implementation boundary is selected, it must be narrow and tied to one module/route/helper family.

## State Machine Impact

- `planning:post-workbench-compute-evidence-gate-next-boundary-selection` transitions to `planning-closed`.
- Insert `server-py:residual-route-handler-boundary-audit` as the next pending boundary.
- Go rows remain `blocked-by-prerequisite`.
- Global state-machine definitions are unchanged. This is an accounting/planning transition covered by the existing `planning-closed` label.
- No module state-machine definitions changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rule changed. |
| 2. Service-layer tests | Not applicable | No service or repository behavior changed. |
| 3. API contract tests | Not applicable | No API shape, status code, permission or error contract changed. |
| 4. Read model/cache/background job tests | Not applicable | No read model, cache, worker or queue behavior changed. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No runtime flow changed. |
| 7. Existing feature regression tests | Applicable | Existing platform guard is updated so the queue cannot treat the post-evidence planning slice as still pending after it closes. |

## Verification

Targeted verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded \
  -v

bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- The selected next slice is an audit. It will not reduce `server.py` runtime coupling until it selects and executes a concrete implementation boundary.
- `read_models.py` remains a separate shared-boundary risk and should be revisited after one or more residual `server.py` surfaces are classified or migrated.
- Production evidence for prior read model and Go hot-path candidates remains deferred.
