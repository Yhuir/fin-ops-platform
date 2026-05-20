# 08 PostgreSQL domain repository 最终闭合执行记录

执行时间：2026-05-20

Gate：`PARTIAL`

## 阶段边界

- 阶段 08 没有做生产切换、shadow-read、dual-write、cutover、服务重启或生产配置修改。
- OA Mongo `form_data_db.form_data` 未触碰；本阶段没有对 OA Mongo 做读写、建索引、清洗或迁移。
- app Mongo `fin_ops_platform_app` 未写入。
- 生产 PostgreSQL `fin_ops` 只做只读 smoke/count/schema 检查。

## 已闭合内容

### tax certified import

- `PostgresStateStore.load_tax_certified_imports()` 优先从正式表恢复：
  - `app.tax_certified_import_sessions`
  - `app.tax_certified_import_batches`
  - `app.tax_certified_import_records`
- `PostgresStateStore.save_tax_certified_imports()` 写入上述正式表，并保留 `state:tax_certified_imports` 作为兼容 fallback。
- `TaxCertifiedImportService._hydrate()` 已支持把 JSON/dict snapshot 恢复为 `TaxCertifiedImportSession`、`TaxCertifiedImportPreviewFile`、`TaxCertifiedImportBatch`、`TaxCertifiedInvoiceRecord`，避免 PostgreSQL JSONB round-trip 后出现 dict attribute error。
- integration 覆盖：正式表保存后重建 `TaxCertifiedImportService`，可继续按月份查询 certified records。

### ETC

- `PostgresStateStore.load_etc_state()` 优先从正式表恢复：
  - `app.etc_invoices`
  - `app.etc_import_batches`
  - `app.etc_submission_batches`
  - `app.etc_business_batches`
- `PostgresStateStore.save_etc_state()` 写入上述正式表，并保留 `state:etc_state` 作为兼容 fallback。
- `EtcService._hydrate()` 已支持把 JSON/dict snapshot 恢复为 `EtcInvoice`、`EtcBatch`、`EtcImportBatch`、`EtcBusinessBatch`，并恢复 `Decimal`、`datetime`、`EtcInvoiceStatus`。
- integration 覆盖：正式表保存后重建 `EtcService`，可继续 `list_invoices()`、`list_import_batches()`、`get_business_batch()`。

### ETC reconciliation

- `PostgresStateStore.load_etc_reconciliation_state()` 优先从：
  - `app.etc_reconciliation_tasks`
  - `app.etc_reconciliation_files`
  恢复 task snapshot。
- `PostgresStateStore.save_etc_reconciliation_state()` 写入 task/file 正式表，并保留 `state:etc_reconciliation_state` fallback。
- integration 覆盖：创建 task、上传 source file、重建 `EtcReconciliationTaskService` 后仍能恢复 task 和 source file。

### historical ETC

- `save_historical_etc_repair_bundle()` 写入：
  - `app.file_objects`
  - `app.historical_etc_repair_bundles`
- `save_historical_etc_repair_parsed_seed()` 写入：
  - `app.historical_etc_repair_parsed_seeds`
- `save_historical_etc_repair_states()` 写入：
  - `app.historical_etc_repair_states`
- 对应 load 方法优先从正式表恢复，snapshot 只作为 fallback。
- integration 覆盖：bundle metadata、parsed seed、repair states 均可从正式表恢复。

### event/history

- `workbench_pair_relation_history`、`no_oa_bank_batch_events`、`bank_transaction_category_events`、`turnover_relation_events` 已补正式表写入和真实 DB 覆盖。
- `bank_transaction_categories` 替换主表行前先按 transaction scope 清理事件，避免 event 外键阻止主表行更新。
- `load_turnover_relations()` 从正式表恢复时返回 service 需要的 list shape，并补齐 `relation_id`。

## search/read model 判定

`read_model.search_index_rows` 仍作为迁移产物和后续加速表保留。当前 `/api/search` runtime 由 `SearchService` 基于 workbench loader 构建内存索引，并不直接依赖 `read_model.search_index_rows`。

阶段 08 没有把 search runtime 切换到 `search_index_rows`。本项判定为：runtime 不阻塞 PostgreSQL mode，但 repository 拆分/正式 search index runtime 化仍是后续架构优化项。

## 仍未完全闭合

### 1. repository package 拆分未完成

08 prompt 要求将 `PostgresStateStore` 内的 workbench/read_models/ops_tax_etc SQL 继续拆到：

- `postgres_repositories/workbench.py`
- `postgres_repositories/read_models.py`
- `postgres_repositories/ops_tax_etc.py`

本阶段只保留阶段 07 已有 `postgres_repositories/core.py`，没有完成上述拆分。因此 Gate 不能标为 `PASS`。

原因：阶段 08 优先处理会导致 runtime 失败的数据恢复、正式表写入、event/history 外键和 integration 覆盖。继续拆分会扩大改动面，需要额外一轮只做 repository extraction 的低风险重构和回归验证。

用户需要做什么：不需要提供新权限或新数据；后续生成一个独立 “09 repository extraction” prompt 即可。

### 2. 部分写路径事务边界仍需统一

`PostgresConnection` 已有 transaction API，integration 已覆盖 rollback 基础能力。但 `PostgresStateStore` 多表写入目前仍有部分方法逐条执行，尚未统一包裹 transaction。

用户需要做什么：不需要提供新信息；建议在 repository extraction 阶段同时把多表写路径收口到 repository/transaction 边界。

### 3. search_index_rows 未作为 runtime repository

当前 search runtime 可从正式表派生，不依赖 `search_index_rows`。如果业务希望 search index 成为 runtime source，需要确认：

- search index 刷新时机；
- stale 删除 scope；
- API 是否允许读取异步索引而不是实时派生结果。

用户需要做什么：确认 search 是“实时派生优先”还是“索引表优先”。

## 验证记录

无 test DB 环境下：

```text
python -m pytest tests/test_postgres_state_store.py tests/test_postgres_state_store_integration.py -q
8 passed, 8 skipped, 5 warnings
```

本机 UTF8 disposable PostgreSQL `fin_ops_stage08_test`：

```text
python -m pytest tests/test_postgres_state_store_integration.py -q
8 passed, 5 warnings, 16 subtests passed
```

阶段相关 PostgreSQL 矩阵，本机 UTF8 disposable PostgreSQL：

```text
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py -q
40 passed, 5 warnings, 26 subtests passed
```

默认全量测试：

```text
python -m pytest -q
1144 passed, 16 skipped, 5 warnings, 17 subtests passed
```

默认 app check：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
status=ready
storage.backend=local_pickle
```

生产只读 smoke：

```text
fin-ops.service=active
schema_migrations=0001,0002,0003,0004,0005,0006,0007
app.import_batches=6
app.import_batch_rows=897
app.import_files=31
app.invoices=391
app.bank_transactions=431
read_model.search_index_rows=822
```

## Gate 判定

`PARTIAL`

PostgreSQL mode 对 app 自身关键 runtime domains 的正式表读写能力已显著推进，阶段 07 的主要 runtime 数据缺口已经闭合并通过真实 PostgreSQL integration 验证。仍不能标为 `PASS` 的原因是 repository package 拆分和多表事务边界统一尚未完成；这两项属于后续工程收口，不需要新的服务器权限或业务数据。

下一阶段建议：生成并执行 `09-postgresql-repository-extraction-transaction-boundary.prompt.md`，只做 repository extraction、transaction 收口、search index runtime 决策，不再扩大迁移范围。
