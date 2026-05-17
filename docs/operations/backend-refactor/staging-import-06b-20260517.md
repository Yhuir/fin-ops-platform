# 06B PostgreSQL staging import validation report - 2026-05-17

## 判定

| 项目 | 结果 |
| --- | --- |
| GO/NO_GO | **NO_GO** |
| operator | `yu` |
| generated_at | `2026-05-17T09:00:23+08:00` |
| source_database | `fin_ops_platform_app` |
| 06A manifest_dir | `/tmp/finops-app-mongo-export-06a-20260517` |
| 06A manifest.json | `/tmp/finops-app-mongo-export-06a-20260517/manifest.json` |
| migration_run_id | `a4227942-8eff-4876-8648-be1fbd821f43` |
| manifest_id | `a4227942-8eff-4876-8648-be1fbd821f43` |
| mode | `validate-only` |
| PostgreSQL staging 写入 | `false` |

本次未设置 `FIN_OPS_POSTGRES_MIGRATION_URL`，只运行 validate-only。导入计划、行解析和输入文件 hash 校验通过，但这不是 PostgreSQL staging 导入成功证据，因此总判定为 **NO_GO**。

## Blocker

| code | severity | required action |
| --- | --- | --- |
| `POSTGRES_STAGING_CONNECTION_NOT_PROVIDED` | blocker | 在受控 staging 环境设置 `FIN_OPS_POSTGRES_MIGRATION_URL` 后重新执行 `--execute`，并生成新的 06B GO 证据。 |

## Validation summary

| 项目 | 结果 |
| --- | --- |
| tool report status | `passed` |
| tool report decision | `GO` |
| started_at | `2026-05-17T00:59:43.275601+00:00` |
| finished_at | `2026-05-17T00:59:43.640179+00:00` |
| expected collection count entries | `31` |
| planned staging rows | `11084` |
| actual imported counts | `{}`（未执行 DB 写入） |
| failed row total | `0` |
| hash matched files | `31/31` |
| hash mismatches | `0` |

## Expected counts

| collection | expected rows | validated plan rows |
| --- | ---: | ---: |
| `app_health_alerts` | 1 | 1 |
| `app_settings` | 1 | 1 |
| `background_jobs` | 76 | 76 |
| `bank_transaction_categories` | 6 | 6 |
| `bank_transactions` | 431 | 431 |
| `cost_statistics_read_models` | 34 | 34 |
| `etc_reconciliation_state` | 1 | 1 |
| `etc_state` | 1 | 1 |
| `file_objects` | 0 | 0 |
| `gridfs-files-manifest` | 462 | 462（映射到 `import_file_blobs.files`） |
| `import_batches` | 6 | 6 |
| `invoices` | 391 | 391 |
| `matching_results` | 0 | 0 |
| `matching_runs` | 0 | 0 |
| `no_oa_bank_batch_audit_log` | 58 | 58 |
| `no_oa_bank_batches` | 54 | 54 |
| `oa_attachment_invoice_cache` | 7026 | 7026 |
| `oa_sync_state` | 1 | 1 |
| `tax_certified_import_batches` | 0 | 0 |
| `tax_certified_import_records` | 0 | 0 |
| `tax_certified_import_sessions` | 0 | 0 |
| `tax_offset_read_models` | 1 | 1 |
| `turnover_ledger_extras` | 0 | 0 |
| `turnover_relation_audit_log` | 1 | 1 |
| `turnover_relations` | 2 | 2 |
| `workbench_candidate_matches` | 2420 | 2420 |
| `workbench_exception_cases` | 2 | 2 |
| `workbench_matching_dirty_scopes` | 0 | 0 |
| `workbench_overrides` | 2 | 2（映射到 `workbench_row_overrides`） |
| `workbench_pair_relations` | 101 | 101 |
| `workbench_read_models` | 6 | 6 |

## Failed rows

validate-only 未发现坏行，`failed_row_counts` 为空。

## 06C inputs

| 字段 | 值 |
| --- | --- |
| allowed_to_start_06c | `false` |
| migration_run_id | `a4227942-8eff-4876-8648-be1fbd821f43` |
| manifest_id | `a4227942-8eff-4876-8648-be1fbd821f43` |
| report_path | `docs/operations/backend-refactor/staging-import-06b-20260517.json` |
| manifest_dir | `/tmp/finops-app-mongo-export-06a-20260517` |

## 安全边界

- 未访问 OA 源数据库。
- 未读取或记录数据库连接值、用户名、密码或认证材料。
- 未修改 Rust migration schema。
- 未写入 `app`、`read_model`、`job`、`audit` 正式 facts schema。
- 本 NO_GO 证据不得用于推进 06C。

## 配套 JSON

- `docs/operations/backend-refactor/staging-import-06b-20260517.json`
