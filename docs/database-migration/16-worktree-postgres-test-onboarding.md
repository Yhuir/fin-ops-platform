# 阶段 16：Worktree PostgreSQL test onboarding

执行时间：2026-05-20

Gate：`BLOCKED_PENDING_INVOICE_COVERAGE`

## 阶段边界

- 本阶段目标是在当前 worktree 上接入 disposable PostgreSQL test DB 做真实运行验证。
- 没有写 production PostgreSQL `fin_ops`。
- 没有写 app Mongo `fin_ops_platform_app`。
- 没有读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- 没有修改或重启 production `fin-ops.service`。
- 没有执行 production mirror-write、dual-write、read switch 或 cutover。
- 本阶段仅写本机临时 PostgreSQL test DB `fin_ops_worktree_test`。
- 使用阶段 03 已生成的 production export artifact 做本机 test DB 导入；未重新连接 app Mongo 导出。

## 执行 prompt

- `docs/database-migration/prompts/16-worktree-postgres-test-onboarding.prompt.md`

## Disposable PostgreSQL test DB

本机工具：

| Tool | Result |
| --- | --- |
| `psql` | `/opt/homebrew/bin/psql` |
| `initdb` | `/opt/homebrew/bin/initdb` |
| `pg_ctl` | `/opt/homebrew/bin/pg_ctl` |
| PostgreSQL version | `17.10` |

Test DB：

| Item | Value |
| --- | --- |
| run id | `stage16-worktree-postgres-test-20260520182420` |
| database | `fin_ops_worktree_test` |
| host | `127.0.0.1` |
| raw URL in docs | redacted |

说明：第一次启动临时 cluster 失败，因为 macOS `$TMPDIR` 路径太长导致 PostgreSQL Unix socket path 超限。随后改用 `/tmp` 作为 socket/base 目录，启动成功。

## Migrations

Applied migrations：

```text
0001 applied extensions_and_schemas
0002 applied core_imports_invoices_bank
0003 applied workbench_relations_exceptions
0004 applied oa_projection_sync
0005 applied tax_etc_turnover_settings_jobs
0006 applied read_models
0007 applied grants
```

`public.schema_migrations` verification：

```text
0001,0002,0003,0004,0005,0006,0007
```

## PostgreSQL integration tests

Command：

```bash
FIN_OPS_TEST_DATABASE_URL=<local-disposable-postgres-url> \
PYTHONPATH=backend/src \
python -m pytest \
  tests/test_postgres_test_utils.py \
  tests/test_postgres_state_store_integration.py \
  tests/test_app_postgres_mode_integration.py \
  -q
```

Result：

```text
15 passed, 5 warnings, 20 subtests passed
```

PostgreSQL integration tests did not skip.

## Empty DB app PostgreSQL smoke

Command：

```bash
FIN_OPS_APP_STORAGE_BACKEND=postgres \
FIN_OPS_POSTGRES_DATABASE_URL=<local-disposable-postgres-url> \
FIN_OPS_DISABLE_STARTUP_HISTORICAL_ETC_REPAIR=1 \
FIN_OPS_OA_POLLING_ENABLED=0 \
FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED=0 \
PYTHONPATH=backend/src \
python -m fin_ops_platform.app.main --check
```

Result：

| Field | Value |
| --- | --- |
| `status` | `ready` |
| `storage.mode` | `postgres` |
| `storage.backend` | `postgres` |
| `storage.postgres_status` | `ready` |
| `storage.postgres_schema_version` | `7` |

## Production export import into local test DB

Reused export：

- export id：`fin_ops_app_export_20260519235526_5a233544`
- source database：`fin_ops_platform_app`
- manifest sha256：`54d14c2ee2c2f09e7fb7c62bd5a6729fbb7dad075c76180f2be3cf2dbc414152`

Local staging import：

| Metric | Result |
| --- | ---: |
| staging records | 15494 |
| status | `imported` |

Stage 04 transform after local fix：

| Metric | Result |
| --- | ---: |
| status | `transformed` |
| staging raw count | 15494 |
| `app.etc_submission_batches` planned count | 5 |

Reconciliation：

| Metric | Result |
| --- | --- |
| status | `pass` |
| mismatches | `[]` |
| id mappings | 16022 |
| invoices | 391 |
| bank transactions | 431 |
| import batches | 6 |
| import batch rows | 897 |
| file objects | 445 |
| import files | 31 |
| no OA batches | 79 |
| workbench pair relations | 142 |
| background jobs | 114 |
| search index rows | 822 |
| workbench candidate matches | 5274 |

Aggregated report：

- `docs/database-migration/reports/stage16-worktree-postgres-test-20260520182420.json`

## ETC transform bug found and fixed locally

Real-data app PostgreSQL check initially failed during `EtcService` hydration:

```text
TypeError: EtcBatch.__init__() missing required fields
```

Root cause：

- `etc_state:etc_submission_batches` export records store submission batch items under `normalized_payload.batches`.
- `postgres_transform.py` incorrectly tried to expand `normalized_payload.submission_batches`.
- Because that key was absent, the generic fallback treated the entire ETC state payload as one submission batch row.
- `PostgresOpsTaxEtcRepository.load_etc_state()` then returned a malformed `batches` entry, causing app startup to fail.

Local fix：

- `backend/src/fin_ops_platform/tools/postgres_transform.py`
  - `etc_state:etc_submission_batches` now expands `payload.batches`.
- `tests/test_postgres_transform.py`
  - added `test_transform_expands_etc_submission_batches_from_batches_snapshot`.

Verification：

```text
python -m pytest tests/test_postgres_transform.py::test_transform_expands_etc_submission_batches_from_batches_snapshot -q
1 passed

python -m py_compile backend/src/fin_ops_platform/tools/postgres_transform.py
PYTHONPATH=backend/src python -m pytest tests/test_postgres_transform.py tests/test_import_postgres_staging.py tests/test_reconcile_postgres_migration.py -q
10 passed
```

## Real-data app PostgreSQL smoke

After the ETC transform fix, the local test DB was reset, transformed again, reconciled again, and app PostgreSQL mode was rechecked.

Result：

| Field | Value |
| --- | --- |
| `status` | `ready` |
| `storage.mode` | `postgres` |
| `storage.backend` | `postgres` |
| `storage.postgres_status` | `ready` |
| `storage.postgres_schema_version` | `7` |

API smoke against imported business data：

| Endpoint | Result |
| --- | --- |
| `GET /health` | 200 |
| `GET /api/session/me` | 200 |
| `GET /api/workbench/settings` | 200 |
| `GET /api/search?q=<redacted>&scope=all&month=all` | 200 |
| `GET /api/etc/invoices` | 200 |

`/api/workbench/settings` response includes the post-main setting groups:

- `bank_transaction_tags`
- `pending_invoice_tag_groups`

## Pending invoice coverage gap

Read-only code review confirmed:

| State | Current PostgreSQL coverage | Gap |
| --- | --- | --- |
| `pending_invoice_manual_invoice_commands` | only `state:full_state` fallback can preserve unknown state keys | no formal table, repository method, export definition, transform target, shadow-read domain, or PostgreSQL API/integration test |
| `bank_transaction_tags` | covered through `app.app_settings.settings_payload` JSONB | missing PostgreSQL-specific round-trip assertion |
| `pending_invoice_tag_groups` | covered through `app.app_settings.settings_payload` JSONB | missing PostgreSQL-specific round-trip assertion |

This means stage 16 proves the worktree can run against PostgreSQL with imported production export data, but it still cannot prove post-main pending invoice command persistence is production-ready.

## Gate rationale

`BLOCKED_PENDING_INVOICE_COVERAGE`

Passed:

- disposable PostgreSQL test DB created;
- migrations `0001` through `0007` applied;
- real PostgreSQL integration tests passed without skip;
- empty DB app PostgreSQL smoke passed;
- existing production export artifact imported into local test DB;
- transform/reconciliation passed with `mismatches=[]`;
- real-data app PostgreSQL check passed;
- lightweight API smoke passed;
- local ETC transform bug was fixed and tested.

Still blocking migration-readiness:

- `pending_invoice_manual_invoice_commands` lacks formal PostgreSQL coverage.
- `bank_transaction_tags` and `pending_invoice_tag_groups` need PostgreSQL-specific round-trip tests.
- Stage 15 production controlled mirror-write rehearsal remains a separate production gate and is not completed by this local worktree test.

## Recommended next stage

Stage 17 should focus on post-main pending invoice PostgreSQL coverage:

1. Add formal PostgreSQL schema for `pending_invoice_manual_invoice_commands`.
2. Add repository/state-store load/save methods.
3. Add export/transform/import coverage.
4. Add shadow-read domain.
5. Add PostgreSQL mode integration/API test for manual invoice confirm and recoverable command log survives app rebuild.
6. Add PostgreSQL settings round-trip test for `bank_transaction_tags` and `pending_invoice_tag_groups`.
