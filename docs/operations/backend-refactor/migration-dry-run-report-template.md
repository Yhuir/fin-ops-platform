# 数据迁移 Dry-run 报告模板

本文是 app Mongo export/staging rows -> PostgreSQL `app` / `read_model` / `job` / `audit` / `staging.legacy_id_map` dry-run 对账报告模板。报告不得包含真实密码、token、完整 URI、S3 secret 或 NATS credential。

## 必填结论

| 字段 | 值 |
| --- | --- |
| go/no-go | `GO` 或 `NO_GO` |
| migration_run_id | UUID |
| manifest_id | UUID |
| dry-run tool | `app-mongo-migration-dry-run-v1` |
| execute mode | `false`，除非显式在隔离 PostgreSQL dry-run 库执行 |
| OA 源数据库访问 | `false` |
| production facts 写入 | `false` |

任一 blocker 必须输出 `NO_GO`。`GO` 只表示 dry-run 对账可进入人工门禁复核，不授权生产切流、冻结 app Mongo 或覆盖现有事实数据。

## 必填对账维度

```json
{
  "phase": "staging_to_facts_dry_run",
  "status": "passed | failed",
  "blocking": false,
  "source_metrics": {
    "record_counts": {},
    "hashes": {},
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
  "row_hash_reconciliation": [
    {
      "object_type": "bank_transactions",
      "legacy_id": "legacy-id",
      "source_line": 1,
      "staging_payload_hash": "sha256",
      "computed_payload_hash": "sha256",
      "matched": true
    }
  ],
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
  "unmapped_invalid_enums": {
    "invoices": {
      "status": [
        "unknown_status_from_source"
      ]
    }
  },
  "file_checksum_scope": {
    "owner_phase": "06D",
    "status": "not_evaluated_in_06c",
    "message": "06C records manifest/file checksum metadata only; file content checksum gate belongs to 06D."
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
| `SOURCE_HASH_MISMATCH` | 06A manifest 中记录的 NDJSON hash 与当前文件内容不一致。 |
| `ROW_HASH_MISMATCH` | `staging.mongo_import_rows.payload_hash` 与 payload 重算 hash 不一致。 |
| `NDJSON_PARSE_ERROR` | 导出文件存在无法解析行。 |
| `DUPLICATE_LEGACY_ID` | 同一批次 legacy id 重复。 |
| `AMOUNT_PARSE_ERROR` | 金额字段无法解析为 decimal。 |
| `UNMAPPED_LEGACY_ID` | source legacy id 没有 `staging.legacy_id_map` 覆盖。 |
| `MAPPING_BLOCKER` | source object type 没有明确 PostgreSQL target mapping。 |
| `INVALID_ENUM` | source status/enum 值无法映射到目标表 check constraint。 |
| `BLOCKED_FACT_SOURCE` | staging 行已失败、source 行不可解析或合同不清楚，不能生成 facts plan。 |
| `PARTITION_PLAN_MISSING` | 目标分区表存在待迁移数据，但无法从 source 推导月份。 |

所有阻断项必须至少能定位到 `object_type`、`legacy_id`、`source_line`、`month`、`status` 或 `dimension`。金额、数量、月份、状态差异必须能继续下钻到对应 object type；月份和状态差异必须填充 `month` 或 `status`。

## 06C/06D 边界

- 06C 可以校验 manifest 中 NDJSON 文件 hash 与当前输入文件是否一致，也可以校验 staging row `payload_hash`。
- GridFS/对象存储文件内容 checksum、抽样下载和字节级一致性属于 06D。
- 06C 报告不得把文件内容 checksum 标记为已通过；只能输出 `file_checksum_scope.owner_phase=06D` 和 `status=not_evaluated_in_06c`。
