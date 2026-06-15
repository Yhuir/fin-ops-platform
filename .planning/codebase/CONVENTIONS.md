# Conventions

**Analysis Date:** 2026-06-16
**Scope:** Full repository map. This file records global coding and workflow conventions.

## Repository Instructions

- Start with `AGENTS.md`, then `README.md`, `ARCHITECTURE.md`, `docs/index.md`, app architecture docs, module docs, product specs, dev docs, and operations docs.
- For any page or feature change, first identify the target module in `docs/modules/README.md`.
- Read the module `README.md`; if state/API/read model/worker/permissions/tests are affected, also read module `state-machine.md`, `tests.md`, and `implementation-notes.md`.
- Do a docs impact assessment for feature, API, architecture, read model, worker, operations, permission, audit, or data-flow changes.

## Backend Boundaries

- `server.py` should stay focused on routing, dependency assembly, and HTTP mapping.
- Business logic belongs in `backend/src/fin_ops_platform/services/`.
- SQL table knowledge belongs in repositories, especially under `services/postgres_repositories/`.
- Worker code must not depend on `Application`, HTTP response objects, cookies, headers, or `app.auth`.
- Services should receive explicit dependencies such as repositories, queues, stores, orchestrators, and settings providers.

## Read Model Conventions

- Query services must go through freshness/status/enqueue boundaries before returning SQL read model payloads.
- Missing/stale/schema-mismatch/source-mismatch read models should return refreshing/stale status and enqueue refresh where appropriate.
- Redis payloads are valid only after a fresh gate.
- RabbitMQ is transport/wakeup only.
- New read models or workers require registry, manifest/systemd env, tests, and docs updates.

## Frontend Conventions

- Page registration is centralized in `web/src/app/pageRegistry.tsx`.
- Page entry components live in `web/src/pages/`.
- API clients live in `web/src/features/*/api.ts`; DTO/domain types live in `web/src/features/*/types.ts`.
- Use user-observable behavior in tests rather than component internals.
- Write operations that affect backend facts or cross-page read models should use operation barrier/overlay patterns where the module requires it.
- Domain events are refresh hints only, not proof of freshness.

## Testing Conventions

- Backend verification uses `PYTHONPATH=backend/src python3 -m unittest ...`.
- Frontend verification uses `cd web && npm test -- --run ...` and `npm run build`.
- Full repository verification uses `bash scripts/verify.sh all`.
- Module test matrices under `docs/modules/<module>/tests.md` define targeted test commands and historical regression coverage.
- Behavior changes must evaluate the seven test categories from `AGENTS.md`.

## Documentation Conventions

- Long-term business facts go under `docs/product-specs/`.
- Current page/API/runtime/read model facts go under `docs/app-architecture/` or `docs/dev/`.
- Module maintenance facts go under `docs/modules/<module>/`.
- Operations and deployment facts go under `docs/operations/` and `deploy/oa/`.
- Historical prompts and raw execution notes should not be added to main docs.

## Error Handling And Contracts

- Validate external input, inferred state, versions, and permissions explicitly.
- Fail fast on missing dependencies or invalid invariants rather than adding broad fallback branches.
- Preserve idempotency, stale/version checks, audit records, dirty/outbox writes, and rollback behavior for mutating paths.
- API tests should assert contract fields, not only HTTP status.

## Git / Planning Conventions

- Keep changes scoped and reversible.
- Do not revert user changes.
- GSD page-specific analysis belongs in `.planning/phases/<phase>/`.
- `.planning/codebase/` is a global map and should only be refreshed as a full repository map, not as page storage.
- Parallel page work should use separate worktree threads and avoid overlapping write targets.

## Dependency Conventions

- Do not add dependencies unless the value clearly outweighs maintenance, security, licensing, bundle-size, and integration cost.
- Prefer local abstractions and existing libraries already present in the repository.
- For common concerns, inspect existing helpers before adding new implementations.
