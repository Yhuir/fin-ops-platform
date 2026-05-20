# 阶段 17：Pending invoice PostgreSQL coverage

执行时间：2026-05-20

Gate：`PASS`

## 阶段边界

- 本阶段目标是关闭阶段 16 的 `BLOCKED_PENDING_INVOICE_COVERAGE`。
- 没有写 production PostgreSQL。
- 没有写 app Mongo `fin_ops_platform_app`。
- 没有读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- 真实 PostgreSQL 验证仅使用本机一次性 disposable test DB `fin_ops_stage17_test`。

## 执行 prompt

- `docs/database-migration/prompts/17-pending-invoice-postgres-coverage.prompt.md`

## 已完成内容

### PostgreSQL schema

- 新增 migration：`backend/src/fin_ops_platform/postgres/migrations/0008_pending_invoice_commands.sql`
- 新表：`app.pending_invoice_manual_invoice_commands`
- 表用于持久化 app-owned pending invoice manual invoice command log。
- 关键字段：`command_id`、`request_id`、`request_key`、`status`、`invoice_id`、`relation_case_id`、`error_code`、`error_message`、`last_successful_status`、`status_history`、`result_payload`、`command_payload`、`raw_payload`。
- migration baseline 从 `0001-0007` 更新为 `0001-0008`。

### Repository / state store

- `PostgresOpsTaxEtcRepository` 新增 `load_pending_invoice_commands()` 和 `save_pending_invoice_commands()`。
- `PostgresStateStore` 新增正式读写，并在 `load()` / `save()` 接入 `pending_invoice_commands`。
- `ApplicationStateStore` 新增同名 public method，支持 shadow-read primary store method contract。
- `DualStateStore` mirror-write method set 新增 `save_pending_invoice_commands`。

### Export / transform

- app Mongo export 新增 artifact：`pending_invoice_manual_invoice_commands.ndjson`。
- export 内部读取 app snapshot key：`pending_invoice_commands`。
- staging `source_collection` 固定为：`pending_invoice_manual_invoice_commands`。
- transform 新增 `ops_tax_etc` source 和 target：`app.pending_invoice_manual_invoice_commands`。
- command payload 会保留完整 `command_payload` 和 `raw_payload.normalized_payload`。

### Shadow-read

- shadow-read catalog 新增 domain：`pending_invoice_commands`。
- method：`load_pending_invoice_commands`。
- severity：`P1`。
- `PsqlShadowReadStore.load_pending_invoice_commands()` 从正式表读取 `{command_id: command_payload}`。
- command `status` / `result` / `error` 不在 ignore path 中；只有 timestamps 和 migration metadata 维持通用忽略。

### App PostgreSQL mode coverage

- pending invoice recoverable command log 写入正式 PostgreSQL 表，并在 app rebuild 后恢复。
- `bank_transaction_tags` 和 `pending_invoice_tag_groups` 经 `/api/workbench/settings` round-trip 后在 PostgreSQL mode app rebuild 中保留。

## 验证

### TDD red

先写红灯测试后运行：

```bash
PYTHONPATH=backend/src:tests python3 -m pytest \
  tests/test_postgres_migrations.py \
  tests/test_postgres_test_utils.py \
  tests/test_export_app_mongo.py \
  tests/test_postgres_transform.py \
  tests/test_shadow_read_rehearsal.py \
  -q
```

红灯结果符合预期，失败集中在 `0008` 缺失、pending invoice export artifact 缺失、transform 未映射新 staging source、shadow-read catalog / psql loader 未实现。

### 离线回归

```bash
python3 -m py_compile \
  backend/src/fin_ops_platform/services/postgres_state_store.py \
  backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py \
  backend/src/fin_ops_platform/tools/postgres_transform.py \
  backend/src/fin_ops_platform/tools/export_app_mongo.py \
  backend/src/fin_ops_platform/services/shadow_read_rehearsal.py \
  backend/src/fin_ops_platform/services/shadow_read_psql_store.py

PYTHONPATH=backend/src:tests python3 -m pytest \
  tests/test_postgres_migrations.py \
  tests/test_postgres_transform.py \
  tests/test_export_app_mongo.py \
  tests/test_shadow_read_rehearsal.py \
  tests/test_postgres_repositories_core.py \
  tests/test_postgres_repositories_boundaries.py \
  tests/test_import_postgres_staging.py \
  -q
```

Result：

```text
41 passed, 4 subtests passed
```

### Disposable PostgreSQL integration

本机一次性 PostgreSQL 17 cluster：

- database：`fin_ops_stage17_test`
- host：`127.0.0.1`
- raw URL：未写入文档

Applied migrations：

```text
0001 applied extensions_and_schemas
0002 applied core_imports_invoices_bank
0003 applied workbench_relations_exceptions
0004 applied oa_projection_sync
0005 applied tax_etc_turnover_settings_jobs
0006 applied read_models
0007 applied grants
0008 applied pending_invoice_commands
```

Integration command：

```bash
FIN_OPS_TEST_DATABASE_URL=<local-disposable-postgres-url> \
PYTHONPATH=backend/src:tests python3 -m pytest \
  tests/test_postgres_test_utils.py \
  tests/test_postgres_state_store_integration.py \
  tests/test_app_postgres_mode_integration.py \
  -q
```

Result：

```text
17 passed, 5 warnings, 21 subtests passed
```

App PostgreSQL mode check：

```text
status: ready
storage.mode: postgres
storage.backend: postgres
storage.postgres_status: ready
storage.postgres_database: fin_ops_stage17_test
storage.postgres_schema_version: 8
```

## Report

- `docs/database-migration/reports/stage17-pending-invoice-postgres-coverage-20260520185819.json`

## 剩余事项

- 阶段 17 已关闭 pending invoice PostgreSQL coverage blocker。
- 下一步才适合重新运行 worktree PostgreSQL full-data import / shadow-read smoke，确认阶段 16 的 real export dataset 在 `0008` schema 下仍保持 PASS。
