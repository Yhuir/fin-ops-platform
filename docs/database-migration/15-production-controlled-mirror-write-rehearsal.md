# 15 Production controlled mirror-write one-off rehearsal

执行时间：2026-05-20

Gate：`BLOCKED_CONSERVATIVE_P0`

## 阶段边界

- 阶段 15 已获得用户授权进入 production controlled mirror-write one-off rehearsal。
- 本阶段先执行 production read-only preflight 和 live runtime policy classification。
- 因 production read-only preflight 出现新的 conservative P0，本阶段没有执行 production mirror-write dry-run、backup 或 write。
- 没有执行 production cutover。
- 没有启用长期 production dual-write、mirror-write、shadow compare 或 read switch。
- 没有修改或重启 production `fin-ops.service`。
- 没有修改 `/etc/systemd/*`、production release、生产运行配置或 `/opt/fin-ops/current`。
- 没有写 app Mongo `fin_ops_platform_app`。
- 没有触碰 OA Mongo `form_data_db.form_data`。
- 没有写 production PostgreSQL `fin_ops`。
- 没有新增 schema migration。

## 承接阶段 14

阶段 14 artifact：

- `docs/database-migration/14-runtime-state-policy-mirror-rehearsal.md`
- `docs/database-migration/reports/stage14-runtime-state-policy.json`

阶段 14 Gate 为 `PASS_FOR_PLANNING`：

- 阶段 13 及之前 P0/P1 已清零。
- `background_jobs` 和 `app_health_alerts` 已有可执行 runtime state classifier。
- `save_background_jobs` 与 `save_app_health_alerts` 已在 mirror-write method list。
- P2-only runtime mismatch gate 固定为 `PARTIAL`。
- 阶段 14 没有生产写入、没有写 app Mongo、没有触碰 OA Mongo、没有修改或重启 service。

阶段 15 启动前已本地复核：

```text
stage14_gate=PASS_FOR_PLANNING
production_dual_write_enabled=false
production_cutover_enabled=false
production_writes_performed=false
oa_mongo_touched=false
app_mongo_written=false
schema_migration_required=false
```

阶段 13 final report 复核：

```text
gate=PARTIAL
matched_domains=5
mismatched_domains=2
primary_errors=0
shadow_errors=0
severity_counts=P0:0,P1:0,P2:13,ignored:0
```

## 本地准备

新增工具：

- `backend/src/fin_ops_platform/tools/run_runtime_state_policy_preflight.py`
- `backend/src/fin_ops_platform/tools/run_controlled_mirror_write_rehearsal.py`

新增测试：

- `tests/test_stage15_runtime_tools.py`

工具行为：

- runtime policy preflight 只读读取 primary/shadow runtime snapshots，输出脱敏 classification report。
- controlled mirror-write rehearsal 默认 `--dry-run`，`--execute` 必须有显式 guard。
- `--execute` 同时要求：
  - `FIN_OPS_STAGE15_CONTROLLED_MIRROR_WRITE=1`
  - `FIN_OPS_STAGE15_BACKUP_CONFIRMED=1`
- `--execute` 只允许调用：
  - `save_background_jobs`
  - `save_app_health_alerts`
- 禁止 cutover/restart/enable-dual-write/write-all 等 flags。
- report 不输出 raw payload，只输出 counts、classification、hash 和 bounded sample。

本地 targeted verification：

```text
python -m pytest tests/test_stage15_runtime_tools.py tests/test_runtime_state_policy.py tests/test_dual_state_store.py tests/test_shadow_read_rehearsal.py tests/test_state_store_factory_preflight.py -q
51 passed, 30 subtests passed
```

本地 PostgreSQL 回归矩阵：

```text
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
32 passed, 11 skipped, 5 warnings, 10 subtests passed
```

默认 app check：

```text
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
status=ready
storage.backend=local_pickle
```

本机 UTF8 disposable PostgreSQL smoke：

```text
runtime-policy PASS
dry-run DRY_RUN_PASS
execute PASS
```

测试结束后临时 PostgreSQL cluster 已 stop 并清理。

## Production preflight

远端临时代码目录：

```text
/tmp/finops-stage15-stage15-mirror-write-20260520164450/
```

目录用途：

- `code/`：阶段 15 one-off 临时代码。
- `reports/`：远端脱敏 report artifact。
- `backup/`：预留 backup 目录；本次未执行 backup。
- `logs/`：命令 stdout/stderr。

生产服务状态：

| Checkpoint | ActiveState | MainPID | WorkingDirectory |
| --- | --- | ---: | --- |
| before | `active` | `452671` | `/opt/fin-ops/current` |
| after read-only preflight | `active` | `452671` | `/opt/fin-ops/current` |

远端能力：

- `/opt/fin-ops/venv/bin/python`: `Python 3.11.6`
- `psql`: available
- `pg_dump`: available
- `psycopg`: missing in production venv

说明：

- `psycopg` 缺失不是 read-only preflight 的 blocker，因为 shadow-read 可使用 `postgres_psql_json` adapter。
- `psycopg` 缺失是 formal `PostgresStateStore` controlled mirror-write execute 的 blocker；在没有临时依赖策略或授权安装依赖前，不应执行 production mirror-write。

## Production read-only shadow-read

Artifact：

- `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.readonly-preflight.json`

结果：

```text
gate=BLOCKED
total_domains=7
matched_domains=4
mismatched_domains=3
primary_errors=0
shadow_errors=0
severity_counts=P0:5,P1:0,P2:13,ignored:0
```

Domain summary：

| Domain | Status | Mismatches | P0 | P1 | P2 |
| --- | --- | ---: | ---: | ---: | ---: |
| `background_jobs` | `mismatched` | 10 | 0 | 0 | 10 |
| `app_health_alerts` | `mismatched` | 3 | 0 | 0 | 3 |
| `workbench_pair_relations` | `mismatched` | 5 | 5 | 0 | 0 |

Blocking P0：

- `workbench_pair_relations`
  - `pair_relation_history.length`
  - 4 个 `pair_relations.candidate:<hash>` `missing_in_shadow`

阶段 15 因此在 production read-only preflight 停止，没有继续 mirror-write dry-run、backup 或 execute。

## Live runtime policy classification

Artifact：

- `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.runtime-policy.json`

结果：

```text
gate=PASS
blocked_unknown_count=0
```

Runtime domain summary：

| Domain | Primary | Shadow | Union | Missing in primary | Missing in shadow | Different | Classification |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `background_jobs` | 135 | 114 | 146 | 11 | 32 | 0 | `cleanup_candidate=11`, `rebuildable=112`, `retention_only=23` |
| `app_health_alerts` | 11 | 8 | 11 | 0 | 3 | 0 | `retention_only=11` |

解释：

- live runtime payload 没有 `blocked_unknown`。
- 当前 `app_health_alerts` 均分类为 `retention_only`，没有 active alert mirror blocker。
- `background_jobs` 的 runtime 差异可分类，但不能绕过 `workbench_pair_relations` 的 P0。

## Artifact redaction

本地扫描：

```text
stage15 readonly-preflight redacted=true, no raw URI, no password/token/secret pattern
stage15 runtime-policy redacted=true, no raw URI, no password/token/secret pattern
```

## Gate 判定

阶段 15 Gate：`BLOCKED_CONSERVATIVE_P0`。

原因：

- production read-only preflight 在 `workbench_pair_relations` 发现 5 个 P0。
- 阶段 15 的 controlled mirror-write 只允许处理 runtime state，不允许修复 business/conservative P0。
- 由于 P0 未清零，不能执行 production mirror-write dry-run、backup 或 write。
- 生产 venv 还缺少 `psycopg`，即使 P0 清零，也需要先解决 formal `PostgresStateStore` one-off runner 的临时依赖策略或获得依赖安装授权。

本阶段未完成项：

- 没有执行 production mirror-write dry-run。
- 没有执行 production backup。
- 没有执行 production controlled mirror-write。
- 没有执行 post-write shadow-read。

这些不是遗漏，而是 safety gate 阻断后的正确停止点。

## 下一步

建议单独做阶段 15A 或阶段 16 前置 remediation：

1. 分析 `workbench_pair_relations` 新增 5 个 P0 是 live drift、阶段 13 repair 后又产生的新数据，还是 adapter/repository shape regression。
2. 只读生成 workbench P0 remediation plan。
3. 若需要 repair production PostgreSQL，必须先 dry-run、backup、row-count bound、事务化，且仍不得写 app Mongo 或 OA Mongo。
4. 修复后重跑 production read-only shadow-read，直到 P0/P1 再次为 0。
5. 解决 production venv `psycopg` 缺失问题：
   - 优先临时目录 dependency strategy，不修改 service venv；
   - 或用户单独授权安装生产 venv dependency；
   - 或重新设计 stage15 execute runner，但必须保持参数化 SQL、白名单 target 和 rollback plan。
6. 之后再重新执行阶段 15 controlled mirror-write one-off rehearsal。
