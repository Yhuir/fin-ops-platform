# Migration Validation Report Template

本文是 app Mongo -> PostgreSQL staging/dry-run 对账报告模板。报告不得包含真实密码、token、完整 URI、S3 secret 或 NATS credential。

```json
{
  "report_id": "migration-validation-YYYYMMDD-HHMMSS",
  "migration_run_id": "uuid",
  "manifest_id": "uuid",
  "phase": "staging_import",
  "source": {
    "kind": "app_mongo_export",
    "database": "fin_ops_platform_app",
    "export_name": "20260516-app-mongo",
    "manifest_sha256": "sha256"
  },
  "target": {
    "kind": "postgresql_staging",
    "schema": "staging",
    "tables": [
      "staging.mongo_export_manifest",
      "staging.mongo_import_rows"
    ]
  },
  "status": "passed | failed",
  "blocking": true,
  "record_counts": {
    "expected": {
      "import_batches": 0,
      "bank_transactions": 0,
      "invoices": 0,
      "file_objects": 0,
      "workbench_overrides": 0,
      "workbench_pair_relations": 0,
      "workbench_candidate_matches": 0,
      "background_jobs": 0,
      "gridfs-files-manifest": 0
    },
    "actual": {},
    "diff": {}
  },
  "amount_totals": {
    "expected": {
      "bank_transactions.amount": "0.00",
      "bank_transactions.signed_amount": "0.00",
      "invoices.amount": "0.00",
      "invoices.signed_amount": "0.00",
      "invoices.tax_amount": "0.00",
      "invoices.total_with_tax": "0.00"
    },
    "actual": {},
    "diff": {}
  },
  "month_distribution": {
    "expected": {
      "bank_transactions": {
        "YYYY-MM": 0
      },
      "invoices": {
        "YYYY-MM": 0
      }
    },
    "actual": {},
    "diff": {}
  },
  "status_distribution": {
    "expected": {
      "import_batches": {},
      "bank_transactions": {},
      "invoices": {},
      "workbench_pair_relations": {},
      "background_jobs": {}
    },
    "actual": {},
    "diff": {}
  },
  "file_checksums": {
    "manifest_file_checksums": {
      "matched": 0,
      "mismatched": 0
    },
    "gridfs_sample_checksums": {
      "sampled": 0,
      "matched": 0,
      "mismatched": 0
    }
  },
  "legacy_id_coverage": {
    "expected": 0,
    "mapped": 0,
    "missing": []
  },
  "findings": [
    {
      "severity": "error",
      "code": "COUNT_MISMATCH",
      "object_type": "bank_transactions",
      "legacy_id": "txn-legacy-id-if-known",
      "row_no": 1,
      "dimension": "record_counts",
      "expected": 10,
      "actual": 9,
      "message": "Count mismatch blocks migration."
    }
  ],
  "decision": {
    "go_no_go": "NO_GO",
    "reason": "Blocking findings exist.",
    "required_action": "Fix mapping/import issue and rerun dry-run."
  }
}
```

## 阻断码

| Code | 含义 | 是否阻断 |
| --- | --- | --- |
| `COUNT_MISMATCH` | 数量不一致 | 是 |
| `AMOUNT_MISMATCH` | 金额汇总不一致 | 是 |
| `MONTH_MISMATCH` | 月份分布不一致 | 是 |
| `STATUS_MISMATCH` | 状态分布不一致 | 是 |
| `FILE_CHECKSUM_MISMATCH` | manifest 文件或文件抽样 checksum 不一致 | 是 |
| `NDJSON_PARSE_ERROR` | 导出文件存在无法解析行 | 是 |
| `DUPLICATE_LEGACY_ID` | 同一批次 legacy id 重复 | 是 |
| `AMOUNT_PARSE_ERROR` | 金额字段无法解析为 decimal | 是 |
| `UNKNOWN_STATUS` | 状态值无映射 | 是 |
| `UNMAPPED_LEGACY_ID` | 目标映射缺失 | 是 |

所有阻断码必须定位到至少一个维度：`object_type`、`legacy_id`、`row_no`、`month`、`status` 或 `dimension`。
