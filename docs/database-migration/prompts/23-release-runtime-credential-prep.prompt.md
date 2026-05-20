# 23 阶段 Codex 执行 Prompt：Release readiness and production PostgreSQL runtime credential/dependency preparation

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 23：基于阶段 22 的 read switch / cutover planning，为后续阶段 24 controlled production read switch 准备正式 release、production PostgreSQL runtime dependency、最小权限 PostgreSQL runtime role/DSN，并执行 no-traffic PostgreSQL mode smoke。

阶段 23 不是 read switch，不是 cutover，不切换 production service backend，不修改 production systemd env/drop-in，不重启 `fin-ops.service`。阶段 23 的目标是证明“正式 release + 正式 runtime dependency + service 可用 PostgreSQL credential”已经准备好，或明确记录 blocker 和用户需要做什么。

## 用户当前授权边界

用户已同意生成并执行阶段 23。当前授权允许：

1. 读取本地代码、文档和 git 状态。
2. 运行本地 release readiness 测试。
3. 通过 SSH 只读读取 production service metadata。
4. 在 production 服务器创建与当前 service 解耦的 release candidate 目录，例如 `/opt/fin-ops/releases/<run_id>/`，用于 no-traffic smoke；不得修改 `/opt/fin-ops/current`。
5. 在 release candidate venv 或 production runtime venv 中安装/验证 `psycopg[binary,pool]==3.3.3`；若要修改 `/opt/fin-ops/venv`，必须先备份 dependency state 并记录，且不得重启 service。
6. 在 production PostgreSQL 创建或更新最小权限 runtime role，例如 `fin_ops_app_runtime`，并授予 app runtime 所需 schema/table/sequence 权限。
7. 生成 runtime DSN secret，并只写入 root-only 临时/准备文件；不得写入 systemd drop-in，不得让当前 service 使用该 DSN。
8. 使用 release candidate + prepared DSN 执行 no-traffic PostgreSQL mode `app.main --check`。
9. 写本地和服务器临时 report artifacts。

当前授权不允许：

1. 修改 `/opt/fin-ops/current`。
2. 修改 `/etc/systemd/system/fin-ops.service` 或 drop-in。
3. 修改 live service env 文件使当前 service 切到 PostgreSQL。
4. 重启、reload、stop 或 start `fin-ops.service`。
5. 切换 `FIN_OPS_APP_STORAGE_BACKEND` 到 live service。
6. 执行 production read switch / cutover。
7. 写 app Mongo `fin_ops_platform_app`。
8. 读取、写入、索引、备份、修复、清洗、迁移或触碰 OA Mongo `form_data_db.form_data`。
9. 输出 SSH 密码、Mongo URI、PostgreSQL URI、role password、token、secret、完整 DSN。

## 必须使用的执行策略

- 主线程负责最终 SSH、artifact 拉取、生产写入边界判断、文档更新和 Gate 判定。
- 可并行执行本地只读代码/文档检查、本地测试、生产只读 metadata 检查。
- 不得让子代理连接生产服务器或处理 secret。
- 所有 secret 必须只在服务器命令内部生成和使用，日志/report 中只能写 redacted DSN。
- 如果需要超出授权边界，例如修改 `/opt/fin-ops/current`、systemd env/drop-in、重启服务或切换 backend，必须停止并记录 blocker。

## 必须先读

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/database-migration/README.md`
- `docs/database-migration/20-production-controlled-runtime-mirror-write-rehearsal.md`
- `docs/database-migration/21-precutover-readonly-p2-closure.md`
- `docs/database-migration/22-production-read-switch-cutover-plan.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`
- `backend/requirements.txt`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/app/main.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_postgres_state_store.py`
- `tests/test_postgres_repositories_core.py`
- `tests/test_postgres_repositories_boundaries.py`
- `tests/test_runtime_state_policy.py`
- `tests/test_shadow_read_rehearsal.py`
- `tests/test_stage15_runtime_tools.py`
- `tests/test_state_store_factory_preflight.py`

## 阶段 23 任务

### 23.1 本地 release readiness

1. 记录：
   - current branch
   - `git rev-parse HEAD`
   - `git status --short`
2. 确认 `backend/requirements.txt` 包含 `psycopg[binary,pool]==3.3.3`。
3. 运行 targeted tests：

```bash
PYTHONPATH=backend/src pytest -q \
  tests/test_postgres_state_store.py \
  tests/test_postgres_repositories_core.py \
  tests/test_postgres_repositories_boundaries.py \
  tests/test_runtime_state_policy.py \
  tests/test_shadow_read_rehearsal.py \
  tests/test_stage15_runtime_tools.py \
  tests/test_state_store_factory_preflight.py
```

4. 运行默认 app check：

```bash
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
```

5. 如时间允许，运行 full test：

```bash
python -m pytest -q
```

阻断条件：

- targeted tests 失败。
- 默认 app check 失败。
- release readiness 无法证明当前代码包含 PostgreSQL migration/cutover 所需模块。

### 23.2 Production service metadata read-only check

只读采集：

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

禁止输出完整 env。可读取 `systemctl cat`，但必须 redact `Environment` / `EnvironmentFile` 行。

阻断条件：

- service 非 active/running。
- service metadata 读取失败。

### 23.3 Release candidate preparation

在服务器创建 release candidate，不改 live current：

- `/opt/fin-ops/releases/<run_id>/src`
- `/opt/fin-ops/releases/<run_id>/venv`
- `/opt/fin-ops/releases/<run_id>/reports`

执行策略：

1. 从本地 worktree 打包 backend code、requirements、必要 project files 到 tar。
2. 上传到 `/tmp/<run_id>.tar.gz`。
3. 解压到 release candidate 目录。
4. 创建 release candidate venv。
5. 安装 `backend/requirements.txt`。
6. 记录 release artifact sha256、解包路径、venv Python version、`psycopg` import result。

阻断条件：

- 无法创建 release candidate。
- requirements 安装失败。
- release candidate venv 无法 import `fin_ops_platform` 或 `psycopg`。
- 任一步需要修改 `/opt/fin-ops/current`。

### 23.4 PostgreSQL runtime role and credential readiness

准备最小权限 runtime role：

- role name: `fin_ops_app_runtime`
- 不授予 superuser。
- 授权 schema:
  - `app`
  - `read_model`
  - `job`
  - `audit`
- `public.schema_migrations` 只读。
- 授权 existing tables：`select, insert, update, delete`。
- 授权 existing sequences：`usage, select, update`。

执行要求：

1. 如果 role 不存在，创建 role。
2. 如果 role 已存在，旋转 password 或记录复用策略。
3. 密码由服务器生成，不写入本地文档、不打印到 stdout/stderr。
4. 将 DSN 写入 root-only credential prep file，例如 `/root/fin_ops_stage23_postgres_runtime.env`，mode `600`。
5. 报告只写 redacted DSN：`postgresql://fin_ops_app_runtime:***@127.0.0.1:5432/fin_ops`。

阻断条件：

- 需要使用 PostgreSQL superuser DSN 给 app runtime。
- role 创建/授权失败。
- credential 文件权限不是 `600`。
- secret 出现在本地 report 或 stdout/stderr。

### 23.5 No-traffic PostgreSQL mode smoke

使用 release candidate，不修改 live service：

```bash
set -a
. /opt/fin-ops/fin-ops.env
. /root/fin_ops_stage23_postgres_runtime.env
set +a
FIN_OPS_APP_STORAGE_BACKEND=postgres \
FIN_OPS_APP_READ_BACKEND=postgres \
FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary_preflight \
PYTHONPATH=/opt/fin-ops/releases/<run_id>/src/backend/src \
/opt/fin-ops/releases/<run_id>/venv/bin/python -m fin_ops_platform.app.main --check
```

要求：

- 只运行 one-off check。
- 不启动 HTTP server。
- 不修改或重启 `fin-ops.service`。
- 不输出完整 DSN。

通过条件：

- exit code `0`。
- readiness JSON status 为 `ready`。
- storage backend 为 `postgres`。
- PostgreSQL health 为 ready。

阻断条件：

- app check 失败。
- PostgreSQL auth/permission error。
- 需要修改 live service 配置才能通过。

### 23.6 Artifact 拉取和文档更新

创建 reports：

- `docs/database-migration/reports/<run_id>.stage23-summary.json`
- `docs/database-migration/reports/<run_id>.service-metadata.txt`
- `docs/database-migration/reports/<run_id>.release-candidate.json`
- `docs/database-migration/reports/<run_id>.postgres-runtime-role.json`
- `docs/database-migration/reports/<run_id>.postgres-mode-check.json`

创建或更新：

- `docs/database-migration/23-release-runtime-credential-prep.md`
- `docs/database-migration/README.md`
- `docs/index.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`

文档必须说明：

1. 本阶段没有 cutover。
2. 本阶段没有修改 `/opt/fin-ops/current`。
3. 本阶段没有修改 systemd env/drop-in。
4. 本阶段没有重启 `fin-ops.service`。
5. 是否修改 `/opt/fin-ops/venv`；若没有，说明使用 release candidate venv。
6. runtime role/DSN 准备结果，DSN 必须 redacted。
7. no-traffic PostgreSQL mode smoke 结果。
8. 下一阶段 controlled read switch 仍需用户单独授权。

## Gate 规则

- `PASS_RELEASE_RUNTIME_CREDENTIAL_READY_REQUIRES_READ_SWITCH_AUTHORIZATION`：
  - targeted local tests pass；
  - release candidate prepared；
  - release candidate venv imports `psycopg`；
  - runtime PostgreSQL role/credential prepared；
  - no-traffic PostgreSQL mode app check pass；
  - live service not modified or restarted；
  - no app Mongo write；
  - OA Mongo `form_data_db.form_data` not touched；
  - next step requires separate read switch authorization。
- `BLOCKED_LOCAL_VERIFICATION`：targeted tests or default app check fail。
- `BLOCKED_RELEASE_CANDIDATE`：release candidate cannot be prepared.
- `BLOCKED_RUNTIME_DEPENDENCY`：release/runtime venv cannot import `psycopg`.
- `BLOCKED_POSTGRES_RUNTIME_ROLE`：role/privilege/credential preparation failed.
- `BLOCKED_NO_TRAFFIC_POSTGRES_SMOKE`：PostgreSQL mode one-off app check failed.
- `BLOCKED_NEEDS_USER_AUTHORIZATION`：需要修改 live service config、restart service、修改 `/opt/fin-ops/current` 或其他超出阶段 23 授权边界的动作。

## 最终回复要求

最终回复必须包含：

1. Gate。
2. run id。
3. production 是否修改：
   - `/opt/fin-ops/current`
   - `/opt/fin-ops/venv`
   - systemd/env
   - `fin-ops.service` restart
   - production PostgreSQL role/privilege
4. no-traffic smoke 结果。
5. 是否还有 blocker。
6. 下一步 controlled read switch 授权边界。
```
