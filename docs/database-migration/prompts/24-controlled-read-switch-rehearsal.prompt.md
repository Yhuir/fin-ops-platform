# 24 阶段 Codex 执行 Prompt：Controlled production read switch planning / rehearsal

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 24：基于阶段 23 已准备好的 release candidate、PostgreSQL runtime role 和 root-only credential file，完成 controlled production read switch 的 same-run preflight rehearsal、dry-run runbook、rollback plan 和授权模板。

阶段 24 本次执行不是正式 read switch，不修改 production service 配置，不修改 systemd unit/drop-in/env，不修改 `/opt/fin-ops/current`，不修改 `/opt/fin-ops/venv`，不重启 `fin-ops.service`，不让 live service 使用 PostgreSQL DSN。本阶段的目标是证明“如果用户后续单独授权执行 read switch，当前 release/credential/data gate 已经满足或明确阻断”，并产出下一步 execute 授权所需的最小、可审计操作清单。

## 用户当前授权边界

用户已同意生成并执行阶段 24 prompt。当前授权允许：

1. 读取本地代码、文档和 git 状态。
2. 运行本地测试和 readiness check。
3. 通过 SSH 读取 production service metadata。
4. 使用阶段 23 release candidate 执行 one-off read-only shadow-read、runtime policy classification、cutover preflight 和 no-traffic PostgreSQL mode check。
5. 读取 app Mongo 作为 app primary read-only source，仅用于 shadow-read 对比；不得写 app Mongo。
6. 读取 production PostgreSQL app tables/job/audit/read_model/public.schema_migrations；不得写生产业务表。
7. 写本地 `docs/database-migration/` 文档和 report artifacts。
8. 在服务器 release candidate report 目录写本阶段 report artifacts。

当前授权不允许：

1. 修改 `/opt/fin-ops/current`。
2. 修改 `/opt/fin-ops/venv`。
3. 修改 `/opt/fin-ops/fin-ops.env` 或任何 live service env/drop-in。
4. 修改 `/etc/systemd/system/fin-ops.service` 或 drop-in。
5. 执行 `systemctl restart|reload|stop|start fin-ops.service`。
6. 切换 live `FIN_OPS_APP_STORAGE_BACKEND` / `FIN_OPS_APP_READ_BACKEND`。
7. 修改 production PostgreSQL business data、runtime data、app settings 或 schema。
8. 写 app Mongo `fin_ops_platform_app`。
9. 读取、写入、索引、备份、修复、清洗、迁移或触碰 OA Mongo `form_data_db.form_data`。
10. 输出 SSH 密码、Mongo URI、PostgreSQL URI、role password、token、secret、完整 DSN。

如任何任务需要超出上述边界，必须停止，记录 blocker 和需要用户做什么。

## 必须先读

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/database-migration/README.md`
- `docs/database-migration/22-production-read-switch-cutover-plan.md`
- `docs/database-migration/23-release-runtime-credential-prep.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/tools/run_runtime_state_policy_preflight.py`
- `backend/src/fin_ops_platform/tools/verify_cutover_preflight.py`
- `backend/src/fin_ops_platform/services/cutover_preflight.py`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/app/main.py`

## 可并行任务

只读任务可并行：

- 本地 docs/code inventory：确认阶段 23 release candidate、credential file、required commands。
- 本地 tests/readiness：运行 targeted tests、`app.main --check`。
- Production read-only metadata：采集 service before/after metadata，不输出完整 env。

生产 SSH、secret handling、report 拉取、Gate 判定必须由主线程串行执行，禁止交给子代理。

## 阶段 24 任务

### 24.1 本地 release/read-switch readiness

1. 记录：
   - current branch
   - `git rev-parse HEAD`
   - `git status --short`
2. 确认阶段 23 文档中的 release candidate 存在：
   - `/opt/fin-ops/releases/stage23-release-runtime-20260520233335`
   - `/root/fin_ops_stage23_postgres_runtime.env`
3. 运行本地 targeted tests：

```bash
PYTHONPATH=backend/src pytest -q \
  tests/test_postgres_state_store.py \
  tests/test_postgres_repositories_core.py \
  tests/test_postgres_repositories_boundaries.py \
  tests/test_runtime_state_policy.py \
  tests/test_shadow_read_rehearsal.py \
  tests/test_stage15_runtime_tools.py \
  tests/test_state_store_factory_preflight.py \
  tests/test_cutover_preflight.py \
  tests/test_app_postgres_mode.py
```

4. 运行本地 default app check：

```bash
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
```

阻断条件：

- targeted tests 失败。
- default app check 失败。
- 当前代码无法对应阶段 23 release candidate 或 release artifact。

### 24.2 Production service metadata guard

只读采集 before/after：

```bash
systemctl show fin-ops.service \
  -p User \
  -p Group \
  -p ExecStart \
  -p WorkingDirectory \
  -p ActiveState \
  -p SubState \
  -p MainPID \
  -p ExecMainStartTimestamp
```

要求：

- before/after diff 必须为空。
- `ActiveState=active`、`SubState=running`。
- `MainPID` 和 `ExecMainStartTimestamp` 不应变化。

阻断条件：

- service 非 running。
- before/after 变化表明 service 被重启或配置被改动。

### 24.3 Same-run production read-only shadow-read

使用阶段 23 release candidate 的 venv/code，执行：

```bash
set -a
. /opt/fin-ops/fin-ops.env
set +a

FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 \
PYTHONPATH=/opt/fin-ops/releases/stage23-release-runtime-20260520233335/src/backend/src \
/opt/fin-ops/releases/stage23-release-runtime-20260520233335/venv/bin/python \
  -m fin_ops_platform.tools.run_shadow_read_rehearsal \
  --json \
  --production \
  --require-read-only-guard \
  --primary-backend mongo_readonly \
  --shadow-backend postgres_psql_json \
  --psql-command "sudo -u postgres psql" \
  --postgres-database fin_ops \
  --domains app_settings,pending_invoice_commands,background_jobs,app_health_alerts,workbench_pair_relations,no_oa_bank_batches,bank_transaction_categories,turnover_relations \
  --limit 20 \
  --run-id <run_id> \
  --output <report_dir>/<run_id>.stage24.shadow-read.json
```

继续条件：

- `primary_errors=0`
- `shadow_errors=0`
- `P0=0`
- `P1=0`

允许记录但不阻断：

- 已解释、已接受的 runtime retention-only `P2`，必须在文档中明确列出。

阻断条件：

- 任意 P0/P1/read error。
- 任何涉及 OA adapter/state 的 read method。
- 需要读取、写入或触碰 OA Mongo `form_data_db.form_data`。

### 24.4 Same-run runtime policy classification

使用阶段 23 release candidate，执行：

```bash
set -a
. /opt/fin-ops/fin-ops.env
set +a

FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 \
PYTHONPATH=/opt/fin-ops/releases/stage23-release-runtime-20260520233335/src/backend/src \
/opt/fin-ops/releases/stage23-release-runtime-20260520233335/venv/bin/python \
  -m fin_ops_platform.tools.run_runtime_state_policy_preflight \
  --json \
  --production \
  --primary-backend mongo_readonly \
  --shadow-backend postgres_psql_json \
  --psql-command "sudo -u postgres psql" \
  --postgres-database fin_ops \
  --sample-limit 20 \
  --run-id <run_id> \
  --output <report_dir>/<run_id>.stage24.runtime-policy.json
```

继续条件：

- `gate_recommendation=PASS`
- `blocked_unknown_count=0`

阻断条件：

- `blocked_unknown_count > 0`
- primary/shadow read error

### 24.5 No-traffic PostgreSQL mode check

使用阶段 23 credential file 和 release candidate，不修改 live service：

```bash
set -a
. /opt/fin-ops/fin-ops.env
. /root/fin_ops_stage23_postgres_runtime.env
set +a

FIN_OPS_APP_STORAGE_BACKEND=postgres \
FIN_OPS_APP_READ_BACKEND=postgres \
FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary_preflight \
FIN_OPS_DATA_DIR=/opt/fin-ops/releases/stage23-release-runtime-20260520233335/stage24-data \
PYTHONPATH=/opt/fin-ops/releases/stage23-release-runtime-20260520233335/src/backend/src \
/opt/fin-ops/releases/stage23-release-runtime-20260520233335/venv/bin/python \
  -m fin_ops_platform.app.main --check
```

继续条件：

- exit code `0`
- readiness `status=ready`
- `storage.backend=postgres`
- `postgres_status=ready`

### 24.6 Read-only cutover preflight

使用阶段 23 runtime credential file，执行 read-only preflight：

```bash
set -a
. /root/fin_ops_stage23_postgres_runtime.env
set +a

PYTHONPATH=/opt/fin-ops/releases/stage23-release-runtime-20260520233335/src/backend/src \
/opt/fin-ops/releases/stage23-release-runtime-20260520233335/venv/bin/python \
  -m fin_ops_platform.tools.verify_cutover_preflight \
  --json \
  --no-production-writes
```

继续条件：

- status `pass`。
- PostgreSQL connectivity ready。
- schema version `0008` 或更高。
- no production writes guard enforced。

### 24.7 生成 read switch dry-run runbook 和授权模板

必须生成文档/报告，但不得执行：

1. `docs/database-migration/24-controlled-read-switch-rehearsal.md`
2. `docs/database-migration/reports/<run_id>.stage24-summary.json`
3. `docs/database-migration/reports/<run_id>.stage24.read-switch-execute-plan.md`

execute plan 必须包含：

- 准备修改哪些 production service env/drop-in。
- 使用哪个 release candidate 或 release path。
- 使用哪个 credential file。
- 修改前 backup/freeze 清单。
- exact restart command，但标记为“未执行，需要用户单独授权”。
- post-restart smoke 清单。
- rollback command 模板。
- 停止条件。

### 24.8 文档索引更新

更新：

- `docs/database-migration/README.md`
- `docs/index.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`

## Gate 规则

- `PASS_READ_SWITCH_REHEARSAL_READY_REQUIRES_EXECUTE_AUTHORIZATION`：
  - local targeted tests pass；
  - default app check pass；
  - production service metadata before/after unchanged；
  - same-run shadow-read has P0=0/P1=0/read errors=0；
  - runtime policy PASS and `blocked_unknown=0`；
  - no-traffic PostgreSQL mode app check pass；
  - cutover preflight pass；
  - read switch execute plan generated；
  - no production service config changed；
  - no service restart；
  - no app Mongo write；
  - OA Mongo `form_data_db.form_data` not touched；
  - next step requires explicit execute authorization。
- `BLOCKED_LOCAL_VERIFICATION`
- `BLOCKED_SERVICE_METADATA_CHANGED`
- `BLOCKED_SHADOW_READ`
- `BLOCKED_RUNTIME_POLICY`
- `BLOCKED_POSTGRES_MODE_CHECK`
- `BLOCKED_CUTOVER_PREFLIGHT`
- `BLOCKED_EXECUTE_AUTHORIZATION_REQUIRED`

## 最终回答要求

最终回答必须用中文，说明：

- prompt 路径。
- 阶段 24 run id。
- Gate。
- production service 是否被修改/重启。
- app Mongo 是否写入。
- OA Mongo 是否触碰。
- 关键报告路径。
- 是否可以进入正式 read switch execute 授权阶段，以及仍需用户单独授权的具体事项。
```
