# Technology Stack

**Analysis Date:** 2026-06-16
**Scope:** Full repository map. This file is the global codebase map, not a page-specific analysis artifact.

## Primary Languages

- Python powers the backend service, domain services, runtime workers, PostgreSQL migrations, import/export tooling, OCR helpers, and deployment checks under `backend/src/fin_ops_platform/`.
- TypeScript powers the React frontend under `web/src/`.
- SQL is maintained through PostgreSQL migrations under `backend/src/fin_ops_platform/postgres/migrations/`.
- Shell scripts under `scripts/` and `deploy/oa/` manage local startup, verification, runtime checks, and OA deployment.

## Backend Runtime

- Entry point: `backend/src/fin_ops_platform/app/main.py`.
- HTTP service and dependency assembly: `backend/src/fin_ops_platform/app/server.py`.
- Route modules: `backend/src/fin_ops_platform/app/routes_*.py`.
- Worker entry point: `backend/src/fin_ops_platform/app/worker.py`.
- Runtime worker registry: `backend/src/fin_ops_platform/services/runtime_worker_registry.py`.
- The backend uses a custom Python HTTP/router stack rather than Flask/FastAPI.

## Frontend Runtime

- Framework: React `19.2.7`.
- Router: `react-router-dom` `^6.30.1`.
- Build/dev server: Vite `^5.4.10`.
- TypeScript: `^5.6.3`.
- UI/style dependencies include HeroUI `3.1.0`, Tailwind CSS `4.3.0`, lucide icons, and dnd-kit.
- Frontend route registry: `web/src/app/pageRegistry.tsx`.
- Frontend route host: `web/src/app/router.tsx` and `web/src/app/PageRouteHost.tsx`.
- Feature API clients live under `web/src/features/*/api.ts`.

## Core Backend Dependencies

- PostgreSQL: `psycopg[binary,pool]==3.3.3`.
- MongoDB / OA read-only integration: `pymongo==4.14.1`.
- RabbitMQ client: `pika==1.4.0`.
- Redis client: `redis==7.4.0`.
- Object storage / S3-compatible integration: `boto3==1.42.88`.
- Excel import/export: `openpyxl==3.1.5`, `xlrd==2.0.2`.
- PDF/OCR/image processing: `pdfplumber==0.11.7`, `pymupdf==1.26.4`, `rapidocr_onnxruntime==1.2.3`, `pillow==11.3.0`.
- MySQL integration for OA role sync: `PyMySQL==1.1.1`.

## Persistent Stores

- PostgreSQL is the production primary app store and durable queue/read model store.
- OA MongoDB is an external read-only source through adapter boundaries.
- Legacy app Mongo paths remain for migration observation, shadow-read, rollback, and audit tooling.
- Object storage can be local/S3-compatible depending on deployment configuration.

## Runtime Infrastructure

- Durable queue source of truth: PostgreSQL `job.outbox_events` and `job.read_model_dirty_scopes`.
- RabbitMQ is optional transport/wakeup, not the read model state source.
- Redis can cache payloads only after a fresh gate.
- App Health reads runtime facts, worker heartbeats, dirty scopes, outbox events, dependencies, and read model readiness.

## Local Commands

- Install backend dependencies: `python -m pip install -r backend/requirements.txt`.
- Backend readiness check: `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`.
- Start backend: `./scripts/start-backend.sh`.
- Start frontend: `cd web && npm install && npm run dev`.
- Full verification: `bash scripts/verify.sh all`.

## Build And Test Tooling

- Backend tests use Python `unittest`.
- Frontend tests use Vitest, Testing Library, jsdom, and Playwright where needed.
- Frontend build uses `npm run build`, which runs `tsc -b && vite build`.
- Repository-wide verification entry point is `scripts/verify.sh`.

## Deployment Shape

- OA same-domain deployment serves frontend under `/fin-ops/`.
- Backend is exposed under `/fin-ops-api/`.
- Deployment assets live under `deploy/oa/`.
- Production release uses `./scripts/deploy-oa.sh` and registry-derived worker manifests.

## Planning Boundary

- `.planning/codebase/*.md` is the global repository map.
- Page-specific analysis must be stored in `.planning/phases/<phase>/` artifacts such as `CONTEXT.md`, `RESEARCH.md`, and `*-PLAN.md`.
- Do not run page-focused `$gsd-map-codebase --focus ...` as the storage mechanism for page analysis.
