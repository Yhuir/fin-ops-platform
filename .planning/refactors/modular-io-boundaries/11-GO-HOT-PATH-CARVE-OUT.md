# Go Hot Path Carve-out Plan

**Status:** Planning only
**Purpose:** Define how Go, Go Fiber, and Go Worker may be introduced after module IO boundaries are clear.
**Non-goal:** This is not a full Python backend replacement plan.

## Decision

This refactor plan accepts Go / Go Fiber / Go Worker as a hot-path carve-out strategy, but rejects a full Go Fiber replacement as the current main line.

Target architecture:

```text
Python facade for auth/audit/API compatibility
+ canonical write ownership
+ module IO contracts
+ partitioned scoped read models
+ scoped incremental projection
+ Go Worker execution
+ PostgreSQL dual queue
+ Workbench active generation swap
+ summary rollups
+ fresh-gated Redis cache
```

Go Fiber is an HTTP/API boundary for selected Go services. It is not a replacement for read models, workers, durable queue, freshness proof, operation barrier, permissions, or audit.

## Fiber vs Go Worker

| Need | Preferred runtime | Notes |
| --- | --- | --- |
| Long-running projection | Go Worker | Do not run long jobs inside a Fiber request handler. |
| Matching/grouping/check computation | Go Worker or Go compute service | Fiber optional only if an internal HTTP API is needed. |
| Import parse/normalize/preview | Go Processor or Go service | Fiber acceptable for internal preview API; canonical confirm remains Python-first initially. |
| Summary/rollup builder | Go Worker | Fiber optional for read-only internal service. |
| OA sync/adapter | Go Worker or Go service | Only after OA module IO contract is complete. |
| Frontend-facing business API | Python facade first | Preserve current API shape, session, permission, and audit behavior. |

## Candidate-gated Carve-out

Go migration is not an automatic global behavior.

Only modules in this candidate list may be evaluated by the autonomous flow. Candidate status does not mean implementation is approved; every candidate still must pass the admission gates below.

| Priority | Candidate | Go shape | Fiber use | Reason |
| --- | --- | --- | --- | --- |
| P1-A | `workbench:matching-grouping-check` | Go Worker / Go compute service | Optional | CPU-heavy calculation path with clear input/output potential. |
| P1-B | `workbench:read-model-builder` | Go Worker | Not required initially | Active generation, month shard, all aggregate and consistency checks are performance-sensitive. |
| P1-C | `imports:parse-normalize-preview` | Go Processor / Go service | Optional internal API | Large file parsing and normalization can be isolated before canonical confirm. |
| P2-A | `cost-statistics:summary-rollup` | Go Worker / Go read service | Optional | Summary and rollup are better served by precomputed scoped projections. |
| P2-B | `bank-details:read-model-builder` | Go Worker | Not required initially | High-frequency page with cross-page impact and scope-friendly facts. |
| P3-A | `pending-invoices:search-projection` | Go Worker | Optional | Search and pending invoice projection can be optimized after contract stabilization. |
| P3-B | `oa:sync-adapter-projection` | Go Worker / Go service | Optional internal API | Feasible after OA boundaries, timeout, retry, cache and idempotency contracts are clear. |
| P3-C | `invoice-usage-collection:projection-builders` | Go Worker | Not required initially | Shared worker handles input usage, output collection and OA pending payment projections. |
| P3-D | `turnover-ledger:read-model-builder` | Go Worker | Not required initially | Ledger projection affects workbench, cost and search chains. |
| P4-A | `tax-offset:read-model-builder` | Go Worker | Not required initially | Later migration after invoice lifecycle and tax scope contracts are stable. |
| P4-B | `no-oa-bank-batches:read-model-builder` | Go Worker | Not required initially | Later migration after bank detail and no-OA contracts are stable. |
| P4-C | `bank-account-balance:read-model-builder` | Go Worker | Not required initially | Later migration, useful for account-level partitioned refresh. |

Do not automatically Go-migrate:

- auth/session/permission.
- audit.
- canonical write command services.
- settings.
- app health status decision logic.
- route-only HTTP mapping.
- modules without a complete IO contract.
- legacy modules whose old write paths are not retired or quarantined.

## Admission Gates

A candidate may enter Go implementation only when all gates pass:

- It is listed in the candidate table above.
- Module IO contract is complete.
- Legacy retirement/quarantine contract is complete.
- Read model freshness, force refresh and operation barrier contract is complete or explicitly not applicable.
- Performance evidence exists, such as API p95, SQL p95, worker lag, enqueue-to-fresh latency, CPU, memory, import parse time, or payload size.
- Input and output are stable enough for contract tests.
- Shadow run is possible.
- Rollback to Python is possible per module or per worker.
- Basic correctness can be verified without staging DB or local `PGSQL_URL`.
- It does not require production writes to prove basic behavior.
- It does not weaken Python facade auth, audit or API compatibility.

If any gate fails, mark the candidate `go-candidate-deferred` and continue with non-Go module hardening.

## Read Model Target For Every Page

`Partitioned Scoped Read Model` and `Scoped Incremental Projection` are not alternatives. They are the combined target.

- Partitioned scoped read model defines how derived data is stored and read.
- Scoped incremental projection defines how only affected scopes are refreshed.

| Domain / page | Current source | Target strategy | Notes |
| --- | --- | --- | --- |
| Workbench / reconciliation | `workbench`, `workbench_relation` | Active generation + partitioned scoped incremental projection | Preserve active generation, month shards, all aggregate, consistency check and atomic publish. |
| Batch Accounting | `workbench_relation` | Partitioned scoped incremental projection | Page owns no independent read model; relation scope freshness must be explicit. |
| Bank Details | `bank_detail`, `bank_account_balance` | Partitioned scoped incremental projection | Partition by account, month, import batch and tag/rule impact scope. |
| Turnover Ledger | `turnover_ledger` | Partitioned scoped incremental projection | Partition by counterparty/family/case/month scope. |
| Pending Invoices | `pending_invoice`, `search`, `invoice_lifecycle` | Partitioned scoped incremental projection | Partition by direction, month, invoice lifecycle and rule version scope. |
| OA Pending Payments | `oa_pending_payment`, `invoice_lifecycle` | Partitioned scoped incremental projection | Partition by OA flow/payment status/month/invoice relation scope. |
| Input Invoice Usage | `input_invoice_usage`, `invoice_lifecycle` | Partitioned scoped incremental projection | Partition by invoice, month, certification and usage state. |
| Output Invoice Collections | `output_invoice_collection`, `invoice_lifecycle` | Partitioned scoped incremental projection | Partition by customer, month and collection relation scope. |
| Tax Offset | `tax_offset`, `invoice_lifecycle` | Partitioned scoped incremental projection | Partition by tax period, month and certification status. |
| Cost Statistics | `cost_statistics` | Partitioned scoped + parent aggregate incremental projection | Month shards first; parent all scope aggregates only from fresh shards. |
| No-OA Bank Batches | `no_oa_bank_batch` | Partitioned scoped incremental projection | Partition by account, month, batch and status scope. |
| Import pages | import jobs | Go import processor + downstream scoped projection | Import page tracks job/preview state; downstream domains own read model freshness. |
| ETC Tickets | import jobs and batch state | Job scoped first; add partitioned read model only if query performance requires it | Do not build a read model before a measured read bottleneck. |
| Settings | settings/state store/OA identity | Config version + targeted invalidation | Config changes trigger affected read model scopes, not global rebuild by default. |
| App Health / Operations | runtime facts | Current-effective runtime projection | PostgreSQL runtime facts remain the source; UI does not infer readiness. |

## Go Worker Target

All runtime workers may eventually migrate to Go Worker, but only worker-by-worker.

Primary runtime:

```text
Go Worker
+ PostgreSQL dual queue
+ batch claim
+ SKIP LOCKED / lease / retry
+ goroutine pool
+ heartbeat
+ readiness/freshness proof
+ per-worker rollback
```

PostgreSQL dual queue means:

```text
job.outbox_events
+ job.read_model_dirty_scopes
```

RabbitMQ is optional future wakeup/transport. It must not become the job, read model or freshness source of truth.

## Worker Migration Targets

| Worker instance | Target | Migration note |
| --- | --- | --- |
| `workbench` | Go Worker | Preserve active generation and consistency proof. |
| `workbench-matching` | Go Worker | First compute pilot candidate. |
| `workbench-relation` | Go Worker | Migrate after relation contract and batch accounting regression are stable. |
| `bank-detail` | Go Worker | Candidate after scoped partition keys are proven. |
| `bank-account-balance` | Go Worker | Later account-level scoped projection. |
| `turnover-ledger` | Go Worker | Migrate after closure/cost/search fan-out is stable. |
| `search` | Go Worker | Candidate for search projection; keep `search-secondary` and `search-tertiary` strategy explicit. |
| `pending-invoice` | Go Worker | Migrate after pending invoice rule/version scope is stable. |
| `invoice-lifecycle` | Go Worker | High impact; migrate after invoice lifecycle contract is fully covered. |
| `invoice-usage-collection` | Go Worker | Shared projection worker; migrate after input/output/OA pending payment contracts are stable. |
| `cost-statistics` | Go Worker | Candidate for summary/rollup pilot. |
| `tax-offset` | Go Worker | Later migration after invoice lifecycle dependency is stable. |
| `import` | Go Worker / Go Processor | Candidate for parser/normalizer/preview first; canonical confirm remains Python-first initially. |
| `no-oa-bank-batch` | Go Worker | Later migration after bank detail/no-OA contracts are stable. |
| `oa-sync` | Go Worker / Go service | Candidate only after OA IO contract and idempotency are stable. |
| `file-migration` | Go Worker optional | Non-required worker; migrate only with object storage/GridFS plan. |

Compatibility workers such as `search-pending` and `cost-tax` should be retired or quarantined as `compat-only` instead of becoming primary Go targets.

## Shadow Run And Equivalence

Go implementation must pass shadow run before owning production output.

Shadow mode:

- Python implementation remains the reference.
- Go implementation receives the same input.
- Go output is compared but not published.
- Go does not ack outbox, mark dirty scope done, publish active generation, or write readiness.

Equivalence checks:

- rows and row count.
- summaries and totals.
- ordering and pagination.
- filters and grouping keys.
- source version and schema version.
- affected scopes.
- readiness metadata.
- error shape.
- empty state semantics.
- permissions and audit visibility if the boundary exposes API behavior.

## Double-write Prevention

Forbidden:

- Python worker and Go worker both ack the same durable event.
- Python worker and Go worker both publish the same read model generation.
- Go code writes unregistered canonical facts.
- Go code directly mutates dirty scope, outbox, readiness or cache outside the registered queue/repository contract.
- Go code returns stale payload as fresh.
- Go hot path leaves an active Python legacy write path for the same scope.

Allowed:

- Shadow-only dual execution when Go output is non-authoritative and cannot publish, ack or alter readiness.
- Controlled rollback to Python by disabling the Go worker/route and re-enabling the Python worker for the same event types.

## Go Module Completion Definition

A Go hot-path module is complete only when:

- IO contract is complete.
- Go contract section is complete.
- Python facade behavior remains compatible.
- Shadow run has passed or produced accepted differences.
- Legacy Python write path is removed or quarantined as `compat-only`.
- Go worker/service has health/check/version behavior.
- Worker registry, App Status registry, deploy env and manifest are updated if implementation changes runtime facts.
- Logs include trace id, event id, scope, worker instance and source version where applicable.
- Timeouts, retry policy, resource limits and rollback switch are documented.
- Tests cover Python old output vs Go new output.
- Read model freshness proof and operation barrier behavior are unchanged or explicitly migrated with tests.
- Production DB/worker evidence is collected or recorded as `production-evidence-deferred`.

## Migration Phases

### Go-0: Performance Baseline

Collect evidence before Go implementation:

- API p95 / p99.
- SQL p95 / p99.
- worker lag and heartbeat.
- read model enqueue-to-fresh latency.
- CPU and memory.
- import parse/normalize time.
- payload size and serialization cost.

### Go-1: Workbench Compute Pilot

Go-migrate matching/grouping/check as shadow-only first.

### Go-2: Scoped Incremental Projection Pilot

Choose one read model builder and implement partitioned scoped incremental projection with Go Worker.

### Go-3: Summary Rollup Pilot

Introduce precomputed rollup and optional Go builder for a high-frequency summary path.

### Go-4: Import Parser Pilot

Move parse/normalize/preview to Go Processor or internal Fiber service. Keep canonical confirm Python-first initially.

### Go-5: OA Module Carve-out

After OA IO contract is complete, migrate adapter/sync/parse/cache layers. External OA latency must be handled by timeout, retry, idempotency, cache and circuit breaker contracts, not by language choice alone.

## Autonomous Rules

Autonomous execution may evaluate only the candidate list in this file.

It must not introduce a Go implementation unless:

- the candidate passes all admission gates,
- tests can be added before implementation,
- shadow run or equivalent fake/stub comparison can be built,
- rollback is documented,
- no secret, staging DB or local `PGSQL_URL` is required for basic verification.

If a candidate fails admission, record:

```text
go-candidate-deferred
```

and continue with Python module boundary hardening or the next independent module.

