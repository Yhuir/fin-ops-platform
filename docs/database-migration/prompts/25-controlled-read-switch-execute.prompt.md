# 25 阶段 Codex 执行 Prompt：Controlled production read switch execute

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 25：在用户明确授权后，尝试进入 controlled production read switch execute。但执行前必须重新运行 same-run production gates；任何 P0/P1/read error/blocked_unknown/实际 PostgreSQL runtime backend mismatch 都必须停止，禁止修改 production service 配置或重启服务。

## 当前授权

用户已回复“同意授权”，授权进入阶段 25 controlled production read switch execute。授权可覆盖以下动作，但只有所有 gate 通过后才允许执行：

1. 修改 production service env/drop-in 或 release pointer，使 live service 使用阶段 23 release candidate。
2. 使用 `/root/fin_ops_stage23_postgres_runtime.env` 作为 live service PostgreSQL credential source。
3. 执行 `systemctl daemon-reload`。
4. 执行 `systemctl restart fin-ops.service`。
5. 执行 post-switch smoke 和 rollback validation。

## 硬停止条件

在任何 production service 配置变更、daemon-reload 或 restart 前，必须停止于以下任一条件：

- same-run shadow-read 出现 P0/P1/read error。
- runtime policy 出现 `blocked_unknown > 0`。
- no-traffic PostgreSQL mode check 失败。
- cutover preflight 失败。
- 使用真实 `PostgresStateStore` backend 的 full-domain shadow-read 出现 P0/P1/read error。
- 需要读取、写入或触碰 OA Mongo `form_data_db.form_data`。

## 必须先读

- `docs/database-migration/23-release-runtime-credential-prep.md`
- `docs/database-migration/24-controlled-read-switch-rehearsal.md`
- `docs/database-migration/reports/stage24-read-switch-rehearsal-20260520233932.stage24.read-switch-execute-plan.md`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `backend/src/fin_ops_platform/services/state_store_factory.py`

## 执行步骤

1. 记录本地 branch、HEAD、dirty state。
2. 读取 production service metadata。
3. 运行 same-run conservative shadow-read，要求 P0/P1/read error 为 0。
4. 运行 runtime policy classification，要求 `PASS` 且 `blocked_unknown=0`。
5. 运行 no-traffic PostgreSQL mode check，要求 `ready`。
6. 运行 cutover preflight，要求 `pass`。
7. 运行真实 `PostgresStateStore` backend full-domain shadow-read：

```bash
set -a
. /opt/fin-ops/fin-ops.env
. /root/fin_ops_stage23_postgres_runtime.env
set +a
FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 \
FIN_OPS_DATA_DIR=/opt/fin-ops/releases/stage23-release-runtime-20260520233335/<run_id>-data \
PYTHONPATH=/opt/fin-ops/releases/stage23-release-runtime-20260520233335/src/backend/src \
/opt/fin-ops/releases/stage23-release-runtime-20260520233335/venv/bin/python \
  -m fin_ops_platform.tools.run_shadow_read_rehearsal \
  --json \
  --production \
  --require-read-only-guard \
  --primary-backend mongo_readonly \
  --shadow-backend postgres \
  --limit 20 \
  --run-id <run_id> \
  --output <report_dir>/<run_id>.stage25.full-shadow-read-postgres.json
```

8. 如果步骤 7 出现 P0/P1/read error，必须停止，不得修改 service。
9. 只有全部 gate 通过后，才允许进入 service backup/freeze、drop-in 写入、daemon-reload、restart 和 post-switch smoke。

## 本次阶段 25 已发现的 blocker

当前执行在步骤 7 停止：

- Full-domain `PostgresStateStore` shadow-read Gate：`BLOCKED`
- P0：`20`
- P1：`77`
- P2：`3`
- read errors：`0`
- 受影响 domain：
  - `workbench_pair_relations`
  - `turnover_ledger_extras`
  - `workbench_read_models`
  - `workbench_candidate_matches`
  - `cost_statistics_read_models`
  - `tax_offset_read_models`
  - `etc_state`
  - `etc_reconciliation_state`
  - `historical_etc_repair_parsed_seeds`
  - `historical_etc_repair_states`

因此本次阶段 25 不允许执行 service config 修改、daemon-reload 或 restart。

## Gate

本次阶段 25 Gate：

- `BLOCKED_FULL_POSTGRES_STORE_SHADOW_READ`

下一步应单独进入阶段 25A：actual PostgreSQL store shadow remediation，修复真实 `PostgresStateStore` runtime shape 与 app Mongo primary 的 P0/P1 差异后，再重新申请 read switch execute 授权。
```
