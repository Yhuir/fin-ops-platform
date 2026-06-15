# Integrations

**Analysis Date:** 2026-06-16
**Scope:** Full repository map. This file describes global integration boundaries.

## PostgreSQL

- PostgreSQL is the primary production fact store, durable queue store, read model store, and App Status readiness store.
- Connection and runtime helpers live in `backend/src/fin_ops_platform/services/postgres_connection.py`, `backend/src/fin_ops_platform/services/postgres_state_store.py`, and `backend/src/fin_ops_platform/services/postgres_repositories/`.
- Migrations live in `backend/src/fin_ops_platform/postgres/migrations/`.
- Runtime queue state lives in `job.outbox_events` and `job.read_model_dirty_scopes`.
- App Status readiness uses read model readiness projections described by `docs/operations/runtime-worker-governance.md`.

## OA System

- OA same-domain deployment is documented in `deploy/oa/README.md`.
- Frontend runs under `/fin-ops/`, backend under `/fin-ops-api/`, and OA embeds the app through iframe/menu entry points.
- Session bootstrap uses OA `Admin-Token` and `/api/session/me`.
- OA identity and permissions are handled by `backend/src/fin_ops_platform/services/oa_identity_service.py`, `backend/src/fin_ops_platform/app/auth.py`, and related route mapping in `server.py`.
- OA MongoDB is read-only through `backend/src/fin_ops_platform/services/mongo_oa_adapter.py` and `backend/src/fin_ops_platform/services/oa_adapter.py`.
- OA role/menu sync uses MySQL integration via `PyMySQL` and deployment templates under `deploy/oa/`.

## File Imports And Object Storage

- Import services live under `backend/src/fin_ops_platform/services/import_*`, `backend/src/fin_ops_platform/services/imports.py`, and route/API tests under `tests/test_import*.py`.
- Excel parsing/export uses `openpyxl` and `xlrd`.
- PDF/OCR flows use `pdfplumber`, `pymupdf`, and `rapidocr_onnxruntime`.
- Object storage abstractions live in `backend/src/fin_ops_platform/services/object_storage.py`.
- Migration and object identity/dedup tooling live in `backend/src/fin_ops_platform/tools/` and service modules such as `object_identity_policy.py`.

## RabbitMQ

- RabbitMQ is optional runtime transport/wakeup for worker delivery.
- Topology and dispatcher code lives in `backend/src/fin_ops_platform/app/rabbitmq_topology.py`, `backend/src/fin_ops_platform/app/rabbitmq_dispatcher.py`, and `backend/src/fin_ops_platform/services/rabbitmq_runtime.py`.
- Deployment env templates live under `deploy/oa/env/fin-ops.rabbitmq-*.env.example`.
- RabbitMQ must not become the read model state source; PostgreSQL remains authoritative.

## Redis

- Redis runtime helpers live in `backend/src/fin_ops_platform/services/runtime_redis.py`.
- Redis is used for fresh-gated payload caching and runtime support.
- Redis cache keys must be tied to schema/source versions/generation/query hashes where relevant.
- Redis must not cache stale read model payloads as fresh.

## Runtime Workers

- Worker entry point: `backend/src/fin_ops_platform/app/worker.py`.
- Registry: `backend/src/fin_ops_platform/services/runtime_worker_registry.py`.
- Worker handlers: `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`.
- Manifest CLI: `backend/src/fin_ops_platform/tools/runtime_worker_manifest.py`.
- Governance doc: `docs/operations/runtime-worker-governance.md`.
- Systemd templates: `deploy/oa/systemd/fin-ops-worker@.service.example`.

## App Health And Monitoring

- App status registries live in `backend/src/fin_ops_platform/services/app_status_*_registry.py`.
- Runtime monitoring lives in `backend/src/fin_ops_platform/services/runtime_monitoring.py`.
- App Health services include `app_health_service.py`, `app_health_alert_service.py`, `operations_dashboard.py`, and `app_status_overview_service.py`.
- Prometheus metrics support exists in `backend/src/fin_ops_platform/services/prometheus_metrics.py`.
- Frontend app health clients live in `web/src/features/appHealth/` and `web/src/features/appStatus/`.

## Frontend API Boundary

- Frontend API clients live under `web/src/features/*/api.ts`.
- Browser-facing feature types live under `web/src/features/*/types.ts`.
- `web/src/test/apiMock.ts` provides broad mocked API behavior for frontend tests.
- Frontend domain events live in `web/src/features/domainEvents.ts`; they are refresh hints, not durable facts.

## Permission And Session Boundary

- Access control is handled by `backend/src/fin_ops_platform/services/access_control_service.py` and route-level auth helpers.
- Session API client: `web/src/features/session/api.ts`.
- Session gate/provider tests live under `web/src/test/Session*.test.tsx` and `web/src/test/SessionApi.test.ts`.
- Mutating APIs must preserve backend permission checks and frontend permission-based disabled/hidden states.

## Deployment And Environment

- OA deployment guide: `deploy/oa/README.md`.
- Main deployment script: `scripts/deploy-oa.sh`.
- Runtime env examples live under `deploy/oa/env/` and `deploy/oa/fin_ops.env.example`.
- Local backend startup reads `.runtime/fin_ops_platform/local-postgres.env` through `scripts/start-backend.sh` when present.

## Integration Rule

When a page-specific phase discovers integration details, save the analysis in that phase directory. Promote only durable facts into `docs/modules/<module>/` or long-term docs after review. Do not overwrite this global integration map for page analysis.
