# 16 阶段 Codex 执行 Prompt：Worktree PostgreSQL test onboarding

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 16：先把 worktree 接入 disposable PostgreSQL test DB 做真实运行验证，再明确哪些缺口仍阻止“接近真实使用”的 PostgreSQL mode 测试。阶段 16 必须生成可复用执行记录，证明 schema migration、integration tests、空库 app PostgreSQL smoke 已通过或给出 blocker；同时复核 main 新增 pending invoice 状态是否已纳入 PostgreSQL schema/repository/export/shadow-read 覆盖。

阶段 16 的核心目标：

1. 创建或启动本机 disposable PostgreSQL test DB，建议库名包含 `test`，例如 `fin_ops_worktree_test` 或一次性临时库。
2. 对 test DB apply migrations `0001` 到 `0007`，确认 `public.schema_migrations` 完整。
3. 设置 `FIN_OPS_TEST_DATABASE_URL` 跑真实 PostgreSQL integration tests。
4. 设置 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 和 `FIN_OPS_POSTGRES_DATABASE_URL` 跑空库 app PostgreSQL mode smoke。
5. 明确 app Mongo 数据导入 test DB 的现状：
   - 如果已有安全、可复现、脱敏的 staging import 路径，则执行或给出精确命令；
   - 如果本阶段不导入真实 app Mongo 数据，则记录为未完成项，不得声称真实业务数据已验证。
6. 单独复核 main 新增状态：
   - `pending_invoice_manual_invoice_commands`
   - app settings `bank_transaction_tags`
   - app settings `pending_invoice_tag_groups`
7. 生成阶段 16 文档和必要 report，说明 worktree 上接入 PostgreSQL 测试还差什么，以及下一步是否需要阶段 17。

## 必须使用子代理并行

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责 test DB 启停、migration apply、测试命令执行、文档最终整合和 Gate 判定。
- 子代理只做只读代码/文档分析，不允许写文件、不允许连接生产、不允许读取或打印 secrets。

建议并行任务：

1. Explorer A：只读梳理 PostgreSQL test DB、migration runner、integration tests、app postgres mode env 的事实来源，返回可执行命令和风险。
2. Explorer B：只读梳理 pending invoice 新状态在 `ApplicationStateStore`、`PostgresStateStore`、migrations、export/transform/shadow-read 中的覆盖情况，返回缺口清单。
3. Explorer C：只读梳理 docs/database-migration 阶段 10-15A 的 Gate，判断阶段 16 进入条件是否满足，返回不能声称完成的边界。

## 硬约束

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. app Mongo `fin_ops_platform_app` 默认不访问；如需导入 app Mongo 数据，必须只读并使用既有导出路径，且不得写 app Mongo。
3. production PostgreSQL `fin_ops` 禁止写入。本阶段只允许写 disposable test DB。
4. disposable test DB 名必须包含 `test`，或显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；无法证明是 test DB 时立即停止。
5. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、prompt 或最终输出。
6. 不修改生产 service、不重启生产、不修改 `/opt/fin-ops/current`、不改 systemd。
7. 不进行 cutover、read switch、长期 dual-write 或 production mirror-write。
8. 如果需要新增 schema migration（例如 `0008` 覆盖 pending invoice command），本阶段只记录缺口和建议，不直接新增，除非用户另行授权实现阶段 17。
9. 不把 `P0/P1` 或功能缺口静默降级为“已完成”；必须写明证据和剩余风险。

## 必须先读

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/database-migration/README.md`
- `docs/database-migration/10-shadow-dualwrite-cutover-preflight.md`
- `docs/database-migration/15A-workbench-p0-remediation.md`
- `backend/src/fin_ops_platform/postgres/migrate.py`
- `tests/postgres_test_utils.py`
- `tests/test_postgres_state_store_integration.py`
- `tests/test_app_postgres_mode_integration.py`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/app/server.py`

## 推荐新增/修改文件

- Create: `docs/database-migration/16-worktree-postgres-test-onboarding.md`
- Optional reports:
  - `docs/database-migration/reports/stage16-worktree-postgres-test-<timestamp>.json`
- Modify: `docs/database-migration/README.md` only if adding the stage 16 index is appropriate.

## 串行执行步骤

### 任务 16.1：生成执行上下文

1. 记录 git branch 和 `git status --short`。
2. 读取必须文档和代码。
3. 并行启动只读 Explorer A/B/C。
4. 主线程同时探测本机 PostgreSQL 工具：
   - `which psql`
   - `which initdb`
   - `which pg_ctl`
   - `psql --version`

### 任务 16.2：创建 disposable PostgreSQL test DB

1. 优先启动本机临时 PostgreSQL cluster：
   - 使用 `initdb` 初始化 `$TMPDIR/finops-stage16-*`。
   - 使用 `pg_ctl -D <data_dir> -l <log_file> -o "-F -p <port>" start`。
   - 创建数据库 `fin_ops_worktree_test`。
2. 设置：
   - `FIN_OPS_TEST_DATABASE_URL=<local-disposable-postgres-url>`
   - `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`
3. 如果本机 PostgreSQL 不可用，记录 `BLOCKED_LOCAL_POSTGRES_UNAVAILABLE`，不得改用 production DB 做 destructive tests。

### 任务 16.3：apply migrations 和 schema verification

1. 对 test DB 执行：
   - `PYTHONPATH=backend/src DATABASE_URL="$FIN_OPS_TEST_DATABASE_URL" FIN_OPS_ALLOW_POSTGRES_TEST_DB=1 python -m fin_ops_platform.postgres.migrate apply`
   - `PYTHONPATH=backend/src DATABASE_URL="$FIN_OPS_TEST_DATABASE_URL" python -m fin_ops_platform.postgres.migrate status`
2. 查询 `public.schema_migrations`，确认版本为 `0001,0002,0003,0004,0005,0006,0007`。

### 任务 16.4：真实 PostgreSQL integration tests

运行：

```bash
FIN_OPS_TEST_DATABASE_URL="$FIN_OPS_TEST_DATABASE_URL" \
PYTHONPATH=backend/src \
python -m pytest \
  tests/test_postgres_test_utils.py \
  tests/test_postgres_state_store_integration.py \
  tests/test_app_postgres_mode_integration.py \
  -q
```

通过标准：

- 不允许 skip 掉 PostgreSQL integration，除非阶段 Gate 写成 blocked。
- 测试必须 exit 0。
- 输出不得包含完整 URI 或 password。

### 任务 16.5：空库 app PostgreSQL mode smoke

运行：

```bash
FIN_OPS_APP_STORAGE_BACKEND=postgres \
FIN_OPS_POSTGRES_DATABASE_URL="$FIN_OPS_TEST_DATABASE_URL" \
FIN_OPS_DISABLE_STARTUP_HISTORICAL_ETC_REPAIR=1 \
FIN_OPS_OA_POLLING_ENABLED=0 \
FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED=0 \
PYTHONPATH=backend/src \
python -m fin_ops_platform.app.main --check
```

通过标准：

- `status=ready`
- `storage.backend=postgres`
- `postgres_status=ready`
- `postgres_schema_version>=7`
- 输出不包含完整 URI、password、token、secret。

### 任务 16.6：app Mongo 数据导入 test DB 判定

1. 检查是否存在可直接复用的阶段 03/04 export/import artifact 和命令。
2. 若执行导入，必须只写 disposable test DB，且 app Mongo 只读。
3. 若本阶段不导入，文档必须明确：
   - “空库 PostgreSQL mode 已验证”；
   - “真实 app Mongo 业务数据导入 test DB 尚未完成”；
   - 后续阶段需要执行 normalized export/import + shadow-read/API smoke。

### 任务 16.7：pending invoice coverage gap

复核并记录：

1. `ApplicationStateStore` 是否保存/加载 `pending_invoice_commands`。
2. `PostgresStateStore.load()` / `save()` 是否保存/加载 `pending_invoice_commands`。
3. SQL migrations 是否有 `app.pending_invoice_manual_invoice_commands` 或等价正式表。
4. export/transform/import 是否覆盖该 collection/state。
5. shadow-read domain list 是否覆盖该 state。
6. PostgreSQL integration/API tests 是否覆盖 confirm manual invoice 后 command log survives rebuild。

判定：

- 如果未覆盖，Gate 不得写 `PASS_FOR_REALISTIC_POSTGRES_TESTING`。
- 应建议单独阶段 17：pending invoice PostgreSQL coverage。

### 任务 16.8：文档、report 和最终验证

1. 创建 `docs/database-migration/16-worktree-postgres-test-onboarding.md`。
2. 创建 JSON report，至少包含：
   - run id
   - postgres tools
   - test DB redacted URL
   - migration status
   - integration test command/result
   - app smoke result
   - pending invoice coverage status
   - gate
3. 更新 `docs/database-migration/README.md` 索引。
4. 运行文档/report 敏感信息扫描。
5. 停止并清理临时 PostgreSQL cluster。

## Gate 判定

- `PASS_EMPTY_DB_POSTGRES_SMOKE`：
  - migrations 0001-0007 applied；
  - real PostgreSQL integration tests 通过；
  - empty DB app PostgreSQL mode smoke 通过；
  - 但 app Mongo 真实数据导入和 pending invoice coverage 尚未完成。
- `PASS_REALISTIC_POSTGRES_TESTING`：
  - 上述全部通过；
  - app Mongo 数据已安全导入 disposable test DB；
  - shadow-read/API smoke 通过；
  - pending invoice 新状态已有 PostgreSQL schema/repository/export/shadow-read/test 覆盖。
- `BLOCKED_LOCAL_POSTGRES_UNAVAILABLE`：
  - 本机无法启动 disposable PostgreSQL，且没有安全 test DB。
- `BLOCKED_TEST_FAILURE`：
  - migration、integration 或 app smoke 失败。
- `BLOCKED_PENDING_INVOICE_COVERAGE`：
  - empty DB smoke 可通过，但 pending invoice coverage 缺口阻止真实使用结论。

## 最终输出

用中文报告：

1. 阶段 16 prompt 路径。
2. disposable PostgreSQL test DB 是否创建并清理。
3. migration、integration tests、app PostgreSQL smoke 结果。
4. 是否导入真实 app Mongo 数据；若没有，为什么。
5. pending invoice coverage 缺口。
6. 当前 Gate。
7. 下一步建议。
```
