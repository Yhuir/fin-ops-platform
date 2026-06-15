# Architecture

**Analysis Date:** 2026-06-16
**Scope:** Full repository map. This file is the global architecture map.

## System Overview

`fin-ops-platform` is a finance operations platform covering imports, reconciliation workbench, bank details, pending invoices, OA pending payments, tax offset, input/output invoice usage, cost statistics, no-OA batches, turnover ledger, ETC ticket management, settings, and App Health.

```text
React/Vite frontend
  -> feature API clients
  -> Python HTTP routes
  -> application/domain services
  -> repositories / stores
  -> PostgreSQL facts + read models + durable queue
  -> runtime workers rebuild projections
  -> frontend reads through freshness/status boundaries
```

## Frontend Architecture

- Route registry is centralized in `web/src/app/pageRegistry.tsx`.
- Route host is `web/src/app/PageRouteHost.tsx`, wired by `web/src/app/router.tsx`.
- Pages live in `web/src/pages/` and page subdirectories such as `web/src/pages/imports/`.
- Feature clients and DTO mappers live in `web/src/features/*/api.ts` and `web/src/features/*/types.ts`.
- Shared UI components live under `web/src/components/`.
- Shared app contexts live under `web/src/contexts/`.
- Table/session hooks live under `web/src/hooks/`.

## Backend Architecture

- Backend entry point is `backend/src/fin_ops_platform/app/main.py`.
- `backend/src/fin_ops_platform/app/server.py` still handles central application assembly, HTTP dispatch, session/auth mapping, and legacy route code.
- Route modules under `backend/src/fin_ops_platform/app/routes_*.py` provide more focused HTTP boundaries for page/API domains.
- Business services live under `backend/src/fin_ops_platform/services/`.
- Domain models live under `backend/src/fin_ops_platform/domain/`.
- PostgreSQL repository and migration code lives under `backend/src/fin_ops_platform/postgres/` and `backend/src/fin_ops_platform/services/postgres_repositories/`.
- Operational tools live under `backend/src/fin_ops_platform/tools/`.

## Write Model

- Routes parse HTTP shape, map permissions, and call explicit services.
- Services validate business rules and call repositories or units of work.
- Writes should emit dirty scopes/outbox events through lifecycle/gateway boundaries.
- Cross-module writes must preserve permissions, audit, idempotency, stale/version checks, and rollback behavior.
- Service constructors should receive explicit dependencies, not a whole application object.

## Read Model

- Read model queries must go through freshness/status gates such as `ReadModelQueryGateway`.
- Missing, dirty, schema mismatch, source version mismatch, or unavailable read models must not be presented as fresh.
- Fresh payloads may be cached in Redis only after the fresh gate.
- Workbench has a special active-generation atomic publish model and should not be forced into a generic read model pattern.

## Runtime Worker Model

- Durable truth is PostgreSQL queue state in `job.outbox_events` and `job.read_model_dirty_scopes`.
- Worker instances and event registrations are defined in `runtime_worker_registry.py`.
- Workers rebuild SQL projections and complete dirty scopes.
- Workers must not depend on HTTP request state, cookies, headers, Flask response objects, or `Application`.
- RabbitMQ can transport wakeups but cannot become the state authority.

## Page / Domain Ownership

- Module ownership and page facts are indexed under `docs/modules/README.md`.
- App architecture facts are under `docs/app-architecture/`.
- Product facts are under `docs/product-specs/`.
- Developer/API/testing facts are under `docs/dev/`.
- Operations facts are under `docs/operations/`.
- Page-specific work should start from the corresponding `docs/modules/<module>/README.md`.

## App Status Plane

- App Status is derived on the backend from session, background jobs, read model dirty scopes, outbox, worker heartbeat, runtime registry, dependencies, alerts, and readiness records.
- Frontend page loading does not write global runtime status.
- Registries must stay in sync: domain registry, read model registry, worker registry, background job registry, and dependency registry.

## Data Flow

```text
OA MongoDB / Excel / PDF / ZIP / user actions
  -> adapters/import services/routes
  -> domain services and canonical facts
  -> PostgreSQL app store
  -> derived lifecycle + runtime queue
  -> runtime workers
  -> SQL read models / active generations
  -> React pages through API clients
```

## Cross-Page Consistency

- Domain events in `web/src/features/domainEvents.ts` are same-browser refresh hints only.
- Durable consistency is maintained through backend derived lifecycle, dirty scopes, outbox events, read model refresh, and operation barriers.
- Write APIs should return enough affected scope information for the frontend to wait on operation freshness before releasing full-screen write overlays.

## Architectural Direction

- Continue moving route logic out of `server.py` into route modules and services.
- Keep business logic in services and SQL details in repositories.
- Preserve PostgreSQL primary behavior while legacy Mongo paths remain only for migration/rollback/shadow-read cases.
- Treat read model freshness and worker readiness as production contracts, not optional UI hints.

## Planning Boundary

- This file is intentionally global.
- Do not overwrite it with page-specific focused analysis.
- Page analysis belongs in `.planning/phases/<phase>/CONTEXT.md`, `.planning/phases/<phase>/RESEARCH.md`, and phase plan files.
