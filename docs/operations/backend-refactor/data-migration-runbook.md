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
