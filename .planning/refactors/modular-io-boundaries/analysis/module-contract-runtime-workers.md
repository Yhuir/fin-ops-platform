# Module Contract - Runtime Workers

**Date:** 2026-06-24
**Worker:** T8 Module IO Contracts
**Status:** documentation/accounting closed
**Runtime behavior:** unchanged

## Module Basic Info

| Field | Content |
| --- | --- |
| Module key | `runtime-workers` |
| Module type | Shared runtime/resource module |
| Route | N/A |
| Frontend entry | App Status and operation barrier consumers |
| Backend entry | `runtime_worker_registry.py`, durable queue, App Status registry, operation freshness barrier |
| Docs entry | `docs/modules/runtime-workers/README.md` |
| Refactor status | Contracted locally; production evidence deferred |

## IO Contract Reconciliation

### Inputs

| Input | Contract |
| --- | --- |
| Worker registration | Read model workers must be visible to App Status registry and runtime worker registry. |
| Durable queue event | Event type, scope type/key, metadata and source versions must match manifest/scope policy contracts. |
| Transactional enqueue | Must use transaction-bound durable queue writer or an equivalent repository/UoW contract. |
| Operation barrier query | Reads current-effective dirty/outbox/readiness/worker facts only. |
| Go admission evidence | May collect read-only performance/shape evidence; cannot implement Go before admission gates pass. |

### Outputs

| Output | Contract |
| --- | --- |
| Worker readiness | App Status-visible, current-effective and tied to read model/worker registry. |
| Dirty/outbox completion | PostgreSQL durable queue is source of truth; RabbitMQ is transport/wakeup only. |
| Operation barrier status | `fresh`, `refreshing` or `blocked` with target-specific reasons. |
| Go admission result | `go-candidate-deferred` until performance, freshness, shadow, equivalence and rollback evidence exists. |

### State / Events

- Non-transactional refresh producers must use `ReadModelRefreshGateway`.
- Transactional writers must keep durable queue writes in the active transaction and satisfy scope policy equivalence.
- Barrier target matching is scope-aware when outbox payload has scope details; event-level payload without scope remains conservative.
- Worker registrations must be bidirectionally visible: App Status -> worker and worker read-model registration -> App Status.

### Public / Internal Surfaces

Public surfaces:

- `RuntimeWorkerRegistry`
- App Status read model/domain registries
- `RuntimeQueueRepository` through gateway/repository/UoW boundaries
- `OperationFreshnessBarrierService`
- Approved read-only evidence tooling

Internal-only surfaces:

- Direct production queue mutation outside approved writer boundaries.
- RabbitMQ/Redis as state truth.
- Worker implementation depending on `Application`, HTTP response, request/session or auth modules.
- Go shadow/admission paths writing canonical facts, dirty scopes, outbox, readiness or cache.

### Legacy Status

| Legacy path | Status | Constraint |
| --- | --- | --- |
| Combined worker lanes | `compat-only` | May remain for deployment compatibility but cannot be the only declared owner when a dedicated primary exists. |
| RabbitMQ dispatch | transport-only | Cannot be readiness/dirty/outbox truth. |
| Go hot-path candidate | `blocked-by-prerequisite` / `go-candidate-deferred` | No Go implementation until evidence and rollback gates pass. |

### Read Model Refresh / Force Refresh

- Worker refresh contracts are driven by `READ_MODEL_MANIFEST`, scope policy registry, runtime worker registry and App Status registry.
- Force refresh remains a gateway/runbook/API contract; runtime workers do not self-authorize broad force refresh.
- Operation barrier reads current-effective runtime facts and never mutates readiness or queue state.

### Partitioned Scoped Incremental Target

Runtime workers execute the per-read-model projection strategy declared in the manifest. The target worker runtime may eventually include Go Worker + PostgreSQL dual queue, but current authoritative runtime remains Python workers with PostgreSQL outbox and dirty scopes as durable truth.

## Test Contract

| Category | Applicability | Evidence |
| --- | --- | --- |
| 1. Business core unit tests | Not directly applicable | Runtime worker module does not own business rules. |
| 2. Service-layer tests | Applicable | Runtime queue, operation barrier, worker registry tests. |
| 3. API contract tests | Indirect | App Health/operation barrier APIs are covered by their modules. |
| 4. Read model/cache/background job tests | Applicable | T3 added/used worker registry, runtime queue, refresh gateway and operation barrier coverage. |
| 5. Frontend component and interaction tests | Indirect | Operation barrier/App Status frontend tests live with frontend modules. |
| 6. E2E business-flow integration tests | Production/staging dependent | Real worker drain remains deferred. |
| 7. Existing feature regression tests | Applicable | Static/runtime guards prevent contract drift and premature Go admission. |

## Handoff Evidence Consumed

- `T3-worker-queue-app-status.md`
- `T7-go-admission-evidence.md`
- `docs/modules/runtime-workers/tests.md`
- `docs/modules/runtime-workers/implementation-notes.md`
- `docs/modules/app-health-operations/tests.md`

## Remaining Risk

Local tests prove fake/static contracts only. Real PostgreSQL/RabbitMQ/systemd worker drain, App Status readiness convergence and production Go admission evidence remain deferred.
