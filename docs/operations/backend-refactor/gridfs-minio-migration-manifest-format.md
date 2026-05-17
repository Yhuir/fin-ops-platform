# GridFS 到 MinIO/S3 文件迁移 Manifest 格式

本文定义 P1-06D 文件迁移工具的输出格式。报告不得包含 MinIO/S3 access key、secret key、session token、完整 Mongo URI 或 PostgreSQL URI。

## 输出文件

文件迁移工具会在 `--output-dir` 下生成：

| 文件 | 说明 |
| --- | --- |
| `gridfs-minio-migration-manifest.json` | 本次文件迁移或 dry-run 的总报告。 |
| `gridfs-object-mapping.ndjson` | `legacy_gridfs_id -> file_object_id` 和对象存储位置映射。 |
| `file-objects-import.ndjson` | 可导入 `app.file_objects` 的元数据草案。 |
| `legacy-id-map-import.ndjson` | 可导入 `staging.legacy_id_map` 的 `app.file_objects` / `app.import_files` 映射草案。 |
| `gridfs-migration-failures.ndjson` | 阻断项和失败文件清单。无失败时为空文件。 |
| `gridfs-checksum-validation-report.json` | readiness gate 和人工门禁可引用的 checksum validation 报告。 |
| `gridfs-minio-migration-report-YYYYMMDD.json/.md` | 06D 外层 GO/NO_GO 报告；可由 06A export metadata-only dry-run 生成，也可引用 live upload/verify 输出。 |

## 执行模式

工具支持 `--mode dry-run|upload|verify`：

| Mode | 行为 | 是否写对象存储 | 是否可作为 `file_checksum` GO 证据 |
| --- | --- | --- | --- |
| `dry-run` | 读取 app GridFS，生成迁移计划、稳定 `file_object_id`、`storage_key` 和导入草案。 | 否 | 否 |
| `upload` | 读取 app GridFS；同一 `storage_key` 已存在且 metadata `sha256` 一致时跳过，否则上传；之后按抽样下载重新计算 SHA-256。 | 是 | 是 |
| `verify` | 读取 app GridFS 和目标对象；不上传，只验证目标对象存在、metadata checksum 一致，并按抽样下载重新计算 SHA-256。 | 否 | 是 |

旧参数 `--execute` 仅作为 `--mode upload` 的兼容别名。S3/MinIO credential 只能通过环境变量或受控运行配置提供，报告和日志不得输出 access key、secret key、session token、presigned URL 或完整连接串。

也支持 06A export metadata-only 报告模式：

```bash
PYTHONPATH=backend/src python3 scripts/tools/migrate_gridfs_minio.py \
  --export-dir /tmp/finops-app-mongo-export-06a-20260517 \
  --migration-run-id a4227942-8eff-4876-8648-be1fbd821f43 \
  --dry-run \
  --report-json-path docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.json \
  --report-md-path docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.md
```

该模式只读取 `manifest.json` 和 `gridfs-files-manifest.ndjson`，不连接 app GridFS、不上传对象、不写 PostgreSQL。它会输出稳定 object key 与 metadata plan 样例，但必须保持 `NO_GO`，直到 live GridFS 读取源 bytes、upload/verify 和抽样下载 checksum 通过。

## Manifest 顶层结构

```json
{
  "tool": "app-gridfs-minio-migration-v1",
  "mode": "dry-run",
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
    "mode": "dry-run",
    "total_files": 0,
    "empty_gridfs": true,
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
  "source_collection": "import_file_blobs.files",
  "legacy_gridfs_id": "import_file_0001",
  "file_object_id": "uuid",
  "storage_provider": "minio",
  "bucket": "fin-ops-files",
  "object_key": "staging/app-gridfs/import_source_file/2026/05/<legacy_hash>/<file_object_id>",
  "storage_key": "staging/app-gridfs/import_source_file/2026/05/<legacy_hash>/<file_object_id>",
  "object_version": null,
  "file_name": "source.xlsx",
  "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "content_type_status": "provided",
  "byte_size": 4341,
  "size": 4341,
  "sha256": "64-char-lowercase-hex",
  "etag": null,
  "purpose": "import_source_file",
  "chunk_count": 1,
  "upload_date": "2026-05-16T00:00:00+00:00",
  "status": "planned",
  "migration_status": "planned",
  "error_code": null,
  "error_summary": null
}
```

`status` 与 `migration_status` 取值相同：

| Status | 含义 |
| --- | --- |
| `planned` | dry-run 中已生成计划，未上传。 |
| `uploaded` | 已上传对象，并纳入 checksum 抽样候选。 |
| `skipped_existing` | 目标对象已存在且 metadata sha256 与源文件一致；upload/verify 都可以出现。 |
| `failed` | 读取、长度、上传或 checksum 校验失败。 |

兼容字段说明：

| 字段 | 说明 |
| --- | --- |
| `legacy_gridfs_id` | app GridFS `.files._id` 的字符串化值。 |
| `file_object_id` | 基于 `legacy_gridfs_id` 生成的稳定 UUID，可用于 `app.file_objects.id` 草案。 |
| `sha256` | 从源 GridFS 文件内容计算的 SHA-256；源读取失败时为 `null`。 |
| `size` / `byte_size` | 实际读取字节数。`GRIDFS_LENGTH_MISMATCH` 时以实际读取值为准，并保留 finding。 |
| `content_type` | GridFS `contentType` 或 metadata `content_type`；缺失时为 `application/octet-stream`。 |
| `content_type_status` | `provided` 或 `defaulted`，用于显式标记 content type 缺失。 |
| `storage_key` / `object_key` | 目标对象 key。报告不得包含 presigned URL。 |
| `source_collection` / `legacy_collection` | 固定为 app GridFS files collection，例如 `import_file_blobs.files`。 |
| `migration_status` / `status` | 当前文件迁移状态。 |
| `error_code` / `error_summary` | 失败或阻断 finding 的首个错误码和摘要；成功时为 `null`。 |

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
  "target_tables": ["app.file_objects", "app.import_files"],
  "bucket": "fin-ops-files",
  "object_key": "staging/app-gridfs/import_source_file/2026/05/<legacy_hash>/<file_object_id>",
  "object_version": null,
  "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "etag": "object-etag",
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

## legacy_id_map NDJSON

`legacy-id-map-import.ndjson` 每个成功 GridFS 文件输出两行，分别映射到 `app.file_objects` 和 `app.import_files`：

```json
{
  "source_system": "app_mongo_gridfs",
  "legacy_collection": "import_file_blobs.files",
  "legacy_id": "import_file_0001",
  "target_schema": "app",
  "target_table": "file_objects",
  "target_id": "file-object-uuid",
  "payload_hash": "sha256",
  "migration_run_id": "migration-run-uuid"
}
```

该文件只作为 `staging.legacy_id_map` 导入计划；除非用户明确授权在受控 staging/dry-run 库执行，工具不得写正式 PostgreSQL facts。

## 阻断项

以下情况必须将 `status` 置为 `failed` 且 `blocking=true`：

| Code | 含义 |
| --- | --- |
| `GRIDFS_LENGTH_MISMATCH` | GridFS `.files.length` 与实际读取字节数不一致。 |
| `GRIDFS_READ_ERROR` | GridFS metadata 存在但文件内容无法读取，视为缺失源文件。 |
| `OBJECT_HEAD_ERROR` | 无法检查目标对象，不能证明幂等或 verify 状态。 |
| `OBJECT_UPLOAD_ERROR` | 上传失败。 |
| `OBJECT_DOWNLOAD_ERROR` | 抽样下载失败。 |
| `OBJECT_NOT_FOUND` | verify 模式下目标对象不存在。 |
| `FILE_CHECKSUM_MISMATCH` | 上传后抽样下载 SHA-256 与源文件 SHA-256 不一致。 |
| `APP_GRIDFS_ENV_MISSING` | 缺少 app GridFS env，无法读取源文件 bytes。 |
| `OBJECT_STORAGE_ENV_MISSING` | 缺少 MinIO/S3 endpoint、bucket 或认证环境。 |
| `POSTGRES_MIGRATION_ENV_MISSING` | 缺少 PostgreSQL migration/staging 连接环境，不能执行 metadata import。 |
| `SOURCE_SHA256_MISSING` | 06A metadata manifest 缺源文件内容 SHA-256；需要 live GridFS 读取后才能 GO。 |

工具不得把 checksum 失败标记为成功，也不得从报告中删除失败文件。

## 边界状态

- 空 GridFS：`summary.total_files=0`、`summary.empty_gridfs=true`、`status=passed`；正式 GO 报告仍需由 checksum validation report 表达 0 文件原因。
- 重复文件：同一 `(sha256, byte_size)` 的多条 GridFS 文件会在 summary/report 的 duplicate groups 中列出；不改变单文件成功状态。
- 重复执行：同一 `storage_key` 已存在且 metadata `sha256` 与源文件一致时不重复上传，状态为 `skipped_existing`。
- 缺失 content type：不会阻断；`content_type` 默认 `application/octet-stream`，`content_type_status=defaulted`。
