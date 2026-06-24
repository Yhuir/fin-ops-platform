# T3 Worker Queue App Status Handoff

Date: 2026-06-24

## Scope

- Audited runtime worker registry, durable queue, App Status read model registry, and operation barrier contracts.
- Touched only local tests, module docs, and this handoff.
- Did not implement Go Worker.
- Did not mutate production queue, dirty scopes, readiness, RabbitMQ, Redis, or worker state.

## Findings

- Non-transactional refresh producers are already guarded by `ReadModelRefreshGateway` and `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY`.
  - `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_read_model_refresh_producers_use_scope_gateway_boundary` blocks direct queue calls outside the gateway/repository boundary.
  - `tests/test_read_model_refresh_gateway.py` covers normalize, validate, dedupe, active-refresh coalescing, metadata propagation, and invalid scope rejection.
- Transactional writers use durable queue contracts inside the active transaction.
  - `tests/test_runtime_queue.py` covers `RuntimeQueueRepository.enqueue_read_model_refresh_in_transaction(...)` using the supplied transaction, source_version payload propagation, dedupe payload merge, metadata sanitization, and non-transaction wrapper delegation.
  - Added a workbench relation transactional scope-policy guard because that repository has a custom helper for aggregate event metadata and dedupe semantics.
- Operation barrier target filtering is already scope-aware for scoped outbox payloads.
  - `tests/test_operation_freshness_barrier.py` covers same read model / unrelated scope and unrelated read model outbox pending cases.
  - Barrier still treats event-level outbox status without scope details conservatively as target-relevant; this is intentional for snapshots that lack scoped details.
- App Status and worker registry parity was mostly covered in the App Status -> worker direction.
  - Added the reverse worker read-model registration -> App Status registry assertion to catch read-model workers that would otherwise be invisible to the global status plane.

## Changes

- Added `RuntimeWorkerRegistryTests.test_worker_read_model_registrations_are_visible_to_app_status_registry`.
- Added `test_workbench_relation_transactional_refresh_scopes_match_scope_policy_contracts`.
- Updated:
  - `docs/modules/runtime-workers/tests.md`
  - `docs/modules/runtime-workers/implementation-notes.md`
  - `docs/modules/app-health-operations/tests.md`

## Verification

Run the focused local checks:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_registry tests.test_operation_freshness_barrier tests.test_runtime_queue tests.test_read_model_refresh_gateway -v
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py -q
bash scripts/verify.sh docs
```

## Remaining Risk

- Local tests prove contracts against fake connections and static guards, not real worker drain.
- Real PostgreSQL/RabbitMQ/systemd convergence still requires staging/production `infra-smoke`, read model SLO smoke, write-operation audit, and App Status read-only observation.
- The named T3 handoff file was absent at the start of this audit; this file is the restored scoped handoff.
