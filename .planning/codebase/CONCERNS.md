# Concerns

**Analysis Date:** 2026-06-16
**Scope:** Full repository map. This file records global risks and fragile areas.

## Global Risks

### `server.py` remains a broad boundary

- `backend/src/fin_ops_platform/app/server.py` still contains central application assembly, HTTP dispatch, dependency wiring, and some legacy route behavior.
- Risk: small endpoint changes can accidentally affect auth, permission mapping, session handling, or unrelated modules.
- Direction: keep new business behavior in services and route modules; use `server.py` mainly for HTTP mapping and dependency assembly.

### Legacy storage paths still exist

- PostgreSQL is production primary, but legacy Mongo/app state paths remain for migration observation, rollback, shadow-read, and audit tooling.
- Risk: new code may accidentally rely on compatibility snapshots or fallback stores.
- Direction: prefer PostgreSQL repositories and documented service boundaries; treat legacy paths as compatibility, not new feature targets.

### Read model freshness is a hard contract

- Pages must not read stale/missing read model payloads and present them as fresh.
- Risk: bypassing `ReadModelQueryGateway`, source-version guards, or operation barriers can reintroduce stale UI behavior.
- Direction: query through freshness/status gates, return explicit stale/refreshing fields, and cover with read model tests.

### Worker/runtime registry drift

- New read models, workers, job types, dependencies, and App Status domains require registry updates.
- Risk: production App Status can show misleading green/yellow/red states if registries diverge.
- Direction: update `runtime_worker_registry.py`, app status registries, manifest/env examples, tests, and docs together.

### Cross-page writes are easy to under-scope

- Workbench, bank details, invoice lifecycle, tax, cost, pending invoices, no-OA, turnover ledger, and search are linked through relation/read model cascades.
- Risk: write APIs refresh the local page but miss downstream scopes.
- Direction: use `DerivedDataLifecycleService`, dirty/outbox gateways, operation freshness barriers, and module test matrices.

### Frontend domain events are not durable facts

- `web/src/features/domainEvents.ts` is useful for same-browser refresh hints only.
- Risk: UI code may treat an event as proof that backend facts or read models are fresh.
- Direction: use events to trigger refetch, then rely on backend freshness/status fields.

### Deployment secrets and runtime env are sensitive

- OA token reuse, PostgreSQL DSNs, RabbitMQ, Redis, MinIO/S3, role sync, and Prometheus bearer tokens are deployment-sensitive.
- Risk: secrets can leak into docs or generated planning artifacts.
- Direction: keep secret values out of repository files; environment templates should use placeholders only.

## Performance Concerns

- Workbench and high-volume read models require active generation / materialized projection patterns and bounded retention.
- Cost statistics all-scope views must aggregate from fresh month shards rather than fake parent freshness.
- Large table rendering, exports, and real production data edge cases may not be fully covered by local fixtures.
- Request threads should not perform expensive live rebuilds for read models.

## Testing Concerns

- Local tests cannot fully prove production PostgreSQL historical data quality, RabbitMQ/Redis/systemd behavior, OA network behavior, or large XLSX/PDF/browser rendering behavior.
- Each behavior change should report which seven test categories apply and which remain untested.
- Module docs often contain historical bug regression lists; read them before modifying the module.

## Documentation Concerns

- Long-term docs are source of truth; historical prompts and old execution notes are not.
- Risk: page-specific findings can be lost if they are written only to `.planning/codebase/`.
- Direction: page analysis goes into `.planning/phases/<phase>/`; durable conclusions are promoted to `docs/modules/<module>/` or long-term docs after review.

## Parallel Work Concerns

- Multiple Codex threads writing `.planning/codebase/*.md` will overwrite or conflict.
- Worktree threads should have disjoint write targets.
- For the current page-analysis setup:
  - Phase 1 writes `.planning/phases/01-turnover-ledger-improvements/`.
  - Phase 2 writes `.planning/phases/02-bank-details-improvements/`.
  - Phase 3 writes `.planning/phases/03-tax-offset-improvements/`.
  - None of those page threads should update `.planning/codebase/*.md`.

## Migration / Refactor Concerns

- Backend refactor direction is documented under `docs/architecture/backend-refactor/`.
- Avoid piling new behavior into legacy modules when a current central boundary already exists.
- If a feature requires broad refactor, stop and plan the expanded scope before implementation.

## Operational Concerns

- Production release entry is `./scripts/deploy-oa.sh`.
- Worker readiness is not the same as systemd active.
- Read model repair must use documented tools and audit trails rather than manually forcing readiness to `fresh`.
- App Health red/yellow/green must derive from current-effective runtime blockers, not stale historical failures.
