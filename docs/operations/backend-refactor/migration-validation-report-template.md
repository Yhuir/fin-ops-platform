# Migration Validation Report Template

本文是 06B app Mongo -> PostgreSQL staging import 对账报告模板。报告不得包含真实密码、token、完整 URI、S3 secret 或 NATS credential。

## JSON Schema 摘要

```json
{
  "tool": "app-mongo-staging-import-v1",
  "phase": "staging_import",
  "status": "passed | failed",
  "blocking": false,
  "migration_run_id": "uuid",
  "manifest_id": "uuid",
  "started_at": "ISO-8601 timestamp",
  "finished_at": "ISO-8601 timestamp",
  "expected_collection_counts": {
    "bank_transactions": 0,
    "invoices": 0,
    "gridfs-files-manifest": 0
  },
  "actual_imported_counts": {
    "bank_transactions": 0,
    "invoices": 0,
    "gridfs-files-manifest": 0
  },
  "failed_row_counts": {
    "bank_transactions": 0
  },
  "input_file_hash_validation": {
    "collections/bank_transactions.ndjson": {
      "object_type": "bank_transactions",
      "expected_sha256": "sha256 from 06A manifest",
      "actual_sha256": "sha256 calculated during 06B",
      "matched": true
    }
  },
  "source_metrics": {
    "record_counts": {},
    "hashes": {}
  },
  "actual_metrics": {
    "record_counts": {},
    "amount_totals": {},
    "month_distribution": {},
    "status_distribution": {},
    "file_checksum_samples": []
  },
  "schema_notes": [
    {
      "code": "LEGACY_ID_MAP_DEFERRED_TO_06C",
      "message": "06B emits legacy_id_map_draft but does not write staging.legacy_id_map."
    }
  ],
  "findings": [
    {
      "severity": "error",
      "code": "COUNT_MISMATCH",
      "object_type": "bank_transactions",
      "source_file": "collections/bank_transactions.ndjson",
      "row_no": 1,
      "dimension": "record_counts",
      "expected": 10,
      "actual": 9,
      "message": "Count mismatch blocks staging import."
    }
  ],
  "decision": {
    "go_no_go": "GO | NO_GO",
    "reason": "Human readable gate result.",
    "required_action": "Next step or remediation."
  }
}
```

## Staging Row 字段映射

`staging.mongo_import_rows` 使用 0006 migration 中已有字段承载 06B 所需行级信息：

| 06B 字段 | PostgreSQL 字段或 JSON 位置 |
| --- | --- |
| `collection` | `legacy_collection` |
| `legacy_id` | `legacy_id` |
| `row_hash` | `payload_hash` |
| `raw_payload` | `payload`，并在 JSON 中保留原始 06A envelope |
| `source_file` | `payload._staging_import.source_file` |
| `source_line` | `row_no` 和 `payload._staging_import.source_line` |
| `import_status` | `status` |
| `error_code` | `error_code` |
| `error_summary` | `error_message` |

解析失败的 NDJSON 行必须写成 `status='failed'` 的 staging row。无法从坏行读取 legacy id 时，工具使用 `__failed__:<source_file>:<source_line>` 作为 synthetic `legacy_id`，并把原始文本保存在 `payload.raw_line`。

## 阻断码

| Code | 含义 | 是否阻断 |
| --- | --- | --- |
| `MISSING_MANIFEST` | 输入目录缺少 `manifest.json` | 是 |
| `INVALID_MANIFEST_JSON` | `manifest.json` 不是合法 JSON | 是 |
| `INVALID_MANIFEST` | manifest schema 不满足 06A/06B 契约 | 是 |
| `MISSING_EXPORT_FILE` | manifest 声明的 NDJSON 文件缺失 | 是 |
| `COUNT_MISMATCH` | manifest count 与 NDJSON 物理行数不一致 | 是 |
| `STAGING_ROW_COUNT_MISMATCH` | parsed + failed staging rows 无法覆盖源行 | 是 |
| `FILE_CHECKSUM_MISSING` | manifest 未提供输入文件 sha256 | 是 |
| `FILE_CHECKSUM_MISMATCH` | manifest sha256 或 GridFS sample checksum 不一致 | 是 |
| `NDJSON_PARSE_ERROR` | NDJSON 行无法解析，必须保留 failed row | 是 |
| `NDJSON_ROW_NOT_OBJECT` | NDJSON 行不是 JSON object | 是 |
| `DUPLICATE_LEGACY_ID` | 同一导入批次 legacy id 重复 | 是 |
| `AMOUNT_PARSE_ERROR` | 金额字段无法解析为 decimal | 是 |

任一 error severity finding 都必须产生 `decision.go_no_go = "NO_GO"`；工具不得把 staging 导入失败伪装成 `GO`。
