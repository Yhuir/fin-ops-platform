# External Integrations

**Analysis Date:** 2026-06-15

## APIs & External Services

**OA HTTP Session / Identity:**
- OA base service - validates current OA user/session and optional login token flow.
  - SDK/Client: Python standard HTTP helpers inside app services; frontend sends cookie/bearer token through `web/src/features/apiClient.ts`.
  - Auth: `FIN_OPS_OA_BASE_URL`, `FIN_OPS_OA_USER_INFO_PATH`, `FIN_OPS_OA_LOGIN_PATH`, `FIN_OPS_OA_REQUIRED_PERMISSION`, `FIN_OPS_OA_REQUEST_TIMEOUT_MS`, `FIN_OPS_OA_SESSION_CACHE_TTL_SECONDS`, `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`, `FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY`.
  - Implementation: `backend/src/fin_ops_platform/app/auth.py`, `backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`, and session boundary docs in `docs/app-architecture/runtime-and-ownership.md`.

**OA MongoDB:**
- OA source data - read-only OA payment/reimbursement/project source records used by workbench, invoices, pending payments, and downstream context.
  - SDK/Client: `pymongo==4.14.1`.
  - Auth: `FIN_OPS_OA_MONGO_HOST`, `FIN_OPS_OA_MONGO_PORT`, `FIN_OPS_OA_MONGO_DATABASE`, `FIN_OPS_OA_MONGO_USERNAME`, `FIN_OPS_OA_MONGO_PASSWORD`, `FIN_OPS_OA_MONGO_AUTH_SOURCE`, `FIN_OPS_OA_MONGO_COLLECTION`, `FIN_OPS_OA_MONGO_TIMEOUT_MS`, `FIN_OPS_OA_MONGO_CACHE_TTL_SECONDS`.
  - Implementation: `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`.

**OA MySQL Role Sync:**
- OA role database - optional sync of fin-ops access roles back to OA.
  - SDK/Client: `PyMySQL==1.1.1`.
  - Auth: `FIN_OPS_OA_ROLE_SYNC_ENABLED`, `FIN_OPS_OA_ROLE_SYNC_HOST`, `FIN_OPS_OA_ROLE_SYNC_PORT`, `FIN_OPS_OA_ROLE_SYNC_DATABASE`, `FIN_OPS_OA_ROLE_SYNC_USERNAME`, `FIN_OPS_OA_ROLE_SYNC_PASSWORD`.
  - Implementation: `backend/src/fin_ops_platform/services/oa_role_sync_service.py`; deploy docs in `deploy/oa/README.md`.

**Object Storage / S3-Compatible Storage:**
- Import and attachment storage - used by import/OA attachment workflows, not a turnover-ledger canonical fact source.
  - SDK/Client: `boto3==1.42.88`.
  - Auth: `OBJECT_STORAGE_BACKEND`, `S3_ENDPOINT_URL`, and provider credentials in root-only env files.
  - Implementation references: `scripts/check-local-runtime.sh`, `docs/dev/local-development.md`, `deploy/oa/env/fin-ops.secrets.env.example`.

## Data Storage

**Databases:**
- PostgreSQL
  - Connection: `FIN_OPS_POSTGRES_DATABASE_URL` or `DATABASE_URL`; optional read DSN `FIN_OPS_POSTGRES_READ_DATABASE_URL`.
  - Client: `psycopg[binary,pool]==3.3.3` via `backend/src/fin_ops_platform/services/postgres_connection.py`.
  - Role: primary app store, read models, runtime queue, outbox, dirty scopes, App Status readiness, and audit data.
  - Turnover-ledger tables/repos: `read_model.turnover_ledger_rows` methods in `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`; extras in `app.turnover_ledger_extras` via `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`; migrations under `backend/src/fin_ops_platform/postgres/migrations/`.
- OA MongoDB
  - Connection: `FIN_OPS_OA_MONGO_*`.
  - Client: `pymongo`.
  - Role: read-only OA external data source; not a turnover-ledger write store.
- App Mongo legacy fallback/shadow
  - Connection: `FIN_OPS_APP_MONGO_*`.
  - Client: `pymongo`.
  - Role: migration observation, rollback, shadow-read, and audit tooling path; production primary writes are PostgreSQL.

**File Storage:**
- Local filesystem data directory for clean/local checks and legacy local state through `FIN_OPS_DATA_DIR` in `scripts/verify.sh` and `backend/src/fin_ops_platform/services/state_store.py`.
- S3-compatible object storage for imports/attachments when configured; object storage is not the freshness source for turnover-ledger.

**Caching:**
- Redis optional runtime helper.
  - Connection: `FIN_OPS_REDIS_URL` or `REDIS_URL`.
  - Client: `redis==7.4.0`.
  - Implementation: `backend/src/fin_ops_platform/services/runtime_redis.py`.
  - Constraint: cache only after read model fresh gate; Redis cannot cache or forge freshness. Turnover-ledger write/read safety still comes from PostgreSQL source versions, `ReadModelQueryGateway`, and durable queue state.
- In-process/local caches exist for OA session and adapter cache TTLs; OA cache env includes `FIN_OPS_OA_SESSION_CACHE_TTL_SECONDS` and `FIN_OPS_OA_MONGO_CACHE_TTL_SECONDS`.

## Authentication & Identity

**Auth Provider:**
- OA session/auth
  - Implementation: frontend attaches OA token/cookie in `web/src/features/apiClient.ts`; backend resolves session and permissions through `backend/src/fin_ops_platform/app/auth.py`.
  - Permission env: `FIN_OPS_ALLOWED_USERNAMES`, `FIN_OPS_READONLY_EXPORT_USERNAMES`, `FIN_OPS_ADMIN_USERNAMES`, `FIN_OPS_ALLOWED_ROLES`.
  - Session API: `/api/session/me` described in `docs/app-architecture/runtime-and-ownership.md`.

**Turnover-Ledger Permissions:**
- Turnover-ledger write actions must continue through backend permission checks and operation-level preconditions in `backend/src/fin_ops_platform/app/server.py` and `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`.
- Frontend can disable actions based on permission/read model state, but backend remains authoritative for stale/version/idempotency checks.

## Workers, Queues & Read Models

**Durable Queue:**
- PostgreSQL tables `job.outbox_events` and `job.read_model_dirty_scopes` are the single truth for read model refresh state.
  - Producer boundary: `ReadModelRefreshGateway` in `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`.
  - Queue repository: `RuntimeQueueRepository` in `backend/src/fin_ops_platform/services/runtime_queue.py`.
  - Turnover write paths enqueue dirty/outbox through `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`, and `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.

**Turnover-Ledger Worker:**
- Worker instance: `turnover-ledger`.
  - Worker kind: `turnover-ledger-read-model`.
  - Event type: `turnover_ledger.read_model.refresh`.
  - Scope type/key: `turnover_ledger` / `all`.
  - Registry: `backend/src/fin_ops_platform/services/runtime_worker_registry.py`.
  - Handler: `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`.
  - Projection: `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`.
  - Env template: `deploy/oa/env/fin-ops.worker.turnover-ledger.env.example`.

**Related Workers for Turnover-Ledger Changes:**
- `workbench` worker handles `workbench.read_model.refresh` for open/paired page views impacted by manual turnover closure.
- `workbench-relation` worker handles `workbench_relation.read_model.refresh` for relation distribution and stale preconditions.
- `bank-detail` worker handles `bank_detail.read_model.refresh` for bank transaction tags/category source facts consumed by turnover-ledger.
- `cost-tax`, `cost-statistics`, and `search` workers can be affected by confirm/withdraw cascades per `docs/modules/turnover-ledger/README.md` and `docs/dev/api-contracts.md`.

**RabbitMQ Transport:**
- RabbitMQ is optional wakeup/transport for worker claim paths.
  - Client: `pika==1.4.0`.
  - Env: `FIN_OPS_QUEUE_BACKEND`, `RABBITMQ_URL`, `RABBITMQ_VHOST`, `RABBITMQ_EXCHANGE`, `RABBITMQ_PREFETCH`, `RABBITMQ_PUBLISH_CONFIRM`, and related DLQ/management settings from `deploy/oa/fin_ops.env.example`.
  - Constraint: RabbitMQ cannot become read model state truth; PostgreSQL outbox/dirty scopes remain authoritative.

## Turnover-Ledger Integration Boundaries

**Bank Details:**
- Turnover-ledger candidates come from bank detail effective categories, external turnover tag rules, and third-level categories.
  - Source services: `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`, `backend/src/fin_ops_platform/services/bank_transaction_effective_category_provider.py`, and `backend/src/fin_ops_platform/services/bank_detail_sql_projection.py`.
  - Tag selection persists in app settings through `backend/src/fin_ops_platform/services/app_settings_service.py`.
  - API contract: `/api/turnover-ledger/tag-selection` in `docs/dev/api-contracts.md`.

**Workbench Relation:**
- Manual zero-difference turnover closure writes a Turnover relation and a Workbench active pair relation in one write boundary.
  - Turnover write UoW: `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`.
  - Workbench command delegation: `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.
  - Constraint: if `WorkbenchRelationCommandService` is unavailable, manual closure/withdraw must fail fast rather than mutate pair relation snapshots directly.

**Operation Barrier:**
- Turnover-ledger frontend writes use an operation overlay and wait for backend freshness targets before releasing UI.
  - Frontend: `web/src/features/operationBarrier/api.ts`, `web/src/pages/TurnoverLedgerPage.tsx`.
  - Backend status plane: operation barrier and App Status services in `backend/src/fin_ops_platform/app/server.py` and runtime docs in `docs/app-architecture/runtime-and-ownership.md`.
  - Targets after confirm include `turnover_ledger:all`, affected `workbench_relation` months, affected `workbench` months, and `workbench:all`.

**Exports:**
- Turnover-ledger export preview/download is backend-generated XLSX.
  - Service: `backend/src/fin_ops_platform/services/turnover_ledger_export_service.py`.
  - Dependencies: `openpyxl`, Python Decimal/date handling.
  - Frontend must treat download as blob, as noted in `docs/modules/turnover-ledger/state-machine.md`.

## Monitoring & Observability

**Error Tracking:**
- No third-party error tracking service detected.
- App Status and health endpoints expose runtime state through `backend/src/fin_ops_platform/services/app_status_overview_service.py`, `backend/src/fin_ops_platform/services/app_status_domain_registry.py`, `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`, and `/api/app-health`.

**Logs:**
- Backend uses service/runtime logs and systemd journal in production.
- Worker heartbeat/readiness is stored in PostgreSQL runtime tables and surfaced through App Health.
- Prometheus metrics endpoint exists when `FIN_OPS_PROMETHEUS_BEARER_TOKEN` is configured; docs in `docs/operations/monitoring.md`.

## CI/CD & Deployment

**Hosting:**
- OA same-domain deployment with frontend path `/fin-ops/` and backend path `/fin-ops-api/`.
- Deployment assets and env examples live in `deploy/oa/`.
- Production entry is `./scripts/deploy-oa.sh` per `AGENTS.md`.

**CI Pipeline:**
- Repository verification is script-driven; `README.md`, `docs/modules/turnover-ledger/tests.md`, and `docs/dev/nightly-ci.md` reference:
  - `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`
  - `cd web && npm test`
  - `cd web && npm run build`
  - `bash scripts/verify.sh all`
- No hosted CI config was identified in the focused scan.

## Environment Configuration

**Required env vars:**
- PostgreSQL production-equivalent runtime: `FIN_OPS_POSTGRES_DATABASE_URL` or `DATABASE_URL`, plus `FIN_OPS_APP_STORAGE_BACKEND=postgres`, `FIN_OPS_APP_READ_BACKEND=postgres`, `FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary`, `FIN_OPS_STORAGE_MODE=postgres`, `FIN_OPS_QUEUE_BACKEND=postgres`.
- OA session: `FIN_OPS_OA_BASE_URL`, `FIN_OPS_OA_USER_INFO_PATH`, `FIN_OPS_OA_REQUIRED_PERMISSION`, and timeout/session env from `deploy/oa/fin_ops.env.example`.
- OA Mongo sync: `FIN_OPS_OA_MONGO_HOST`, `FIN_OPS_OA_MONGO_DATABASE`, and credential/env group when OA sync worker is enabled.
- Turnover-ledger worker: use registry-derived worker env from `deploy/oa/env/fin-ops.worker.turnover-ledger.env.example`.

**Secrets location:**
- Production secrets belong in root-only `/etc/fin-ops/*.env` files, not inline systemd `Environment=` or git-tracked files; see `docs/operations/deployment.md`.
- Local private env can live in ignored `.runtime/fin_ops_platform/` files per `docs/dev/local-development.md`.
- `.env`, secrets, credentials, keys, and ignored secret files were not read.

## Webhooks & Callbacks

**Incoming:**
- No generic external webhook endpoint detected for turnover-ledger.
- Browser/frontend calls internal app APIs under `/api/turnover-ledger*`.
- App Health SSE `/api/app-health/stream` emits status events to UI, but it is not an external webhook source.

**Outgoing:**
- OA HTTP user/session requests go to `FIN_OPS_OA_BASE_URL`.
- Optional OA role sync writes to OA MySQL when enabled.
- Optional RabbitMQ publish/consume is used for worker wakeup/transport, not business callbacks.
- Optional S3-compatible object storage is used by import/attachment workflows.

---

*Integration audit: 2026-06-15*
