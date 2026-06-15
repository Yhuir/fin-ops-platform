# Testing

**Analysis Date:** 2026-06-16
**Scope:** Full repository map. This file records global test and verification strategy.

## Primary Verification Entrypoints

```bash
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh docs
bash scripts/verify.sh all
```

`scripts/verify.sh all` runs backend app check, backend unittest discovery, frontend Vitest, frontend build, and docs checks.

## Backend Tests

- Backend tests live under `tests/`.
- Default command: `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`.
- App readiness check: `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`.
- Test files are organized by API, service, repository, runtime queue/worker, read model refresh, App Status, deployment, and domain modules.

## Frontend Tests

- Frontend tests live under `web/src/test/`.
- Default command: `cd web && npm test -- --run`.
- Build/type verification: `cd web && npm run build`.
- Tests use Vitest, Testing Library, jsdom, user-event, and shared render/mock helpers.
- `web/src/test/apiMock.ts` provides broad mocked API behavior for app/page tests.

## Docs Tests

- Docs verification is `bash scripts/verify.sh docs`.
- It checks stale references and required docs such as `docs/dev/testing.md`, `docs/dev/nightly-ci.md`, `docs/dev/testing-closure-state.md`, `docs/dev/testing-closure-dependency-map.md`, and `docs/modules/README.md`.

## Module Test Matrices

- Each page/resource module should maintain a `docs/modules/<module>/tests.md` matrix.
- For page work, read that matrix before changing code.
- Module matrices list business core tests, service/API/read model/frontend tests, integration paths, smoke flows, and known untested risks.

## Seven Test Categories

For behavior changes, evaluate:

1. Business core unit tests.
2. Service-layer tests.
3. API contract tests.
4. Read model/cache/background job tests.
5. Frontend component and interaction tests.
6. End-to-end business-flow integration tests.
7. Existing feature regression tests.

Do not add low-value tests mechanically, but do cover applicable failure paths, permission paths, stale/refreshing states, idempotency, and affected old behavior.

## Runtime / Worker Testing

- Runtime queue tests include `tests/test_runtime_queue.py`, `tests/test_runtime_worker.py`, `tests/test_runtime_worker_registry.py`, and related read model tests.
- App Status tests include `tests/test_app_status_overview_service.py`, `tests/test_app_health_api.py`, and frontend app status tests.
- Worker manifest and deployment expectations are guarded by tests such as deploy/runtime example tests.

## API Testing Pattern

- Backend API tests should assert status, response shape, error code/message, freshness fields, version/idempotency fields, and affected scopes where relevant.
- Frontend API tests should verify request URLs, payload mapping, response mapping, error behavior, and blob/download handling.
- Do not assert only `status_code == 200` for changed contracts.

## Frontend Interaction Pattern

- Prefer user-observable behavior: loading, empty, stale, refreshing, error, permission disabled state, drawer/dialog open/close, filters, sorting, pagination, search, export, and post-write reload.
- Use existing render helpers and mock API patterns in `web/src/test/`.
- Preserve route/page activation behavior from the app shell.

## Performance / Production Smoke

- Some risks require staging/production smoke rather than local fixtures: real PostgreSQL data volume, RabbitMQ/Redis/systemd worker drain, object storage, OA connectivity, file downloads, and large table rendering.
- Document remaining untested risks in final responses and module docs when relevant.

## Planning Boundary

- Page-specific testing research belongs in the page phase directory.
- Global testing conventions stay here.
- Do not rewrite this global test map for a single page.
