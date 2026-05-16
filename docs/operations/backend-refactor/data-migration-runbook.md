# App Mongo 到 PostgreSQL 数据迁移 Runbook

本文记录后端重构迁移工具的执行方式和约束。当前版本覆盖 app Mongo 规范化导出、PostgreSQL staging 导入、dry-run 门禁报告和后续正式迁移前的对账要求；GridFS 文件内容迁移和 MinIO/S3 抽样下载校验在 06D 阶段继续补充。

## 总边界

- 只处理 app Mongo 数据库，例如 `fin_ops_platform_app`。
- 不访问、不备份、不导出、不查询、不修改、不压测 OA 源数据库。
- 不执行 PostgreSQL 正式数据迁移。
- 不执行生产切流。
- 不把 Mongo URI、密码、token、S3 secret、NATS credential 写入 git、manifest、日志或报告。
- 导出工具只读取 app Mongo detailed collections 和 GridFS 元数据，不下载 GridFS 文件内容，不删除 GridFS 文件。

## 前置条件

执行导出前必须确认：

1. 已读取 `docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md`。
2. app Mongo 备份和恢复演练已通过。
3. 使用的 `app_mongo_config.json` 或环境变量指向 app Mongo，不是 OA 源库。
4. 输出目录位于受控工作目录或迁移专用目录，不放在仓库根目录散落文件。
5. 执行终端不会记录真实连接串；不要把完整 URI 作为命令参数粘贴进 shell history。

## 导出工具

代码入口：

```text
backend/src/fin_ops_platform/services/app_mongo_exporter.py
scripts/tools/export_app_mongo.py
```

工具复用 `ApplicationStateStore` 的 app Mongo detailed collection 读取和 binary payload 反序列化逻辑，避免手写 pickle/binary 解析。导出范围：

```text
manifest.json
collections/import_batches.ndjson
collections/bank_transactions.ndjson
collections/invoices.ndjson
collections/file_objects.ndjson
collections/workbench_overrides.ndjson
collections/workbench_pair_relations.ndjson
collections/workbench_candidate_matches.ndjson
collections/background_jobs.ndjson
collections/gridfs-files-manifest.ndjson
```

### Dry-run

Dry-run 只读取 app Mongo 并输出记录数量摘要，不创建输出目录，不写 NDJSON。

```bash
PYTHONPATH=backend/src:. python3 scripts/tools/export_app_mongo.py \
  --data-dir /path/to/runtime-dir \
  --output-dir /path/to/exports/20260516-app-mongo \
  --dry-run
```

`--data-dir` 应包含 app 状态目录和 `app_mongo_config.json`。如果使用环境变量配置 app Mongo，仍要确保它们只指向 app Mongo。

### Validate-only

Validate-only 只读取 app Mongo、在内存中生成 manifest 和 validation 结果，不创建输出目录、不写 NDJSON。若发现阻断错误，例如重复 legacy id 或无法 JSON 序列化的 BSON/二进制 payload，命令返回非 0：

```bash
PYTHONPATH=backend/src:. python3 scripts/tools/export_app_mongo.py \
  --data-dir /path/to/runtime-dir \
  --output-dir /path/to/exports/20260516-app-mongo \
  --validate-only
```

### 正式导出到文件

```bash
PYTHONPATH=backend/src:. python3 scripts/tools/export_app_mongo.py \
  --data-dir /path/to/runtime-dir \
  --output-dir /path/to/exports/20260516-app-mongo
```

执行成功后检查：

```bash
find /path/to/exports/20260516-app-mongo -maxdepth 2 -type f | sort
python3 -m json.tool /path/to/exports/20260516-app-mongo/manifest.json >/dev/null
```

## Manifest 约定

`manifest.json` 包含：

- `schema_version`，当前为 `finops.app_mongo_export_manifest.v1`。
- `tool_version` / `tool`，当前为 `app-mongo-export-v1`。
- `dry_run` / `validate_only` 标记。
- `export_started_at` / `export_finished_at`，并保留兼容字段 `started_at` / `finished_at`。
- app Mongo source 摘要：database、host、port、auth source、是否配置用户名/密码。
- `source_database`。
- `output.manifest_file` 和 `output.files`；`output.files` 的值是相对 export 目录的 `collections/*.ndjson` 路径。
- `collection_counts`，记录 app Mongo detailed collections 以及 GridFS `.files` / `.chunks` 的源端数量。
- `record_counts`，记录各导出 dataset 的 NDJSON 行数。
- `checksums`，按相对文件路径记录各 NDJSON 内容 SHA-256。
- `hashes.files` 和 `hashes.aggregate_sha256`，供 06B/06C 做输入完整性校验。
- `validation.warnings` / `validation.errors`，记录空 collection、空/缺失 GridFS、重复 legacy id、非法 BSON/JSON 等问题。

Manifest 不包含：

- 完整 Mongo URI。
- 明文 username/password。
- token、私钥、S3/NATS secret。
- GridFS 文件二进制内容。

## 记录口径

每条 NDJSON 记录使用统一外层结构：

```json
{"legacy_collection":"import_batches","legacy_id":"batch-1","payload":{}}
```

说明：

- `legacy_collection` 是 app Mongo 中的来源集合或逻辑集合。
- `legacy_id` 用于后续 staging 导入和差异定位。
- `payload` 是通过 `ApplicationStateStore` 规范化后的 JSON 兼容数据。
- `collections/gridfs-files-manifest.ndjson` 只记录 GridFS 文件元数据、chunk 数和 metadata，不读取文件内容 checksum。文件内容 checksum 在 `06d-gridfs-minio-migration.md` 阶段完成。

## 验收检查

导出完成后至少检查：

1. `manifest.json` 可解析。
2. `manifest.record_counts` 与实际 NDJSON 行数一致。
3. `manifest.checksums` 与 NDJSON 文件内容一致。
4. `manifest.hashes.aggregate_sha256` 可由 `manifest.hashes.files` 稳定重算。
5. `manifest.validation.errors` 为空；warnings 必须逐条复核。
6. `manifest` 和 NDJSON 中不包含真实密码、token 或完整连接串。
7. `collections/gridfs-files-manifest.ndjson` 中的文件数量与 app Mongo GridFS `.files` 集合数量一致。
8. dry-run / validate-only 不创建输出目录或导出文件。

06B/06C 消费字段：

| 字段 | 用途 |
| --- | --- |
| `schema_version` | 判断 manifest 契约版本。 |
| `source_database` / `source.database` | 证明 source 是 app Mongo 数据库，不是 OA 源库。 |
| `output.files` | 定位每个 dataset 的 `collections/*.ndjson` 文件。 |
| `collection_counts` | 记录 Mongo 源 collection count baseline。 |
| `record_counts` | 校验 NDJSON 行数和 staging rows 数量。 |
| `checksums` / `hashes.files` | 校验每个输出文件内容。 |
| `hashes.aggregate_sha256` | 校验整批导出输入是否被替换。 |
| `validation.errors` | 任一阻断错误必须停止 06B/06C。 |

## 禁止事项

- 不要用该工具连接 OA 源 Mongo。
- 不要用该工具替代 `mongodump` 备份。
- 不要把导出结果声明为 PostgreSQL 迁移完成。
- 不要直接把 NDJSON 导入 PostgreSQL 正式 `app` schema；下一步必须先进 `staging` 并生成对账报告。
- 不要删除 app Mongo、GridFS 或已有备份。

## 下一步

完成本导出工具后，继续执行：

1. `docs/exec-plans/active/backend-refactor-prompts/06b-postgres-import-validation-tooling.md`
2. `docs/exec-plans/active/backend-refactor-prompts/06c-data-migration-dry-run.md`
3. `docs/exec-plans/active/backend-refactor-prompts/06d-gridfs-minio-migration.md`

## PostgreSQL Staging 导入工具

代码入口：

```text
backend/src/fin_ops_platform/services/app_mongo_staging_importer.py
scripts/tools/import_app_mongo_staging.py
```

该工具读取 06A 产出的 `manifest.json` 和 NDJSON，生成：

- `staging.mongo_export_manifest` 插入记录。
- `staging.mongo_import_rows` 插入记录。
- validation report。
- 可选 staging import plan JSON。

导入隔离规则：

- 每次执行必须使用一个 `migration_run_id`。
- `migration_run_id` 同时作为 `staging.mongo_export_manifest.id` 和 `staging.mongo_import_rows.manifest_id`。
- 重跑同一 `migration_run_id` 时，工具只允许清理同一 `manifest_id` 下的 staging rows 和 manifest 记录。
- 工具不得写 `app`、`read_model`、`job`、`audit` 正式事实表；正式转换必须单独执行 dry-run 设计和门禁。

### 生成 plan 和 report

默认模式不连接 PostgreSQL，只做本地校验、plan 和 report 生成：

```bash
PYTHONPATH=backend/src:. python3 scripts/tools/import_app_mongo_staging.py \
  --export-dir /path/to/exports/20260516-app-mongo \
  --migration-run-id 00000000-0000-4000-8000-000000000001 \
  --plan-path /path/to/reports/staging-import-plan.json \
  --report-path /path/to/reports/staging-validation-report.json
```

如果 report 存在 blocking findings，命令返回非 0，并保留 findings。不要跳过失败记录继续导入。

### 写入 PostgreSQL staging

只有在明确使用受控临时库或 staging 环境时才允许执行：

```bash
export FIN_OPS_POSTGRES_MIGRATION_URL='postgres://USER:***@127.0.0.1:5432/fin_ops_staging'

PYTHONPATH=backend/src:. python3 scripts/tools/import_app_mongo_staging.py \
  --export-dir /path/to/exports/20260516-app-mongo \
  --migration-run-id 00000000-0000-4000-8000-000000000001 \
  --report-path /path/to/reports/staging-validation-report.json \
  --execute
```

约束：

- PostgreSQL URL 只能通过环境变量读取，不写入命令行、manifest、report 或日志。
- `--execute` 仅写 `staging.mongo_export_manifest` 和 `staging.mongo_import_rows`。
- 若 validation report 有 blocking findings，工具拒绝写 staging。
- 当前 Python requirements 不强制安装 PostgreSQL driver；`--execute` 需要运行环境提供 `psycopg`。

## Staging 对账

工具当前生成的 report 覆盖以下维度：

| 维度 | 来源 | 阻断规则 |
| --- | --- | --- |
| 数量 | `manifest.record_counts` vs NDJSON 实际行数 | 任一对象类型不一致即失败。 |
| manifest checksum | `manifest.checksums` vs NDJSON 文件内容 | 任一文件不一致即失败。 |
| 金额 | `amount`、`signed_amount`、`tax_amount`、`total_with_tax` | expected/actual 不一致即失败。 |
| 月份 | 银行流水 `txn_date`、发票 `invoice_date` 等 | expected/actual 分布不一致即失败。 |
| 状态 | payload `status` | expected/actual 分布不一致即失败。 |
| 文件 checksum 抽样 | `gridfs-files-manifest.ndjson` 中的 `sha256`/`sample_sha256` | 抽样值不一致即失败。 |
| 解析失败 | NDJSON 解析和金额 decimal 解析 | 必须保留 row_no 和 object_type，失败即阻断。 |

报告模板见：

```text
docs/operations/backend-refactor/migration-validation-report-template.md
```

## Staging 到事实表转换草案

转换设计见：

```text
docs/operations/backend-refactor/staging-to-facts-conversion-design.md
```

关键门禁：

- staging import report 必须无 blocking findings。
- `staging.mongo_import_rows` 中每个需要迁移的 legacy id 都必须生成 `staging.legacy_id_map`。
- 每个批次转换后必须执行 count/hash/amount/month/status/file checksum 对账。
- 没有 dry-run 对账报告，不允许生产数据迁移。

## 数据迁移 Dry-run

06C dry-run 只允许在备份恢复演练、SQL migration 验证、06A 导出工具和 06B staging 导入工具都具备后执行。dry-run 目标是生成可审计报告，不授权生产切流，不冻结 app Mongo，不把演练结果当作正式事实源。

代码入口：

```text
backend/src/fin_ops_platform/services/app_mongo_migration_dry_run.py
scripts/tools/dry_run_app_mongo_migration.py
```

当前 dry-run 阻断报告见：

```text
docs/operations/backend-refactor/migration-dry-run-report-20260516.md
```

该报告的结论为 `NO_GO`：当前工作区没有可审计的 06A manifest/NDJSON 导出产物、06B staging import 执行报告、staging -> facts 转换结果和实际对账数据。缺少 dry-run 对账报告时，不允许进入正式迁移门禁。

### 环境确认

执行 dry-run 前必须确认：

1. source 只能是 app Mongo 备份恢复测试库、备份恢复出的临时库，或明确只读的 app Mongo；不得访问 OA 源数据库。
2. PostgreSQL 目标只能是 staging/临时 dry-run 库，或同一库内由 `migration_run_id`/`manifest_id` 隔离的 staging 范围。
3. PostgreSQL 不开放公网；连接 secret 只通过受控环境变量或 secret manager 注入，不写入命令行、报告或 git。
4. dry-run 不写生产 API 当前读写路径，不切读，不切写，不冻结 app Mongo。
5. report 输出目录位于迁移专用目录或 `docs/operations/backend-refactor/` 的审计文档位置，不在仓库根目录散放临时文件。

### 分区准备

导入历史数据前，先从 06A manifest 和 NDJSON 日期字段推导月份范围，再准备历史分区。分区准备必须可重复执行。

需要覆盖的分区父表：

| 父表 | 分区函数或准备方式 | 月份来源 |
| --- | --- | --- |
| `app.bank_transactions` | `app.create_financial_fact_month_partition('app.bank_transactions'::regclass, month)` | `bank_transactions.txn_date` |
| `app.invoices` | `app.create_financial_fact_month_partition('app.invoices'::regclass, month)` | `invoices.invoice_date` |
| `app.oa_applications` | `app.create_oa_applications_month_partition(month)` | OA 归一化后的 `source_updated_month` 或 `approved_month`，06C 不访问 OA 源库补数 |
| `read_model.workbench_rows` | `read_model.create_workbench_rows_partition(month)` | workbench row `scope_month` |
| `read_model.search_index_rows` | `read_model.create_search_index_rows_partition(month)` | search index `scope_month` |

分区准备记录至少包含：

```json
{
  "migration_run_id": "uuid",
  "source_manifest": "/path/to/export/manifest.json",
  "month_range": {
    "min": "YYYY-MM",
    "max": "YYYY-MM"
  },
  "prepared_partitions": [
    {
      "schema": "app",
      "parent_table": "bank_transactions",
      "month": "YYYY-MM",
      "status": "created_or_already_exists"
    }
  ]
}
```

没有 manifest 月份范围时，不要猜测分区；报告必须标记 `PARTITION_PLAN_MISSING` 并阻断。

### 可重复执行顺序

1. 运行 06A 导出工具生成 export 目录。
2. 校验 `manifest.json` 可解析、record count 与 NDJSON 行数一致、manifest checksum 与文件内容一致。
3. 按 manifest 日期范围准备历史分区，并保存分区准备记录。
4. 运行 06B staging 导入工具，使用新的 `migration_run_id`。
5. 如果 validation report 有 blocking findings，停止，不执行 staging -> facts 转换。
6. 在隔离 dry-run 库或明确隔离的 `migration_run_id` 范围内执行 staging -> app/read_model/job/audit 转换演练。
7. 生成 migration dry-run report，覆盖 count/hash/amount/month/status/file checksum 和 legacy id 覆盖率。
8. 只有报告无未解释差异时，才允许进入正式迁移门禁评审。

### 生成 dry-run 报告

默认模式只读取 06A export 目录并在内存中构造 staging plan、target row plan、分区计划和 `staging.legacy_id_map` 计划，不连接 PostgreSQL、不写数据库：

```bash
PYTHONPATH=backend/src:. python3 scripts/tools/dry_run_app_mongo_migration.py \
  --export-dir /path/to/exports/20260516-app-mongo \
  --migration-run-id 00000000-0000-4000-8000-000000000001 \
  --report-json-path /path/to/reports/migration-dry-run-report.json \
  --report-md-path /path/to/reports/migration-dry-run-report.md
```

只有显式 `--execute` 时才允许连接 `FIN_OPS_POSTGRES_MIGRATION_URL` 指向的隔离 dry-run PostgreSQL，并执行分区准备和 `staging.legacy_id_map` upsert。该模式仍不授权生产切流：

```bash
export FIN_OPS_POSTGRES_MIGRATION_URL='postgres://USER:***@127.0.0.1:5432/fin_ops_dry_run'

PYTHONPATH=backend/src:. python3 scripts/tools/dry_run_app_mongo_migration.py \
  --export-dir /path/to/exports/20260516-app-mongo \
  --migration-run-id 00000000-0000-4000-8000-000000000001 \
  --report-json-path /path/to/reports/migration-dry-run-report.json \
  --report-md-path /path/to/reports/migration-dry-run-report.md \
  --execute
```

报告模板见：

```text
docs/operations/backend-refactor/migration-dry-run-report-template.md
```

### Dry-run 报告门禁

报告必须包含：

| 维度 | 必填内容 | 阻断规则 |
| --- | --- | --- |
| 数量 | source collection/NDJSON count、staging count、target dry-run count | 任一差异未解释即失败。 |
| hash | manifest checksum、NDJSON payload hash、target 聚合 hash | 任一 hash 差异未解释即失败。 |
| 金额 | 银行流水 inflow/outflow、发票 output/input、税额、价税合计 | 任一金额差异即失败。 |
| 月份 | 银行流水、发票、OA 归一化、workbench/search 分布 | 任一月份分布差异未解释即失败。 |
| 状态 | import、bank、invoice、workbench、job 状态分布 | 未识别状态或分布差异未解释即失败。 |
| 文件 | GridFS metadata 数量、字节数、manifest checksum、06D 文件内容抽样状态 | checksum 抽样失败即失败；06D 未完成时不得宣称文件内容 checksum 通过。 |
| legacy id | 每个迁移对象的 `legacy_collection`、`legacy_id` 到 target id 覆盖率 | 需要迁移对象缺少映射即失败。 |

报告必须能定位差异到至少一个维度：对象类型、月份、状态、legacy id、row_no 或文件 id。

## GridFS 到 MinIO/S3 文件迁移

06D 文件迁移只处理 app Mongo 的 GridFS bucket：

```text
import_file_blobs
```

不处理 OA 源数据库，不删除 GridFS 原文件，不在命令行、manifest、日志或 git 中写 MinIO/S3 access key、secret key、session token。文件内容 checksum 属于本阶段真实校验项；没有 checksum 校验不得标记成功。

代码入口：

```text
backend/src/fin_ops_platform/services/app_gridfs_migration.py
scripts/tools/migrate_gridfs_minio.py
```

Manifest 格式说明见：

```text
docs/operations/backend-refactor/gridfs-minio-migration-manifest-format.md
```

### 文件分类

工具读取 app Mongo `import_file_blobs.files` 和 GridFS 内容，按 `metadata.purpose`、legacy id 和 metadata 分类：

| Purpose | 来源 |
| --- | --- |
| `import_source_file` | 导入原始文件，通常有 `metadata.session_id` 或 `import_file_` 前缀。 |
| `etc_reconciliation_source` | ETC 对账源文件，通常为 `etc_reconciliation:` 前缀或同名 purpose。 |
| `etc_invoice_attachment` | ETC 发票附件，通常为 `etc_invoice:` 前缀或同名 purpose。 |
| `historical_etc_repair_seed` | 历史 ETC 修复包，通常为 `historical_etc_repair:` 前缀。 |
| `oa_attachment_cache` | app Mongo 中的 OA 附件解析缓存文件；不代表访问 OA 源库。 |
| `other_gridfs_file` | 无法归入上述类别的 app GridFS 文件。 |

### Object Key 规范

对象 key 必须稳定、可追溯，并避免泄露业务敏感信息。当前工具格式：

```text
{environment}/app-gridfs/{purpose}/{yyyy}/{mm}/{legacy_gridfs_id_sha256_16}/{file_object_id}
```

规则：

- `file_object_id` 使用固定 namespace 对 `legacy_gridfs_id` 做 UUIDv5，重复运行保持稳定。
- `legacy_gridfs_id_sha256_16` 是 legacy id 的 SHA-256 前 16 位，用于排查和分散路径。
- object key 不包含原始文件名、往来单位、发票号、人员姓名或其他业务文本。
- `yyyy/mm` 来自 GridFS `uploadDate`；缺失或无法解析时使用 `unknown/unknown`，并在报告中保留原始 metadata。
- bucket 由执行参数传入，不把 endpoint、access key 或 secret 写入报告。

### Dry-run

默认不加 `--execute` 即为 dry-run。dry-run 会读取 app GridFS、计算源文件 SHA-256、生成 object key、生成 file object 映射和报告，但不会写 MinIO/S3。

```bash
PYTHONPATH=backend/src:. python3 scripts/tools/migrate_gridfs_minio.py \
  --data-dir /path/to/runtime-dir \
  --bucket fin-ops-files \
  --environment staging-dryrun \
  --output-dir /path/to/reports/gridfs-20260516
```

输出文件：

```text
gridfs-minio-migration-manifest.json
gridfs-object-mapping.ndjson
file-objects-import.ndjson
gridfs-migration-failures.ndjson
```

### 执行上传

只有在受控迁移环境中才允许加 `--execute`。执行环境必须自行提供对象存储凭据，例如通过标准 AWS/MinIO 环境变量或 secret manager 注入；不要把真实 secret 写入命令或仓库。当前 CLI 使用可选 `boto3` 适配器，部署环境需要提供该依赖。

```bash
PYTHONPATH=backend/src:. python3 scripts/tools/migrate_gridfs_minio.py \
  --data-dir /path/to/runtime-dir \
  --bucket fin-ops-files \
  --environment staging \
  --output-dir /path/to/reports/gridfs-20260516 \
  --sample-size 50 \
  --max-workers 4 \
  --execute
```

约束：

- 目标对象已存在且 metadata `sha256` 与源文件一致时，记录为 `skipped_existing`，不重复上传。
- 目标对象缺失或 checksum 不一致时，重新上传并记录 etag/version。
- 上传后按 `--sample-size` 对 `uploaded` 和 `skipped_existing` 对象做下载抽样，重新计算 SHA-256。
- 任一抽样 checksum 失败，报告必须 `status=failed`、`blocking=true`，命令返回非 0。
- 工具不删除 GridFS 原文件，也不写 PostgreSQL；`file-objects-import.ndjson` 是后续受控导入 `app.file_objects` 的输入草案。

### PostgreSQL 元数据映射

`file-objects-import.ndjson` 对应 `app.file_objects` 字段：

| 字段 | 来源 |
| --- | --- |
| `id` | 稳定 UUIDv5 file object id。 |
| `storage_provider` | `minio` 或 `s3`。 |
| `bucket` | CLI 参数。 |
| `object_key` | 稳定 object key。 |
| `object_version` | S3/MinIO version id；未启用版本化时为 null。 |
| `file_name` | GridFS 原始 filename，只保存在元数据，不进入 object key。 |
| `content_type` | GridFS `contentType` 或 metadata `content_type`。 |
| `byte_size` | 实际读取字节数。 |
| `sha256` | 上传前对 GridFS 内容计算。 |
| `etag` | 对象存储返回值。 |
| `legacy_gridfs_id` | 旧 GridFS id。 |
| `purpose` | 文件分类。 |

`gridfs-object-mapping.ndjson` 提供 `legacy_gridfs_id -> file_object_id` 映射，供后续 staging -> facts 转换和 `staging.legacy_id_map` 使用。
