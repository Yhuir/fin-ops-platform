# 阶段 22：Production read switch / cutover planning

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for implementation tasks or `superpowers:executing-plans` for serial execution. 本阶段是规划阶段，不执行 production service 配置变更、不重启服务、不切换事实源。

**Goal:** 将阶段 20/21 已完成的 production mirror-write execute 和 read-only validation 转化为可执行、可回滚、可审计的 PostgreSQL read switch / cutover runbook。

**Architecture:** 正式切换必须分为 release readiness、runtime dependency/credential readiness、same-run read-only gate、backup/freeze、service config switch、smoke validation、rollback/observe 七段。任何会修改 `/opt/fin-ops/current`、`/opt/fin-ops/venv`、systemd/env、service 状态或 production PostgreSQL 的动作，都必须在执行阶段由用户单独授权。

**Tech Stack:** Python 3, systemd, PostgreSQL 16, `psycopg`, existing `fin_ops_platform.app.main`, `run_shadow_read_rehearsal`, `run_runtime_state_policy_preflight`, `verify_cutover_preflight`, production smoke/API checks.

---

## 当前事实

- 阶段 20 已完成 controlled runtime mirror-write execute。
- 阶段 21 已完成 post-execute production read-only validation。
- 当前 conservative domains 无 P0/P1/read error。
- 当前 runtime policy 无 `blocked_unknown`。
- 剩余 `app_health_alerts` P2 已接受为 retention-only runtime state。
- 生产 `fin-ops.service` 当前运行状态：
  - `User=root`
  - `WorkingDirectory=/opt/fin-ops/current`
  - `ExecStart=/opt/fin-ops/venv/bin/python -m fin_ops_platform.app.main --host 127.0.0.1 --port 18001`
  - 当前 `MainPID=452671`
  - 当前 `ExecMainStartTimestamp=Wed 2026-05-20 16:07:52 CST`
- 阶段 20/21 的 one-off PostgreSQL 访问使用 `sudo -u postgres psql` 或 `sudo -u postgres` + Unix socket DSN。
- 正式 service 以 `root` 运行，不能假设能通过 `postgres` peer auth 连接 PostgreSQL。

## 当前不能直接 cutover 的原因

1. **代码发布未完成**
   - 当前 worktree 的 PostgreSQL migration/repository/cutover 代码尚未确认已合并到 `main` 并部署到 `/opt/fin-ops/current`。
   - one-off runner 使用的是服务器 `/tmp/stage19A-production-retry-20260520202738/backend/src` 临时代码，不等价于 production service runtime。

2. **production runtime dependency 未完成**
   - 阶段 20 已证明 `/opt/fin-ops/venv` 原本缺少 `psycopg`。
   - one-off dry-run/execute 使用的是 `/tmp` 临时 virtualenv。
   - 正式 service 切 PostgreSQL 前必须让 `/opt/fin-ops/venv` 或 release venv 能 import `psycopg`。

3. **production service PostgreSQL credential 未完成**
   - service 当前 `User=root`。
   - one-off execute 通过 `sudo -u postgres` 使用 peer auth；service 不能自动复用该认证路径。
   - 切换前必须准备并验证 `FIN_OPS_POSTGRES_DATABASE_URL` 或 `DATABASE_URL`，且该 DSN 对 service runtime user 可用。
   - 推荐创建最小权限 PostgreSQL app role，并授予 app schema 所需权限；不得把超级用户 DSN 写入 service env。

4. **service 配置变更尚未授权**
   - 修改 systemd env/drop-in、修改 `/opt/fin-ops/current`、修改 `/opt/fin-ops/venv`、重启 `fin-ops.service` 都属于执行型生产变更。
   - 当前只完成规划，不执行这些动作。

## 阶段 22 边界

允许：

- 只读读取本地代码和文档。
- 只读读取 production service metadata。
- 编写 read switch / cutover 规划文档和后续 prompt。
- 明确执行前 gate、授权模板、回滚路径和观察期指标。

禁止：

- 修改 `/opt/fin-ops/current`。
- 修改 `/opt/fin-ops/venv`。
- 修改 systemd unit/drop-in/env。
- 重启 `fin-ops.service`。
- 切换 `FIN_OPS_APP_STORAGE_BACKEND`。
- 写 production PostgreSQL。
- 写 app Mongo。
- 读取、写入或触碰 OA Mongo `form_data_db.form_data`。

## 推荐执行路线

### 22A：Release readiness

目标：把当前 worktree 的 PostgreSQL 迁移代码变成可部署 release，而不是继续依赖服务器 `/tmp` 临时代码。

必须完成：

1. 将当前 worktree 变更合并到 `main` 或生成明确 release branch。
2. 在 clean checkout 上运行回归：
   - `python -m pytest -q`
   - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
   - PostgreSQL targeted tests：
     - `tests/test_postgres_state_store.py`
     - `tests/test_postgres_repositories_core.py`
     - `tests/test_postgres_repositories_boundaries.py`
     - `tests/test_runtime_state_policy.py`
     - `tests/test_shadow_read_rehearsal.py`
     - `tests/test_stage15_runtime_tools.py`
     - `tests/test_state_store_factory_preflight.py`
3. 生成 release artifact 或部署包。
4. 记录 release commit、artifact checksum、rollback commit。

阻断条件：

- 任何测试失败。
- 无法证明 release 代码包含阶段 19A、20、21 所需修复。
- release 仍依赖 `/tmp/stage19A-*` 临时代码。

### 22B：Production runtime dependency readiness

目标：让正式 service runtime 能加载 PostgreSQL mode 所需依赖。

执行前必须单独授权，因为会修改 production runtime environment。

推荐策略：

1. 优先使用新 release venv 或可回滚 venv 更新，而不是直接不可追踪修改旧 venv。
2. 安装/确认：
   - `psycopg`
   - `psycopg-binary` 或等价 libpq binary/runtime dependency
3. 执行只读 import check：

```bash
/opt/fin-ops/venv/bin/python - <<'PY'
import psycopg
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
print("postgres-runtime-import-ok")
PY
```

阻断条件：

- `/opt/fin-ops/venv` 无法 import `psycopg`。
- import check 依赖 `/tmp` 临时 venv。
- 依赖安装无 rollback 记录。

### 22C：Production PostgreSQL app credential readiness

目标：准备 service runtime 可用的最小权限 PostgreSQL DSN。

执行前必须单独授权，因为可能会创建/修改 PostgreSQL role/privileges 和 service secret。

推荐策略：

1. 创建最小权限 app role，例如 `fin_ops_app_runtime`。
2. 授权范围应覆盖 app runtime 需要的 schema/table/sequence：
   - `app`
   - `read_model`
   - `job`
   - `audit`
   - `public.schema_migrations` 只读
3. 不授予 PostgreSQL superuser。
4. 不使用 `postgres` 超级用户作为 app DSN。
5. 将 DSN 写入受控 secret/env 文件，禁止在日志、文档或 shell history 中输出完整值。
6. 以 service runtime user 只读验证：

```bash
FIN_OPS_APP_STORAGE_BACKEND=postgres \
FIN_OPS_POSTGRES_DATABASE_URL='<redacted>' \
/opt/fin-ops/venv/bin/python -m fin_ops_platform.app.main --check
```

阻断条件：

- service runtime 无法连接 PostgreSQL。
- DSN 使用超级用户且无风险接受记录。
- DSN 被明文写入文档或命令输出。
- `app.main --check` 在 PostgreSQL mode 失败。

### 22D：Same-run production read-only gate

目标：在任何执行型 read switch 前重新证明数据状态可接受。

每次执行前都必须重新跑，不允许复用旧报告：

```bash
FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 \
PYTHONPATH=<release-code-path> \
/opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.run_shadow_read_rehearsal \
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
  --output <report_dir>/<run_id>.shadow-read.json
```

```bash
FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 \
PYTHONPATH=<release-code-path> \
/opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.run_runtime_state_policy_preflight \
  --json \
  --production \
  --primary-backend mongo_readonly \
  --shadow-backend postgres_psql_json \
  --psql-command "sudo -u postgres psql" \
  --postgres-database fin_ops \
  --sample-limit 20 \
  --run-id <run_id> \
  --output <report_dir>/<run_id>.runtime-policy.json
```

阻断条件：

- `primary_errors > 0`
- `shadow_errors > 0`
- `P0 > 0`
- `P1 > 0`
- runtime policy `blocked_unknown_count > 0`

允许继续条件：

- P0/P1/read error 均为 0。
- runtime policy `PASS`。
- 只剩已解释 retention-only runtime P2。

### 22E：Backup and freeze point

目标：在切换前保留可恢复点。

执行前必须单独授权。

必须备份：

1. production PostgreSQL full logical backup。
2. production PostgreSQL cutover target schema/table subset。
3. app Mongo backup 或确认最近 backup 仍可恢复。
4. 当前 service config/env 备份。
5. 当前 `/opt/fin-ops/current` release 指针或目录快照。

必须记录：

- backup path
- bytes
- sha256
- timestamp
- operator
- restore command

阻断条件：

- PostgreSQL backup 失败。
- app Mongo backup 不存在或不可恢复。
- 无法恢复 service config/env。

### 22F：PostgreSQL mode no-traffic smoke

目标：不改 production service，通过 one-off 命令证明正式 release + 正式 venv + 正式 DSN 可启动 app PostgreSQL mode。

执行前必须满足 22A-22E。

命令模板：

```bash
FIN_OPS_APP_STORAGE_BACKEND=postgres \
FIN_OPS_APP_READ_BACKEND=postgres \
FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary_preflight \
FIN_OPS_POSTGRES_DATABASE_URL='<redacted>' \
/opt/fin-ops/venv/bin/python -m fin_ops_platform.app.main --check
```

阻断条件：

- readiness 不是 `ready`。
- `storage.backend` 不是 `postgres`。
- 出现 PostgreSQL connection/config error。
- 输出泄漏完整 DSN。

### 22G：Controlled service read switch

目标：将 production service 主读写切到 PostgreSQL。

执行前必须由用户单独授权，授权内容至少包括：

- 允许修改 production service env/drop-in。
- 允许设置 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。
- 允许设置 `FIN_OPS_APP_READ_BACKEND=postgres`。
- 允许设置 `FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary`。
- 允许设置 `FIN_OPS_POSTGRES_DATABASE_URL` 或引用受控 secret。
- 允许重启 `fin-ops.service`。
- 明确回滚窗口和回滚责任人。

执行步骤：

1. 记录 service before state。
2. 确认 same-run read-only gate pass。
3. 确认 backup/freeze point pass。
4. 更新 service env/drop-in。
5. `systemctl daemon-reload`。
6. `systemctl restart fin-ops.service`。
7. 等待 service active。
8. 执行 readiness check。
9. 执行 API smoke。
10. 执行 post-switch read-only shadow-read/runtime policy。
11. 记录 service after state。

阻断或回滚条件：

- service 未能 active。
- readiness 失败。
- API smoke 失败。
- post-switch shadow-read 出现 P0/P1/read error。
- runtime policy 出现 `blocked_unknown`。
- logs 出现 PostgreSQL connection/auth/permission error。

### 22H：Rollback

目标：切换失败时恢复到原 production backend。

回滚步骤：

1. 恢复 service env/drop-in 到切换前版本。
2. 恢复：
   - `FIN_OPS_APP_STORAGE_BACKEND` 到原值。
   - `FIN_OPS_APP_READ_BACKEND` 到原值或删除该变量。
   - `FIN_OPS_POSTGRES_CUTOVER_PHASE=rollback` 或删除该变量。
3. `systemctl daemon-reload`。
4. `systemctl restart fin-ops.service`。
5. 执行 readiness。
6. 执行 API smoke。
7. 记录 rollback 后新增业务写入处理策略。

严禁：

- 用旧 app Mongo 全量覆盖 PostgreSQL。
- 在未确认切换窗口内新增写入前破坏 PostgreSQL 数据。
- 写 OA Mongo。

### 22I：Observation window

目标：切换后保留观察窗口，确认 PostgreSQL 作为 app 数据事实源稳定。

建议观察 24-72 小时：

- service restart count
- app error rate
- PostgreSQL connection errors
- slow queries
- import/file API
- workbench API
- search API
- no-OA batch API
- pending invoice commands
- background jobs
- app health alerts
- shadow-read P0/P1/read error
- runtime policy `blocked_unknown`

观察期结束条件：

- 无未解释 P0/P1。
- 无 runtime `blocked_unknown`。
- API smoke 持续通过。
- PostgreSQL backup 策略已确认。
- 回滚路径仍可执行或已正式关闭并记录。

## 后续阶段建议

建议拆成两个后续阶段，不要把 release/deploy 和 service switch 混在一个 prompt：

1. **阶段 23：Release readiness and production PostgreSQL runtime credential/dependency preparation**
   - 合并/部署代码。
   - 准备 production venv dependency。
   - 准备最小权限 PostgreSQL app role/DSN。
   - 执行 no-traffic PostgreSQL mode smoke。
   - 不重启生产服务。
2. **阶段 24：Controlled production read switch**
   - same-run read-only gate。
   - backup/freeze。
   - 修改 service env。
   - restart service。
   - smoke。
   - post-switch validation。
   - rollback 或进入 observation。

## Gate

`PLAN_READY_REQUIRES_RELEASE_AND_EXECUTE_AUTHORIZATION`

阶段 22 只完成 read switch / cutover planning。当前不能直接 cutover；必须先完成 release readiness、production runtime dependency、service PostgreSQL credential、same-run read-only gate、backup/freeze 和 no-traffic PostgreSQL mode smoke。任何 production service 配置变更、`/opt/fin-ops/current` 修改、`/opt/fin-ops/venv` 修改、service restart 或 PostgreSQL role/secret 写入都需要用户单独授权。
