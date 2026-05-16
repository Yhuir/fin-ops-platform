# GridFS 到 MinIO/S3 文件迁移 Manifest 格式

本文定义 P1-06D 文件迁移工具的输出格式。报告不得包含 MinIO/S3 access key、secret key、session token、完整 Mongo URI 或 PostgreSQL URI。

## 输出文件

文件迁移工具会在 `--output-dir` 下生成：

| 文件 | 说明 |
| --- | --- |
| `gridfs-minio-migration-manifest.json` | 本次文件迁移或 dry-run 的总报告。 |
| `gridfs-object-mapping.ndjson` | `legacy_gridfs_id -> file_object_id` 和对象存储位置映射。 |
| `file-objects-import.ndjson` | 可导入 `app.file_objects` 的元数据草案。 |
| `gridfs-migration-failures.ndjson` | 阻断项和失败文件清单。无失败时为空文件。 |

## Manifest 顶层结构

```json
{
  "tool": "app-gridfs-minio-migration-v1",
  "dry_run": true,
  "started_at": "2026-05-16T00:00:00+00:00",
  "finished_at": "2026-05-16T00:00:01+00:00",
  "source": {
    "storage_backend": "mongo",
    "database": "fin_ops_platform_app",
    "gridfs_bucket": "import_file_blobs"
  },
  "target": {
    "storage_provider": "minio",
    "bucket": "fin-ops-files",
    "environment": "staging"
  },
  "summary": {
    "dry_run": true,
    "total_files": 0,
    "total_bytes": 0,
    "planned": 0,
    "uploaded": 0,
    "skipped_existing": 0,
    "failed": 0,
    "checksum_samples": {
      "sampled": 0,
      "matched": 0,
      "mismatched": 0
    }
  },
  "files": [],
  "findings": [],
  "blocking": false,
  "status": "passed"
}
```

## File Entry

`files[]` 每条记录代表一个 app GridFS 文件：

```json
{
  "legacy_collection": "import_file_blobs.files",
  "legacy_gridfs_id": "import_file_0001",
  "file_object_id": "uuid",
  "storage_provider": "minio",
  "bucket": "fin-ops-files",
  "object_key": "staging/app-gridfs/import_source_file/2026/05/<legacy_hash>/<file_object_id>",
  "object_version": null,
  "file_name": "source.xlsx",
  "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "byte_size": 4341,
  "sha256": "64-char-lowercase-hex",
  "etag": null,
  "purpose": "import_source_file",
  "chunk_count": 1,
  "upload_date": "2026-05-16T00:00:00+00:00",
  "status": "planned"
}
```

`status` 取值：

| Status | 含义 |
| --- | --- |
| `planned` | dry-run 中已生成计划，未上传。 |
| `uploaded` | 已上传对象，并纳入 checksum 抽样候选。 |
| `skipped_existing` | 目标对象已存在且 metadata sha256 与源文件一致。 |
| `failed` | 读取、长度、上传或 checksum 校验失败。 |

## Mapping NDJSON

`gridfs-object-mapping.ndjson` 每行格式：

```json
{
  "source_system": "app_mongo_gridfs",
  "legacy_collection": "import_file_blobs.files",
  "legacy_gridfs_id": "import_file_0001",
  "file_object_id": "uuid",
  "target_schema": "app",
  "target_table": "app.file_objects",
  "bucket": "fin-ops-files",
  "object_key": "staging/app-gridfs/import_source_file/2026/05/<legacy_hash>/<file_object_id>",
  "sha256": "64-char-lowercase-hex",
  "byte_size": 4341,
  "purpose": "import_source_file",
  "status": "uploaded"
}
```

## file_objects NDJSON

`file-objects-import.ndjson` 每行对应 `app.file_objects` 元数据草案：

```json
{
  "id": "uuid",
  "storage_provider": "minio",
  "bucket": "fin-ops-files",
  "object_key": "staging/app-gridfs/import_source_file/2026/05/<legacy_hash>/<file_object_id>",
  "object_version": null,
  "file_name": "source.xlsx",
  "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "byte_size": 4341,
  "sha256": "64-char-lowercase-hex",
  "etag": "object-etag",
  "metadata": {
    "legacy_collection": "import_file_blobs.files",
    "chunk_count": 1,
    "upload_date": "2026-05-16T00:00:00+00:00"
  },
  "legacy_gridfs_id": "import_file_0001",
  "purpose": "import_source_file",
  "created_by": "mongo_migration"
}
```

## 阻断项

以下情况必须将 `status` 置为 `failed` 且 `blocking=true`：

| Code | 含义 |
| --- | --- |
| `GRIDFS_LENGTH_MISMATCH` | GridFS `.files.length` 与实际读取字节数不一致。 |
| `FILE_CHECKSUM_MISMATCH` | 上传后抽样下载 SHA-256 与源文件 SHA-256 不一致。 |

工具不得把 checksum 失败标记为成功，也不得从报告中删除失败文件。
