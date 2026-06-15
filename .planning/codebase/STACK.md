# Technology Stack

**Analysis Date:** 2026-06-15

## Languages

**Primary:**
- Python 3 - Backend service, worker, PostgreSQL migration, import/export, OCR, and runtime tooling under `backend/src/fin_ops_platform/`; startup uses `python3 -m fin_ops_platform.app.main` from `README.md` and `backend/src/fin_ops_platform/app/main.py`.
- TypeScript - React frontend in `web/src/`, including turnover-ledger page code in `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/components/turnoverLedger/`, and `web/src/features/turnoverLedger/`.

**Secondary:**
- SQL - PostgreSQL schema migrations in `backend/src/fin_ops_platform/postgres/migrations/`; turnover-ledger read model storage and query SQL live behind `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`.
- Shell - Developer, deploy, runtime, and verification scripts in `scripts/` and `deploy/oa/`.
- JavaScript - Vite runtime config exists as generated/compatibility files in `web/vite.config.js` and declarations in `web/vite.config.d.ts`; source config is `web/vite.config.ts`.

## Runtime

**Environment:**
- Backend runs as a custom Python HTTP service, not Flask/FastAPI. Entry point: `backend/src/fin_ops_platform/app/main.py`; routing and dependency assembly are in `backend/src/fin_ops_platform/app/server.py`.
- Worker processes run through `backend/src/fin_ops_platform/app/worker.py` and registration data in `backend/src/fin_ops_platform/services/runtime_worker_registry.py`.
- Frontend runs in the browser via Vite. Local dev entry is `web/package.json` script `dev`, which delegates to `../scripts/start-web.sh`.
- Production/OA deployment serves frontend under `/fin-ops/` and backend under `/fin-ops-api/`, documented in `README.md`, `ARCHITECTURE.md`, and `deploy/oa/README.md`.

**Package Manager:**
- Backend: `pip` with pinned requirements in `backend/requirements.txt`.
- Frontend: `npm` with `web/package-lock.json` present.
- Lockfile: frontend present at `web/package-lock.json`; backend has no lockfile beyond pinned `backend/requirements.txt`.

## Frameworks

**Core:**
- Custom Python HTTP/router stack - `backend/src/fin_ops_platform/app/server.py` dispatches `/api/*` routes, maps auth/permissions, and wires services.
- React 19.2.7 - UI framework for `web/src/pages/TurnoverLedgerPage.tsx` and shared frontend state/providers.
- React Router DOM 6.30.1 - SPA routing; turnover-ledger route is `/turnover-ledger` per `docs/modules/turnover-ledger/README.md`.
- Vite 5.4.10 - frontend build/dev server configured by `web/vite.config.ts`.
- HeroUI React 3.1.0 and HeroUI styles 3.1.0 - frontend component library declared in `web/package.json`.
- Tailwind CSS 4.3.0 with `@tailwindcss/vite` 4.3.0 - frontend styling pipeline via `web/vite.config.ts`.

**Testing:**
- Python `unittest` - backend tests run with `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v` from `README.md`.
- Vitest 2.1.4 + jsdom 25.0.1 - frontend unit/component test runner configured in `web/vite.config.ts`.
- Testing Library - `@testing-library/react`, `@testing-library/jest-dom`, and `@testing-library/user-event` in `web/package.json`.
- Playwright 1.60.0 - available in `web/package.json` for browser-level checks.

**Build/Dev:**
- TypeScript 5.6.3 - frontend type checking through `web/package.json` script `build` (`tsc -b && vite build`) and `web/tsconfig.json`.
- Vite proxy - `web/vite.config.ts` proxies `/api`, `/imports`, and `/fin-ops-api` to `VITE_API_PROXY_TARGET` or `http://127.0.0.1:8001`.
- Backend checks - `README.md` and `scripts/verify.sh` use `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`.

## Key Dependencies

**Critical:**
- `psycopg[binary,pool]==3.3.3` - PostgreSQL runtime, connection pooling, and SQL repositories; configured in `backend/src/fin_ops_platform/services/postgres_connection.py`.
- `pymongo==4.14.1` - OA MongoDB read adapter and legacy app Mongo fallback/shadow paths; OA adapter is `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`.
- `redis==7.4.0` - optional runtime helper for fresh-gated cache and wakeup signals in `backend/src/fin_ops_platform/services/runtime_redis.py`; Redis must not become freshness truth.
- `pika==1.4.0` - RabbitMQ dispatcher/consumer transport used only as optional wakeup/transport over PostgreSQL durable queue.
- `openpyxl==3.1.5` and `xlrd==2.0.2` - Excel import/export support; turnover-ledger XLSX export is implemented by `backend/src/fin_ops_platform/services/turnover_ledger_export_service.py`.
- `dayjs==1.11.20` - frontend date handling in `web/package.json`.
- `lucide-react==1.17.0` - frontend icon package in `web/package.json`.

**Infrastructure:**
- `boto3==1.42.88` - object storage/S3-compatible integration for imports and attachments; local/deploy env references object storage through `OBJECT_STORAGE_BACKEND` and `S3_ENDPOINT_URL`.
- `PyMySQL==1.1.1` - optional OA role sync integration in `backend/src/fin_ops_platform/services/oa_role_sync_service.py`.
- `pdfplumber==0.11.7`, `pymupdf==1.26.4`, `pillow==11.3.0`, `rapidocr_onnxruntime==1.2.3` - document/OCR tooling for import and attachment workflows.
- `@dnd-kit/*` - drag/sort frontend dependencies in `web/package.json`.

## Turnover-Ledger Stack Surface

**Backend API and Services:**
- Route dispatch: `backend/src/fin_ops_platform/app/server.py` handles `/api/turnover-ledger`, `/api/turnover-ledger/tag-selection`, `/api/turnover-ledger/bank-row-tags/batch`, `/api/turnover-ledger/relations/{id}/extra`, `/api/turnover-ledger/closures/confirm`, `/api/turnover-ledger/relations/{id}/withdraw`, `/api/turnover-ledger/export-preview`, and `/api/turnover-ledger/export`.
- Route facade: `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`.
- Read facade: `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`.
- Core services: `backend/src/fin_ops_platform/services/turnover_ledger_service.py`, `backend/src/fin_ops_platform/services/turnover_relation_service.py`, `backend/src/fin_ops_platform/services/turnover_ledger_extra_service.py`, and `backend/src/fin_ops_platform/services/turnover_ledger_export_service.py`.
- Query/read-model gate: `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py` uses `ReadModelQueryGateway` from `backend/src/fin_ops_platform/services/read_model_query_gateway.py`.
- Write boundary: `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`, and `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.
- Projection/worker: `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py` and `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`.

**Frontend API and UI:**
- Page: `web/src/pages/TurnoverLedgerPage.tsx`.
- Components: `web/src/components/turnoverLedger/`.
- API client/mappers: `web/src/features/turnoverLedger/api.ts`.
- Types: `web/src/features/turnoverLedger/types.ts`.
- HTTP base, auth cookie, and bounded JSON handling: `web/src/features/apiClient.ts`, `web/src/app/runtime`, and `web/src/features/authToken`.
- Operation freshness overlay uses operation barrier client in `web/src/features/operationBarrier/api.ts` and domain events in `web/src/features/domainEvents.ts`.

## Configuration

**Environment:**
- PostgreSQL primary runtime uses `FIN_OPS_APP_STORAGE_BACKEND=postgres`, `FIN_OPS_APP_READ_BACKEND=postgres`, `FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary`, `FIN_OPS_STORAGE_MODE=postgres`, `FIN_OPS_QUEUE_BACKEND=postgres`, and `FIN_OPS_POSTGRES_DATABASE_URL` or `DATABASE_URL`; see `docs/dev/local-development.md`, `docs/operations/postgresql-runtime.md`, and `backend/src/fin_ops_platform/services/postgres_connection.py`.
- Optional read DSN uses `FIN_OPS_POSTGRES_READ_DATABASE_URL` plus read-specific timeout/pool env vars in `backend/src/fin_ops_platform/services/postgres_connection.py`.
- Redis uses `FIN_OPS_REDIS_URL` or `REDIS_URL`, plus `FIN_OPS_REDIS_KEY_PREFIX`, `FIN_OPS_REDIS_WAKEUP_CHANNEL`, and `FIN_OPS_REDIS_DEFAULT_TTL_SECONDS`; implemented by `backend/src/fin_ops_platform/services/runtime_redis.py`.
- RabbitMQ env is defined in `deploy/oa/fin_ops.env.example`, `deploy/oa/env/fin-ops.rabbitmq-worker.env.example`, and per-worker env examples. Keep PostgreSQL as durable queue truth.
- OA session/auth env is in `deploy/oa/fin_ops.env.example`: `FIN_OPS_OA_BASE_URL`, `FIN_OPS_OA_USER_INFO_PATH`, `FIN_OPS_OA_LOGIN_PATH`, `FIN_OPS_OA_REQUIRED_PERMISSION`, `FIN_OPS_OA_REQUEST_TIMEOUT_MS`, `FIN_OPS_OA_SESSION_CACHE_TTL_SECONDS`, `FIN_OPS_ALLOWED_USERNAMES`, `FIN_OPS_ADMIN_USERNAMES`, and related role env vars.
- OA Mongo env uses `FIN_OPS_OA_MONGO_*` in `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`; app Mongo fallback/shadow env uses `FIN_OPS_APP_MONGO_*` in `backend/src/fin_ops_platform/services/state_store.py`.
- Frontend base/proxy uses `VITE_APP_BASE_PATH` and `VITE_API_PROXY_TARGET` in `web/vite.config.ts`.
- `.env`-style files are intentionally not read; local private runtime env may live under ignored `.runtime/fin_ops_platform/` per `docs/dev/local-development.md`.

**Build:**
- Backend dependencies: `backend/requirements.txt`.
- Frontend manifest and lockfile: `web/package.json`, `web/package-lock.json`.
- Frontend build config: `web/vite.config.ts`, `web/tsconfig.json`, `web/tsconfig.node.json`.
- PostgreSQL migrations: `backend/src/fin_ops_platform/postgres/migrations/`.
- Deploy env examples: `deploy/oa/fin_ops.env.example` and `deploy/oa/env/`.

## Platform Requirements

**Development:**
- Python environment with packages from `backend/requirements.txt`.
- Node/npm environment for `web/package.json`.
- PostgreSQL for production-equivalent local runtime; `scripts/check-local-runtime.sh` requires `FIN_OPS_POSTGRES_DATABASE_URL` or `DATABASE_URL`.
- Optional Redis and S3/MinIO tunnels are described in `docs/dev/local-development.md`; Redis is optional and PostgreSQL polling remains authoritative when disabled.
- Targeted turnover-ledger verification commands are listed in `docs/modules/turnover-ledger/tests.md`.

**Production:**
- PostgreSQL is the app primary store and durable worker queue.
- OA MongoDB remains a read-only external source through `MongoOAAdapter`.
- systemd manages API, worker, dispatcher, and timers in the OA deployment model; worker manifest is generated by `backend/src/fin_ops_platform/services/runtime_worker_registry.py` and `backend/src/fin_ops_platform/tools/runtime_worker_manifest`.
- RabbitMQ can be enabled per worker as a transport/wakeup layer, but rollback is `FIN_OPS_QUEUE_BACKEND=postgres`.
- Redis can cache only fresh-gated payloads and cannot prove read model freshness.
- Frontend and backend are deployed as same-domain OA iframe/app paths `/fin-ops/` and `/fin-ops-api/`.

---

*Stack analysis: 2026-06-15*
