# 阶段 19A：Production transform natural-key remediation

执行时间：2026-05-20

Gate：`PRODUCTION_RETRY_PASS_CONSERVATIVE_DOMAINS_RUNTIME_P2_REMAINS`

## 阶段边界

- 本阶段目标是修复阶段 19 的 production transform natural-key conflict，使 fresh transform 的写入语义与 PostgreSQL repository 的运行时写入语义一致。
- 本阶段已完成本地代码修复、本地 disposable PostgreSQL 复现测试、本地真实 export transform/reconcile/shadow-read 复核。
- 在用户明确授权后，本阶段已完成 production PostgreSQL transform retry、reconcile、production read-only shadow-read。
- 本阶段 production PostgreSQL 写入范围限于 `staging.id_mappings` 以及 transform 目标表。
- 本阶段没有写 app Mongo `fin_ops_platform_app`。
- 本阶段没有读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- 本阶段没有修改或重启 production `fin-ops.service`。

## 阶段 19 blocker

阶段 19 production fresh transform 在正式 target write 时失败并回滚：

```text
ERROR: duplicate key value violates unique constraint "workbench_pair_relations_case_id_key"
DETAIL: Key (case_id)=(salary_auto_txn_imported_1228) already exists.
```

根因：

- 生产 PostgreSQL 已存在前序 repair/repository 写入的 rows。
- 这些 rows 使用 runtime repository 语义，以 natural key 写入，例如 `app.workbench_pair_relations.case_id`。
- fresh transform 旧实现统一按 deterministic `id` 做 `on conflict (id)`。
- 当 fresh export 中的 row 与既有 production row 有相同 natural key 但不同 UUID 时，PostgreSQL 正确拒绝写入。

## 代码修复

更新文件：

- `backend/src/fin_ops_platform/tools/postgres_transform.py`
- `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `tests/test_postgres_transform.py`
- `tests/test_app_postgres_mode_integration.py`
- `tests/test_postgres_state_store.py`
- `tests/test_reconcile_postgres_migration.py`
- `tests/test_shadow_read_rehearsal.py`

### Natural-key upsert targets

`target_upsert_sql()` 新增表级 conflict target：

| Table | Conflict target |
| --- | --- |
| `app.app_settings` | `settings_key` |
| `app.matching_runs` | `run_id` |
| `app.workbench_pair_relations` | `case_id` |
| `app.workbench_row_overrides` | `row_id, row_type` |
| `app.workbench_exception_cases` | `case_id` |
| `app.no_oa_bank_batches` | `batch_id` |
| `job.workbench_matching_dirty_scopes` | `scope_month` |
| `app.pending_invoice_manual_invoice_commands` | `command_id` |

未列入的表继续使用 `id` 作为 conflict target。

### Replace-style event/history rows

`build_transaction_sql()` 在 target upsert 前新增事务内 refresh prelude。生产 shadow-read 复核后进一步收紧为 full snapshot event table replacement：当 fresh export 带有完整 event/history snapshot 时，事务内先清空对应 event table，再插入 fresh rows。

| Table | Delete key |
| --- | --- |
| `app.workbench_pair_relation_history` | full replace |
| `app.bank_transaction_category_events` | full replace |
| `app.workbench_exception_case_events` | full replace |
| `app.no_oa_bank_batch_events` | full replace |
| `app.turnover_relation_events` | full replace |

目的：

- 避免 fresh transform 与前序 repair/repository history 重复；
- 保持 repository 的 replace-history / replace-audit-log 语义；
- 删除和插入在同一 PostgreSQL transaction 中执行，失败会整体回滚。

### Shadow-read shape/order alignment

生产 shadow-read 发现 `workbench_pair_relation_history` 数量修复后仍有 P0 mismatch。根因不是数据缺失，而是 Mongo meta 数组中部分 history event 缺少 `occurred_at/case_id`，PostgreSQL shadow reader 按 `occurred_at, case_id` 排序会改变原数组顺序。

修复：

- transform 写入 `workbench_pair_relation_history.raw_payload.raw_payload._stage04_child_index`；
- `PsqlShadowReadStore.load_workbench_pair_relations()` 按该 ordinal 读取 history；
- PostgreSQL app settings / psql shadow settings 默认补齐 `bank_transaction_tags` 与 `pending_invoice_tag_groups` 空对象，保持与 Mongo state shape 一致。

### Reconcile stale mapping handling

阶段 19 多次 fresh export/retry 后，`staging.id_mappings` 中存在旧 export 的历史 mapping。reconcile 现在区分：

- current export mappings；
- stale mappings；
- true conflicting mappings。

旧 export stale mappings 不再阻断；同一 current export 的真实冲突仍阻断。

### Integration test alignment

`tests/test_app_postgres_mode_integration.py` 中 PostgreSQL mode settings round-trip 不再硬编码 `bank_transaction_tags.version=3`，改为使用当前 GET 到的版本，符合 main 新增的乐观锁语义。

## Red/green 证据

新增红灯测试先复现旧实现失败：

- `test_target_upsert_sql_casts_jsonb_and_text_values`
- `test_target_upsert_sql_uses_natural_conflict_targets_for_refresh_tables`
- `test_fresh_transform_updates_repaired_workbench_relation_and_replaces_history`
- `test_fresh_transform_updates_existing_natural_key_runtime_tables`

红灯结果：

```text
4 failed, 6 passed
```

关键失败：

```text
duplicate key value violates unique constraint "workbench_pair_relations_case_id_key"
duplicate key value violates unique constraint "workbench_row_overrides_row_uidx"
```

修复后：

```text
tests/test_postgres_transform.py
10 passed
```

## Verification

### 离线相关回归

```bash
PYTHONPATH=backend/src:tests python3 -m pytest \
  tests/test_postgres_transform.py \
  tests/test_import_postgres_staging.py \
  tests/test_reconcile_postgres_migration.py \
  tests/test_shadow_read_rehearsal.py \
  tests/test_postgres_repositories_core.py \
  tests/test_postgres_repositories_boundaries.py \
  -q
```

Result：

```text
30 passed, 2 skipped, 4 subtests passed
```

### Disposable PostgreSQL integration

Test DB：

- `fin_ops_19a_test`
- `127.0.0.1:55443`

Command：

```bash
FIN_OPS_ALLOW_POSTGRES_TEST_DB=1 \
FIN_OPS_TEST_DATABASE_URL=<local-disposable-postgres-url> \
PYTHONPATH=backend/src:tests python3 -m pytest \
  tests/test_postgres_transform.py \
  tests/test_postgres_state_store_integration.py \
  tests/test_app_postgres_mode_integration.py \
  -q
```

Result：

```text
23 passed, 5 warnings, 17 subtests passed
```

### Local full-data transform/reconcile with preexisting repair row

复用阶段 16/18 真实 export：

| Item | Value |
| --- | --- |
| export id | `fin_ops_app_export_20260519235526_5a233544` |
| local export dir | `/tmp/fin_ops_stage18_export/fin_ops_app_export_20260519235526_5a233544` |
| total records | `15494` |

本地 disposable PostgreSQL 中先预置：

- `app.workbench_pair_relations.case_id='CASE-AUTO-0001'`
- `app.workbench_pair_relation_history.case_id='CASE-AUTO-0001'`

随后执行：

1. `0001-0008` migrations；
2. staging import；
3. transform；
4. reconcile；
5. shadow-read smoke。

Result：

| Check | Result |
| --- | --- |
| preexisting relation id preserved | yes |
| `CASE-AUTO-0001` relation count | `1` |
| transform status | `transformed` |
| transform warnings | `46` known optional warnings |
| reconcile status | `pass` |
| reconcile mismatches | `[]` |
| shadow-read gate | `PASS` |
| shadow-read P0/P1/P2 | `0/0/0` |

Shadow-read artifact：

- `docs/database-migration/reports/stage19A-local-natural-key-remediation-20260520.shadow-read.json`

## Production retry execution

用户授权：

```text
我授权执行阶段 19A production PostgreSQL transform retry，基于阶段 19 fresh export
fin_ops_app_export_20260520115838_e5c03820 和已导入的 production staging 数据，
允许写 production PostgreSQL 的 staging.id_mappings 以及 transform 目标表，
不允许写 app Mongo，不允许读取/写入/触碰 OA Mongo form_data_db.form_data，
不允许修改或重启 production fin-ops.service。
transform 后必须执行 reconcile 和 production read-only shadow-read。
```

执行方式：

- 使用服务器临时代码目录：`/tmp/stage19A-production-retry-20260520202738/backend/src`
- 未覆盖 `/opt/fin-ops/current`
- 未修改或重启 `fin-ops.service`
- service 执行前后均为：
  - `MainPID=452671`
  - `ExecMainStartTimestamp=Wed 2026-05-20 16:07:52 CST`
  - `ActiveState=active`
  - `SubState=running`

### Pre-retry backup

生产 PostgreSQL transform retry 前已创建 server-side backup：

- metadata：`docs/database-migration/reports/stage19A-production-retry-20260520202738.pg-backup.json`
- server dump：`/data/backups/postgres/stage19A-production-retry-20260520202738/fin_ops_pre_19A.dump`
- bytes：`13354787`
- sha256：`8c6218facb42f9f8bfc2cc88d70a6f5995aefe10b83313a4817045322cbf49b5`

### Production transform retry

Fresh export：

- `fin_ops_app_export_20260520115838_e5c03820`
- status：`imported`
- manifest total records：`12300`

最终 transform result：

- artifact：`docs/database-migration/reports/stage19A-production-retry-20260520202738.transform-result-2.json`
- status：`transformed`
- warnings：`46` known optional warnings
- `app.workbench_pair_relations`：`150`
- `app.workbench_pair_relation_history`：`25`
- `app.bank_transaction_category_events`：`13`
- `staging.id_mappings total`：`16217`
- `staging.id_mappings current export`：`12803`
- `staging.id_mappings stale`：`3414`

执行中遇到并已修复的生产问题：

1. `workbench_row_overrides.projection_version` 源值可能为非数字字符串，已默认归一为 `1`。
2. fresh transform 后旧 event rows 与 fresh snapshot 重复，已改为 full replacement。
3. `workbench_pair_relation_history` 数组顺序与 PostgreSQL shadow reader 排序不一致，已通过 `_stage04_child_index` 保留原数组顺序。
4. `app_settings` shadow shape 缺少空对象默认值，已补齐。

### Production reconcile

- artifact：`docs/database-migration/reports/stage19A-production-retry-20260520202738.reconcile-2.json`
- status：`pass`
- mismatches：`[]`
- `conflicting_mappings`：`0`
- `current_export_mappings`：`12803`
- `stale_mappings`：`3414`

### Production read-only shadow-read

- artifact：`docs/database-migration/reports/stage19A-production-retry-20260520202738.shadow-read-2.json`
- gate：`PARTIAL`
- compared domains：`8`
- matched domains：`7`
- mismatched domains：`1`
- severity：`P0=0, P1=0, P2=11`

Matched conservative domains：

- `app_settings`
- `pending_invoice_commands`
- `app_health_alerts`
- `workbench_pair_relations`
- `no_oa_bank_batches`
- `bank_transaction_categories`
- `turnover_relations`

Remaining mismatch：

- `background_jobs`：`11` 条 `missing_in_primary`，severity `P2`
- 解释：这是 runtime state 历史 job 差异，属于阶段 14 已要求单独分类的运行态数据，不是 conservative business domain P0/P1 blocker。

### Runtime P2 policy closure

阶段 19A production transform retry 后已单独复跑 runtime policy preflight：

- artifact：`docs/database-migration/reports/stage19A-production-retry-20260520202738.runtime-policy-after-19a.json`
- gate：`PASS`
- `blocked_unknown_count`：`0`
- `background_jobs`：
  - `primary_count=137`
  - `shadow_count=148`
  - `missing_in_primary=11`
  - classification：`cleanup_candidate=11`, `rebuildable=114`, `retention_only=23`
- `app_health_alerts`：
  - `primary_count=11`
  - `shadow_count=11`
  - classification：`retention_only=11`

Runtime state decision：

- 当前剩余 11 条 `background_jobs` P2 全部是 PostgreSQL shadow-only terminal `succeeded` job，且 runtime policy 分类为 `cleanup_candidate`。
- 这些 rows 不是当前 primary 中的 active/attention runtime，不应该 mirror-write 回 primary，也不需要作为 cutover conservative blocker。
- 阶段 19A 接受这些 rows 为已解释、可审计 runtime P2。后续如果希望把 shadow-read 从 `PARTIAL` 变成 `PASS`，应单独做 production PostgreSQL runtime cleanup 阶段：先 dry-run、备份、row-count bound、事务化删除这 11 条 shadow-only terminal jobs，再重跑 runtime policy 和 read-only shadow-read。
- 后续任何执行型 cutover/mirror-write 阶段前仍必须重跑 production read-only shadow-read 和 runtime policy classification；若出现 `P0`、`P1`、read error 或 `blocked_unknown`，必须停止。
- 若出现 `queued/running`，或未确认/未 superseded 的 `failed/partial_success` background job，则必须 mirror-write 或延后切换；这类当前运行态不能按 P2 接受。

## Gate

`PRODUCTION_RETRY_PASS_CONSERVATIVE_DOMAINS_RUNTIME_P2_ACCEPTED`

阶段 19A 的 production transform retry、reconcile、production read-only shadow-read 和 runtime policy closure 已完成。conservative domains 当前无 P0/P1；剩余 `background_jobs` P2 已解释为 shadow-only terminal cleanup candidates，并作为可审计 runtime P2 接受，不阻断下一阶段规划或受控执行前置检查。
