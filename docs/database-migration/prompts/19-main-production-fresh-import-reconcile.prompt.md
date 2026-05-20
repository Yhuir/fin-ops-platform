# 19 阶段 Codex 执行 Prompt：Main merge + production fresh import/reconcile

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 19：完成 post-main PostgreSQL 迁移代码合并前检查，确认当前 worktree 已包含最新 `main`，然后在生产服务器上执行 production migration preflight、fresh app Mongo 只读 export、production PostgreSQL 备份、`0001-0008` migrations apply、fresh staging import、正式表 transform、reconciliation、production read-only shadow-read 和 runtime policy preflight。阶段 19 完成后，生产 PostgreSQL 必须包含最新 app Mongo snapshot 的可对账数据，且报告明确是否允许进入阶段 20 controlled mirror-write rehearsal。

阶段 19 不是 mirror-write、dual-write、switch-read、switch-write 或 cutover；不得修改生产 service 配置，不得重启生产服务。

## 必须使用子代理并行

- 主线程负责所有写文件、git 决策、生产 SSH、生产 PostgreSQL 写入、最终文档和 Gate 判定。
- 子代理只允许只读阅读本地代码/文档，不允许写文件、不允许连接服务器、不允许读取或打印 secrets。

建议并行任务：

1. Explorer A：只读复核阶段 03/04/17/18/15A 文档和工具命令，返回 production fresh export/import/reconcile 命令清单与 Gate。
2. Explorer B：只读复核当前 worktree 与 `main` 的关系、未提交变更、必须进入 main 的 migration 文件、测试命令和风险。
3. Explorer C：只读复核 shadow-read/runtime policy/preflight 报告格式，返回阶段 19 应生成的 artifact 路径。

## 用户授权边界

用户已同意执行阶段 19。阶段 19 允许：

1. 只读读取 app Mongo `fin_ops_platform_app`，用于 fresh export。
2. 写生产 PostgreSQL `fin_ops` 的 migration/staging/target migration tables，用于 fresh import、transform、reconcile。
3. 在生产 PostgreSQL 写入前创建 server-local backup。
4. 将当前 worktree 的迁移 runner/tools 临时同步到服务器临时目录执行。

阶段 19 不允许：

1. 读取、写入、索引、备份、修复、清洗、迁移 OA Mongo `form_data_db.form_data`。
2. 写 app Mongo `fin_ops_platform_app`。
3. 执行 production mirror-write、dual-write、switch-read、switch-write、cutover。
4. 修改 `/opt/fin-ops/current`、systemd unit、生产 env、生产 service 配置。
5. 重启生产 `fin-ops.service`。
6. 将服务器密码、Mongo URI、PostgreSQL URI、token、secret、完整 DSN 写入文档、日志、prompt 或最终输出。
7. 在 transform/reconcile/shadow-read 有未解释 P0/P1 时进入阶段 20。

## 必须先读

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/database-migration/README.md`
- `docs/database-migration/15A-workbench-p0-remediation.md`
- `docs/database-migration/17-pending-invoice-postgres-coverage.md`
- `docs/database-migration/18-worktree-0008-full-data-revalidation.md`
- `backend/src/fin_ops_platform/postgres/migrate.py`
- `backend/src/fin_ops_platform/postgres/migrations/*.sql`
- `backend/src/fin_ops_platform/tools/export_app_mongo.py`
- `backend/src/fin_ops_platform/tools/import_postgres_staging.py`
- `backend/src/fin_ops_platform/tools/transform_staging_to_postgres.py`
- `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/tools/run_runtime_state_policy_preflight.py`
- `tests/test_postgres_migrations.py`
- `tests/test_import_postgres_staging.py`
- `tests/test_postgres_transform.py`
- `tests/test_reconcile_postgres_migration.py`
- `tests/test_shadow_read_rehearsal.py`

## 目标 artifact

Create:

- `docs/database-migration/19-main-production-fresh-import-reconcile.md`
- `docs/database-migration/reports/stage19-<timestamp>.json`
- `docs/database-migration/reports/stage19-<timestamp>.production-preflight.json`
- `docs/database-migration/reports/stage19-<timestamp>.fresh-export-summary.json`
- `docs/database-migration/reports/stage19-<timestamp>.transform.json`
- `docs/database-migration/reports/stage19-<timestamp>.reconcile.json`
- `docs/database-migration/reports/stage19-<timestamp>.shadow-read.json`
- `docs/database-migration/reports/stage19-<timestamp>.runtime-policy.json`

Modify:

- `docs/database-migration/README.md`

Do not commit backup dumps or export NDJSON payloads into git. Server-local backup/export paths may be documented only as redacted path summaries without secrets.

## 串行执行步骤

### 19.1 本地 main/worktree preflight

1. 记录 branch、`git log --oneline --decorate -5`、`git status --short`。
2. 确认当前 worktree 已 merge 最新 `origin/main`。
3. 如果当前迁移代码还未合入本地 `main`，本阶段只记录 `main_merge_status=worktree_contains_main_but_not_yet_merged_back`；不得因未 commit 就强行切分支或覆盖用户变更。
4. 跑本地最小验证：

```bash
PYTHONPATH=backend/src:tests python3 -m pytest \
  tests/test_import_postgres_staging.py \
  tests/test_postgres_migrations.py \
  tests/test_postgres_transform.py \
  tests/test_reconcile_postgres_migration.py \
  tests/test_shadow_read_rehearsal.py \
  tests/test_runtime_state_policy.py \
  -q
```

5. 如 frontend package 发生变更，确认：

```bash
cd web && npm test -- --run
cd web && npm run build
```

如果本地验证失败，Gate=`BLOCKED_LOCAL_VERIFICATION`，不得写生产 PostgreSQL。

### 19.2 生产只读 preflight

通过 SSH 登录生产服务器，只读采集：

1. `fin-ops.service` active state、MainPID、WorkingDirectory。
2. PostgreSQL service active state。
3. `public.schema_migrations` 当前版本。
4. 生产 PostgreSQL `fin_ops` 当前目标表行数摘要。
5. 当前 app Mongo app-owned database 名称与只读连接可用性。
6. 确认不访问 OA Mongo `form_data_db.form_data`。

将 preflight 写入 report，所有 URI/密码必须 redacted。

### 19.3 临时同步迁移 runner/tools 到服务器

1. 在服务器创建临时目录，例如 `/tmp/fin_ops_stage19_<timestamp>`。
2. 只同步执行迁移所需的最小代码：
   - `backend/src/fin_ops_platform/postgres/`
   - `backend/src/fin_ops_platform/tools/`
   - `backend/src/fin_ops_platform/services/` 中 migration/export/transform/shadow/runtime 所需模块
   - 必要的 `backend/requirements.txt`
3. 不覆盖 `/opt/fin-ops/current`。
4. 不重启 service。
5. 在服务器临时目录用 `python -m py_compile` 校验工具可加载。

### 19.4 生产 PostgreSQL 备份

在任何生产 PostgreSQL 写入前创建 server-local backup：

1. 备份目录：`/data/backups/postgres/stage19_<timestamp>/`。
2. `pg_dump -Fc` 备份 `fin_ops`。
3. 生成 sha256。
4. 记录 backup path、bytes、sha256 到本地 report；不得把 dump 拉入 repo。

备份失败时 Gate=`BLOCKED_BACKUP_FAILED`，不得继续。

### 19.5 fresh app Mongo export

在服务器临时 runner 中执行 fresh export：

```bash
PYTHONPATH=<stage19-runner>/backend/src \
python3 -m fin_ops_platform.tools.export_app_mongo \
  --output /data/exports/fin_ops \
  --source production
```

要求：

1. 只读 app Mongo。
2. 不连接 OA Mongo `form_data_db.form_data`。
3. export manifest 必须包含 schema migration versions `0001-0008`。
4. 记录 export id、source database、record counts、manifest sha256、文件数量。
5. 复制 manifest/counts/checksum 摘要到本地 report；不得提交 NDJSON payload。

export 失败时 Gate=`BLOCKED_EXPORT_FAILED`。

### 19.6 apply production migrations 0001-0008

在生产 PostgreSQL 执行：

```bash
PYTHONPATH=<stage19-runner>/backend/src \
python3 -m fin_ops_platform.postgres.migrate apply
```

要求：

1. 只允许 expand-only migrations。
2. apply 后 `public.schema_migrations` 必须包含 `0001` 到 `0008`。
3. migration 输出不得包含 secret。

失败时 Gate=`BLOCKED_MIGRATION_FAILED`。

### 19.7 import staging

将 fresh export 导入生产 PostgreSQL staging：

```bash
PYTHONPATH=<stage19-runner>/backend/src \
python3 -m fin_ops_platform.tools.import_postgres_staging \
  --export-dir /data/exports/fin_ops/<fresh-export-id> \
  --replace-existing-staging
```

要求：

1. `staging.mongo_exports` 当前 fresh export status=`imported`。
2. `staging.mongo_raw_records` count 与 manifest total records 一致。
3. 不写 app Mongo/OA Mongo。

失败时 Gate=`BLOCKED_STAGING_IMPORT_FAILED`。

### 19.8 transform正式表

执行 transform：

```bash
PYTHONPATH=<stage19-runner>/backend/src \
python3 -m fin_ops_platform.tools.transform_staging_to_postgres \
  --export-id <fresh-export-id> \
  --report-dir /tmp/fin_ops_stage19_<timestamp>/reports
```

要求：

1. transform 不允许 `--replace-existing-target`，除非工具本身以安全方式处理 fresh target refresh；如发现目标表已有数据且工具阻断，停止并记录 Gate。
2. warning 可存在，但必须分类；未解释 P0/P1/blocker 必须停止。
3. 输出 transform report。

失败时 Gate=`BLOCKED_TRANSFORM_FAILED`。

### 19.9 reconciliation

执行 reconcile：

```bash
PYTHONPATH=<stage19-runner>/backend/src \
python3 -m fin_ops_platform.tools.reconcile_postgres_migration \
  --export-id <fresh-export-id> \
  --report-dir /tmp/fin_ops_stage19_<timestamp>/reports
```

通过标准：

- `status=pass`
- `mismatches=[]`
- target counts 与 source counts 可解释一致

失败时 Gate=`BLOCKED_RECONCILE_FAILED`。

### 19.10 production read-only shadow-read

执行 production read-only shadow-read：

```bash
FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 \
PYTHONPATH=<stage19-runner>/backend/src \
python3 -m fin_ops_platform.tools.run_shadow_read_rehearsal \
  --production \
  --require-read-only-guard \
  --primary-backend mongo_readonly \
  --shadow-backend postgres_psql_json \
  --postgres-database fin_ops \
  --output /tmp/fin_ops_stage19_<timestamp>/reports/<run-id>.shadow-read.json \
  --json
```

通过标准：

- conservative domains 无未解释 `P0`/`P1`
- `workbench_pair_relations` matched
- `pending_invoice_commands` matched 或 empty matched
- runtime `P2` 只可在 runtime policy 分类为 accepted 后保留

失败时 Gate=`BLOCKED_SHADOW_READ_P0_P1` 或 `PARTIAL_RUNTIME_ONLY`。

### 19.11 runtime policy preflight

执行 live runtime state classifier：

```bash
FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 \
PYTHONPATH=<stage19-runner>/backend/src \
python3 -m fin_ops_platform.tools.run_runtime_state_policy_preflight \
  --production \
  --shadow-backend postgres_psql_json \
  --postgres-database fin_ops \
  --output /tmp/fin_ops_stage19_<timestamp>/reports/<run-id>.runtime-policy.json \
  --json
```

通过标准：

- `gate_recommendation=PASS`
- `blocked_unknown_count=0`

失败时 Gate=`BLOCKED_RUNTIME_POLICY_UNKNOWN`。

### 19.12 本地拉取摘要报告并写阶段文档

1. 从服务器拉取 JSON report 摘要、transform/reconcile/shadow/runtime policy report。
2. 不拉取 backup dump 和 NDJSON payload。
3. 创建 `docs/database-migration/19-main-production-fresh-import-reconcile.md`。
4. 创建聚合 JSON report。
5. 更新 `docs/database-migration/README.md`。
6. 运行敏感信息扫描：

```bash
rg -n "(PASSWORD|SECRET|TOKEN|KEY|URI)=.*[A-Za-z0-9]|mongodb://|postgresql://|postgres://" docs/database-migration docs/index.md || true
```

## Gate 判定

- `PASS_READY_FOR_STAGE20`：
  - local verification passed；
  - production backup succeeded；
  - fresh export succeeded；
  - migrations `0001-0008` applied；
  - fresh staging import succeeded；
  - transform succeeded；
  - reconciliation passed with no mismatch；
  - production read-only shadow-read has no unexplained P0/P1；
  - runtime policy has no blocked unknown；
  - no app Mongo write；
  - no OA Mongo touch；
  - production service not restarted/modified。

- `PARTIAL_RUNTIME_ONLY_READY_FOR_STAGE20_WITH_CAUTION`：
  - all conservative domains pass；
  - only accepted runtime P2 remains；
  - runtime policy `PASS`。

- `BLOCKED_*`：
  - any local verification, backup, export, migration, import, transform, reconcile, shadow-read P0/P1, or runtime unknown failure。

## 最终输出

用中文报告：

1. 阶段 19 prompt 路径。
2. 是否已包含最新 main，以及是否已真正 merge 回 main。
3. 本地验证结果。
4. 生产 backup/export/migration/import/transform/reconcile/shadow/runtime policy 结果。
5. fresh export id、record count、manifest sha256。
6. 是否写 app Mongo / 是否触碰 OA Mongo。
7. 当前 Gate。
8. 是否可以进入阶段 20 controlled mirror-write rehearsal；若不能，列出阻断原因和用户需要做什么。
```
