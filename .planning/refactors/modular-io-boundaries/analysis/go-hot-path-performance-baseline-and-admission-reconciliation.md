# Go Hot Path Performance Baseline And Admission Reconciliation

**Date:** 2026-06-24
**Boundary:** `go-hot-path:performance-baseline-and-admission-reconciliation`
**Slice status:** `planning-closed`
**Module closure:** `go-admission-not-started`

## Goal

Reconcile whether the autonomous modular IO queue can move any Go / Go Fiber / Go Worker candidate from `blocked-by-prerequisite` into a bounded admission review, without implementing Go or changing Python runtime behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md`
- `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-local-implementation-closure-audit.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/operations/runtime-worker-governance.md`
- `backend/src/fin_ops_platform/tools/http_slo_probe.py`
- `backend/src/fin_ops_platform/tools/sync_slo_baseline.py`
- `backend/src/fin_ops_platform/tools/read_model_slo_smoke.py`
- `backend/src/fin_ops_platform/tools/write_operation_slo_audit.py`
- `tests/test_http_slo_probe.py`
- `tests/test_sync_slo_baseline.py`
- `tests/test_read_model_slo_smoke.py`
- `tests/test_write_operation_slo_audit.py`
- `tests/test_slo_tool_defaults.py`

## Reconciliation Result

No Go/Fiber/Go Worker implementation may start from the current evidence.

All prior non-Go read model implementation-pending queue items are locally accounted for or explicitly production-evidence-deferred, but the Go admission gates still require candidate-specific performance evidence, stable IO contracts, shadow-run comparison, rollback controls and Python facade compatibility proof.

The next safe step is a narrower planning/admission-contract boundary for `workbench:matching-grouping-check` because it is the highest priority Go candidate in `11-GO-HOT-PATH-CARVE-OUT.md` and has the clearest compute-only shape. This next boundary must still not implement Go.

## Candidate Decisions

| Candidate | Decision | Missing evidence before admission can start |
| --- | --- | --- |
| `workbench:matching-grouping-check` | Keep blocked; create a narrower performance-baseline/IO-contract boundary. | Candidate-specific API/worker p95/p99 baseline, exact Python input/output contract, shadow-run comparison plan, rollback switch, and proof that Workbench active generation / relation freshness contracts are not weakened. |
| `workbench:read-model-builder` | Keep blocked. | Workbench builder admission depends on active generation publish, month/all scope performance, source-version proof, shadow output comparison and rollback. |
| `imports:parse-normalize-preview` | Keep blocked. | Import parser admission needs file-size/parse/normalize timing evidence, preview IO contract, canonical confirm boundary and rollback path. |
| `cost-statistics:summary-rollup` | Keep blocked. | Cost summary admission needs summary/rollup p95 evidence, parent aggregate IO contract, source-version proof and compatibility with existing cost read model freshness. |

No candidate is marked `go-candidate-deferred` in this slice because this boundary is global reconciliation, not a candidate-specific admission review. The queued candidates remain `blocked-by-prerequisite` with concrete missing evidence.

## Performance Evidence Classification

Existing local evidence:

- `http_slo_probe.py` can collect authenticated page/API first-response p95/p99 and fails probes when read model responses are non-fresh or enqueue refresh.
- `sync_slo_baseline.py` can collect read-only runtime health, App Status attention, worker/queue dashboard sections, PostgreSQL table/index usage, `pg_stat_statements` and fixed EXPLAIN probes.
- `read_model_slo_smoke.py` dry-run can discover smoke scopes without enqueueing; `--apply` is required to prove enqueue-to-fresh latency and worker drain.
- `write_operation_slo_audit.py` audits real durable outbox events and fails when required scope samples are missing, failed, over p95 target or over p99 long-tail target.
- Unit tests prove the tools fail closed for missing samples, non-fresh read model responses and target breaches.

Evidence collectible without local `PGSQL_URL` or staging:

- Static/code-level verification of tool semantics.
- Unit tests using fake connections.
- Dry-run planning for local tools only when configuration exists.
- Documentation of candidate-specific probes, scopes, outputs and rollback requirements.

Evidence that remains production/staging dependent:

- Real PostgreSQL `pg_stat_statements`, table sizes, queue/worker/App Status facts.
- Authenticated HTTP p95/p99 for deployed pages and APIs.
- Worker lag, heartbeat and enqueue-to-fresh p95/p99 from real durable queue events.
- High-row Workbench/cost/import performance evidence.
- Browser smoke against real deployed data.
- Any controlled `read_model_slo_smoke --apply` or write-operation SLO audit that depends on real durable outbox/dirty scope state.

## State Machine Impact

- `go-hot-path:performance-baseline-and-admission-reconciliation` transitions to `planning-closed`.
- Go hot-path state remains `blocked-by-read-model-implementation-prerequisites`.
- Insert `go-hot-path:workbench-compute-performance-baseline-contract` as the next planning boundary.
- Keep all actual Go implementation/admission candidates `blocked-by-prerequisite` until candidate-specific gates pass.
- No global state-machine definition changes are required; `03-REFACTOR-STATE-MACHINE.md` already defines Go candidate states and admission requirements.
- No module state-machine definition changes are required; this slice changes planning/admission accounting only.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rules, amount logic, classification or state transitions changed. |
| 2. Service-layer tests | Not applicable | No service/repository/runtime behavior changed. |
| 3. API contract tests | Not applicable | No HTTP/API contract changed. Existing `http_slo_probe` tests were reviewed as evidence. |
| 4. Read model/cache/background job tests | Applicable as evidence review | Existing SLO/read-model smoke tests prove tool semantics; no new runtime behavior was added. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Deferred | Real Go admission requires production/staging-like performance and shadow-run evidence; this slice does not run it. |
| 7. Existing feature regression tests | Applicable as planning guard | Verification should run existing SLO tool tests to ensure admission evidence tooling still fails closed. |

## Next Boundary

`go-hot-path:workbench-compute-performance-baseline-contract`

This next slice must:

- Inspect Workbench matching/grouping/check entry points and tests.
- Define the exact Python reference input/output contract for `workbench:matching-grouping-check`.
- Define the SLO probes and real evidence required before `go-hot-path:workbench-compute-admission` can enter admission review.
- Define shadow-run comparison, rollback and forbidden-write rules.
- Not implement Go, Go Fiber or Go Worker.
- Not change Python runtime behavior.
