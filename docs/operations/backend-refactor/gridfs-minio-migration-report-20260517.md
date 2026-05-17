# 06D GridFS -> MinIO/S3 checksum validation report - 2026-05-17

## 判定

| 字段 | 值 |
| --- | --- |
| go/no-go | `NO_GO` |
| blocking | `true` |
| operator | `yu` |
| generated_at | `2026-05-17T09:16:00+08:00` |
| source_database | `fin_ops_platform_app` |
| source_manifest | `/tmp/finops-app-mongo-export-06a-20260517/collections/gridfs-files-manifest.ndjson` |
| source_manifest_sha256 | `88d0fd7787115b29eee8617d31ebd4f25071ea41217782cc85d536ed4369f8e1` |
| file_checksum gate | `NO_GO` |
| upload executed | `false` |
| verify executed | `false` |
| sample download executed | `false` |

本报告优先使用 06A `gridfs-files-manifest.ndjson` 作为输入，只完成 metadata 级别审计。当前没有 S3/MinIO staging 环境和 bucket 配置，未执行 upload/verify，也未进行抽样下载重算 SHA-256；dry-run 或 metadata-only 结果不能作为 `file_checksum` GO 证据。

## 06A GridFS metadata 摘要

| 维度 | 值 |
| --- | ---: |
| metadata entries | 462 |
| total bytes from metadata | 102579191 |
| content type defaulted | 462 |
| source content sha256 missing in metadata | 459 |

## 缺文件与 checksum mismatch 摘要

| 项目 | 结果 |
| --- | --- |
| missing source files | `not_evaluated_without_gridfs_content_read` |
| checksum mismatches | `not_evaluated_without_upload_or_verify` |
| sample_download_hash | `sampled=0 matched=0 mismatched=0` |
| duplicate files | `not_evaluated_without_source_content_sha256` |
| size differences | `not_evaluated_without_gridfs_content_read` |

## Blockers

| code | dimension | action |
| --- | --- | --- |
| `OBJECT_STORAGE_ENV_MISSING` | `object_storage_environment` | 在受控 staging 环境提供对象存储认证与 bucket 配置后重跑 upload 或 verify。 |
| `DRY_RUN_CANNOT_PASS_FILE_CHECKSUM_GATE` | `sample_download_hash` | 需要真实上传/校验并抽样下载重算 SHA-256，且 mismatched=0。 |

## 安全边界

- 未访问 OA 源数据库。
- 未处理或写入业务 facts。
- 未切换 API。
- 未记录对象存储认证值、临时对象访问 URL、完整连接串或 bucket 访问材料。
- 06D 后续 GO 证据必须由 `migrate_gridfs_minio.py --mode upload|verify` 的 checksum validation report 产生。

## 配套 JSON

- `docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.json`
