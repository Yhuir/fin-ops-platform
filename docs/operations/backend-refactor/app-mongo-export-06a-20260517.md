# 06A App Mongo Export Evidence - 20260517

本文记录 06A app Mongo export 工具对 `fin_ops_platform_app` 的本次只读导出证据。未访问 OA 源数据库，未迁移生产数据，未切换 API，未修改 Rust migration。实际 NDJSON 与 `manifest.json` 位于本机 `/tmp`，不提交到 git。

## 结论

| 项 | 值 |
| --- | --- |
| GO/NO_GO | `GO` |
| operator | Codex |
| generated_at | `2026-05-17T09:05:00+08:00` |
| source_database | `fin_ops_platform_app` |
| tool_version | `app-mongo-export-v1` |
| schema_version | `finops.app_mongo_export_manifest.v1` |
| export_started_at | `2026-05-17T00:55:05.098443+00:00` |
| export_finished_at | `2026-05-17T00:55:37.659517+00:00` |
| manifest_dir | `/tmp/finops-app-mongo-export-06a-20260517` |
| manifest.json | `/tmp/finops-app-mongo-export-06a-20260517/manifest.json` |
| aggregate_hash | `f5283032a599e2ee72a8583fc31725071ae78f40e02ce4c71ec49d387925343c` |
| warning_count | `8` |
| error_count | `0` |

## Collection Counts

| collection | count |
| --- | ---: |
| `import_batches` | 6 |
| `bank_transactions` | 431 |
| `invoices` | 391 |
| `file_objects` | 0 |
| `gridfs-files-manifest` | 462 |
| `workbench_pair_relations` | 101 |
| `workbench_candidate_matches` | 2420 |
| `workbench_read_models` | 6 |
| `oa_attachment_invoice_cache` | 7026 |
| `background_jobs` | 76 |
| `no_oa_bank_batches` | 54 |
| `cost_statistics_read_models` | 34 |

## Source Collection Counts

| source collection | count |
| --- | ---: |
| `import_batches` | 6 |
| `bank_transactions` | 431 |
| `invoices` | 391 |
| `file_import_sessions` | 11 |
| `file_import_files` | 31 |
| `import_file_blobs.files` | 462 |
| `import_file_blobs.chunks` | 726 |
| `workbench_pair_relations` | 101 |
| `workbench_candidate_matches` | 2420 |
| `workbench_read_models` | 6 |
| `oa_attachment_invoice_cache` | 7026 |
| `background_jobs` | 76 |

## File SHA-256

| file | sha256 |
| --- | --- |
| `collections/import_batches.ndjson` | `1ae51b6a04b2eaf5a36a9e488e98b708caebe0b4c4fb68258fbab69d094ab56a` |
| `collections/bank_transactions.ndjson` | `cd48c633a49fa401dea787283d5cf794819b23692b0149f57894cc11051e2e81` |
| `collections/invoices.ndjson` | `b57d78a91cf8aee259199a299035f90329502d8fe56eca126d1c9ce27d8afed0` |
| `collections/gridfs-files-manifest.ndjson` | `88d0fd7787115b29eee8617d31ebd4f25071ea41217782cc85d536ed4369f8e1` |
| `collections/workbench_pair_relations.ndjson` | `9c0292c7662e7f0a3f26aa7208a9605863b37ad7351b47854e02d28290cd297c` |
| `collections/workbench_candidate_matches.ndjson` | `48c67a108ddd9f5e8dedf8824f9ca9792ef2ed376779433771487422b6abe783` |
| `collections/oa_attachment_invoice_cache.ndjson` | `57c4edcb6ce62de9003c01474d9de57215f5f91b10aa9d7d6a8fb23280baef13` |

## GridFS Metadata Manifest

- manifest file: `collections/gridfs-files-manifest.ndjson`
- record_count: `462`
- source files collection count: `462`
- source chunks collection count: `726`
- sha256: `88d0fd7787115b29eee8617d31ebd4f25071ea41217782cc85d536ed4369f8e1`

## Warnings / Errors

| severity | code | object_type | message |
| --- | --- | --- | --- |
| `warning` | `EMPTY_COLLECTION` | `file_objects` | Export dataset contains zero records. |
| `warning` | `EMPTY_COLLECTION` | `matching_results` | Export dataset contains zero records. |
| `warning` | `EMPTY_COLLECTION` | `matching_runs` | Export dataset contains zero records. |
| `warning` | `EMPTY_COLLECTION` | `tax_certified_import_batches` | Export dataset contains zero records. |
| `warning` | `EMPTY_COLLECTION` | `tax_certified_import_records` | Export dataset contains zero records. |
| `warning` | `EMPTY_COLLECTION` | `tax_certified_import_sessions` | Export dataset contains zero records. |
| `warning` | `EMPTY_COLLECTION` | `turnover_ledger_extras` | Export dataset contains zero records. |
| `warning` | `EMPTY_COLLECTION` | `workbench_matching_dirty_scopes` | Export dataset contains zero records. |

- errors: none

## 06B Inputs

- manifest_dir: `/tmp/finops-app-mongo-export-06a-20260517`
- manifest_json: `/tmp/finops-app-mongo-export-06a-20260517/manifest.json`
- schema_version: `finops.app_mongo_export_manifest.v1`
- source_database: `fin_ops_platform_app`
- aggregate_sha256: `f5283032a599e2ee72a8583fc31725071ae78f40e02ce4c71ec49d387925343c`

## Safety

- 未访问 OA 源数据库。
- 未导出 secret、完整 URI、用户名或密码。
- 未迁移生产数据，未切换 API。
- 未修改 Rust migration。
