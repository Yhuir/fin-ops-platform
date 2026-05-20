# 17 阶段 Codex 执行 Prompt：Pending invoice PostgreSQL coverage

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 17：补齐 post-main 新增 pending invoice 持久化在 PostgreSQL 下的正式覆盖，解除阶段 16 的 `BLOCKED_PENDING_INVOICE_COVERAGE`。完成后，`pending_invoice_manual_invoice_commands` 必须具备正式 PostgreSQL schema、repository/state-store load/save、export/transform/import、shadow-read domain 和真实 PostgreSQL integration/API 测试；`bank_transaction_tags` 与 `pending_invoice_tag_groups` 必须具备 PostgreSQL mode round-trip 测试。阶段 17 不做生产 cutover，不写生产 PostgreSQL，不写 app Mongo，不触碰 OA Mongo。

## 必须使用子代理并行

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- REQUIRED SUB-SKILL: `superpowers:test-driven-development`
- 主线程负责最终集成、真实 disposable PostgreSQL 验证、文档和 Gate 判定。
- 子代理可以并行只读分析，也可以在明确文件所有权下改代码；worker 必须知道不是独自在 codebase 中工作，不得 revert 用户或其他 worker 改动。

建议并行任务：

1. Explorer A：只读梳理 pending invoice command payload contract、API recoverable command log tests、state-store load/save path。
2. Explorer B：只读梳理 PostgreSQL migrations/test lists/truncate lists/grants，列出新增 `0008` 需要同步的测试。
3. Explorer C：只读梳理 export/transform/shadow-read 添加 app-owned domain 的既有模式。
4. Worker D：负责 schema/migration/test DB helper 更新。
5. Worker E：负责 Postgres repository/state-store + integration tests。
6. Worker F：负责 export/transform/shadow-read + tests。
7. 主线程整合、修复冲突、跑完整验证、更新文档。

## 硬约束

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. app Mongo `fin_ops_platform_app` 本阶段不写；如需要验证 export，只能使用 fake store 或既有只读 artifact。
3. production PostgreSQL `fin_ops` 禁止写入。本阶段所有 destructive DB 操作只允许 disposable test DB。
4. disposable test DB 名必须包含 `test`，或显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；不能证明是 test DB 时立即停止。
5. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、prompt 或最终输出。
6. 不修改生产 service、不重启生产、不修改 `/opt/fin-ops/current`、不改 systemd。
7. 不进行 cutover、read switch、长期 dual-write 或 production mirror-write。
8. 不把 pending invoice 缺口静默塞进 `state:full_state` 后声称完成；必须有正式表和可审计 domain 覆盖。
9. PostgreSQL SQL 必须参数化；仅允许对受控 schema/table/domain 名使用白名单拼接。
10. 新增 migration 必须是 expand-only：`create table if not exists`、`create index if not exists`、grant；禁止 drop/truncate/delete/alter system。

## 必须先读

- `AGENTS.md`
- `docs/database-migration/16-worktree-postgres-test-onboarding.md`
- `docs/database-migration/reports/stage16-worktree-postgres-test-20260520182420.json`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/common.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/postgres/migrate.py`
- `backend/src/fin_ops_platform/postgres/migrations/*.sql`
- `tests/postgres_test_utils.py`
- `tests/test_postgres_migrations.py`
- `tests/test_postgres_state_store_integration.py`
- `tests/test_app_postgres_mode_integration.py`
- `tests/test_pending_invoice_api.py`
- `backend/src/fin_ops_platform/tools/exporters/*.py`
- `backend/src/fin_ops_platform/tools/postgres_transform.py`
- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `tests/test_export_app_mongo.py`
- `tests/test_postgres_transform.py`
- `tests/test_shadow_read_rehearsal.py`

## 目标文件

Expected create/modify:

- Create: `backend/src/fin_ops_platform/postgres/migrations/0008_pending_invoice_commands.sql`
- Modify: `backend/src/fin_ops_platform/postgres/migrations/0007_grants.sql` only if grants must include future table defaults; otherwise prefer grants in `0008`.
- Modify: `tests/postgres_test_utils.py`
- Modify: `tests/test_postgres_migrations.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- Modify: `tests/test_postgres_state_store_integration.py`
- Modify: `tests/test_app_postgres_mode_integration.py`
- Modify: `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py`
- Modify: `backend/src/fin_ops_platform/tools/postgres_transform.py`
- Modify: `tests/test_export_app_mongo.py`
- Modify: `tests/test_postgres_transform.py`
- Modify: `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- Modify: `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- Modify: `tests/test_shadow_read_rehearsal.py`
- Create: `docs/database-migration/17-pending-invoice-postgres-coverage.md`
- Create report: `docs/database-migration/reports/stage17-pending-invoice-postgres-coverage-<timestamp>.json`
- Modify: `docs/database-migration/README.md`

## 串行执行步骤

### 17.1 TDD red tests

先写测试并运行确认失败：

1. Migration tests:
   - 期望 migration list 包含 `0008_pending_invoice_commands.sql`。
   - 期望 SQL 包含 `app.pending_invoice_manual_invoice_commands`。
   - 期望 forbidden SQL scan 仍通过。
2. PostgresStateStore integration:
   - `save({"pending_invoice_commands": {...}})` 写正式表；
   - `load()["pending_invoice_commands"]` 可重建同 shape；
   - 重复保存同一 command 幂等；
   - table count 与 command count 一致。
3. App PostgreSQL mode integration:
   - recoverable manual invoice failure 产生 command log；
   - rebuild app 后 command log survives rebuild；
   - confirm/recover flow 不依赖 `state:full_state` 兜底。
4. App settings integration:
   - PostgreSQL mode 下更新 `bank_transaction_tags` 和 `pending_invoice_tag_groups`；
   - rebuild app 后字段和值仍存在且版本语义正确。
5. Export/transform tests:
   - fake export 包含 `pending_invoice_manual_invoice_commands.ndjson`；
   - transform 将该 source 写入 `app.pending_invoice_manual_invoice_commands`；
   - raw payload 保留 command payload。
6. Shadow-read tests:
   - default catalog 包含 pending invoice command domain；
   - psql shadow store 可读取 `app.pending_invoice_manual_invoice_commands`；
   - diff severity 建议为 `P1` 或更高，不能 ignored。

必须记录至少一个 red failure 摘要到阶段 17 文档。

### 17.2 Implement schema

新增 `0008_pending_invoice_commands.sql`：

- `create table if not exists app.pending_invoice_manual_invoice_commands (...)`
- 推荐列：
  - `id uuid primary key default gen_random_uuid()`
  - `command_id text not null unique`
  - `request_id text`
  - `request_key text`
  - `status text not null`
  - `invoice_id text`
  - `case_id text`
  - `actor_id text`
  - `error_code text`
  - `error_message text`
  - `attempt_count integer not null default 0`
  - `command_payload jsonb not null default '{}'::jsonb`
  - `raw_payload jsonb not null default '{}'::jsonb`
  - `created_at timestamptz not null default now()`
  - `updated_at timestamptz not null default now()`
- indexes：
  - `request_key`
  - `status, updated_at desc`
  - `invoice_id`
  - `case_id`
- grants for existing `fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly`、`fin_ops_migrator` roles inside guarded `do $$`.

Update migration expected lists and truncate table list.

### 17.3 Implement repository/state-store

In `PostgresOpsTaxEtcRepository` add:

- `load_pending_invoice_commands() -> dict[str, Any]`
- `save_pending_invoice_commands(snapshot: dict[str, Any]) -> None`

Rules:

- Use command id as map key. Accept `command_id`, `id`, `request_id`, or map key as fallback identity.
- Preserve exact payload in `command_payload` and `raw_payload.normalized_payload`.
- Save is snapshot-style for this domain: upsert current keys and remove rows absent from the snapshot, inside one transaction.
- Empty snapshot deletes current rows.
- Load returns `{command_id: payload}` compatible with `Application._pending_invoice_commands`.

In `PostgresStateStore`:

- `load()` must include `pending_invoice_commands`.
- `save()` must call repository when payload includes `pending_invoice_commands`.
- Add explicit `load_pending_invoice_commands()` / `save_pending_invoice_commands()` if useful for tests/shadow-read.
- Do not rely on `state:full_state` for this domain.

### 17.4 Implement export/transform

Export:

- Add an export definition for `pending_invoice_manual_invoice_commands`.
- Source should call `store.load().get("pending_invoice_commands", {})` or a dedicated store method if available.
- Output one NDJSON row per command.
- Empty snapshot should still produce a manifest file with `record_count=0`.

Transform:

- Add source collection/domain to transform domain list.
- Add target table to target tables.
- Convert rows to `app.pending_invoice_manual_invoice_commands`.
- Preserve raw normalized payload.
- Add unit tests.

### 17.5 Implement shadow-read

- Add shadow-read domain spec for pending invoice commands.
- Add `PsqlShadowReadStore.load_pending_invoice_commands()`.
- Query formal table, return `{command_id: command_payload}`.
- Redact/ignore only runtime timestamps/metadata, not command status/result.
- Add tests that compare primary/shadow and catch missing command as mismatch.

### 17.6 Real DB verification

Use local disposable PostgreSQL test DB:

1. Start temp cluster.
2. Apply migrations `0001-0008`.
3. Run:

```bash
FIN_OPS_TEST_DATABASE_URL=<local-disposable-postgres-url> \
PYTHONPATH=backend/src \
python -m pytest \
  tests/test_postgres_test_utils.py \
  tests/test_postgres_state_store_integration.py \
  tests/test_app_postgres_mode_integration.py \
  -q
```

4. Run unit/regression:

```bash
python -m py_compile \
  backend/src/fin_ops_platform/services/postgres_state_store.py \
  backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py \
  backend/src/fin_ops_platform/tools/postgres_transform.py \
  backend/src/fin_ops_platform/services/shadow_read_rehearsal.py \
  backend/src/fin_ops_platform/services/shadow_read_psql_store.py

PYTHONPATH=backend/src python -m pytest \
  tests/test_postgres_migrations.py \
  tests/test_postgres_transform.py \
  tests/test_export_app_mongo.py \
  tests/test_shadow_read_rehearsal.py \
  tests/test_postgres_repositories_core.py \
  tests/test_postgres_repositories_boundaries.py \
  -q
```

5. Run app check:

```bash
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
```

### 17.7 Docs and Gate

Create `docs/database-migration/17-pending-invoice-postgres-coverage.md` with:

- red tests run and failure summary;
- implementation summary;
- migration/table/repository/export/transform/shadow-read coverage;
- real DB verification results;
- remaining production gates.

Gate can be:

- `PASS_PENDING_INVOICE_POSTGRES_COVERAGE` if all local/real test DB checks pass.
- `BLOCKED_TEST_FAILURE` if verification fails.
- `BLOCKED_NEEDS_USER_DECISION` if command payload identity/retention cannot be inferred from code/tests.

Final output in Chinese:

1. prompt path;
2. changed files;
3. verification results;
4. Gate;
5. remaining production-only steps.
```
