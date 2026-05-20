# 09 PostgreSQL repository extraction + transaction boundary 执行记录

执行时间：2026-05-20

Gate：`PASS`

## 阶段边界

- 阶段 09 没有做生产切换、shadow-read、dual-write、cutover、服务重启或生产配置修改。
- OA Mongo `form_data_db.form_data` 未触碰；本阶段没有对 OA Mongo 做读、写、建索引、清洗、备份或迁移。
- app Mongo `fin_ops_platform_app` 未写入。
- 生产 PostgreSQL `fin_ops` 只做只读 smoke/count/schema 检查。
- destructive PostgreSQL integration 只在本机一次性 UTF8 test cluster 的 `fin_ops_stage09_test` 上执行，测试结束后停止并删除 cluster。

## 完成内容

### repository package 拆分

`PostgresStateStore` 已收口为 public state-store API、snapshot fallback、文件存储桥接和 repository 编排。正式表 domain SQL 已拆到：

- `backend/src/fin_ops_platform/services/postgres_repositories/common.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`

`postgres_repositories/__init__.py` 已导出：

- `PostgresCoreRepository`
- `PostgresWorkbenchRepository`
- `PostgresReadModelRepository`
- `PostgresOpsTaxEtcRepository`

### workbench / no-OA / turnover

以下正式表读写从 `PostgresStateStore` 抽到 `PostgresWorkbenchRepository`：

- workbench pair relations + history
- no-OA bank batches + audit events
- bank transaction categories + audit events
- turnover relations + audit events
- turnover ledger extras
- workbench row overrides
- workbench exception cases + events

`PostgresStateStore` 保留 snapshot fallback，并在 save 后继续写兼容 snapshot。

### read models

以下正式表读写从 `PostgresStateStore` 抽到 `PostgresReadModelRepository`：

- `read_model.workbench_snapshots`
- `read_model.workbench_candidate_matches`
- `read_model.cost_statistics_read_models`
- `read_model.tax_offset_read_models`

修正点：

- `tax_offset_read_models` 使用现有 schema 的 `entry_count`，不再错误写入不存在的 `row_count`。
- read model 的 changed-scope delete + upsert 已包在 transaction boundary 中。

### ops / tax / ETC

以下正式表读写从 `PostgresStateStore` 抽到 `PostgresOpsTaxEtcRepository`：

- app settings / state snapshot settings
- OA attachment invoice cache
- OA sync watermarks 的只读恢复
- manual OA imports 的只读恢复
- tax certified import sessions / batches / records
- ETC invoices / import batches / submission batches / business batches
- ETC reconciliation tasks / files
- historical ETC repair bundles / parsed seeds / states
- background jobs
- app health alerts

文件内容写入、local file path、旧 GridFS reference 兼容读取继续保留在 `PostgresStateStore`，repository 只负责 SQL persistence。

## transaction boundary

新增共享 helper：

- `run_in_transaction(connection, callback)`

以下多表或 delete+insert 写路径已经通过 repository transaction boundary 执行：

- `PostgresCoreRepository.save_imports()`
- workbench pair relation + history
- no-OA bank batch + events
- bank category replace + events
- turnover relation + events
- workbench exception cases + events
- workbench/candidate/cost/tax read model scoped writes
- tax certified import sessions/batches/records
- ETC invoices/import/submission/business batches
- ETC reconciliation tasks/files
- historical ETC repair states
- background jobs
- app health alerts

新增 `tests/test_postgres_repositories_boundaries.py` 覆盖：

- category event cleanup、category replace 和 event insert 在同一 transaction 中执行；
- tax read model 使用 `entry_count` 且 transaction 生效；
- ETC reconciliation task/file 多表写入使用 transaction。

剩余说明：

- 文件系统写入无法随 PostgreSQL transaction 自动 rollback。`PostgresStateStore` 仍可能在 DB 写失败时留下 app-owned local orphan file；这与阶段 08 一致，后续如要完全闭合，需要单独做 orphan file cleanup/compensation 任务。

## search runtime 决策

阶段 09 明确保持当前 runtime 决策：

- `/api/search` 继续由 `SearchService` 基于 workbench loader 实时派生内存索引。
- `read_model.search_index_rows` 继续作为 migration 产物、staging reconciliation 证据和后续加速表保留。
- 本阶段不把 `/api/search` runtime source 切到 `read_model.search_index_rows`，原因是切换还需要定义 refresh timing、stale scope 删除、回退策略和异步索引一致性语义，属于后续优化，不是 repository extraction 的必要条件。

新增 PostgreSQL app integration smoke：

- 在 PostgreSQL mode 下持久化 no-OA workbench read model；
- 重建 app 后调用 `/api/search?q=NO-OA-STAGE09-SERIAL&scope=bank&month=all`；
- 同时验证 invalid scope 返回 `invalid_search_request`。

## 生产只读 smoke

本阶段只执行 read-only 检查：

```text
fin-ops.service=active
schema_migrations=0001,0002,0003,0004,0005,0006,0007
counts=6,897,31,391,431,822
```

计数顺序：

```text
app.import_batches,
app.import_batch_rows,
app.import_files,
app.invoices,
app.bank_transactions,
read_model.search_index_rows
```

说明：生产库 migration 记录表位于 `public.schema_migrations`。

## 验证记录

无 test DB 环境下 PostgreSQL integration 安全 skip：

```text
python -m pytest tests/test_postgres_repositories_boundaries.py tests/test_postgres_state_store.py tests/test_postgres_repositories_core.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
12 passed, 11 skipped, 5 warnings
```

本机 UTF8 disposable PostgreSQL `fin_ops_stage09_test`：

```text
python -m pytest tests/test_postgres_migrations.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
21 passed, 5 warnings, 16 subtests passed
```

阶段 09 常规矩阵：

```text
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
32 passed, 11 skipped, 5 warnings, 10 subtests passed
```

默认 app check：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
status=ready
storage.backend=local_pickle
```

默认全量测试：

```text
python -m pytest -q
1147 passed, 16 skipped, 5 warnings, 17 subtests passed
```

## Gate 判定

`PASS`

阶段 08 的 `PARTIAL` 剩余项已经闭合：

- repository package 拆分完成；
- 多表写入已通过明确 transaction boundary 收口并新增测试；
- search runtime 决策已记录，并补 PostgreSQL no-OA `/api/search` smoke；
- 默认 local/Mongo 行为保持，app check 仍为 `local_pickle`；
- 真实 PostgreSQL integration 通过；
- 生产 PostgreSQL 只读 smoke 通过。

下一阶段可以进入 shadow/dual-write/cutover 前的准备 prompt，但建议先单独生成阶段 10：生产 shadow-read / dual-write preflight，明确观测指标、回滚开关、差异比对和禁止写 OA Mongo 的运行守卫。
