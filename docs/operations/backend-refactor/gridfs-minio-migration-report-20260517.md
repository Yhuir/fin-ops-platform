# 06D GridFS -> MinIO/S3 checksum validation report

## 判定

| 字段 | 值 |
| --- | --- |
| go/no-go | `NO_GO` |
| blocking | `true` |
| generated_at | `2026-05-17T12:25:51.614990+00:00` |
| source_database | `fin_ops_platform_app` |
| source_manifest | `/tmp/finops-app-mongo-export-06a-20260517/collections/gridfs-files-manifest.ndjson` |
| source_manifest_sha256 | `88d0fd7787115b29eee8617d31ebd4f25071ea41217782cc85d536ed4369f8e1` |
| file_checksum gate | `NO_GO` |
| upload executed | `false` |
| verify executed | `false` |
| sample download executed | `false` |

本报告只记录环境变量是否存在，不记录 Mongo/PostgreSQL URI、S3 access key、secret key、session token、presigned URL 或其他 secret 值。dry-run/export metadata 不能作为 `file_checksum` GO 证据。

## 06A GridFS metadata 摘要

| 维度 | 值 |
| --- | ---: |
| metadata entries | 462 |
| total bytes from metadata | 102579191 |
| content type defaulted | 462 |
| source content sha256 missing in metadata | 459 |

## Blockers

| code | dimension | action |
| --- | --- | --- |
| `APP_GRIDFS_ENV_MISSING` | `app_gridfs_environment` | Set app GridFS connection env and rerun live 06D migration against app Mongo only. |
| `OBJECT_STORAGE_ENV_MISSING` | `object_storage_environment` | Provide controlled staging object storage env and rerun upload or verify mode. |
| `POSTGRES_MIGRATION_ENV_MISSING` | `postgres_metadata_environment` | Set FIN_OPS_POSTGRES_MIGRATION_URL for a controlled staging/dry-run database before writing metadata. |
| `DRY_RUN_CANNOT_PASS_FILE_CHECKSUM_GATE` | `sample_download_hash` | Run upload or verify mode against controlled staging MinIO/S3 and require mismatched=0. |
| `SOURCE_SHA256_MISSING` | `source_hash` | Provide app GridFS env and rerun live dry-run/upload so source sha256 is computed. |

## 安全边界

- 未访问 OA 源数据库。
- 未写入 `app`、`read_model`、`job`、`audit` 正式 facts。
- 未删除 GridFS 原文件。
- 未记录对象存储认证值、临时对象访问 URL、完整连接串或 bucket 访问材料。

## 配套 JSON

- `docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.json`
