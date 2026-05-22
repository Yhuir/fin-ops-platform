# RabbitMQ Production Cutover Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the production-grade RabbitMQ cutover closure for fin-ops without making RabbitMQ the business fact source.

**Architecture:** PostgreSQL remains the source of truth for outbox events, dirty scopes, status, retries, DLQ facts, and read model version guards. RabbitMQ is only the envelope transport between a dispatcher and consumers; production rollout must keep a PostgreSQL polling rollback path and use shadow publish before enabling RabbitMQ consumers.

**Tech Stack:** Python backend, PostgreSQL migrations, RabbitMQ, systemd, SSH tunnel staging checks, pytest, fin-ops deployment docs.

---

## /goal Prompt

```text
/goal 生产级完成 RabbitMQ 接入收口：修复 0018 migration 缺失，确认并应用生产 pending migrations，补 systemd/env 部署边界，启动并验证 dispatcher shadow publish，准备 RabbitMQ consumer 灰度切换与 PostgreSQL rollback 路径。

要求：
1. 不能让 RabbitMQ 成为业务事实源；PostgreSQL outbox/dirty scopes/status/publish state 仍是事实源。
2. 先修测试和 migration，再做生产库 migration status/apply。
3. 生产 RabbitMQ topology 用独立 bootstrap/topology 凭据，dispatcher/worker 不扩大权限。
4. systemd/env 必须区分 API、worker、dispatcher、topology，secret 只能走 root-only EnvironmentFile。
5. shadow publish 先跑，观察 backlog/lag/DLQ/confirm，再灰度一个 RabbitMQ worker。
6. 任何时候必须保留 FIN_OPS_QUEUE_BACKEND=postgres 回滚路径。
7. 输出验证证据：pytest、git diff --check、RabbitMQ staging preflight、生产 migration status、shadow publish check/metrics。
```

## Files

- Modify: `backend/src/fin_ops_platform/postgres/migrations/0018_api_performance_read_model.sql`
- Modify: `tests/test_postgres_migrations.py`
- Create: `deploy/oa/systemd/fin-ops.service.example`
- Create: `deploy/oa/systemd/fin-ops-rabbitmq-topology.service.example`
- Create: `deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example`
- Create: `deploy/oa/systemd/fin-ops-worker@.service.example`
- Create: `deploy/oa/env/fin-ops.common.env.example`
- Create: `deploy/oa/env/fin-ops.secrets.env.example`
- Create: `deploy/oa/env/fin-ops.rabbitmq-topology.env.example`
- Create: `deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example`
- Create: `deploy/oa/env/fin-ops.rabbitmq-worker.env.example`
- Modify: `deploy/oa/README.md`
- Modify: `docs/operations/deployment.md`
- Modify: `docs/operations/runtime-read-model-hardening.md`
- Generate/update: `docs/database-migration/reports/rabbitmq-staging-preflight-latest.json`
- Generate/update: `docs/database-migration/reports/rabbitmq-production-cutover-*.json`

## Task 1: 0018 Migration Closure

- [ ] Verify `0018_api_performance_read_model.sql` exists and creates `read_model.workbench_summary`.
- [ ] Add migration test assertions for `workbench_summary_scope_key_uidx`, `workbench_summary_scope_month_idx`, `workbench_summary_source_version_idx`.
- [ ] Add migration test assertions for API/readonly select grants as well as worker/migrator write grants.
- [ ] Run:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_migrations.py tests/test_workbench_sql_runtime.py tests/test_api_performance_metrics.py -q
```

Expected: all selected tests pass or failures are unrelated and explicitly recorded.

## Task 2: Production Migration Status And Apply

- [ ] Use `.runtime/fin_ops_platform/local-postgres.env` to check production status:

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres status --migrations-dir backend/src/fin_ops_platform/postgres/migrations
```

- [ ] Confirm only additive pending migrations are applied: `0016`, `0017`, `0018`.
- [ ] Capture a pre-apply status report in `docs/database-migration/reports/`.
- [ ] Apply migrations through the repository migration runner, not ad hoc SQL.
- [ ] Capture post-apply status report and verify no pending migration remains.

## Task 3: Systemd And Env Deployment Boundary

- [ ] Add example systemd units for API, topology oneshot, dispatcher, and worker template.
- [ ] Add env examples that separate non-secret config from secret URLs/passwords.
- [ ] Ensure units use explicit `PYTHONPATH`, `WorkingDirectory`, bounded restart policy, and root-only secret environment files.
- [ ] Document that topology uses `RABBITMQ_TOPOLOGY_URL`, dispatcher uses dispatcher credentials, worker uses worker credentials.

## Task 4: Shadow Publish Verification

- [ ] Confirm RabbitMQ tunnel and topology are available.
- [ ] Run staging preflight with real `FIN_OPS_TEST_DATABASE_URL` and `RABBITMQ_TEST_URL`.
- [ ] Run dispatcher `--check --shadow-publish`.
- [ ] If production code and migration are present, run dispatcher for a bounded single iteration first:

```bash
FIN_OPS_QUEUE_BACKEND=postgres \
RABBITMQ_SHADOW_PUBLISH=true \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.rabbitmq_dispatcher \
  --shadow-publish \
  --publisher-id rabbitmq-dispatcher-shadow-local-check \
  --max-iterations 1 \
  --batch-size 10
```

- [ ] Inspect `job.outbox_events` publish status/backlog and RabbitMQ queue depth.

## Task 5: Consumer Cutover Readiness

- [ ] Do not start a full production RabbitMQ consumer until API/worker release code is deployed and monitored.
- [ ] Document the exact one-worker gray command and rollback command.
- [ ] Verify `FIN_OPS_QUEUE_BACKEND=postgres` rollback remains valid.

## Verification Commands

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_postgres_migrations.py \
  tests/test_runtime_queue.py \
  tests/test_runtime_worker.py \
  tests/test_runtime_monitoring.py \
  tests/test_rabbitmq_runtime.py \
  tests/test_runtime_queue_ops.py \
  tests/test_rabbitmq_staging_preflight.py \
  tests/test_rabbitmq_integration.py \
  tests/test_workbench_sql_runtime.py \
  tests/test_api_performance_metrics.py \
  -q

set -a
source .runtime/fin_ops_platform/staging-rabbitmq.env
set +a
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight \
  --json \
  --output docs/database-migration/reports/rabbitmq-staging-preflight-latest.json

git diff --check
```

## Rollback

- Stop `fin-ops-rabbitmq-dispatcher.service`.
- Stop any RabbitMQ consumer worker instance.
- Restore worker env to `FIN_OPS_QUEUE_BACKEND=postgres`.
- Start PostgreSQL polling worker.
- Use `runtime_queue_ops republish/requeue/replay-unpublished` only after inspecting event facts in PostgreSQL.

