# 阶段 03：规范化导出和 staging 导入

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for parallel work or `superpowers:executing-plans` for serial execution. 本阶段文档用于生成后续 Codex 执行 prompt；执行时必须逐项更新 checklist 和阶段记录。

**Goal:** 从 app Mongo 只读导出规范化数据，生成可审计 export artifact，并把导出结果导入 PostgreSQL `staging` schema；不写 OA Mongo，不写 app Mongo，不写 PostgreSQL 正式业务表。

**Architecture:** 复用现有 Python `ApplicationStateStore` 和业务 service 的读取/规范化逻辑，避免手写解析 Mongo pickle/Binary。导出产物采用 `manifest.json` + NDJSON 文件 + GridFS manifest，先进入 `staging.mongo_exports` 和 `staging.mongo_raw_records`，阶段 04 再转换正式表。

**Tech Stack:** Python 3, `ApplicationStateStore`, pymongo/GridFS read-only, PostgreSQL 16, `psql` subprocess 或既有 migration runner 风格, NDJSON, unittest.

**2026-05-20 执行状态:** `PASS`。

本地阶段 03 代码、目标测试、全量后端测试和 app check 已完成；服务器 restore/production export + staging import 已完成。阶段 03 结束时 PostgreSQL staging 只保留 production export：`staging.mongo_exports=1`，`staging.mongo_raw_records=15494`。未触碰 OA Mongo；未写 app Mongo；未写 PostgreSQL 正式业务表；未重启服务。

---

## 前置条件

- 阶段 02 gate 必须是 `PASS`。
- PostgreSQL `fin_ops` 已有 `app/read_model/job/audit/staging` schema。
- `public.schema_migrations` 0001-0007 已 applied。
- 阶段 01 app Mongo 备份和 restore gate 已通过。
- OA Mongo `form_data_db.form_data` 禁止触碰；本阶段不需要连接 OA Mongo。
- app Mongo 只读；不得 insert/update/delete/drop/createIndex/repair/compact。
- PostgreSQL 正式 schema `app/read_model/job/audit` 本阶段不得写业务行。

## 阶段边界

允许：

- 只读连接 app Mongo `fin_ops_platform_app` 或阶段 01 restore 库。
- 通过 `ApplicationStateStore` 加载当前 app 数据。
- 生成本地或服务器 export 目录。
- 写 PostgreSQL `staging.mongo_exports`、`staging.mongo_raw_records`。
- 为导出批次写 manifest、checksum、校验报告。

禁止：

- 连接、读取或写入 OA Mongo 业务正文。
- 写 app Mongo 或修改 Mongo 索引。
- 解析 pickle/Binary 时绕过现有 Python 读路径。
- 向 `app/read_model/job/audit` 写正式业务数据。
- 切换 app 读写路径、dual-write、shadow-read、重启生产服务。
- 把密码、完整连接 URI、token 写入代码、文档、日志或 prompt。

## 建议新增/修改文件

| 路径 | 动作 | 责任 |
| --- | --- | --- |
| `backend/src/fin_ops_platform/tools/__init__.py` | Create | tools package。 |
| `backend/src/fin_ops_platform/tools/export_app_mongo.py` | Create | app Mongo 只读规范化导出 CLI。 |
| `backend/src/fin_ops_platform/tools/import_postgres_staging.py` | Create | NDJSON 导入 PostgreSQL staging CLI。 |
| `backend/src/fin_ops_platform/tools/export_manifest.py` | Create | manifest、checksum、NDJSON writer、safe JSON helpers。 |
| `backend/src/fin_ops_platform/tools/exporters/` | Create | 按领域拆分 exporter，避免单文件过大。 |
| `backend/src/fin_ops_platform/tools/exporters/core.py` | Create | import batches、rows、invoices、bank transactions、files。 |
| `backend/src/fin_ops_platform/tools/exporters/workbench.py` | Create | workbench relations、overrides、exceptions、no OA、matching。 |
| `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py` | Create | settings、jobs、health、tax、ETC、turnover。 |
| `backend/src/fin_ops_platform/tools/exporters/read_models.py` | Create | read model snapshot/candidate/search source export。 |
| `tests/test_mongo_export_manifest.py` | Create | manifest/NDJSON/checksum 单元测试。 |
| `tests/test_export_app_mongo.py` | Create | fake state store 导出测试。 |
| `tests/test_import_postgres_staging.py` | Create | staging importer SQL/psql 调用和幂等测试。 |
| `docs/database-migration/03-normalized-export-staging-import.md` | Modify | 阶段执行记录。 |

## 输出目录规范

每次导出必须创建一个不可变目录：

```text
<export-root>/fin_ops_app_export_<timestamp>/
  manifest.json
  checksums.sha256
  counts.json
  import_batches.ndjson
  import_batch_rows.ndjson
  invoices.ndjson
  bank_transactions.ndjson
  import_files.ndjson
  file_objects.ndjson
  gridfs_files_manifest.ndjson
  matching_runs.ndjson
  matching_results.ndjson
  workbench_pair_relations.ndjson
  workbench_pair_relation_history.ndjson
  workbench_row_overrides.ndjson
  workbench_exception_cases.ndjson
  workbench_exception_case_events.ndjson
  workbench_matching_dirty_scopes.ndjson
  no_oa_bank_batches.ndjson
  no_oa_bank_batch_events.ndjson
  bank_transaction_categories.ndjson
  bank_transaction_category_events.ndjson
  oa_sync_state.ndjson
  oa_attachment_invoice_cache.ndjson
  manual_oa_imports.ndjson
  app_settings.ndjson
  background_jobs.ndjson
  app_health_alerts.ndjson
  tax_certified_import_sessions.ndjson
  tax_certified_import_batches.ndjson
  tax_certified_import_records.ndjson
  etc_invoices.ndjson
  etc_import_sessions.ndjson
  etc_import_batches.ndjson
  etc_submission_batches.ndjson
  etc_business_batches.ndjson
  etc_reconciliation_tasks.ndjson
  etc_reconciliation_files.ndjson
  historical_etc_repair_bundles.ndjson
  historical_etc_repair_parsed_seeds.ndjson
  historical_etc_repair_states.ndjson
  turnover_relations.ndjson
  turnover_relation_events.ndjson
  turnover_ledger_extras.ndjson
  cost_statistics_read_models.ndjson
  tax_offset_read_models.ndjson
  workbench_read_models.ndjson
  workbench_candidate_matches.ndjson
```

`manifest.json` 至少包含：

- `export_id`
- `created_at`
- `source_database`
- `source_mode`：`production` 或 `restore`
- `app_backup_archive`
- `app_backup_sha256`
- `code_git_commit`
- `schema_migration_versions`
- 每个 NDJSON 文件的 `record_count`、`sha256`、`bytes`
- GridFS 文件数量、chunk 数、总字节数、抽样 checksum 记录
- 执行环境摘要，不包含密码和完整 URI

## 数据规范

每条 NDJSON 必须是单行 UTF-8 JSON object，必须包含：

- `export_id`
- `source_collection`
- `legacy_mongo_id` 或明确的 `legacy_key`
- `record_type`
- `normalized_payload`
- `raw_payload`
- `source_versions` 可选
- `exported_at`

金额字段：

- 输出为字符串或 decimal-safe JSON，不允许 float。
- 字段名需与阶段 02 表设计对齐，例如 `amount`、`signed_amount`、`tax_amount`、`total_with_tax`、`written_off_amount`。

日期字段：

- 业务日期输出 `YYYY-MM-DD`。
- 时间戳输出 ISO 8601。
- 月份 scope 输出当月第一天 `YYYY-MM-01`。

错误处理：

- JSON 序列化失败必须 fail fast。
- Decimal/datetime/enum 必须有明确序列化函数。
- 任一 exporter 失败时，不得写入 staging；导出目录标记为 `failed`。

## 并行任务

### 任务 3.1：导出框架和 manifest

**Files:**

- Create: `backend/src/fin_ops_platform/tools/export_manifest.py`
- Create: `backend/src/fin_ops_platform/tools/export_app_mongo.py`
- Test: `tests/test_mongo_export_manifest.py`
- Test: `tests/test_export_app_mongo.py`

**Steps:**

- [ ] 读取 `ApplicationStateStore` 初始化方式和 `load_*` public methods。
- [x] 读取 `ApplicationStateStore` 初始化方式和 `load_*` public methods。
- [x] 实现显式转换函数，覆盖 `Decimal`、`datetime`、`date`、`Enum`、`Path`、`bytes/Binary` 阻断或元数据化。
- [x] 实现 `NdjsonWriter`：写临时文件，close 后计算 sha256，再原子 rename。
- [x] 实现 manifest 结构：记录文件、count、sha256、bytes、warnings、errors。
- [x] 实现 CLI：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.export_app_mongo \
  --output /data/exports/fin_ops \
  --source production
```

- [x] CLI 参数：
  - `--output`
  - `--source production|restore`
  - `--data-dir` 可选
  - `--force` 仅允许覆盖未完成目录
  - `--dry-run`
  - `--database` 可选，用于显式指定 restore DB。
- [x] 无 Mongo 配置时报清晰错误。
- [x] 输出目录已存在且 completed 时拒绝覆盖。
- [x] 测试 manifest checksum、NDJSON 单行、序列化失败、目录覆盖保护。

**Acceptance:**

- `python -m unittest tests.test_mongo_export_manifest tests.test_export_app_mongo -v` 通过。
- 导出命令在 fake store 下能生成完整 manifest。
- 输出中不包含连接密码或完整 URI。

### 任务 3.2：核心事实 exporter

**Files:**

- Create: `backend/src/fin_ops_platform/tools/exporters/core.py`
- Modify: `backend/src/fin_ops_platform/tools/export_app_mongo.py`
- Test: `tests/test_export_app_mongo.py`

**Scope:**

- `import_batches.ndjson`
- `import_batch_rows.ndjson`
- `invoices.ndjson`
- `bank_transactions.ndjson`
- `import_files.ndjson`
- `file_objects.ndjson`
- `gridfs_files_manifest.ndjson`

**Steps:**

- [x] 复用 `ApplicationStateStore` detailed collection 和 `_load_binary_payload()` 读取 import/invoice/bank/file 状态，避免手写解析 pickle 内容。
- [x] 对 `Invoice` 输出 identity：`legacy_mongo_id`、`invoice_no`、`invoice_code`、`digital_invoice_no`、`source_unique_key`、`data_fingerprint`。
- [x] 对 `BankTransaction` 输出 identity：`legacy_mongo_id`、`account_no`、`trade_time`、`txn_direction`、`amount`、`counterparty_name_raw`、`source_unique_key`、`data_fingerprint`。
- [x] 对 import batch/row 输出行级 decision、normalized row、raw row payload。
- [x] GridFS 只导出 manifest，不迁移文件内容。
- [x] GridFS manifest 包含 `gridfs_id`、`filename`、`length`、`upload_date`、`metadata`、`content_type`。
- [x] 抽样读取最多 5 个 GridFS 文件计算 checksum；文件少于 5 时全部抽样。
- [x] 测试金额不输出 float。
- [x] 测试核心对象 count 与 fake store 一致。

**Acceptance:**

- 每个核心文件 count 写入 manifest。
- 任何对象缺失 legacy identity 时记录 warning；核心对象缺失 required identity 时 fail fast。

### 任务 3.3：工作台、异常、matching、免 OA exporter

**Files:**

- Create: `backend/src/fin_ops_platform/tools/exporters/workbench.py`
- Test: `tests/test_export_app_mongo.py`

**Scope:**

- `matching_runs.ndjson`
- `matching_results.ndjson`
- `workbench_pair_relations.ndjson`
- `workbench_pair_relation_history.ndjson`
- `workbench_row_overrides.ndjson`
- `workbench_exception_cases.ndjson`
- `workbench_exception_case_events.ndjson`
- `no_oa_bank_batches.ndjson`
- `no_oa_bank_batch_events.ndjson`
- `bank_transaction_categories.ndjson`
- `bank_transaction_category_events.ndjson`

**Steps:**

- [x] 导出 relation `case_id`、`relation_mode`、`status`、`version`、`month_scope`、`row_ids`、`row_types`、`amount_check`、`special_metadata`、`source_versions`。
- [x] 导出 relation history/event snapshot，保留 actor、event_type、occurred_at、before/after payload。
- [x] 导出 row overrides，保留 `projection_version`、changed rows、override payload。
- [x] 导出 exception cases，保留 `case_id`、status、business_line、scenario、resolution、candidate ids、history/audit。
- [x] 导出 no OA batches，保留 `batch_id`、status/status_bucket、version、scope_month、account_key、total_amount、submitted/withdrawn。
- [x] 导出 bank category manual/auto 状态和 version。
- [x] 用 fake store 覆盖 exporter 文件生成和 JSON 序列化。

**Acceptance:**

- 工作台事实和审计类 payload 可完整 JSON 序列化。
- 所有 `case_id`、`batch_id`、`row_id` 进入 normalized payload。

### 任务 3.4：设置、任务、税金、ETC、往来 exporter

**Files:**

- Create: `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py`
- Test: `tests/test_export_app_mongo.py`

**Scope:**

- `app_settings.ndjson`
- `background_jobs.ndjson`
- `app_health_alerts.ndjson`
- `tax_certified_import_sessions.ndjson`
- `tax_certified_import_batches.ndjson`
- `tax_certified_import_records.ndjson`
- `etc_invoices.ndjson`
- `etc_import_sessions.ndjson`
- `etc_import_batches.ndjson`
- `etc_submission_batches.ndjson`
- `etc_business_batches.ndjson`
- `etc_reconciliation_tasks.ndjson`
- `etc_reconciliation_files.ndjson`
- `historical_etc_repair_bundles.ndjson`
- `historical_etc_repair_parsed_seeds.ndjson`
- `historical_etc_repair_states.ndjson`
- `turnover_relations.ndjson`
- `turnover_relation_events.ndjson`
- `turnover_ledger_extras.ndjson`

**Steps:**

- [x] settings 保留 singleton key、version、settings payload。
- [x] background jobs 保留 job id、type、status、owner、visibility、source、affected_months、progress、result_summary、error。
- [x] tax certified records 保留 certified unique key、invoice identity、tax amount、scope month、matched plan id。
- [x] ETC 保留 invoice number、dates、amounts、status、batch ids、task id、business batch id、version、OA detection fields、file paths/hash。
- [x] turnover 保留 relation id、bank transaction id、status、scope month、counterparty、amount、audit payload。
- [x] historical ETC repair 保留 bundle/seed/state ids 和 file references。
- [x] 测试 singleton、empty collection、legacy shape、JSON 序列化。

**Acceptance:**

- 每个已有 app Mongo collection 在 manifest 中有 covered/skipped/rebuildable 标记。
- 未发现 collection 必须写入 warning，不得 silently ignore。

### 任务 3.5：read model exporter

**Files:**

- Create: `backend/src/fin_ops_platform/tools/exporters/read_models.py`
- Test: `tests/test_export_app_mongo.py`

**Scope:**

- `workbench_read_models.ndjson`
- `workbench_candidate_matches.ndjson`
- `cost_statistics_read_models.ndjson`
- `tax_offset_read_models.ndjson`

**Steps:**

- [x] 标记 read model 为 `rebuildable=true`。
- [x] 保留 scope key、scope month、source_versions、generated_at、cache_status、payload。
- [x] 导出 candidate matches 的 candidate key、row ids、confidence、status。
- [x] 不要求阶段 03 重建 read model。
- [x] fake store 测试覆盖 read model 文件输出。

**Acceptance:**

- 阶段 04 可以选择从旧 read model 对账，但不得依赖旧 read model 作为正式事实源。

### 任务 3.6：staging importer

**Files:**

- Create: `backend/src/fin_ops_platform/tools/import_postgres_staging.py`
- Test: `tests/test_import_postgres_staging.py`

**Steps:**

- [x] 读取 export `manifest.json`，校验每个文件 sha256。
- [x] 验证 `schema_migrations` 包含 0001-0007。
- [x] 写入 `staging.mongo_exports`。
- [x] 将每条 NDJSON 写入 `staging.mongo_raw_records`：
  - `export_id`
  - `source_collection`
  - `legacy_mongo_id`
  - `record_type`
  - `normalized_payload`
  - `raw_payload`
- [x] 支持 `--dry-run`：只校验文件和输出计划，不写 DB。
- [x] 支持重复导入同一 `export_id`：已导入且 checksum 一致则跳过；checksum 不一致则失败。
- [x] 使用事务；任一文件失败时 rollback。
- [x] 不打印完整 DB URI。

**Acceptance:**

- staging 记录数等于 manifest 所有 NDJSON count 总和。
- `staging.mongo_exports.status` 为 `imported`。
- 重复导入同一 export 不产生重复记录。

## 串行执行顺序

1. 在本地实现导出框架和单元测试。
2. 用 fake store 跑所有 exporter 测试。
3. 在服务器上创建 app Mongo 只读 export 目录。
4. 连接 app Mongo restore 库先执行一次完整导出。
5. 校验 manifest 和 checksums。
6. 将 restore export 导入 PostgreSQL staging。
7. 校验 staging count。
8. 如 restore gate 通过，再对生产 app Mongo 执行只读导出。
9. 将生产 export 导入 PostgreSQL staging。
10. 更新本阶段文档。

## 推荐命令

本地：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_mongo_export_manifest tests.test_export_app_mongo tests.test_import_postgres_staging -v
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

服务器 dry-run：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src python3 -m fin_ops_platform.tools.export_app_mongo --output /data/exports/fin_ops --source restore --dry-run
PYTHONPATH=/opt/fin-ops/current/backend/src python3 -m fin_ops_platform.tools.import_postgres_staging --export-dir <export-dir> --dry-run
```

服务器正式：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src python3 -m fin_ops_platform.tools.export_app_mongo --output /data/exports/fin_ops --source production
PYTHONPATH=/opt/fin-ops/current/backend/src python3 -m fin_ops_platform.tools.import_postgres_staging --export-dir <export-dir>
```

生产导入前如果同一个 PostgreSQL staging 已保留 restore gate 数据，需要先完成 restore gate 记录，再用 importer 的 `--replace-existing-staging` 选项清空 `staging.mongo_exports` 和 `staging.mongo_raw_records` 后导入 production export。原因是阶段 02 的 `mongo_raw_records_identity_uidx` 对 `(source_collection, legacy_mongo_id)` 建唯一索引，同一份 app Mongo restore 与 production 数据会共享 legacy id；阶段 03 结束状态以 production export 为准。

## 2026-05-20 执行记录

### 子代理并行复核结果

- 1A 导出框架复核：确认 `ApplicationStateStore.__init__()` 原本会执行 `_ensure_mongo_metadata()`，严格只读导出必须增加 `read_only=True` 或绕开初始化写路径；建议实现独立 safe JSON、NDJSON writer、manifest/checksum，并用 fake store 断言不写 Mongo。
- 1B 核心事实复核：确认 `import_batch_rows` 不在独立 collection 中，必须从 `import_batches.payload.row_results` 与 `normalized_rows` 拆行；`Invoice` / `BankTransaction` 完整事实以反序列化 payload 为准，顶层展开字段不完整；GridFS metadata 来自 `import_file_blobs.files`。
- 1C 工作台/税金/ETC/read model 复核：确认工作台关系、异常、免 OA、分类、税金、ETC、往来为事实类；read model 和 cache 标记为 `rebuildable=true` reference；空集合应生成空 NDJSON 和 manifest 条目。
- 1D 未单独启动：由于当时 agent 线程数达到上限，staging importer 复核由主线程完成。

### 新增/修改文件

- `backend/src/fin_ops_platform/services/state_store.py`：新增 `ApplicationStateStore(..., read_only=True)`，只读初始化跳过 Mongo metadata upsert；默认行为不变。
- `backend/src/fin_ops_platform/tools/__init__.py`
- `backend/src/fin_ops_platform/tools/export_manifest.py`
- `backend/src/fin_ops_platform/tools/export_app_mongo.py`
- `backend/src/fin_ops_platform/tools/import_postgres_staging.py`
- `backend/src/fin_ops_platform/tools/exporters/__init__.py`
- `backend/src/fin_ops_platform/tools/exporters/core.py`
- `backend/src/fin_ops_platform/tools/exporters/workbench.py`
- `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py`
- `backend/src/fin_ops_platform/tools/exporters/read_models.py`
- `tests/test_mongo_export_manifest.py`
- `tests/test_export_app_mongo.py`
- `tests/test_import_postgres_staging.py`
- `docs/database-migration/03-normalized-export-staging-import.md`

### 本地验证结果

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_mongo_export_manifest tests.test_export_app_mongo tests.test_import_postgres_staging -v
```

结果：`OK`，8 tests。

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

结果：`OK (skipped=5)`，1126 tests。

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

结果：`status=ready`，storage local check 通过。

### 服务器执行结果

- SSH 登录成功；密码未写入代码、文档或服务器文件。
- `fin-ops.service` 执行前后均为 `active`。
- 阶段 03 工具上传到服务器临时目录执行，未覆盖 `/opt/fin-ops/current`，未重启服务。
- restore export dry-run：通过。
- restore export：通过。
- restore staging importer dry-run：通过。
- restore staging import：通过，`15481` rows。
- production export dry-run：通过。
- production export：通过。
- production staging importer dry-run：通过。
- production staging import：通过，使用 `--replace-existing-staging` 清除 restore staging 后导入 production，`15494` rows。
- 重复导入同一 production export：安全跳过，返回 `status=skipped` / `reason=export_already_imported`。
- PostgreSQL 后验：`staging.mongo_exports=1`，`staging.mongo_raw_records=15494`。
- OA Mongo：未触碰。
- app Mongo：只读导出，未写入、未建索引、未清理。

### Export/Import 记录

| 项目 | 状态 |
| --- | --- |
| restore export id | `fin_ops_app_export_20260519235445_034e74e8` |
| restore export path | `/data/exports/fin_ops/fin_ops_app_export_20260519235445_034e74e8` |
| restore manifest path | `/data/exports/fin_ops/fin_ops_app_export_20260519235445_034e74e8/manifest.json` |
| restore manifest file sha256 | `76a69e3ec922e158805ffd46af4b31c3df7ead6681f8507d7f1ff2cf9c7eac1e` |
| restore manifest payload sha256 | `a9bbe32f11ee168f4b94150ae7889ee374ae3d0261ff567aa4b54c596601d8ac` |
| restore total records | `15481` |
| restore staging import | `imported`，后验 `15481` rows |
| production export id | `fin_ops_app_export_20260519235526_5a233544` |
| production export path | `/data/exports/fin_ops/fin_ops_app_export_20260519235526_5a233544` |
| production manifest path | `/data/exports/fin_ops/fin_ops_app_export_20260519235526_5a233544/manifest.json` |
| production manifest file sha256 | `924ae80f2d613d8954a875a6a2f4508fcaf940d88085120ab48db72957c09901` |
| production manifest payload sha256 | `54d14c2ee2c2f09e7fb7c62bd5a6729fbb7dad075c76180f2be3cf2dbc414152` |
| production total records | `15494` |
| production staging import | `imported` |
| production duplicate import | `skipped` |
| `staging.mongo_exports` 后验 count | `1` |
| `staging.mongo_raw_records` 后验 count | `15494` |
| OA Mongo | 未触碰 |

### GridFS 结果

restore 和 production export 的 GridFS 统计均与阶段 01 记录一致：

- files：`445`
- chunks：`709`
- total bytes：`98716321`
- sampled checksum count：`5`
- sampled sha256：
  - `c60ad00223c2b0b0e0096c60cc4a94fa35a05161346e25190ac807f5ca1ff197`
  - `a86ff733cf22e1cc8b3c1de1919d69b24d6d75ce9fffb08f4cfc476c3c73a4f6`
  - `424c71679aacbafd03158ab1be18fc109227342c078a480c071df505a01f71a1`
  - `1f61bf6f1d334d3b0bb4bf4cf4a7fd4b9647de1eee843801a321690ea97a67a3`
  - `c719052e094e40c06a638afd8057ef9d949451c705d4d14c91d2849b3bf1b85e`

### Restore 与 Production 差异说明

production export 比 restore export 多 `13` 条记录。差异集中在运行期派生/运维状态：

- background jobs：restore `111`，production `114`
- cost statistics read models：restore `30`，production `34`
- workbench candidate matches：restore `5276`，production `5274`
- workbench matching dirty scopes：restore `0`，production `2`
- workbench read models：restore `0`，production `6`

核心业务事实数量未变化：invoices `391`，bank transactions `431`，import batches `6`，GridFS files `445`。

## Gate

当前 gate：`PASS`。

`PASS` 条件：

- 导出命令不写 Mongo。
- manifest 中所有 NDJSON checksum 校验通过。
- export count 与 app Mongo 只读 count 对齐；差异必须有解释。
- GridFS files/chunks/total length 与阶段 01 记录或当次只读统计一致。
- staging row count 与 manifest 总数一致。
- 重复导入同一 export 安全跳过。
- 后端全量单测通过。
- 文档记录 export id、路径、counts、checksum、staging import result。

`BLOCKED` 条件：

- 发现导出需要写 Mongo 或修改索引。
- JSON/Decimal/datetime 序列化失败。
- manifest checksum 不一致。
- staging count 与 manifest 不一致。
- export 中出现不可解释的缺失核心 identity。
- 任何命令输出或文档包含密码、token 或完整 URI。

## 阶段产物

- export 目录。
- `manifest.json`
- `checksums.sha256`
- PostgreSQL `staging.mongo_exports` 记录。
- PostgreSQL `staging.mongo_raw_records` 记录。
- 阶段 03 执行报告。
