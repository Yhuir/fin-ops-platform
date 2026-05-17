# App Mongo 备份恢复门禁证据 - 20260517

本文把既有 `app-mongo-backup-runbook.md` 中已完成的 app Mongo 备份、checksum 校验、恢复演练和 GridFS 抽样校验整理为 readiness gate 可识别证据。本文只覆盖 app Mongo 数据库 `fin_ops_platform_app`，未访问 OA 源数据库，未执行新的生产备份，未冻结或删除 app Mongo，未执行生产切流。

## 结论

| 项 | 值 |
| --- | --- |
| Gate | **GO** |
| go/no-go | `GO` |
| operator | Codex |
| generated_at | `2026-05-17T08:44:25+08:00` |
| scope | 已完成 app Mongo 备份、checksum、非破坏归档可读性检查、恢复演练、collection count 比对和 GridFS 抽样完整性。 |
| source_database | `fin_ops_platform_app` |
| OA source database accessed | no |

## 备份工件

| 字段 | 值 |
| --- | --- |
| backup time | `2026-05-16 01:29:00 CST` |
| database | `fin_ops_platform_app` |
| archive path | `/data/backups/fin_ops/2026-05-16_012900/mongo/app-mongo-fin_ops_platform_app.archive.gz` |
| archive size | about `92M` |
| latest pointer | `/data/backups/fin_ops/latest-app-mongo` |
| checksum algorithm | `sha256` |
| checksum | `1968e81888dd359ba7d9d8424cdef399744d81a6d5e7305db1f8222404b9422a` |
| checksum verification | `OK` |

## 备份前统计

db stats:

```text
collections=50
objects=10231
dataSize=119986119
storageSize=111943680
indexSize=2826240
```

关键 collection count:

| collection | count |
| --- | ---: |
| `bank_transactions` | 431 |
| `invoices` | 391 |
| `import_batches` | 6 |
| `file_import_sessions` | 11 |
| `file_import_files` | 31 |
| `import_file_blobs.files` | 462 |
| `import_file_blobs.chunks` | 726 |
| `workbench_pair_relations` | 101 |
| `workbench_candidate_matches` | 771 |
| `workbench_read_models` | 6 |
| `oa_attachment_invoice_cache` | 7026 |
| `background_jobs` | 75 |
| `no_oa_bank_batches` | 54 |
| `cost_statistics_read_models` | 34 |

## 恢复结果

| 字段 | 值 |
| --- | --- |
| restore target DB | `fin_ops_platform_app_restore_test_20260516` |
| namespace mapping | `fin_ops_platform_app.*` -> `fin_ops_platform_app_restore_test_20260516.*` |
| production database overwritten | no |
| collection count summary | `summary total=50 diff=0` |
| restore result | `GO` |

GridFS sample integrity:

```text
file_id=import_file_0001
filename=historydetail14080.xlsx
file_length=4341
chunk_count=1
chunk_bytes=4341
integrity=OK
```

## 安全边界

- 未访问 OA 源数据库。
- 未写入 secret、完整 URI、密码、token、S3 credential 或 NATS credential。
- 未执行新的生产备份。
- 未执行生产切流。
- 未冻结、归档或删除 app Mongo。

## remaining_risks

- 本证据只覆盖 `fin_ops_platform_app` 的既有 app Mongo 备份和恢复演练。
- PostgreSQL backup/PITR、迁移 dry-run reconciliation、GridFS 到对象存储 checksum validation、API shadow validation、NATS/worker replay、read model rebuild、monitoring alert verification、load test、rollback drill 仍需独立证据支撑。

## evidence_sources

- `docs/operations/backend-refactor/app-mongo-backup-runbook.md`
- `docs/operations/backend-refactor/formal-migration-go-no-go-20260517.md`
- `docs/operations/backend-refactor/formal-migration-go-no-go-20260517.json`
