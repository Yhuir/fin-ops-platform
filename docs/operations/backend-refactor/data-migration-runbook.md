# App Mongo 到 PostgreSQL 数据迁移 Runbook

本文记录后端重构迁移工具的执行方式和约束。当前 06B 只覆盖 06A manifest/NDJSON 到 PostgreSQL `staging` 的导入校验，不执行 staging -> facts 转换，不写正式 `app`、`read_model`、`job`、`audit` 事实表，不切换 API。

## 总边界

- 只处理 06A app Mongo 导出目录。
- 不访问、不备份、不导出、不查询、不修改 OA 源数据库。
- PostgreSQL 连接串只能从环境变量读取。
- 不把 Mongo URI、PostgreSQL URI、密码、token、S3 secret、NATS credential 写入 git、manifest、日志或报告。
- 06B 只允许写 `staging.mongo_export_manifest` 和 `staging.mongo_import_rows`。
- `staging.legacy_id_map` 需要 facts target id，由 06C staging -> facts dry-run 生成；06B 只输出 `legacy_id_map_draft`，不写该表。

## 06A 输入契约

输入目录必须包含 `manifest.json`。manifest 至少包含：

```json
{
  "source": {
    "database": "fin_ops_platform_app"
  },
  "output": {
    "files": {
      "bank_transactions": "collections/bank_transactions.ndjson"
    }
  },
  "record_counts": {
    "bank_transactions": 1
  },
  "checksums": {
    "collections/bank_transactions.ndjson": "sha256"
  }
}
```

每条 NDJSON 记录使用 06A envelope：

```json
{"legacy_collection":"bank_transactions","legacy_id":"txn-1","payload":{}}
```

## 06B Staging 导入工具

代码入口：

```text
backend/src/fin_ops_platform/services/app_mongo_staging_importer.py
scripts/tools/import_app_mongo_staging.py
```

每次执行生成或接收一个 UUID `migration_run_id`，同时作为：

- `staging.mongo_export_manifest.id`
- `staging.mongo_import_rows.manifest_id`
- 06C `staging.legacy_id_map.migration_run_id`

### Validate-only / Dry-run

默认模式不连接 PostgreSQL，只验证 manifest、读取 NDJSON、生成 staging plan 和 validation report：

```bash
PYTHONPATH=backend/src:. python3 scripts/tools/import_app_mongo_staging.py \
  --export-dir /path/to/exports/20260516-app-mongo \
  --validate-only \
  --plan-path /path/to/reports/staging-import-plan.json \
  --report-path /path/to/reports/staging-validation-report.json
```

`--dry-run` 与 `--validate-only` 等价。任一 blocking finding 会返回非 0，并保留 report 和 plan。

### 写入 PostgreSQL Staging

只有在受控临时库或 staging 环境中才允许执行：

```bash
export FIN_OPS_POSTGRES_MIGRATION_URL='<controlled-postgres-migration-url>'

PYTHONPATH=backend/src:. python3 scripts/tools/import_app_mongo_staging.py \
  --export-dir /path/to/exports/20260516-app-mongo \
  --migration-run-id 00000000-0000-4000-8000-000000000001 \
  --report-path /path/to/reports/staging-validation-report.json \
  --execute
```

执行规则：

1. 若 validation report 有 blocking findings，拒绝写 staging。
2. 重跑同一 `migration_run_id` 时，只清理同一 `manifest_id` 下的 `staging.mongo_import_rows` 和 `staging.mongo_export_manifest`。
3. 不写 `staging.legacy_id_map`；06B plan 中的 `legacy_id_map_draft` 仅供 06C 读取。
4. CLI stdout 只输出计数、状态和 UUID，不输出数据库 URL 或 secret。

## Staging Row 保留字段

`staging.mongo_import_rows` 中每行保留：

| 语义 | 存储位置 |
| --- | --- |
| collection | `legacy_collection` |
| legacy id | `legacy_id` |
| row hash | `payload_hash` |
| raw payload | `payload` |
| source file | `payload._staging_import.source_file` |
| source line | `row_no` 和 `payload._staging_import.source_line` |
| import status | `status` |
| error code | `error_code` |
| error summary | `error_message` |

坏 JSON 行不得吞掉。工具会生成 failed staging row：

```json
{
  "legacy_id": "__failed__:collections/bank_transactions.ndjson:2",
  "payload": {
    "raw_line": "{bad json",
    "_staging_import": {
      "source_file": "collections/bank_transactions.ndjson",
      "source_line": 2,
      "import_status": "failed",
      "error_code": "NDJSON_PARSE_ERROR",
      "error_summary": "..."
    }
  },
  "status": "failed"
}
```

## Validation Report 门禁

Report 必须包含：

- `migration_run_id`
- `started_at`
- `finished_at`
- `expected_collection_counts`
- `actual_imported_counts`
- `failed_row_counts`
- `input_file_hash_validation`
- `findings`
- `decision.go_no_go`

阻断规则：

| 维度 | 来源 | 阻断条件 |
| --- | --- | --- |
| 数量 | `manifest.record_counts` vs NDJSON 物理行数 | 任一对象类型不一致。 |
| 导入行 | parsed + failed staging rows vs NDJSON 物理行数 | 任一源行未被 staging plan 覆盖。 |
| 文件 hash | `manifest.checksums` vs 实际 NDJSON sha256 | 缺失或不一致。 |
| 坏行 | NDJSON parse/type validation | 任何 failed row 都是 `NO_GO`。 |
| 重复 legacy id | `(legacy_collection, legacy_id)` | 后续重复行标记 failed，report `NO_GO`。 |
| 文件抽样 checksum | `gridfs-files-manifest` payload | expected/actual 不一致。 |

报告模板见：

```text
docs/operations/backend-refactor/migration-validation-report-template.md
```

## 与 06C 的接口

06C staging -> facts dry-run 必须消费：

- `migration_run_id`
- `manifest_id`
- `staging.mongo_import_rows.legacy_collection`
- `staging.mongo_import_rows.legacy_id`
- `staging.mongo_import_rows.row_no`
- `staging.mongo_import_rows.payload`
- `staging.mongo_import_rows.payload_hash`
- `staging.mongo_import_rows.target_table`
- `staging.mongo_import_rows.status`
- `staging.mongo_import_rows.error_code`
- `staging.mongo_import_rows.error_message`
- validation report `decision.go_no_go`
- plan `legacy_id_map_draft`

若 validation report 为 `NO_GO`，06C 不得执行 staging -> facts 转换。

## 06C Dataset -> PostgreSQL 合同

06C 的职责是冻结 app Mongo dataset 到 PostgreSQL target 的生产级迁移合同，并生成 facts plan、`staging.legacy_id_map` plan 和对账报告。06C 不访问 OA 源数据库，不写 `app`、`read_model`、`job`、`audit` 正式事实表；`--execute` 只允许在隔离 dry-run/staging 库内准备分区和写入 `staging.legacy_id_map`。

### blocker dataset 合同

| app Mongo dataset | 迁移命运 | primary target | supporting/audit target | 说明 |
| --- | --- | --- | --- | --- |
| `background_jobs` | 迁入 job facts | `job.worker_tasks` | `job.worker_task_acknowledgements`, `audit.events`, `staging.legacy_id_map` | legacy `acknowledged` 是用户已确认的展示状态，不是 worker 执行状态；目标 worker task 使用可执行状态，确认痕迹保留在 migration metadata/raw payload，并可投影到 acknowledgement 表。legacy `superseded` 表示旧任务被新任务替代，目标 worker task 归一为 `cancelled`，替代关系保留在 raw payload。 |
| `workbench_candidate_matches` | 迁入 read model | `read_model.workbench_candidate_matches` | `audit.events`, `staging.legacy_id_map` | 目标表 status 只表达 read-model 生命周期：`active/superseded/dismissed`。legacy 候选业务细分状态保留在 raw payload/migration metadata。 |
| `workbench_pair_relations` | 迁入 reconciliation facts | `app.reconciliation_cases`, `app.reconciliation_case_rows` | `audit.events`, `staging.legacy_id_map` | legacy `active` 是有效配对关系，目标 case status 归一为 `confirmed`；legacy `cancelled` 继续映射为 `cancelled`。 |
| `etc_state` | 归档 raw payload | `audit.events` | `staging.legacy_id_map` | 这是旧 ETC aggregate state，单行内包含批次、发票和导入状态。06C 不拆嵌套结构；整包归档为审计事件 raw payload。canonical ETC invoice/import/file facts 由 `invoices`、`import_batches`、`file_objects`、GridFS/06D 证据覆盖。 |
| `etc_reconciliation_state` | 归档 raw payload | `audit.events` | `staging.legacy_id_map` | 这是旧 ETC reconciliation aggregate state，单行内包含 task/file/item/audit event。06C 整包归档为审计事件 raw payload；如需写入 `app.etc_reconciliation_*` 结构化表，必须后续基于 raw archive 做专门 fan-out 迁移并重新出具 dry-run 报告。 |

空集合在 `record_counts` 中允许表现为 `0` 或 absent key；两者等价。非空集合缺失、金额/月分布/status 分布、row hash 或 legacy id map 任一不一致仍必须阻断。

### legacy status normalization

06C 不把未知 legacy status 直接加入 PostgreSQL enum。每个可接受的 legacy status 必须有显式 normalized target status；目标 payload 必须保留：

- `raw_payload.status`：原始 legacy status。
- `migration_metadata.legacy_status`：原始 status。
- `migration_metadata.normalized_status`：目标 schema status。
- `migration_metadata.status_mapping_applied=true`：标记发生过归一化。

当前合同：

| dataset | legacy status | normalized target status | 保留/追溯 |
| --- | --- | --- | --- |
| `background_jobs` | `acknowledged` | `succeeded` | raw payload + migration metadata；确认语义可投影到 `job.worker_task_acknowledgements`。 |
| `background_jobs` | `superseded` | `cancelled` | raw payload + migration metadata；`superseded_by_job_id` 保留在 raw payload。 |
| `background_jobs` | `partial_success` | `succeeded` | raw payload + migration metadata；部分成功明细保留在 `result_summary`/raw payload。 |
| `workbench_candidate_matches` | `needs_review` | `active` | raw payload + migration metadata；业务细分状态由 read model detail/raw payload 承载。 |
| `workbench_candidate_matches` | `suppressed` | `dismissed` | raw payload + migration metadata；抑制原因保留在 raw payload。 |
| `workbench_candidate_matches` | `incomplete` | `active` | raw payload + migration metadata。 |
| `workbench_candidate_matches` | `auto_closed` | `active` | raw payload + migration metadata；自动闭环标签和规则证据保留在 raw payload。 |
| `workbench_candidate_matches` | `conflict` | `active` | raw payload + migration metadata；冲突候选 keys 保留在 raw payload。 |
| `workbench_pair_relations` | `active` | `confirmed` | raw payload + migration metadata；有效配对关系成为 confirmed reconciliation case。 |

如果 source 出现未列入合同且不属于目标 enum 的 status，06C 必须输出 `INVALID_ENUM` 并保持 `NO_GO`。如果 source 出现无 mapping 的 dataset，06C 必须输出 `MAPPING_BLOCKER` 和 `UNMAPPED_LEGACY_ID`，不得通过 exclusion 或跳过行提升 `legacy_id_coverage`。

## 06D GridFS -> MinIO/S3 文件迁移

06D 只处理 app Mongo GridFS bucket `import_file_blobs`，不访问 OA 源数据库，不删除 GridFS 原文件，不切换 API。文件内容迁移到 MinIO/S3；PostgreSQL 只保存 `app.file_objects`、`app.import_files` metadata 计划和 `legacy_gridfs_id -> file_object_id` 映射。除非在受控 staging/dry-run 库并获得明确授权，06D 不写 `app`、`read_model`、`job`、`audit` 正式事实表。

### 输入和环境

优先使用 06A export 目录里的 `collections/gridfs-files-manifest.ndjson` 做 metadata 盘点；若要计算源文件 SHA-256、上传或 verify，必须连接 app Mongo/GridFS 并读取文件 bytes。

连接和 secret 只能来自环境变量；报告只记录 env var 是否 present，不记录真实值：

| 类别 | 变量 |
| --- | --- |
| app GridFS | `APP_MONGO_URI`、`STAGING_APP_MONGO_URI`，或 `FIN_OPS_APP_MONGO_HOST` + `FIN_OPS_APP_MONGO_DATABASE` |
| MinIO/S3 endpoint | `FIN_OPS_S3_ENDPOINT_URL`、`S3_ENDPOINT`、`AWS_ENDPOINT_URL_S3` |
| MinIO/S3 bucket | `FIN_OPS_S3_BUCKET`、`S3_BUCKET`，或受控 CLI `--bucket` |
| MinIO/S3 auth | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`，或 `MINIO_ACCESS_KEY` + `MINIO_SECRET_KEY`，或 `S3_ACCESS_KEY_ID` + `S3_SECRET_ACCESS_KEY` |
| PostgreSQL metadata import | `FIN_OPS_POSTGRES_MIGRATION_URL`，或受控 staging `DATABASE_URL` |

若 app GridFS、MinIO/S3 或 PostgreSQL migration 环境缺失，06D 必须生成 `NO_GO` 报告并列出缺口；不得伪造 GO。

### Metadata-only dry-run

metadata-only dry-run 不写对象存储、不写 PostgreSQL，只读取 06A manifest，生成可审计 `NO_GO` 报告：

```bash
PYTHONPATH=backend/src python3 scripts/tools/migrate_gridfs_minio.py \
  --export-dir /tmp/finops-app-mongo-export-06a-20260517 \
  --migration-run-id a4227942-8eff-4876-8648-be1fbd821f43 \
  --dry-run \
  --report-json-path docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.json \
  --report-md-path docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.md
```

该模式可以盘点文件数量、metadata 字节数、content type、domain 分类、稳定 `object_key`、`file_object_id` 和 `import_file_id` 草案；但不能证明文件内容 checksum，因此 `readiness_gates.file_checksum.decision` 必须是 `NO_GO`。

### Live dry-run / upload / verify

有 app GridFS 环境时，live dry-run 会读取每个 GridFS 文件并计算源 SHA-256，但仍不写对象存储和 PostgreSQL：

```bash
PYTHONPATH=backend/src python3 scripts/tools/migrate_gridfs_minio.py \
  --data-dir "$FIN_OPS_DATA_DIR" \
  --bucket "$FIN_OPS_S3_BUCKET" \
  --environment staging \
  --mode dry-run \
  --output-dir /tmp/finops-gridfs-minio-06d-dry-run
```

受控 staging 上传：

```bash
PYTHONPATH=backend/src python3 scripts/tools/migrate_gridfs_minio.py \
  --data-dir "$FIN_OPS_DATA_DIR" \
  --bucket "$FIN_OPS_S3_BUCKET" \
  --environment staging \
  --mode upload \
  --sample-size 20 \
  --max-workers 4 \
  --max-retries 3 \
  --output-dir /tmp/finops-gridfs-minio-06d-upload
```

verify 模式不上传，只检查目标对象存在、metadata sha256 一致，并抽样下载重新计算 SHA-256：

```bash
PYTHONPATH=backend/src python3 scripts/tools/migrate_gridfs_minio.py \
  --data-dir "$FIN_OPS_DATA_DIR" \
  --bucket "$FIN_OPS_S3_BUCKET" \
  --environment staging \
  --mode verify \
  --sample-size 20 \
  --output-dir /tmp/finops-gridfs-minio-06d-verify
```

### 输出和门禁

live 模式在 `--output-dir` 下生成：

| 文件 | 用途 |
| --- | --- |
| `gridfs-minio-migration-manifest.json` | 每个 GridFS 文件的源、目标、checksum、状态和错误摘要。 |
| `gridfs-object-mapping.ndjson` | `legacy_gridfs_id -> file_object_id/import_file_id` 和 object storage 位置。 |
| `file-objects-import.ndjson` | 可导入 `app.file_objects` 的 metadata 草案。 |
| `legacy-id-map-import.ndjson` | 可导入 `staging.legacy_id_map` 的 `app.file_objects` / `app.import_files` 映射草案。 |
| `gridfs-migration-failures.ndjson` | 失败或阻断文件清单。 |
| `gridfs-checksum-validation-report.json` | `file_checksum` readiness gate 证据。 |

阻断规则：

| 维度 | 阻断条件 |
| --- | --- |
| 源文件 | GridFS metadata 有记录但 bytes 读取失败。 |
| length | `.files.length` 与实际读取 bytes 不一致，或 manifest 缺 length。 |
| chunk | manifest 缺 chunk count；live 盘点发现 chunk 不一致。 |
| 重复 id | `legacy_gridfs_id` 重复。 |
| 上传 | head/upload/download 任一失败。 |
| checksum | 源 SHA-256 缺失、目标 metadata sha256 不一致、抽样下载 SHA-256 不一致。 |
| PostgreSQL | 缺 `FIN_OPS_POSTGRES_MIGRATION_URL` 或未在受控 staging 执行 metadata import。 |

GO 条件：

- 非 dry-run 的 upload 或 verify 报告。
- 每个成功对象都有源 SHA-256。
- `sample_download_hash.mismatched=0`，且有源文件时至少有一个抽样下载样本。
- `missing_files.count=0`、`size_differences.count=0`。
- 每个成功文件都有稳定 `file_object_id`，并能通过 `legacy-id-map-import.ndjson` 追溯到 `app.file_objects` 和 `app.import_files`。
- 报告、manifest、NDJSON 均不得包含 access key、secret key、session token、presigned URL、完整 Mongo URI 或 PostgreSQL URI。
