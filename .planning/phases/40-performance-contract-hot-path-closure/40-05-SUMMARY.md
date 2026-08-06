---
phase: 40-performance-contract-hot-path-closure
plan: "05"
subsystem: read-model-freshness
tags: [workbench, exact-scope, self-heal, durable-queue, tdd]

requires:
  - phase: 39-production-runtime-and-search-convergence
    provides: retained Workbench active-generation runtime and ReadModelRefreshGateway
provides:
  - public Workbench refresh-status self-heals exact stale month scopes through the existing gateway
  - one-proof regression coverage for stale, fresh, refreshing, failed, and cold-start states
  - unchanged Workbench API mapping and ordinary bank-flow writer isolation evidence
affects: [40-06, 40-07, 40-08, reconciliation-workbench, runtime-workers]

tech-stack:
  added: []
  patterns: [query-owned self-healing, exact-scope enqueue, active refresh coalescing]

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/services/workbench_query_facade.py
    - tests/test_workbench_query_facade.py
    - tests/test_workbench_routes.py

key-decisions:
  - "Public refresh-status reuses _groups_refresh_status_payload with enqueue_non_fresh=True; it does not own a second repository or canonical-proof path."
  - "Ordinary writers remain unchanged and emit no Workbench notification, target, dirty-scope, outbox, or operation-barrier I/O."

patterns-established:
  - "The Workbench consumer that proves staleness advances only exact mismatch scopes through the existing injected gateway."
  - "Fresh and active refreshing states are no-ops; failed exact scopes retry exactly; all remains cold-start/explicit recovery only."

requirements-completed: []

duration: 7 min
completed: 2026-08-06
---

# Phase 40 Plan 05: Workbench Public Status Exact Self-Heal Summary

**Workbench public refresh-status now uses the existing one-proof exact-scope self-heal seam, enqueueing only real stale/failed month shards while keeping fresh, active refreshing, API, and ordinary writer contracts unchanged.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-08-06T06:20:28Z
- **Completed:** 2026-08-06T06:27:47Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Replaced the public `refresh_status` duplicate repository/source-proof flow with `_groups_refresh_status_payload(scope_key, enqueue_non_fresh=True)` inside the existing transient-error boundary.
- Preserved one lightweight repository status read and one canonical source proof per request; no second proof, full payload GET, helper, port, registry, or runtime component was added.
- Locked `all` stale mismatch scopes to deduped exact month enqueue, exact-month stale to that month, failed dirty scope to that failed month, and cold-start active-generation-missing recovery to the existing `all` command.
- Locked fresh and active pending/processing refreshing paths to zero enqueue; ordinary stale `all` without exact targets cannot fan out.
- Preserved timeout mapping, route status/error/payload forwarding, shared API authentication gate, and exact month forwarding.
- Re-ran the existing bank-flow route, service boundary, mutation persistence, and PostgreSQL relation writer guards; ordinary writers still perform zero Workbench dirty-scope/outbox/target/fan-out I/O.

## Task Commits

1. **Task 1 RED: lock public status exact self-heal and API contracts** - `0764212b3` (test)
2. **Task 1 GREEN: reuse the existing exact status/enqueue helper** - `6c61af912` (fix)

## Files Created/Modified

- `backend/src/fin_ops_platform/services/workbench_query_facade.py` - deletes the duplicate public status repository/proof path and reuses the existing exact self-heal helper.
- `tests/test_workbench_query_facade.py` - table-driven stale/fresh/refreshing/failed/cold-start, one-proof, exact-scope, no-fan-out, and enqueue-timeout coverage.
- `tests/test_workbench_routes.py` - route-level month/status/error/payload forwarding and shared authentication-gate regression coverage.

## Decisions Made

- Reused the existing facade helper and injected enqueue port. Composition continues to route through `ReadModelRefreshGateway`, scope policy normalization/validation/dedupe, and active-event coalescing.
- Kept the existing `api_groups_source_versions_stale` reason so gateway behavior and operational attribution remain shared with normal Workbench reads.
- Changed no bank-flow route, application service, relation command, persistence repository, queue, worker, cache, endpoint, DTO, or response shape.
- Docs impact assessment: the long-lived Workbench/read-model/worker/bank-flow boundary documents already describe consumer-owned exact access convergence and zero ordinary-writer fan-out. No boundary, I/O, registry, worker, API shape, or permission fact changed; Phase 40-08 owns final phase-wide documentation/evidence closure, so long-term docs are not applicable to this plan's minimal root fix.

## Deviations from Plan

None - plan executed exactly as written.

## TDD Gate Compliance

- RED commit `0764212b3`: the service/API slice produced 58 passed and 2 expected failures because public refresh-status still reported stale without enqueueing.
- GREEN commit `6c61af912`: the exact plan service/API/gateway slice passed 75/75.
- Git history contains the required `test(40-05)` commit followed by the GREEN `fix(40-05)` implementation commit.

## Tests

- **Business core unit:** Not applicable. No finance rule, amount, classification, relation membership, or state-transition semantics changed.
- **Service layer:** Applicable. One-proof exact stale enqueue, fresh/refreshing no-op, failed exact retry, ordinary stale no-`all`, cold-start `all`, and transient enqueue failure mapping are covered.
- **API contract:** Applicable. Shared authentication protection, exact month forwarding, status/error/payload shape, and timeout mapping are covered without changing the endpoint.
- **Read model/cache/background job:** Applicable. Existing gateway normalize/validate/dedupe/coalescing tests passed; no cache, queue type, worker, projection, or active-generation publish code changed.
- **Frontend component/interaction:** Not applicable to 40-05. The browser polling lifecycle is explicitly owned by Plan 40-06; no frontend file changed here.
- **End-to-end business flow:** Deferred to the planned 40-07 cross-module writer-proof/E2E closure. This plan proves the backend self-heal edge and writer isolation without adding or mutating a real business fixture.
- **Existing feature regression:** Applicable. Workbench route/facade/gateway plus bank-flow route/backend-boundary and PostgreSQL zero-dirty/outbox guards passed.

## Verification

- RED: `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_workbench_query_facade.py tests/test_workbench_routes.py` - 58 passed, 2 expected failures.
- GREEN plan gate: `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_workbench_query_facade.py tests/test_workbench_routes.py tests/test_read_model_refresh_gateway.py` - 75 passed.
- Final regression slice including bank-flow route/backend boundary and PostgreSQL zero-dirty/outbox writer guard - 94 passed.
- Focused bank-flow submit/persistence/list and zero-fan-out guard slice - 12 passed.
- `bash scripts/verify.sh lint` - passed.
- `git diff --check` - passed.

## Known Stubs

None. No placeholder, mock runtime data source, TODO/FIXME, empty UI payload, or unwired component was introduced.

## Security

- T-40-05-01: existing scope policy remains the only normalize/validate boundary; tests cover exact months, dedupe, and retained cold-start `all` semantics.
- T-40-05-02: fresh/refreshing no-op tests and existing gateway active coalescing prevent duplicate enqueue amplification; public status performs one proof.
- T-40-05-03: the endpoint remains behind the shared OA API access gate, with no auth or permission code change.
- No new endpoint, authentication path, file access, schema, secret, or trust boundary was introduced; no threat flag is required.

## Remaining Risk

- Full browser-visible bank-flow submit -> status proof -> worker publish -> reload evidence is intentionally owned by Plans 40-06/40-07, and production concurrency/p99 evidence by 40-08. No push, deploy, production mutation, or production claim was made here.

## User Setup Required

None - no dependency, environment variable, migration, worker, or external service configuration was added.

## Next Phase Readiness

- Plan 40-06 can rely on every public status request to advance exact stale scopes while implementing completion-driven visible-page polling.
- Plan 40-07 can reuse the zero-writer-fan-out and exact self-heal service contracts for the writer-proof/E2E matrix.
- Plan 40-08 still owns target-concurrency, four-segment p99, production read-only evidence, and final documentation/release closure.

## Self-Check: PASSED

- All three plan-owned source/test files and this SUMMARY exist.
- RED `0764212b3` and GREEN `6c61af912` resolve in git history in the required order.
- The 75-test plan gate, 94-test final regression slice, focused bank-flow isolation slice, lint, and diff check passed.
- No plan-owned file deletion, untracked artifact, push, or deployment occurred.

---
*Phase: 40-performance-contract-hot-path-closure*
*Completed: 2026-08-06*
