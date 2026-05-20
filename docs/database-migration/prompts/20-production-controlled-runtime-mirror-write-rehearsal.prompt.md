# 20 阶段 Codex 执行 Prompt：Production controlled runtime mirror-write rehearsal dry-run

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 20：基于阶段 19A 已完成的 production transform/reconcile/shadow-read 和 runtime P2 policy closure，完成 production controlled runtime mirror-write rehearsal 的前置检查和 dry-run。阶段 20 当前只执行到 dry-run；真正写 production PostgreSQL runtime state 前必须停止并请求用户单独授权。

阶段 20 不是 cutover，不切换 production read/write backend，不启用长期 dual-write，不修改或重启 production `fin-ops.service`。

## 用户当前授权边界

用户已同意：

1. 生成阶段 20 给 Codex 执行的 prompt。
2. 执行阶段 20 到 production controlled runtime mirror-write dry-run。
3. 真正写 production PostgreSQL runtime state 前必须停止并请求单独授权。

当前授权允许：

1. 只读读取 app Mongo primary state，用于 shadow-read、runtime policy classification 和 mirror-write dry-run plan。
2. 只读读取 production PostgreSQL，用于 shadow-read、runtime policy classification、target count 和 dry-run plan。
3. 将当前 worktree 的只读/dry-run runner 临时同步到服务器 `/tmp/stage20-*` 目录执行。
4. 写本地和服务器临时 report artifact。

当前授权不允许：

1. 写 app Mongo `fin_ops_platform_app`。
2. 读取、写入、索引、备份、修复、清洗、迁移或触碰 OA Mongo `form_data_db.form_data`。
3. 写 production PostgreSQL runtime target。包括但不限于：
   - `job.background_jobs`
   - `audit.app_health_alerts`
   - `app.app_settings` 中 `settings_key in ('state:background_jobs','state:app_health_alerts')`
4. 修改 `/opt/fin-ops/current`、production env、systemd unit/drop-in、service 配置。
5. 重启 production `fin-ops.service`。
6. 切换 production read/write backend，启用 cutover、dual-write 或长期 mirror-write flag。
7. 输出或写入 SSH 密码、Mongo URI、PostgreSQL URI、token、secret、完整 DSN。

## 必须使用的执行策略

- 主线程负责最终 production SSH、artifact 拉取、文档更新和 Gate 判定。
- 可使用子代理并行，但子代理只能只读阅读本地代码/文档，不允许写文件、不允许连接服务器、不允许读取或打印 secrets。
- 任何 production 写入动作必须在 dry-run 完成后停止，等待用户明确授权。

## 必须先读

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/database-migration/README.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`
- `docs/database-migration/14-runtime-state-policy-mirror-rehearsal.md`
- `docs/database-migration/15-production-controlled-mirror-write-rehearsal.md`
- `docs/database-migration/19-main-production-fresh-import-reconcile.md`
- `docs/database-migration/19A-production-transform-natural-key-remediation.md`
- `docs/database-migration/reports/stage19A-production-retry-20260520202738.shadow-read-2.json`
- `docs/database-migration/reports/stage19A-production-retry-20260520202738.runtime-policy-after-19a.json`
- 最新 `docs/database-migration/reports/stage20-preflight-*.shadow-read.json`
- 最新 `docs/database-migration/reports/stage20-preflight-*.runtime-policy.json`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/tools/run_runtime_state_policy_preflight.py`
- `backend/src/fin_ops_platform/tools/run_controlled_mirror_write_rehearsal.py`
- `backend/src/fin_ops_platform/services/runtime_state_policy.py`
- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/dual_state_store.py`
- `tests/test_runtime_state_policy.py`
- `tests/test_stage15_runtime_tools.py`
- `tests/test_shadow_read_rehearsal.py`

## 必须执行的本地验证

```bash
PYTHONPATH=backend/src pytest -q \
  tests/test_runtime_state_policy.py \
  tests/test_stage15_runtime_tools.py \
  tests/test_shadow_read_rehearsal.py
```

如果失败，Gate=`BLOCKED_LOCAL_VERIFICATION`，不得连接 production 执行 dry-run。

## 生产执行步骤

### 20.1 本地状态记录

1. 记录 `git status --short`。
2. 记录当前 branch。
3. 不 revert、不覆盖、不清理与本阶段无关的用户改动。

### 20.2 生产只读 service/dependency preflight

通过 SSH 在生产服务器只读采集：

1. `fin-ops.service` 的 `ActiveState`、`SubState`、`MainPID`、`ExecMainStartTimestamp`、`WorkingDirectory`。
2. `/opt/fin-ops/venv/bin/python` 是否可以 import：
   - `fin_ops_platform.tools.run_shadow_read_rehearsal`
   - `fin_ops_platform.tools.run_runtime_state_policy_preflight`
   - `fin_ops_platform.tools.run_controlled_mirror_write_rehearsal`
   - `psycopg`
3. `psql`、`pg_dump` 是否可用。
4. 不输出完整 env，不输出 URI，不输出密码。

若 `psycopg` 不可用且 dry-run runner 需要 `PostgresStateStore`，Gate=`BLOCKED_DEPENDENCY_PSYCOPG`。不得安装依赖，除非用户另行授权。

### 20.3 Same-run production read-only gate

必须重新执行，不允许复用旧报告：

1. production read-only shadow-read：
   - `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`
   - `--production`
   - `--require-read-only-guard`
   - primary：`mongo_readonly`
   - shadow：`postgres_psql_json`
   - domains：
     - `app_settings`
     - `pending_invoice_commands`
     - `background_jobs`
     - `app_health_alerts`
     - `workbench_pair_relations`
     - `no_oa_bank_batches`
     - `bank_transaction_categories`
     - `turnover_relations`
2. production runtime policy classification：
   - primary：`mongo_readonly`
   - shadow：`postgres_psql_json`
   - `sample-limit=20`

阻断条件：

- `primary_errors > 0`
- `shadow_errors > 0`
- `severity_counts.P0 > 0`
- `severity_counts.P1 > 0`
- runtime policy `blocked_unknown_count > 0`

允许继续 dry-run 的条件：

- P0/P1/read error 均为 0；
- runtime policy `gate_recommendation=PASS`；
- 只剩已解释 runtime P2，例如 `background_jobs cleanup_candidate`。

### 20.4 Controlled mirror-write dry-run

只有 20.3 通过后才可执行 dry-run：

```bash
FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 \
PYTHONPATH=<临时代码路径> \
/opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.run_controlled_mirror_write_rehearsal \
  --json \
  --production \
  --dry-run \
  --primary-backend mongo_readonly \
  --mirror-backend postgres \
  --max-background-jobs 5000 \
  --max-app-health-alerts 200 \
  --run-id <run_id> \
  --output <report_dir>/<run_id>.mirror-write-dry-run.json
```

dry-run 不得设置：

- `FIN_OPS_STAGE15_CONTROLLED_MIRROR_WRITE=1`
- `FIN_OPS_STAGE15_BACKUP_CONFIRMED=1`
- `--execute`

dry-run 通过条件：

- `gate_recommendation=DRY_RUN_PASS`
- `executed=false`
- `plan.bound_status=pass`
- `policy_summary.blocked_unknown_count=0`
- planned write methods 只对应 runtime state：
  - `save_background_jobs`
  - `save_app_health_alerts`
- target tables 只包括：
  - `job.background_jobs`
  - `audit.app_health_alerts`
  - `app.app_settings[state:background_jobs,state:app_health_alerts]`

### 20.5 Artifact 拉取和文档更新

Create reports：

- `docs/database-migration/reports/<run_id>.shadow-read.json`
- `docs/database-migration/reports/<run_id>.runtime-policy.json`
- `docs/database-migration/reports/<run_id>.mirror-write-dry-run.json`
- 如 blocked：`docs/database-migration/reports/<run_id>.blocked-summary.json`

Create or update：

- `docs/database-migration/20-production-controlled-runtime-mirror-write-rehearsal.md`
- `docs/database-migration/README.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md` 仅补阶段 20 outcome 链接，不重写历史。

阶段 20 文档必须说明：

1. 本阶段只执行到 dry-run，未写 production PostgreSQL。
2. 未写 app Mongo。
3. 未读取/写入/触碰 OA Mongo `form_data_db.form_data`。
4. 未修改或重启 `fin-ops.service`。
5. service 前后状态。
6. same-run shadow-read 结果。
7. runtime policy 结果。
8. dry-run result 或 blocked 原因。
9. 若 dry-run 通过，下一步需要用户授权的 execute 写入边界。

## Gate 规则

- `DRY_RUN_PASS_REQUIRES_EXECUTE_AUTHORIZATION`：
  - same-run shadow-read 无 P0/P1/read error；
  - runtime policy PASS；
  - controlled mirror-write dry-run PASS；
  - 未执行 production PostgreSQL 写入；
  - 下一步需用户授权 execute。
- `BLOCKED_LOCAL_VERIFICATION`：本地测试失败。
- `BLOCKED_DEPENDENCY_PSYCOPG`：production runner 缺 `psycopg` 或正式 dry-run runner 无法加载。
- `BLOCKED_CONSERVATIVE_P0_P1`：shadow-read 出现 P0/P1。
- `BLOCKED_READ_ERROR`：primary 或 shadow read error。
- `BLOCKED_RUNTIME_POLICY_UNKNOWN`：runtime policy 存在 `blocked_unknown`。
- `BLOCKED_ROW_COUNT_BOUND`：dry-run row-count bound 不通过。

## 最终输出要求

最终回复必须包含：

1. Stage 20 gate。
2. 是否执行了 production PostgreSQL 写入：必须是 `否`。
3. 是否写 app Mongo：必须是 `否`。
4. 是否触碰 OA Mongo `form_data_db.form_data`：必须是 `否`。
5. 是否修改或重启 `fin-ops.service`：必须是 `否`。
6. artifact 路径。
7. 若 dry-run 通过，给出下一步 execute 授权模板；不得自行 execute。
8. 若 blocked，说明原因和用户需要做什么。
```
