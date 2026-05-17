# 06C staging -> facts dry-run report - 2026-05-17

## 判定

| 字段 | 值 |
| --- | --- |
| go/no-go | `NO_GO` |
| blocking | `true` |
| operator | `yu` |
| generated_at | `2026-05-17T09:10:00+08:00` |
| migration_run_id | `a4227942-8eff-4876-8648-be1fbd821f43` |
| manifest_id | `a4227942-8eff-4876-8648-be1fbd821f43` |
| source_database | `fin_ops_platform_app` |
| dry-run tool | `app-mongo-migration-dry-run-v1` |
| execute mode | `false` |
| production facts 写入 | `false` |
| OA 源数据库访问 | `false` |

本报告只执行 06C dry-run/report-only 校验，未写 `app`、`read_model`、`job`、`audit` 正式 facts。上游 06B 证据为 `NO_GO` 且 `FIN_OPS_POSTGRES_MIGRATION_URL` 缺失，因此没有从 PostgreSQL staging 读取真实 rows；本次使用 06A manifest_dir 与 06B `migration_run_id` 生成阻断型 dry-run 对账报告，不能进入人工 GO 门禁。

## 上游 06B 状态

| 字段 | 值 |
| --- | --- |
| 06B evidence | `docs/operations/backend-refactor/staging-import-06b-20260517.json` |
| 06B GO/NO_GO | `NO_GO` |
| allowed_to_start_06c | `false` |
| blocker | `POSTGRES_STAGING_CONNECTION_NOT_PROVIDED` |

## 覆盖对象类型

`app_health_alerts`, `app_settings`, `background_jobs`, `bank_transaction_categories`, `bank_transactions`, `cost_statistics_read_models`, `etc_reconciliation_state`, `etc_state`, `file_objects`, `gridfs-files-manifest`, `import_batches`, `invoices`, `matching_results`, `matching_runs`, `no_oa_bank_batch_audit_log`, `no_oa_bank_batches`, `oa_attachment_invoice_cache`, `oa_sync_state`, `tax_certified_import_batches`, `tax_certified_import_records`, `tax_certified_import_sessions`, `tax_offset_read_models`, `turnover_ledger_extras`, `turnover_relation_audit_log`, `turnover_relations`, `workbench_candidate_matches`, `workbench_exception_cases`, `workbench_matching_dirty_scopes`, `workbench_overrides`, `workbench_pair_relations`, `workbench_read_models`

## 对账摘要

| 维度 | 结果 |
| --- | --- |
| target_row_count | `8625` |
| legacy_id_map_row_count | `8625` |
| legacy_id_coverage | `8625/11084 (0.7781)` |
| row_hash matched | `11084/11084` |
| row_hash mismatches | `0` |
| partition month range | `2025-12..2026-04` |
| file checksum scope | `06D:not_evaluated_in_06c` |
| blocking findings | `4932` |

## Finding summary

| code | count | top object types |
| --- | ---: | --- |
| `COUNT_MISMATCH` | 10 | `file_objects`:1, `matching_results`:1, `matching_runs`:1, `tax_certified_import_batches`:1, `tax_certified_import_records`:1, `tax_certified_import_sessions`:1, `turnover_ledger_extras`:1, `workbench_matching_dirty_scopes`:1 |
| `INVALID_ENUM` | 2457 | `workbench_candidate_matches`:2420, `workbench_pair_relations`:31, `background_jobs`:6 |
| `MAPPING_BLOCKER` | 2 | `etc_reconciliation_state`:1, `etc_state`:1 |
| `MONTH_MISMATCH` | 2 | `background_jobs`:1, `workbench_pair_relations`:1 |
| `STATUS_MISMATCH` | 2 | `background_jobs`:1, `workbench_pair_relations`:1 |
| `UNMAPPED_LEGACY_ID` | 2459 | `workbench_candidate_matches`:2420, `workbench_pair_relations`:31, `background_jobs`:6, `etc_reconciliation_state`:1, `etc_state`:1 |

## Mapping blockers

| object_type | legacy_id | source_line | dimension | message |
| --- | --- | ---: | --- | --- |
| `etc_reconciliation_state` | `current_state` | `1` | `legacy_id_coverage` | No explicit PostgreSQL target mapping exists for this app Mongo dataset. |
| `etc_state` | `current_state` | `1` | `legacy_id_coverage` | No explicit PostgreSQL target mapping exists for this app Mongo dataset. |

## Invalid enum summary

| object_type | count | status values |
| --- | ---: | --- |
| `background_jobs` | 6 | `acknowledged`:5, `superseded`:1 |
| `workbench_candidate_matches` | 2420 | `needs_review`:2167, `suppressed`:123, `incomplete`:67, `auto_closed`:53, `conflict`:10 |
| `workbench_pair_relations` | 31 | `active`:31 |

## Required partition range

| parent | month | status |
| --- | --- | --- |
| `app.bank_transactions` | `2026-01` | `planned` |
| `app.bank_transactions` | `2026-02` | `planned` |
| `app.bank_transactions` | `2026-03` | `planned` |
| `app.bank_transactions` | `2026-04` | `planned` |
| `app.invoices` | `2025-12` | `planned` |
| `app.invoices` | `2026-01` | `planned` |
| `app.invoices` | `2026-02` | `planned` |
| `app.invoices` | `2026-03` | `planned` |
| `app.invoices` | `2026-04` | `planned` |

## 06C/06D 边界

- 06C 只记录 manifest/NDJSON hash、staging payload hash、row_hash/source_hash 对账；GridFS/对象存储文件内容 checksum 属于 06D。
- 本报告未把文件内容 checksum 标记为通过，`file_checksum_scope.owner_phase=06D` 且 `status=not_evaluated_in_06c`。
- 全量可定位 blocker findings 写入配套 JSON 的 `findings` 字段；每条保留 `object_type`、`legacy_id`、`source_line`、`status`、`month` 或 `dimension` 中可用定位字段。

## 配套 JSON

- `docs/operations/backend-refactor/migration-dry-run-report-20260517.json`
