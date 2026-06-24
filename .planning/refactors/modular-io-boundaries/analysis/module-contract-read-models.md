# Module Contract - Read Models

**Date:** 2026-06-24
**Worker:** T8 Module IO Contracts
**Status:** documentation/accounting closed
**Runtime behavior:** unchanged

## Source Limitations

- `.planning/refactors/modular-io-boundaries/parallel/handoffs/T8-module-io-contracts.md` did not exist before this pass.
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-*.md` did not exist before this pass.
- The contract was reconciled from `docs/modules/read-models/*`, `backend/src/fin_ops_platform/services/read_model_manifest.py`, existing module docs, and existing modular IO analysis files whose names are read-model/module-specific rather than `module-contract-*`.

## Module Basic Info

| Field | Content |
| --- | --- |
| Module key | `read-models` |
| Module type | Resource/runtime module |
| Route | N/A |
| Frontend entry | `web/src/features/operationBarrier/api.ts` plus page API clients that consume `read_model_status` |
| Backend entry | `ReadModelQueryGateway`, `ReadModelRefreshGateway`, `OperationFreshnessBarrierService`, `READ_MODEL_MANIFEST`, runtime worker registry |
| Docs entry | `docs/modules/read-models/README.md` |
| Current owner | shared read model/runtime boundary |
| Refactor status | Contracted; production evidence remains deferred by module |

## Contract Reconciliation

### Inputs

| Input | Contract |
| --- | --- |
| Query reads | Must enter `ReadModelQueryGateway` or an explicitly registered equivalent freshness service with expected schema/source contract. |
| Refresh requests | Must enter `ReadModelRefreshGateway` and `ReadModelScopePolicyRegistry` for normalize, validate and dedupe before durable enqueue. |
| Transactional refresh | Must remain in the same business transaction and satisfy equivalent scope contract. |
| Operation barrier targets | Must be derived from write API affected scopes/freshness targets and checked through current-effective readiness/dirty/outbox state. |
| Force refresh | Must be controlled by runbook/API/smoke boundary with permission, scope validation, dedupe/idempotency, readiness proof and audit. |

### Outputs

| Output | Contract |
| --- | --- |
| API payload | Must expose `read_model_status` or equivalent freshness semantics, scope keys, stale/missing reasons and refresh enqueue status. |
| Write API result | Must include affected scopes/months, version/job or operation barrier target when cross-page visibility is affected. |
| Dirty scope/outbox | PostgreSQL durable queue remains source of truth. Redis and RabbitMQ cannot become state facts. |
| Readiness | Must be source/schema/version proven and current-effective. Historical covered failure cannot block current fresh/refreshing state. |
| Cache | Redis can store only fresh-gated payloads that pass payload contract validation. |

### State / Events

- `fresh`, `missing`, `refreshing`, `stale`, `failed` and `unavailable` remain the shared read model states.
- Added documentation for `validated`, `deduped`, `queued`, `force_refresh_requested`, `force_refresh_rejected`, `barrier_fresh`, `barrier_refreshing` and `barrier_blocked`.
- Domain/derived lifecycle events are producer hints; durable dirty/outbox and readiness are facts.
- Frontend domain events are refetch hints only.

### Read Model Refresh And Force Refresh

- Non-transactional refresh must go through `ReadModelRefreshGateway`.
- Transactional writers must carry an equivalent scope contract inside the write transaction.
- Force refresh is not a generic page action. It requires controlled caller, valid scope source, dedupe/idempotency, readiness proof and audit.
- Fan-out-only `all` scopes cannot publish fake parent fresh proof. Queryable `all` must be proven by child shards or a real parent aggregate.

### Partitioned Scoped Incremental Target

The shared target remains partitioned scoped read model + scoped incremental projection.

Exceptions and special cases:

- `workbench`: active generation atomic publish.
- `bank_account_balance`: all-only projection.
- `pending_invoice`: page-first-screen explicit scope; bare `all` rejected.
- `cost_statistics`: active/all shard plus parent aggregate scope.

### Permission / Audit

- Routes map HTTP/session to actor, tenant and permission.
- Services receive actor/permission results and must not read HTTP headers/cookies or import `app.auth`.
- Force refresh/runtime repair/scope cleanup require runbook/API/tool audit with actor, scope, reason and rollback evidence.
- Secrets, tokens and raw sensitive payloads must not be logged.

### Public Surface

- `ReadModelQueryGateway`
- `ReadModelRefreshGateway`
- `ReadModelScopePolicyRegistry`
- `OperationFreshnessBarrierService`
- `READ_MODEL_MANIFEST`
- Manifest-registered query facades, repository ports, refresh producers, derived lifecycle executors and worker handlers.

### Internal-Only Surface

- Raw durable queue writes except gateway-backed wrappers or transactionally equivalent writers.
- Raw readiness writes from business services.
- Unregistered `PostgresReadModelRepository` methods.
- Legacy `Application` read/cache/rebuild helpers as production freshness owners.
- Redis/RabbitMQ/frontend event facts.

### Legacy Status

| Legacy path | Status | Constraint |
| --- | --- | --- |
| Legacy/local query fallback | `compat-only` | Forbidden in production SQL runtime fresh path. |
| Combined worker lanes | `compat-only` | Cannot become new unique owner. |
| Fan-out-only `all` | quarantined semantics | Refresh command only unless a real aggregate proof exists. |
| Broad shared SQL repository | transition owner | Every public method needs a single manifest owner. |

## Test Contract

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rules or state transitions changed. |
| 2. Service-layer tests | Covered by existing guards | No runtime service changed; existing gateway/manifest/barrier tests protect the contract. |
| 3. API contract tests | Not applicable | No HTTP shape changed. |
| 4. Read model/cache/background job tests | Applicable, existing coverage | Manifest, refresh gateway, operation barrier, runtime worker registry and scope contract tests remain the enforcement layer. |
| 5. Frontend component and interaction tests | Not applicable | No UI/API client behavior changed. |
| 6. E2E business-flow integration tests | Not applicable for this docs pass | Business-flow evidence remains module-specific and production/staging dependent. |
| 7. Existing feature regression tests | Applicable, existing coverage | Manifest/architecture/module SQL runtime tests remain required before behavior-changing slices. |

## Files Updated

- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/read-models/implementation-notes.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-read-models.md`
- `.planning/refactors/modular-io-boundaries/parallel/handoffs/T8-module-io-contracts.md`

## Verification

Planned for this documentation-only pass:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- No real PostgreSQL/worker/App Status/high-row/browser evidence was collected.
- No specific page module was assigned to T8 in the prompt; this pass reconciles the shared read-model contract. If the controller assigns a page module later, page-specific API/DTO/UI/export/permission contracts should be filled in that module using this shared contract as the baseline.
