# 阶段 19：Main merge + production fresh import/reconcile

执行时间：2026-05-20

Gate：`BLOCKED_TRANSFORM_NATURAL_KEY_CONFLICT`

## 阶段边界

- 本阶段目标是在生产 PostgreSQL 上执行 fresh app Mongo export、staging import、正式表 transform、reconcile 和进入阶段 20 前的只读验证。
- 本阶段不是 mirror-write、dual-write、switch-read、switch-write 或 cutover。
- 没有修改或重启 production `fin-ops.service`。
- 没有写 app Mongo `fin_ops_platform_app`。
- 没有读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- PostgreSQL 写入仅发生在生产 `fin_ops` 的 migration metadata、`0008` expand-only migration 和 staging import；正式 target transform 在事务内失败并回滚。

## 执行 prompt

- `docs/database-migration/prompts/19-main-production-fresh-import-reconcile.prompt.md`

## Main/worktree 状态

- 当前 worktree 分支：`codex/db-migration`
- 当前 HEAD：`18ca5999 Merge remote-tracking branch 'origin/main' into codex/db-migration`
- 当前 worktree 已包含 `main` 的 `d9e4eff2 feat: group pending invoice table columns`。
- 迁移代码尚未形成可发布提交并合回 `main`；阶段 20 前仍需要先形成可审计 release commit。

## 本地验证

阶段 19 写生产前运行：

```text
tests/test_import_postgres_staging.py
tests/test_postgres_migrations.py
tests/test_postgres_transform.py
tests/test_reconcile_postgres_migration.py
tests/test_shadow_read_rehearsal.py
tests/test_runtime_state_policy.py
```

Result：

```text
46 passed, 20 subtests passed
```

生产 fresh export 首次发现真实 app data 中存在有限 `float`。导出序列化已修正为：

- finite float 输出为 decimal-safe string；
- NaN/Infinity 继续阻断；
- JSON artifact 不输出 JSON number float。

补充验证：

```text
tests/test_mongo_export_manifest.py
tests/test_export_app_mongo.py
tests/test_import_postgres_staging.py
tests/test_postgres_transform.py
tests/test_reconcile_postgres_migration.py
```

Result：

```text
17 passed
```

## Production preflight

Production service before/after：

| Field | Value |
| --- | --- |
| `ActiveState` | `active` |
| `SubState` | `running` |
| `MainPID` | `452671` |
| `WorkingDirectory` | `/opt/fin-ops/current` |

PostgreSQL：

| Item | Value |
| --- | --- |
| PostgreSQL service | `active/running` |
| `psql` | PostgreSQL 16.12 |
| `pg_dump` | PostgreSQL 16.12 |
| Python | 3.11.6 |

Schema migrations after stage 19:

```text
0001,0002,0003,0004,0005,0006,0007,0008
```

## Production PostgreSQL backup

Backup artifact:

- local metadata report: `docs/database-migration/reports/stage19-fresh-production-20260520195220.pg-backup.json`
- server backup dir: `/data/backups/postgres/stage19-fresh-production-20260520195220`

| Item | Value |
| --- | ---: |
| dump bytes | `13318124` |
| dump sha256 | `508e7670a0990f52c71fb0e2f8051b62b82d1c06097212f5731687244a755aff` |

Backup dump remains server-local and is not committed to the repo.

## Fresh export

Fresh app Mongo export completed:

| Item | Value |
| --- | --- |
| export id | `fin_ops_app_export_20260520115838_e5c03820` |
| source database | `fin_ops_platform_app` |
| status | `completed` |
| total records | `12300` |
| manifest sha256 | `00a3bf36bc20f57a8719a3e37ff786d9e0a79d93d3df5f5a0fd0989ae2099632` |
| server export dir | `/data/exports/fin_ops/fin_ops_app_export_20260520115838_e5c03820` |

Local summary report:

- `docs/database-migration/reports/stage19-fresh-production-20260520195220.fresh-export-summary.json`

## Staging import

Fresh export was imported into production PostgreSQL staging:

| Item | Value |
| --- | --- |
| status | `imported` |
| replace existing staging | `true` |
| total records | `12300` |

Local report:

- `docs/database-migration/reports/stage19-fresh-production-20260520195220.staging-import.json`

Post-failure verification confirmed:

```text
staging.mongo_raw_records|12300
```

## Transform blocker

Transform generated a plan but failed during formal target write:

```text
ERROR: duplicate key value violates unique constraint "workbench_pair_relations_case_id_key"
DETAIL: Key (case_id)=(salary_auto_txn_imported_1228) already exists.
```

Interpretation:

- Production PostgreSQL already has `app.workbench_pair_relations` rows from previous production repair.
- The stage 19 transform currently upserts by deterministic `id`.
- `app.workbench_pair_relations` also has a natural unique key on `case_id`.
- At least one fresh export relation has the same `case_id` as an existing row but would be written with a different `id`.
- PostgreSQL correctly rejected the write before commit.

The failed transform ran inside a transaction and did not commit target writes. Post-failure verification:

| Target | Rows |
| --- | ---: |
| `app.invoices` | `391` |
| `app.bank_transactions` | `431` |
| `app.workbench_pair_relations` | `150` |
| `app.workbench_pair_relation_history` | `25` |
| `job.background_jobs` | `114` |

Transform plan artifact:

- `docs/database-migration/reports/stage19-fresh-production-20260520195220.transform-plan.json`

Selected plan deltas:

| Target | Existing | Planned |
| --- | ---: | ---: |
| `app.workbench_pair_relations` | `150` | `150` |
| `app.workbench_pair_relation_history` | `25` | `25` |
| `job.background_jobs` | `114` | `137` |
| `app.file_objects` | `445` | `523` |
| `read_model.workbench_candidate_matches` | `5274` | `1883` |

The plan had 46 known optional warnings, same class as previous stages: duplicate optional invoice fingerprints and missing optional file import batch FK.

## Not executed

Because transform failed, stage 19 did not execute:

- reconciliation;
- production read-only shadow-read;
- runtime policy preflight;
- stage 20 controlled mirror-write rehearsal.

## Reports

- `docs/database-migration/reports/stage19-fresh-production-20260520195220.production-preflight.json`
- `docs/database-migration/reports/stage19-fresh-production-20260520195220.pg-backup.json`
- `docs/database-migration/reports/stage19-fresh-production-20260520195220.fresh-export-summary.json`
- `docs/database-migration/reports/stage19-fresh-production-20260520195220.staging-import.json`
- `docs/database-migration/reports/stage19-fresh-production-20260520195220.transform-plan.json`
- `docs/database-migration/reports/stage19-fresh-production-20260520195220.stage19.aggregate.json`

## Gate

`BLOCKED_TRANSFORM_NATURAL_KEY_CONFLICT`

阶段 20 不能开始。

下一步需要单独做阶段 19A：production transform natural-key remediation。目标是让 transform 对已有 production PostgreSQL rows 使用和 repository 一致的 natural-key upsert 语义，特别是：

- `app.workbench_pair_relations` 按 `case_id` upsert；
- `app.workbench_pair_relation_history` 需要避免 fresh transform 与既有 repair history 重复；
- 其他存在 natural unique key 的表需要同类审计，例如 no-OA batches、exception cases、row overrides、matching runs、pending invoice commands；
- 修复后必须先在本地 disposable PostgreSQL 中构造“已有 repair rows + fresh transform”复现测试，再重新执行生产 transform/reconcile/shadow-read。
