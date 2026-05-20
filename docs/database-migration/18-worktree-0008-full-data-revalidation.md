# 阶段 18：Worktree 0008 full-data revalidation

执行时间：2026-05-20

Gate：`PASS`

## 阶段边界

- 本阶段目标是在阶段 17 新增 `0008` schema 后，重新验证阶段 16 使用过的真实 production export dataset 仍可完整导入、转换、对账并由 app PostgreSQL mode 读取。
- 没有写 production PostgreSQL。
- 没有写 app Mongo `fin_ops_platform_app`。
- 没有读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- 仅通过 SSH 只读复制既有 export artifact。
- PostgreSQL 写入仅发生在本机一次性 disposable test DB `fin_ops_stage18_test`。

## 输入 artifact

复用阶段 16 的 production export：

| Item | Value |
| --- | --- |
| export id | `fin_ops_app_export_20260519235526_5a233544` |
| source database | `fin_ops_platform_app` |
| manifest sha256 | `54d14c2ee2c2f09e7fb7c62bd5a6729fbb7dad075c76180f2be3cf2dbc414152` |
| total records | `15494` |
| remote source | `/data/exports/fin_ops/fin_ops_app_export_20260519235526_5a233544` |
| local temp copy | `/tmp/fin_ops_stage18_export/fin_ops_app_export_20260519235526_5a233544` |

## 前置修正

重跑时发现 `import_postgres_staging.assert_required_migrations()` 的 SQL 仍只查询 `0001-0007`，导致 `0008` schema 被误判为不满足前置条件。

已修正：

- `backend/src/fin_ops_platform/tools/import_postgres_staging.py`
  - migration guard 改为按 `REQUIRED_MIGRATIONS` 动态生成查询和错误信息。
- `tests/test_import_postgres_staging.py`
  - 增加断言，确保 guard SQL 包含 `0008`。

验证：

```text
tests/test_import_postgres_staging.py tests/test_postgres_migrations.py tests/test_postgres_test_utils.py
17 passed, 4 subtests passed
```

## 执行结果

### Migrations

Applied migrations：

```text
0001 applied extensions_and_schemas
0002 applied core_imports_invoices_bank
0003 applied workbench_relations_exceptions
0004 applied oa_projection_sync
0005 applied tax_etc_turnover_settings_jobs
0006 applied read_models
0007 applied grants
0008 applied pending_invoice_commands
```

### Staging import

| Metric | Result |
| --- | ---: |
| status | `imported` |
| total records | `15494` |

### Transform

| Metric | Result |
| --- | ---: |
| status | `transformed` |
| staging raw count | `15494` |
| warnings | `46` |

Warning note：

- Strict `--fail-on-warning` 会阻断此旧 export。
- warnings 为阶段 16 数据集中已有的 optional warning，主要是 `duplicate_optional_unique:app.invoices.data_fingerprint` 与 `missing_optional_fk:app.import_files.import_batch_id`。
- 本阶段按阶段 16 兼容口径继续执行默认 transform，并在 report 中记录 warning count/sample。

### Reconciliation

| Metric | Result |
| --- | --- |
| status | `pass` |
| mismatches | `[]` |

Target count sample：

| Table | Count |
| --- | ---: |
| `app.invoices` | `391` |
| `app.bank_transactions` | `431` |
| `app.import_batches` | `6` |
| `app.import_batch_rows` | `897` |
| `app.file_objects` | `445` |
| `app.import_files` | `31` |
| `app.no_oa_bank_batches` | `79` |
| `app.workbench_pair_relations` | `142` |
| `job.background_jobs` | `114` |
| `read_model.search_index_rows` | `822` |
| `read_model.workbench_candidate_matches` | `5274` |

### App PostgreSQL mode check

Result：

```text
status: ready
storage.mode: postgres
storage.backend: postgres
storage.postgres_status: ready
storage.postgres_database: fin_ops_stage18_test
storage.postgres_schema_version: 8
```

### API smoke

`FIN_OPS_TEST_DEFAULT_AUTH=1` was enabled for local smoke only.

| Endpoint | Result |
| --- | ---: |
| `GET /health` | `200` |
| `GET /api/session/me` | `200` |
| `GET /api/workbench/settings` | `200` |
| `GET /api/search?q=<redacted-query>&scope=all&month=all` | `200` |
| `GET /api/etc/invoices` | `200` |

### Shadow-read smoke

Primary：`PostgresStateStore`

Shadow：`PsqlShadowReadStore`

Domains：

- `app_settings`
- `pending_invoice_commands`
- `background_jobs`
- `app_health_alerts`
- `workbench_pair_relations`
- `no_oa_bank_batches`
- `bank_transaction_categories`
- `turnover_relations`

Result：

```text
gate_recommendation: PASS
total_domains: 8
matched_domains: 8
mismatched_domains: 0
primary_errors: 0
shadow_errors: 0
P0/P1/P2: 0/0/0
```

## Reports

- `docs/database-migration/reports/stage18-worktree-0008-revalidation-20260520191151.json`
- `docs/database-migration/reports/stage18-worktree-0008-revalidation-20260520191151.shadow-read.json`

## 结论

阶段 16 的真实 production export dataset 在 `0008` schema 下重新验证通过。

阶段 17 的 pending invoice PostgreSQL coverage 没有破坏既有 full-data import / transform / reconciliation / app PostgreSQL mode / shadow-read smoke。

下一步可进入“重新做 production read-only preflight / shadow-read rehearsal”的规划；进入任何 production repair、mirror-write、dual-write 或 cutover 前仍需要单独授权。
