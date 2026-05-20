# 13 Shadow mismatch remediation / backfill repair 执行记录

执行时间：2026-05-20

Gate：`PARTIAL`

## 阶段边界

- 阶段 13 只修复或解释阶段 12 production one-off shadow-read 的 mismatch。
- 没有执行 production cutover。
- 没有启用 production dual-write 或 mirror-write。
- 没有把生产 backend 切到 PostgreSQL、shadow 或 dual。
- 没有修改或重启生产 `fin-ops.service`。
- 没有修改 `/etc/systemd/*`、systemd drop-in、生产配置或 `/opt/fin-ops/current`。
- app Mongo `fin_ops_platform_app` 只作为 read-only primary source。
- OA Mongo `form_data_db.form_data` 未触碰；没有读、写、建索引、清洗、备份或迁移该库/集合。
- 生产 PostgreSQL `fin_ops` 仅写入 app-owned repair 范围：
  - `app.app_settings`
  - `app.workbench_pair_relations`
  - `app.workbench_pair_relation_history`
- 远端临时代码和原始 repair snapshot 已清理；远端保留 PostgreSQL backup 和脱敏 report artifact 用于回滚/审计。

## 承接阶段 12

阶段 12 final report：

- `docs/database-migration/reports/stage12-shadow-read-20260520142049.stage12.shadow-read.json`

阶段 12 Gate 为 `BLOCKED`：

```text
total_domains=7
matched_domains=0
mismatched_domains=7
severity_counts=P0:14,P1:8,P2:12,ignored:0
```

阻塞项：

- `app_settings`：`allowed_usernames` P1。
- `workbench_pair_relations`：history/event wrapper 和 relation payload P0。
- `no_oa_bank_batches`：缺 `schema_version` P0。
- `bank_transaction_categories`：缺 `schema_version/categories/audit_log` P1。
- `turnover_relations`：缺 `schema_version/relations/audit_log` P0。

P2 运行态噪声：

- `background_jobs`
- `app_health_alerts`

## 根因分类

| Domain | 阶段 12 根因 | 阶段 13 处理 |
| --- | --- | --- |
| `app_settings` | `runtime_drift`：阶段 04 backfill 后 live app Mongo allowed users 继续变化 | 以当前 app Mongo read-only snapshot 事务化修复 PostgreSQL `app.app_settings` |
| `workbench_pair_relations` | `transform_backfill_bug` + `repository_load_shape_bug`：history event 被 wrapper 包裹，后续又出现 Decimal/string 类型等价误报 | 修复 transform 展开逻辑、repository/psql shape；以当前 app Mongo snapshot 重建 PostgreSQL pair relations/history |
| `no_oa_bank_batches` | `repository_load_shape_bug`：structured rows 非空时丢 `schema_version` envelope | 修复 native repository 和 psql one-off adapter，最终 matched |
| `bank_transaction_categories` | `repository_load_shape_bug` + empty snapshot/meta handling 缺口 | 修复 empty envelope、audit wrapper 展开和 transform meta snapshot，最终 matched |
| `turnover_relations` | `repository_load_shape_bug` + empty snapshot/meta handling 缺口 | 修复 empty envelope、meta export 和 psql/native shape，最终 matched |
| `background_jobs` | `acceptable_runtime_noise`：PostgreSQL 中保留了 live Mongo 当前未出现的历史/terminal job ids | 保留 P2，不阻塞 controlled rehearsal；后续阶段决定 job retention/cleanup 策略 |
| `app_health_alerts` | `acceptable_runtime_noise`：运行态 health alert 记录 live Mongo 有、shadow 未同步 | 保留 P2，不阻塞 controlled rehearsal；后续阶段决定 health runtime 是否迁移或重建 |

## 本地代码修复

新增/修改：

- `backend/src/fin_ops_platform/services/postgres_snapshot_contracts.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `backend/src/fin_ops_platform/services/state_store_diff.py`
- `backend/src/fin_ops_platform/tools/exporters/workbench.py`
- `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py`
- `backend/src/fin_ops_platform/tools/postgres_transform.py`
- `tests/test_shadow_read_rehearsal.py`
- `tests/test_state_store_diff.py`
- `tests/test_postgres_transform.py`
- `tests/test_export_app_mongo.py`

修复内容：

- 将 app health alerts 统一为 service snapshot contract：`{"records": {...}}`。
- 展开 `pair_relation_history` wrapper，避免把整段 meta snapshot 当成单个 event。
- `no_oa_bank_batches`、`bank_transaction_categories`、`turnover_relations` 空集合时仍返回完整 envelope。
- psql one-off adapter 与 native PostgreSQL loader 复用相同 snapshot contract 规则。
- 阶段 04 export 补齐：
  - `no_oa_bank_batches_meta`
  - `turnover_relations_meta`
- 阶段 04 transform 补齐：
  - `workbench_pair_relations_meta` 展开为逐条 history event。
  - `bank_transaction_categories_meta` 展开 audit log，并保存 `state:bank_transaction_categories` snapshot。
  - `no_oa_bank_batches_meta` 保存 `state:no_oa_bank_batches` snapshot。
  - `turnover_relations_meta` 保存 `state:turnover_relations` snapshot。
- shadow diff 将 `Decimal` 与 JSON string 的同值标量视为等价，避免 value hash 相同但类型不同的误报。

## 本地验证

阶段 13 代码修复后运行：

```text
python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py tests/test_postgres_transform.py tests/test_export_app_mongo.py tests/test_postgres_state_store.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
64 passed, 13 subtests passed
```

追加 Decimal/string diff 修复后运行：

```text
python -m pytest tests/test_state_store_diff.py tests/test_shadow_read_rehearsal.py tests/test_postgres_transform.py tests/test_export_app_mongo.py tests/test_postgres_state_store.py -q
37 passed, 4 subtests passed
```

最终全量验证：

```text
python -m pytest -q
1203 passed, 16 skipped, 5 warnings, 30 subtests passed
```

默认 app check：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
status=ready
storage.backend=local_pickle
```

## Production rehearsal before repair

Artifact：

- `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.shadow-read.json`

结果：

```text
gate=BLOCKED
total_domains=7
matched_domains=3
mismatched_domains=4
severity_counts=P0:10,P1:5,P2:13,ignored:0
service_before=251543:active
service_after=251543:active
```

已通过代码修复清零：

- `no_oa_bank_batches`
- `bank_transaction_categories`
- `turnover_relations`

仍阻塞：

- `app_settings` P1：live Mongo allowed users 与 PostgreSQL 不一致。
- `workbench_pair_relations` P0：PostgreSQL backfill 仍不是当前 live Mongo snapshot。

## Production repair

Repair dry-run artifact：

- `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-dry-run.json`

Dry-run 摘要：

```text
source=app_mongo_readonly
target=production_postgresql_app_owned_tables
allowed_tables=app.app_settings,app.workbench_pair_relations,app.workbench_pair_relation_history
allowed_usernames_count=6
pair_relations_count=142
pair_relation_history_count=17
pair_relations_bound=5000
pair_relation_history_bound=20000
snapshot_sha256=b15ca4dfd16f430428e760e2a212d518dca7a036f3b03e89864c24d5d6e18673
```

Backup：

```text
remote_backup=/tmp/finops-stage13-shadow-read-stage13-shadow-read-20260520150138/reports/stage13-shadow-read-20260520150138.stage13.pg-backup.sql
backup_size_bytes=595301
```

Repair 执行：

- 使用 app Mongo read-only snapshot 生成受控 JSON。
- `pg_dump --data-only --column-inserts` 备份 3 张 app-owned 表。
- 使用固定 SQL、事务、row count bounds 执行 repair。
- 没有写 app Mongo。
- 没有触碰 OA Mongo。
- 没有重启或修改 `fin-ops.service`。

Repair result artifact：

- `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-result.json`

Repair result：

```text
app_settings_rows=2
pair_relations_count=142
pair_relation_history_count=17
expected_pair_relations_count=142
expected_pair_relation_history_count=17
service_before=251543:active
service_after=251543:active
```

## Final production one-off shadow-read

Final artifact：

- `docs/database-migration/reports/stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`

结果：

```text
gate=PARTIAL
total_domains=7
compared_domains=7
matched_domains=5
mismatched_domains=2
primary_errors=0
shadow_errors=0
severity_counts=P0:0,P1:0,P2:13,ignored:0
service_before=251543:active
service_after=251543:active
```

Domain 结果：

| Domain | Status | P0 | P1 | P2 |
| --- | --- | ---: | ---: | ---: |
| `app_settings` | `matched` | 0 | 0 | 0 |
| `background_jobs` | `mismatched` | 0 | 0 | 10 |
| `app_health_alerts` | `mismatched` | 0 | 0 | 3 |
| `workbench_pair_relations` | `matched` | 0 | 0 | 0 |
| `no_oa_bank_batches` | `matched` | 0 | 0 | 0 |
| `bank_transaction_categories` | `matched` | 0 | 0 | 0 |
| `turnover_relations` | `matched` | 0 | 0 | 0 |

## Gate 判定

`PARTIAL`

阶段 13 已完成：

- 阶段 12 及阶段 13 repair 前的所有 P0/P1 均已修复或消除。
- 真实 production one-off shadow-read 已重跑。
- Final report 中 P0/P1 为 0。
- app Mongo 只读。
- OA Mongo `form_data_db.form_data` 未触碰。
- production PostgreSQL 只写 app-owned repair 表，且有 dry-run、backup、row count bound、事务和 post-repair count。
- 生产服务保持 active，PID 未变化。

仍存在：

- `background_jobs` P2：shadow 中存在 primary 当前没有的 job ids，属于运行态/保留策略差异。
- `app_health_alerts` P2：primary 有当前 health alert records，shadow 未同步，属于运行态状态差异。

这些 P2 不阻塞下一阶段 controlled dual-write / mirror-write rehearsal planning，但下一阶段必须明确 runtime state retention 策略：

- background jobs 是否迁移历史/terminal job，还是仅迁移 active/retryable job。
- health alerts 是否作为可重建 runtime 状态，还是在 dual-write rehearsal 中纳入同步。

## 下一步

进入阶段 14：controlled dual-write / mirror-write rehearsal planning。

阶段 14 必须基于本阶段 final report 的事实继续：

- 不得再次修复 P0/P1，除非新 rehearsal 重新出现 P0/P1。
- 先规划 background jobs 和 app health alerts 的 P2 runtime policy。
- 只在受控范围启用 mirror-write/dual-write rehearsal。
- 保留 PostgreSQL backup/rollback 路径，禁止直接 production cutover。
