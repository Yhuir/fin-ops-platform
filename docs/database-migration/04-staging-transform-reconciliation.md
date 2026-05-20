# 阶段 04：staging 转正式表和对账

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for parallel work or `superpowers:executing-plans` for serial execution. 本阶段文档用于生成后续 Codex 执行 prompt；执行时必须先从阶段 03 的 manifest 和 staging import result 建立基线。

**Goal:** 将 `staging.mongo_raw_records` 中的规范化导出数据转换到 PostgreSQL 正式 schema，并生成可审计对账报告，证明 Mongo export 与 PostgreSQL 正式表在数量、金额、状态、月份、文件和关键样本上可解释一致。

**Architecture:** 使用可重复执行的转换工具，从 staging 读取 normalized payload，生成稳定 UUID 映射后写入 `app/read_model/job/audit`。转换先在事务中执行，写入正式表后立即生成 reconciliation report；任何差异必须阻断切到阶段 05。

**Tech Stack:** Python 3, PostgreSQL 16, SQL transactions, NDJSON/JSON report, unittest, `psql`.

---

## 前置条件

- 阶段 02 gate 是 `PASS`。
- 阶段 03 gate 是 `PASS`。
- PostgreSQL staging 已导入至少一个 production export。
- `staging.mongo_exports.status='imported'`。
- `staging.mongo_raw_records` count 与 manifest 一致。
- 本阶段开始前必须对 PostgreSQL `fin_ops` 做 `pg_dump -Fc` 备份。

## 阶段边界

允许：

- 读取 `staging`。
- 写 `staging.id_mappings`。
- 写正式表：`app/read_model/job/audit`。
- 生成 reconciliation report。
- 为转换过程写 audit/migration event。

禁止：

- 连接或读取 OA Mongo。
- 连接或写 app Mongo。
- 从 Mongo 重新导出数据。
- 解析原始 pickle/Binary。
- 切换 app 读写路径。
- 在差异未解释时继续阶段 05。

## 建议新增/修改文件

| 路径 | 动作 | 责任 |
| --- | --- | --- |
| `backend/src/fin_ops_platform/tools/transform_staging_to_postgres.py` | Create | staging 到正式表转换 CLI。 |
| `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py` | Create | 对账报告 CLI。 |
| `backend/src/fin_ops_platform/tools/transformers/__init__.py` | Create | transformer package。 |
| `backend/src/fin_ops_platform/tools/transformers/ids.py` | Create | 稳定 UUID 映射。 |
| `backend/src/fin_ops_platform/tools/transformers/core.py` | Create | imports/invoices/bank/files 转换。 |
| `backend/src/fin_ops_platform/tools/transformers/workbench.py` | Create | matching/workbench/no OA/bank category 转换。 |
| `backend/src/fin_ops_platform/tools/transformers/ops_tax_etc.py` | Create | settings/jobs/health/tax/ETC/turnover 转换。 |
| `backend/src/fin_ops_platform/tools/transformers/read_models.py` | Create | read model 重建或迁移。 |
| `backend/src/fin_ops_platform/tools/reconciliation_report.py` | Create | report model 和 writer。 |
| `tests/test_postgres_transform_ids.py` | Create | UUID 映射测试。 |
| `tests/test_transform_staging_to_postgres.py` | Create | transformer 单元/集成测试。 |
| `tests/test_reconcile_postgres_migration.py` | Create | 对账报告测试。 |
| `docs/database-migration/04-staging-transform-reconciliation.md` | Modify | 阶段执行记录。 |

## 转换原则

- 稳定 UUID：同一 `(source_collection, legacy_mongo_id, target_table)` 多次转换必须生成同一 UUID。
- 幂等：同一 export 重跑转换不得重复写正式表；checksum 不一致必须失败。
- 事务：一个 export 的正式表转换必须具备可回滚边界。
- 严格校验：金额、日期、状态、identity、foreign key 解析失败必须阻断。
- 原始保留：无法第一版拆列的字段保留在 `raw_payload` 或领域 JSONB。
- 不依赖旧 read model 作为事实源：read model 可以导入用于对账，也可以从事实表重建。

## 并行任务

### 任务 4.1：转换框架和稳定 ID 映射

**Files:**

- Create: `backend/src/fin_ops_platform/tools/transform_staging_to_postgres.py`
- Create: `backend/src/fin_ops_platform/tools/transformers/ids.py`
- Test: `tests/test_postgres_transform_ids.py`

**Steps:**

- [ ] 实现 deterministic UUID 生成：建议 `uuid5(namespace, f"{source_collection}:{legacy_id}:{target_table}")`。
- [ ] 将映射写入 `staging.id_mappings`。
- [ ] 已存在映射且 target_id 一致则复用。
- [ ] 已存在映射但 target_id 不一致则 fail fast。
- [ ] CLI 支持：
  - `--export-id`
  - `--dry-run`
  - `--only-domain`
  - `--rebuild-read-models`
  - `--fail-on-warning`
- [ ] transform 前确认 0001-0007 migrations applied。
- [ ] transform 前确认 export 已 imported。
- [ ] 测试同一旧 id 多次转换生成同一 UUID。
- [ ] 测试不同 table 的同一旧 id 生成不同 UUID。

**Acceptance:**

- `staging.id_mappings` 数量与转换对象数量一致。
- 重跑不会改变 UUID。

### 任务 4.2：核心事实转换

**Files:**

- Create: `backend/src/fin_ops_platform/tools/transformers/core.py`
- Test: `tests/test_transform_staging_to_postgres.py`

**Target tables:**

- `app.import_batches`
- `app.import_batch_rows`
- `app.file_objects`
- `app.import_files`
- `app.invoices`
- `app.bank_transactions`

**Steps:**

- [ ] 从 `staging.mongo_raw_records` 读取核心 source collections。
- [ ] import batch 转换 row_count、success/error/duplicate、status、imported_at。
- [ ] import rows 转换 decision、linked object、identity fields。
- [ ] invoice 转换 invoice identity、counterparty、seller/buyer、amount、tax、month、status、source batch。
- [ ] bank transaction 转换 account、direction、counterparty、amount、signed amount、date/month、status、source batch。
- [ ] file object 转换 GridFS legacy id、storage_backend、storage_uri、size_bytes、content_type、metadata。
- [ ] 对 source_unique_key/data_fingerprint 冲突做 fail fast。
- [ ] 金额不能通过 float 转换。
- [ ] 测试数量、金额合计、月份分布、状态分布。

**Acceptance:**

- 核心对象数量与 manifest 对齐。
- 发票和流水金额合计差异为 0。
- 旧 id 能映射到新 UUID。

### 任务 4.3：工作台、matching、异常、免 OA 转换

**Files:**

- Create: `backend/src/fin_ops_platform/tools/transformers/workbench.py`
- Test: `tests/test_transform_staging_to_postgres.py`

**Target tables:**

- `app.matching_runs`
- `app.matching_results`
- `app.workbench_pair_relations`
- `app.workbench_pair_relation_history`
- `app.workbench_row_overrides`
- `app.workbench_exception_cases`
- `app.workbench_exception_case_events`
- `app.no_oa_bank_batches`
- `app.no_oa_bank_batch_events`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_events`
- `job.workbench_matching_dirty_scopes`

**Steps:**

- [ ] 转换 relation `case_id`、row ids、row types、relation mode、status、amount_check、special metadata。
- [ ] 转换 relation history，不丢失撤回/重开/取消事件。
- [ ] 转换 exception case 和 events，保留 `WEX-*` case id、history/audit。
- [ ] 转换 row overrides，保留 projection version 和 changed rows。
- [ ] 转换 no OA batches 和 event log，保留 version 和提交/撤回信息。
- [ ] 转换 bank category manual/auto 状态，保留 expected version 语义基础。
- [ ] 转换 matching runs/results 作为历史兼容数据。
- [ ] 测试 active/reverted/withdrawn 状态分布。
- [ ] 测试同一 case_id unique。

**Acceptance:**

- active relation count 与 export 一致。
- no OA batch count 与 export 一致。
- 所有 event/audit payload 可读取。

### 任务 4.4：设置、任务、税金、ETC、往来转换

**Files:**

- Create: `backend/src/fin_ops_platform/tools/transformers/ops_tax_etc.py`
- Test: `tests/test_transform_staging_to_postgres.py`

**Target tables:**

- `app.app_settings`
- `job.background_jobs`
- `audit.app_health_alerts`
- `app.tax_certified_import_sessions`
- `app.tax_certified_import_batches`
- `app.tax_certified_import_records`
- `app.etc_*`
- `app.historical_etc_repair_*`
- `app.turnover_relations`
- `app.turnover_relation_events`
- `app.turnover_ledger_extras`

**Steps:**

- [ ] 转换 app settings singleton。
- [ ] 转换 background jobs，保留 progress、result_summary、attention、superseded_by。
- [ ] 转换 app health alerts。
- [ ] 转换 tax certified sessions/batches/records，校验 certified unique key。
- [ ] 转换 ETC invoices/imports/submissions/business batches/reconciliation tasks/files。
- [ ] 转换 historical ETC repair bundle/seed/state。
- [ ] 转换 turnover relations/events/extras。
- [ ] 测试空集合可安全处理。
- [ ] 测试 version/expected_version 所需字段存在。

**Acceptance:**

- 所有非空 app Mongo collection 有正式表承接或明确标记为 rebuildable/skipped。

### 任务 4.5：read model 重建和搜索索引

**Files:**

- Create: `backend/src/fin_ops_platform/tools/transformers/read_models.py`
- Test: `tests/test_transform_staging_to_postgres.py`

**Target tables:**

- `read_model.workbench_rows`
- `read_model.workbench_snapshots`
- `read_model.workbench_candidate_matches`
- `read_model.search_index_rows`
- `read_model.cost_statistics_read_models`
- `read_model.tax_offset_read_models`

**Steps:**

- [ ] 先导入旧 read model payload 作为对账参考，标记 `cache_status='imported_reference'`。
- [ ] 从正式事实表重建 `search_index_rows`。
- [ ] 如当前 service 可复用，则调用现有 workbench/cost/tax read model service 生成新 read model。
- [ ] 如果重建依赖 OA Mongo，则本阶段只使用阶段 03 已导出的 app-side OA cache/manual import，不连接 OA Mongo。
- [ ] 对旧 read model 和新 read model 做样本 diff。
- [ ] 测试 search index 覆盖 OA/bank/invoice 文本字段。

**Acceptance:**

- read model 可以重建或明确延期到阶段 05 shadow-read。
- search index row count 与可搜索对象数量有可解释关系。

### 任务 4.6：对账报告

**Files:**

- Create: `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`
- Create: `backend/src/fin_ops_platform/tools/reconciliation_report.py`
- Test: `tests/test_reconcile_postgres_migration.py`

**Report outputs:**

```text
<report-dir>/migration_reconciliation_report_<export_id>.json
<report-dir>/migration_reconciliation_report_<export_id>.md
```

**Report sections:**

- export identity、manifest checksum、code commit。
- source counts vs staging counts vs app/read_model/job/audit counts。
- 金额合计：发票、银行、税金、ETC、往来。
- 状态分布：invoice、bank、relation、exception、no OA、ETC、jobs。
- 月份分布：invoice_month、txn_month、scope_month。
- 文件：GridFS manifest count、total bytes、抽样 checksum。
- ID mapping：每个 source collection 映射数量。
- 样本 diff：按对象类型抽样旧 normalized payload 与新 row。
- warnings/errors/blockers。

**Steps:**

- [ ] 实现 SQL 聚合查询。
- [ ] 实现 manifest 读取和 expected counts。
- [ ] 实现金额 Decimal 比较，差异必须精确输出。
- [ ] 实现 Markdown 摘要。
- [ ] 差异对象必须包含 source_collection、legacy_mongo_id、target_table、target_id、field、source_value、target_value。
- [ ] 测试报告在无差异时 `status=pass`。
- [ ] 测试报告在金额差异时 `status=blocked`。

**Acceptance:**

- 核心对象数量 100% 一致，除非报告明确说明废弃原因。
- 金额合计差异为 0。
- 状态和月份分布差异为 0 或有逐项解释。
- 文件数量和抽样 checksum 通过。
- 工作台样本 API payload 差异为 0 或有业务确认。

## 串行执行顺序

1. DDL 前备份 PostgreSQL。
2. 确认 staging import result。
3. dry-run transform，输出将写入的 table/count。
4. 执行 ID mapping。
5. 转换核心事实。
6. 转换工作台/异常/免 OA。
7. 转换设置/任务/税金/ETC/往来。
8. 重建或导入 read model/reference。
9. 生成 reconciliation report。
10. 如果报告 PASS，记录阶段 04 gate。
11. 如果报告 BLOCKED，停止，不进入阶段 05。

## 推荐命令

本地：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_transform_ids tests.test_transform_staging_to_postgres tests.test_reconcile_postgres_migration -v
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

服务器：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src python3 -m fin_ops_platform.tools.transform_staging_to_postgres --export-id <export-id> --dry-run
PYTHONPATH=/opt/fin-ops/current/backend/src python3 -m fin_ops_platform.tools.transform_staging_to_postgres --export-id <export-id>
PYTHONPATH=/opt/fin-ops/current/backend/src python3 -m fin_ops_platform.tools.reconcile_postgres_migration --export-id <export-id> --output /data/exports/fin_ops/reports
```

## Gate

`PASS` 条件：

- PostgreSQL DDL 前备份完成。
- 转换工具可重复执行，不重复写数据。
- `staging.id_mappings` 稳定。
- 核心对象数量一致。
- 发票、流水、税金、ETC 关键金额合计差异为 0。
- 文件 manifest 数量和抽样 checksum 通过。
- reconciliation report `status=pass`。
- 后端全量单测通过。
- 阶段文档记录 export id、report path、关键 count、差异结论。

`BLOCKED` 条件：

- staging count 与 manifest 不一致。
- 稳定 UUID 映射冲突。
- source identity 缺失且无法解释。
- 金额/日期/status 解析失败。
- 任何核心对象数量差异无法解释。
- reconciliation report `status=blocked`。

## 阶段产物

- `staging.id_mappings`
- 正式表数据
- `migration_reconciliation_report_<export_id>.json`
- `migration_reconciliation_report_<export_id>.md`
- 阶段 04 执行报告

## 执行记录（2026-05-20）

### 输入基线

- production export id：`fin_ops_app_export_20260519235526_5a233544`
- source database：`fin_ops_platform_app`
- manifest payload sha256：`54d14c2ee2c2f09e7fb7c62bd5a6729fbb7dad075c76180f2be3cf2dbc414152`
- staging raw records：`15494`
- manifest total records：`15494`
- 阶段 04 未连接 OA Mongo，未连接或写入 app Mongo。
- 阶段 04 工具上传到服务器临时目录执行：`/tmp/finops_stage04_202605200815/src`，未覆盖 `/opt/fin-ops/current`。

### PostgreSQL phase04 pre-backup

- dump path：`/data/backups/fin_ops/postgres_phase04_20260520081506/fin_ops_pre_phase04_20260520081506.dump`
- dump sha256：`1700535833a79072094cea257f09a005be1723aa1b8b2c4b2a91ca68e165cecb`

### 实现产物

- `backend/src/fin_ops_platform/tools/postgres_transform.py`
- `backend/src/fin_ops_platform/tools/transform_staging_to_postgres.py`
- `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`
- `tests/test_postgres_transform.py`
- `tests/test_reconcile_postgres_migration.py`

说明：本次实现采用一个集中 `postgres_transform.py` transformer 模块承接 core/workbench/ops_tax_etc/read_models 转换逻辑，而不是拆分为 `tools/transformers/*` 多文件；CLI 名称和阶段 04 执行入口保持不变。

### dry-run 结果

- blockers：`0`
- planned id mappings：`15993`
- planned core counts：
  - `app.import_batches=6`
  - `app.import_batch_rows=897`
  - `app.file_objects=445`
  - `app.import_files=31`
  - `app.invoices=391`
  - `app.bank_transactions=431`
- read/search reference：
  - `read_model.search_index_rows=822`
  - `read_model.workbench_candidate_matches=5274`
  - `read_model.workbench_snapshots=6`
  - `read_model.cost_statistics_read_models=34`
- 其他主要正式表：
  - `app.oa_attachment_invoice_cache=7066`
  - `job.background_jobs=114`
  - `app.no_oa_bank_batches=79`
  - `app.no_oa_bank_batch_events=91`
  - `app.workbench_pair_relations=142`

### 正式转换结果

- transform status：`transformed`
- `staging.id_mappings=15993`
- 幂等重跑后核心 counts 未增加：
  - `app.invoices=391`
  - `app.bank_transactions=431`
  - `app.import_batches=6`
  - `app.import_batch_rows=897`
  - `app.file_objects=445`
  - `app.import_files=31`
- `fin-ops.service` 转换前后均为 `active`，本阶段未重启服务、未改服务配置、未切换 app 读写路径。

### 对账报告

- remote JSON：`/data/exports/fin_ops/fin_ops_app_export_20260519235526_5a233544/stage04/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`
- remote Markdown：`/data/exports/fin_ops/fin_ops_app_export_20260519235526_5a233544/stage04/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.md`
- local JSON copy：`docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`
- local Markdown copy：`docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.md`
- reconciliation status：`pass`
- mismatches：`[]`
- id mapping checks：
  - `total_mappings=15993`
  - `current_export_mappings=15993`
  - `conflicting_mappings=0`
- core amount checks：
  - invoices：`count=391`，`amount_sum=2164926.230000`，`signed_amount_sum=2164926.230000`
  - bank transactions：`count=431`，`amount_sum=28428537.660000`，`signed_amount_sum=-338747.500000`，`inflow_sum=14044895.080000`，`outflow_sum=14383642.580000`
- GridFS manifest：
  - files：`445`
  - chunks：`709`
  - total bytes：`98716321`
  - sampled checksum：报告中 5 个样本均保留。

### 已解释 warnings

- `duplicate_optional_unique:app.invoices.data_fingerprint`：
  - 生产 Mongo 中存在若干发票记录共享同一辅助 `data_fingerprint`。
  - 阶段 02 PostgreSQL schema 对 `app.invoices.data_fingerprint` 建了可空唯一索引。
  - 为保留所有发票记录并满足唯一约束，本阶段仅将重复组中的可选 `data_fingerprint` 列置空；原始 fingerprint 仍保留在 `raw_payload.normalized_payload.data_fingerprint`。
  - 主迁移身份不依赖该字段，而依赖 deterministic UUID、`legacy_mongo_id` 和 `staging.id_mappings`。
- `missing_optional_fk:app.import_files.import_batch_id`：
  - 21 个 `file_import_files` 记录的 batch id 在 `app.import_batches` 中没有可证明映射。
  - `app.import_files.import_batch_id` 是可选 FK；本阶段置空该 FK，保留 `legacy`/raw payload，未丢弃文件导入记录。

### 阶段 04 Gate

状态：`PASS`

依据：

- PostgreSQL phase04 pre-backup 已完成并记录 sha256。
- staging count 与 manifest total 一致：`15494/15494`。
- 正式转换成功提交，并通过同 export 幂等重跑验证。
- `staging.id_mappings` 稳定且无冲突：`15993`。
- 核心对象数量一致：import batches、batch rows、file objects、import files、invoices、bank transactions 全部通过。
- 对账报告 `status=pass`，`mismatches=[]`。
- `fin-ops.service` 保持 `active`。
- 本阶段未连接 OA Mongo，未写 app Mongo，未修改生产服务配置。
