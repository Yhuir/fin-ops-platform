# 数据迁移 Dry-run 报告模板

本文是 app Mongo export/staging rows -> PostgreSQL `app` / `read_model` / `job` / `audit` / `staging.legacy_id_map` dry-run 对账报告模板。报告不得包含真实密码、token、完整 URI、S3 secret 或 NATS credential。

## 必填结论

| 字段 | 值 |
| --- | --- |
| go/no-go | `GO` 或 `NO_GO` |
| migration_run_id | UUID |
| manifest_id | UUID |
| source manifest schema | `finops.app_mongo_export_manifest.v1` |
| source manifest aggregate hash | `manifest.hashes.aggregate_sha256` |
| dry-run tool | `app-mongo-migration-dry-run-v1` |
| execute mode | `false`，除非显式在隔离 PostgreSQL dry-run 库执行 |

任一 blocker 必须输出 `NO_GO`。`GO` 只表示 dry-run 对账可进入人工门禁复核，不授权生产切流、冻结 app Mongo 或覆盖现有事实数据。

## 必填对账维度

```json
{
  "phase": "staging_to_facts_dry_run",
  "status": "passed | failed",
  "blocking": false,
  "source_metrics": {
    "schema_version": "finops.app_mongo_export_manifest.v1",
    "source_database": "fin_ops_platform_app",
    "collection_counts": {},
    "record_counts": {},
    "hashes": {
      "files": {},
      "aggregate_sha256": "sha256"
    },
    "amount_totals": {},
    "month_distribution": {},
    "status_distribution": {},
    "failed_row_reasons": []
  },
  "staging_metrics": {
    "record_counts": {},
    "hashes": {},
    "amount_totals": {},
    "month_distribution": {},
    "status_distribution": {},
    "failed_row_reasons": []
  },
  "target_metrics": {
    "record_counts": {},
    "hashes": {},
    "amount_totals": {},
    "month_distribution": {},
    "status_distribution": {},
    "failed_row_reasons": []
  },
  "partition_plan": {
    "month_range": {
      "min": "YYYY-MM",
      "max": "YYYY-MM"
    },
    "prepared_partitions": [
      {
        "schema": "app",
        "parent_table": "bank_transactions",
        "month": "YYYY-MM",
        "status": "planned | created_or_already_exists"
      }
    ]
  },
  "legacy_id_coverage": {
    "expected": 0,
    "mapped": 0,
    "coverage_ratio": "1.0000",
    "missing": []
  },
  "findings": [],
  "decision": {
    "go_no_go": "GO",
    "reason": "Dry-run reconciliation passed.",
    "required_action": "Eligible for human gate review; this dry-run does not authorize production cutover."
  }
}
```

## 阻断码

| Code | 含义 |
| --- | --- |
| `COUNT_MISMATCH` | source、staging、target 数量不一致。 |
| `AMOUNT_MISMATCH` | 金额汇总不一致。 |
| `MONTH_MISMATCH` | 月份分布不一致。 |
| `STATUS_MISMATCH` | 状态分布不一致。 |
| `FILE_CHECKSUM_MISMATCH` | manifest 或文件抽样 checksum 不一致。 |
| `SOURCE_EXPORT_VALIDATION_ERROR` | 06A manifest 中 `validation.errors` 非空。 |
| `SOURCE_EXPORT_HASH_MISMATCH` | 06A `hashes.aggregate_sha256` 或 `checksums` 与实际文件不一致。 |
| `NDJSON_PARSE_ERROR` | 导出文件存在无法解析行。 |
| `DUPLICATE_LEGACY_ID` | 同一批次 legacy id 重复。 |
| `AMOUNT_PARSE_ERROR` | 金额字段无法解析为 decimal。 |
| `UNMAPPED_LEGACY_ID` | source legacy id 没有 `staging.legacy_id_map` 覆盖。 |
| `PARTITION_PLAN_MISSING` | 目标分区表存在待迁移数据，但无法从 source 推导月份。 |

所有阻断项必须至少能定位到 `object_type`、`legacy_id`、`row_no`、`month`、`status` 或 `dimension`。
