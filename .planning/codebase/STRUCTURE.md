# Structure

**Analysis Date:** 2026-06-16
**Scope:** Full repository map. This file describes repository layout globally.

## Top-Level Layout

```text
backend/        Python backend source and requirements
web/            React + TypeScript frontend
tests/          Backend unittest suite
docs/           Long-term architecture, product, dev, operations, and module docs
deploy/         OA deployment assets
fixtures/       Local manual validation samples
scripts/        Local startup, verification, deployment, runtime helper scripts
.planning/      GSD planning artifacts and global codebase map
```

## Backend Layout

- `backend/requirements.txt` pins backend runtime dependencies.
- `backend/src/fin_ops_platform/app/` contains server entry points, auth helpers, route modules, worker entry, RabbitMQ dispatcher/topology, and backfill CLIs.
- `backend/src/fin_ops_platform/services/` contains business services, read model refresh services, runtime queue/worker services, app status services, import services, and integration adapters.
- `backend/src/fin_ops_platform/services/postgres_repositories/` contains repository implementations that know SQL table structure.
- `backend/src/fin_ops_platform/domain/` contains domain-level models and policies.
- `backend/src/fin_ops_platform/postgres/migrations/` contains PostgreSQL schema migrations.
- `backend/src/fin_ops_platform/tools/` contains operational and migration tools.

## Frontend Layout

- `web/package.json` defines frontend scripts and dependencies.
- `web/src/app/` contains route registry, router, and route host.
- `web/src/pages/` contains page entry components.
- `web/src/pages/imports/` contains import page entries.
- `web/src/features/` contains per-domain API clients and types.
- `web/src/components/` contains shared and domain-specific UI components.
- `web/src/contexts/` contains app/session/runtime contexts.
- `web/src/hooks/` contains shared hooks such as finance table session behavior.
- `web/src/test/` contains Vitest tests, mocks, render helpers, and frontend test setup.

## Documentation Layout

- `AGENTS.md` is the repository agent navigation entry.
- `README.md` is the project overview and quick start.
- `ARCHITECTURE.md` is the high-level system architecture.
- `docs/index.md` is the long-term documentation map.
- `docs/app-architecture/` describes current page/runtime/read model/worker architecture.
- `docs/modules/` stores page and resource module maintenance docs.
- `docs/product-specs/` stores business/product contracts.
- `docs/dev/` stores API, testing, local development, and runtime development docs.
- `docs/operations/` stores deployment, data safety, worker/read model governance, and monitoring docs.

## Module Documentation Pattern

Each module under `docs/modules/<module>/` normally includes:

- `README.md` for module boundary, route, code entry points, and required reading.
- `state-machine.md` for business/UI/read model/worker state.
- `tests.md` for test matrix and verification commands.
- `implementation-notes.md` for distilled decisions and risk notes.

## Backend Test Layout

- Backend tests live directly under `tests/` as `test_*.py`.
- Tests cover API routes, service behavior, repositories, migrations, runtime queue/worker, read model refresh, App Status, imports, OA integration, workbench, banking, tax, cost, ETC, and deployment scripts.
- `pytest.ini` exists for tooling compatibility, but the documented backend entry point is `python3 -m unittest discover -s tests -v`.

## Frontend Test Layout

- Frontend tests live in `web/src/test/`.
- Tests are grouped by page, API client, domain events, shared components, and runtime contexts.
- `web/src/test/apiMock.ts` is the broad frontend mock API surface.
- `web/src/test/renderHelpers.tsx` and domain-specific helpers support user-observable component tests.

## Runtime And Deployment Layout

- `scripts/verify.sh` is the main verification script.
- `scripts/start-backend.sh` and `scripts/start-web.sh` start local backend/frontend.
- `deploy/oa/` contains OA same-domain deployment docs, env templates, systemd templates, nginx/config assets, and SQL snippets.
- `.runtime/fin_ops_platform/` is used locally for runtime env/data and should not be treated as source truth.

## GSD Planning Layout

- `.planning/codebase/` contains seven global map documents: stack, integrations, architecture, structure, conventions, testing, and concerns.
- `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, and `.planning/STATE.md` describe current GSD planning state.
- `.planning/phases/01-turnover-ledger-improvements/`, `.planning/phases/02-bank-details-improvements/`, and `.planning/phases/03-tax-offset-improvements/` are page-specific phase containers.
- Page-specific analysis must be added under the relevant phase directory, not under `.planning/codebase/`.

## Naming Patterns

- Backend route modules use `routes_<domain>.py`.
- Backend read model refresh services often use `<domain>_read_model_refresh.py`.
- Frontend page entries use `<Name>Page.tsx`.
- Frontend feature API clients use `web/src/features/<domain>/api.ts`.
- Tests use `test_<domain>.py` for backend and `<Domain>.test.ts(x)` for frontend.
