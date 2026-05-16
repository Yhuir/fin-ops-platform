# GridFS -> MinIO/S3 Checksum Validation Report Template

本文是 06D GridFS 文件内容迁移的 checksum validation 报告模板。报告必须可以直接支撑 `file_checksum` readiness gate；没有 GO 报告时，`file_checksum` 一律视为未通过。

报告不得包含 Mongo URI、S3 endpoint credential、access key、secret key、session token、presigned URL 或其他裸 secret。对象访问 URL 只允许由 Axum 在线短 TTL 生成，不写入迁移报告。

报告由 `scripts/tools/migrate_gridfs_minio.py --mode upload|verify` 生成。`dry-run` 可以生成报告文件，但 `readiness_gates.file_checksum.decision` 必须是 `NO_GO`，原因包含 `dry_run_does_not_download_verify_objects`。

```json
{
  "report_id": "gridfs-minio-checksum-YYYYMMDD-HHMMSS",
  "migration_run_id": "uuid-or-operator-run-id",
  "phase": "06d_gridfs_minio_migration",
  "tool": "app-gridfs-minio-migration-v1",
  "secret_free": true,
  "source": {
    "kind": "app_mongo_gridfs",
    "database": "fin_ops_platform_app",
    "gridfs_bucket": "import_file_blobs",
    "source_manifest_path": "/path/to/gridfs-minio-migration-manifest.json",
    "source_manifest_sha256": "sha256"
  },
  "target": {
    "storage_provider": "minio | s3",
    "bucket": "fin-ops-files",
    "environment": "staging | production",
    "endpoint_present": null
  },
  "status": "GO | NO_GO",
  "readiness_gates": {
    "file_checksum": {
      "decision": "GO | NO_GO",
      "requires_report": "gridfs-checksum-validation-report.json",
      "reasons": []
    }
  },
  "coverage": {
    "manifest_checksum": {
      "status": "covered",
      "sha256": "sha256-of-gridfs-minio-migration-manifest-json"
    },
    "output_file_checksums": {
      "gridfs-minio-migration-manifest.json": "sha256",
      "gridfs-object-mapping.ndjson": "sha256",
      "file-objects-import.ndjson": "sha256",
      "gridfs-migration-failures.ndjson": "sha256"
    },
    "sample_download_hash": {
      "sampled": 0,
      "matched": 0,
      "mismatched": 0
    },
    "missing_files": {
      "count": 0,
      "items": []
    },
    "duplicate_files": {
      "count": 0,
      "groups": [
        {
          "sha256": "sha256",
          "byte_size": 123,
          "legacy_gridfs_ids": ["legacy-id-1", "legacy-id-2"],
          "file_object_ids": ["uuid-1", "uuid-2"]
        }
      ]
    },
    "size_differences": {
      "count": 0,
      "items": []
    }
  },
  "legacy_id_mapping": {
    "mapping_file": "gridfs-object-mapping.ndjson",
    "expected_gridfs_files": 0,
    "mapped_file_objects": 0,
    "mapped_import_files": 0,
    "missing_mappings": []
  },
  "findings": [
    {
      "severity": "error",
      "code": "FILE_CHECKSUM_MISMATCH",
      "legacy_gridfs_id": "legacy-gridfs-id",
      "file_object_id": "uuid",
      "dimension": "sample_download_hash",
      "expected": "source-sha256",
      "actual": "downloaded-sha256",
      "message": "Downloaded object checksum differs from source GridFS checksum."
    }
  ],
  "decision": {
    "go_no_go": "NO_GO",
    "reason": "Blocking file checksum findings exist.",
    "required_action": "Fix object migration issue and rerun 06D execute mode until file_checksum is GO."
  }
}
```

## GO 条件

- `readiness_gates.file_checksum.decision` 必须是 `GO`。
- 报告必须覆盖 `manifest_checksum`、`sample_download_hash`、`missing_files`、`duplicate_files`、`size_differences`。
- `sample_download_hash.mismatched` 必须为 `0`；有源文件时正式执行报告必须至少有一个下载样本，或在报告中说明全量为 0 文件。
- `missing_files.count` 和 `size_differences.count` 必须为 `0`。
- 所有 `legacy_gridfs_id` 必须能映射到稳定 `file_object_id`；需要导入 import 文件事实的记录还必须有稳定 `import_file_id`。
- dry-run 报告不能作为 `file_checksum` GO 报告，因为 dry-run 不执行对象存储下载校验。
- 任一 `FILE_CHECKSUM_MISMATCH` 或 `OBJECT_DOWNLOAD_ERROR` 都必须是 `NO_GO`，并且对应 manifest file entry 的 `migration_status` 必须为 `failed`。
- `verify` 模式不能上传对象；如果目标对象不存在，必须输出阻断 finding。

## 阻断码

| Code | 含义 | 是否阻断 |
| --- | --- | --- |
| `GRIDFS_READ_ERROR` | 源 GridFS 文件无法读取，视为缺失文件 | 是 |
| `GRIDFS_LENGTH_MISMATCH` | GridFS metadata length 与实际读取字节数不一致 | 是 |
| `OBJECT_HEAD_ERROR` | 无法检查目标对象，不能证明幂等状态 | 是 |
| `OBJECT_UPLOAD_ERROR` | 上传失败 | 是 |
| `OBJECT_DOWNLOAD_ERROR` | 抽样下载失败 | 是 |
| `OBJECT_NOT_FOUND` | verify 模式下目标对象不存在 | 是 |
| `FILE_CHECKSUM_MISMATCH` | 抽样下载 SHA-256 与源文件 SHA-256 不一致 | 是 |
| `UNMAPPED_LEGACY_GRIDFS_ID` | 缺少 legacy GridFS 到目标 id 映射 | 是 |

所有阻断 findings 必须保留 `reason` 或可审计 message，且至少包含 `legacy_gridfs_id` 或 `file_object_id` 之一。

## 人工门禁建议引用

readiness gate 或人工门禁至少读取以下证据：

| 文件 | 用途 |
| --- | --- |
| `gridfs-checksum-validation-report.json` | `file_checksum` GO/NO_GO 决策、coverage、blocking findings。 |
| `gridfs-minio-migration-manifest.json` | 每个 GridFS 文件的 `legacy_gridfs_id`、`file_object_id`、`sha256`、`size`、`storage_key`、`migration_status` 和错误摘要。 |
| `gridfs-object-mapping.ndjson` | legacy GridFS 到 `app.file_objects` / `app.import_files` 草案的稳定映射。 |
| `gridfs-migration-failures.ndjson` | 阻断项清单，人工复核和重跑前处理依据。 |
