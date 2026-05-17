# 迁移合同 blocker closure - 2026-05-17

## 结论

- source report: `docs/operations/backend-refactor/migration-dry-run-report-20260517.json`
- before: `NO_GO` / blocking findings `4932` / legacy_id_coverage `8625/11084`
- after contract check: `GO` / blocking findings `0` / legacy_id_coverage `11084/11084`
- production facts written: `false`
- OA source database accessed: `false`
- readiness gate logic modified: `false`
- secrets recorded: `false`

本报告只关闭 06C migration contract / mapper blocker，不把 06D file checksum 标记为通过，不执行生产切流、双写或 app Mongo 冻结。

## blocker 分类

| category | count |
| --- | ---: |
| `COUNT_MISMATCH` | 10 |
| `INVALID_ENUM` | 2457 |
| `MAPPING_BLOCKER` | 2 |
| `MONTH_MISMATCH` | 2 |
| `STATUS_MISMATCH` | 2 |
| `UNMAPPED_LEGACY_ID` | 2459 |

| dimension | count |
| --- | ---: |
| `legacy_id_coverage` | 2461 |
| `month_distribution` | 2 |
| `record_counts` | 10 |
| `status_distribution` | 2459 |

## dataset / status / month / coverage

| dataset | blocker codes | invalid statuses | month findings | legacy_id_coverage findings |
| --- | --- | --- | --- | ---: |
| `background_jobs` | `COUNT_MISMATCH`=1, `INVALID_ENUM`=6, `MONTH_MISMATCH`=1, `STATUS_MISMATCH`=1, `UNMAPPED_LEGACY_ID`=6 | `acknowledged`=5, `superseded`=1 | `2026-05`=1 | 6 |
| `etc_reconciliation_state` | `MAPPING_BLOCKER`=1, `UNMAPPED_LEGACY_ID`=1 | - | - | 2 |
| `etc_state` | `MAPPING_BLOCKER`=1, `UNMAPPED_LEGACY_ID`=1 | - | - | 2 |
| `file_objects` | `COUNT_MISMATCH`=1 | - | - | 0 |
| `matching_results` | `COUNT_MISMATCH`=1 | - | - | 0 |
| `matching_runs` | `COUNT_MISMATCH`=1 | - | - | 0 |
| `tax_certified_import_batches` | `COUNT_MISMATCH`=1 | - | - | 0 |
| `tax_certified_import_records` | `COUNT_MISMATCH`=1 | - | - | 0 |
| `tax_certified_import_sessions` | `COUNT_MISMATCH`=1 | - | - | 0 |
| `turnover_ledger_extras` | `COUNT_MISMATCH`=1 | - | - | 0 |
| `workbench_candidate_matches` | `INVALID_ENUM`=2420, `UNMAPPED_LEGACY_ID`=2420 | `auto_closed`=53, `conflict`=10, `incomplete`=67, `needs_review`=2167, `suppressed`=123 | - | 2420 |
| `workbench_matching_dirty_scopes` | `COUNT_MISMATCH`=1 | - | - | 0 |
| `workbench_pair_relations` | `COUNT_MISMATCH`=1, `INVALID_ENUM`=31, `MONTH_MISMATCH`=1, `STATUS_MISMATCH`=1, `UNMAPPED_LEGACY_ID`=31 | `active`=31 | `2026-05`=1 | 31 |

- hash blocker findings: `0`

## 合同闭合

| dataset | target tables | status mapping | migration strategy / reason |
| --- | --- | --- | --- |
| `background_jobs` | `job.worker_tasks`, `job.worker_task_acknowledgements` | `acknowledged` -> `succeeded`, `partial_success` -> `succeeded`, `superseded` -> `cancelled` | direct |
| `etc_reconciliation_state` | `audit.events` | - | ETC reconciliation legacy aggregate state is archived as one audit event raw payload; structured task/file/item/event fan-out must be performed from this raw archive in a later dedicated migration step before production cutover. |
| `etc_state` | `audit.events` | - | ETC legacy aggregate state is archived as one audit event raw payload; canonical ETC invoice/import/file facts are covered by invoices, import_batches, file_objects, and GridFS migration evidence. |
| `file_objects` | `app.file_objects`, `app.import_files` | - | direct |
| `matching_results` | `app.reconciliation_case_rows` | - | direct |
| `matching_runs` | `app.reconciliation_cases` | - | direct |
| `tax_certified_import_batches` | `app.import_batches` | - | direct |
| `tax_certified_import_records` | `app.invoice_certifications` | - | direct |
| `tax_certified_import_sessions` | `app.import_batches` | - | direct |
| `turnover_ledger_extras` | `audit.events` | - | direct |
| `workbench_candidate_matches` | `read_model.workbench_candidate_matches` | `auto_closed` -> `active`, `conflict` -> `active`, `incomplete` -> `active`, `needs_review` -> `active`, `suppressed` -> `dismissed` | direct |
| `workbench_matching_dirty_scopes` | `job.worker_tasks` | - | direct |
| `workbench_pair_relations` | `app.reconciliation_cases`, `app.reconciliation_case_rows` | `active` -> `confirmed` | direct |

## 验证命令

- `PYTHONPATH=backend/src python3 -m unittest tests.test_app_mongo_migration_dry_run -v`
- `PYTHONPATH=backend/src python3 scripts/tools/dry_run_app_mongo_migration.py --export-dir /tmp/finops-app-mongo-export-06a-20260517 --migration-run-id a4227942-8eff-4876-8648-be1fbd821f43 --validate-only --report-json-path /tmp/finops-migration-contract-check.json --report-md-path /tmp/finops-migration-contract-check.md`
- `python3 -m json.tool docs/operations/backend-refactor/migration-contract-blocker-closure-20260517.json`

## 剩余风险

- This closure is based on 06A export files and 06C report-only validation; it does not write production app/read_model/job/audit facts.
- 06D file content checksum/sample download remains outside 06C and is not marked passed by this report.
- ETC aggregate states are archived as raw audit payload in this contract; structured fan-out into app.etc_reconciliation_* requires a later dedicated migration contract if production needs queryable task/file/item facts.
