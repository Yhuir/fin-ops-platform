# 12 阶段 Codex 执行 Prompt：Authorized production shadow-read one-off rehearsal

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 12：基于阶段 11 `PARTIAL` 结果和用户已同意的生产只读演练路径，完成一次“授权后的 production shadow-read one-off rehearsal”。阶段 12 只能临时同步/部署执行 one-off rehearsal 所需代码，不修改生产 systemd 服务、不重启服务、不切换 backend、不启用 dual-write、不执行 cutover。最终必须产出真实 production shadow-read rehearsal report，或明确说明为什么仍无法执行以及用户还需要做什么。

阶段 12 的核心目标：

1. 在不改变生产服务运行状态的前提下，把阶段 11 的 one-off read-only rehearsal CLI/runner 安全放到服务器临时位置。
2. 在服务器上使用生产当前 app primary state source 的只读视图作为 primary，使用生产 PostgreSQL `fin_ops` 作为 shadow。
3. 只运行保守无参数 read-domain 白名单，生成脱敏 JSON/Markdown report artifact。
4. 将 report artifact 安全取回当前 worktree 的 `docs/database-migration/reports/`。
5. 基于真实 production rehearsal report 判定是否存在未解释 P0/P1 mismatch，以及是否可以进入后续 controlled dual-write / mirror-write planning。

阶段 12 不是 dual-write，不是 mirror-write，不是 cutover，不是生产服务配置变更。阶段 12 完成后必须能清楚回答：

1. 生产 one-off shadow-read rehearsal 是否真实执行。
2. primary backend、shadow backend、run id、domain 白名单和 sample/limit 是什么。
3. 每个 domain 的 matched/mismatched/error 状态是什么。
4. 是否存在未解释 P0/P1 mismatch。
5. 如果无法执行，具体 blocker 是代码同步、Python 依赖、Mongo primary read-only 构造、PostgreSQL URL/env、权限、数据差异还是人工授权缺失。

如果阶段 12 无法完全完成，最终输出和文档必须用 `BLOCKED` 或 `PARTIAL` 标明原因。不得把“只同步了代码”“只跑了本地测试”“只做了 production count smoke”包装成 production shadow-read rehearsal 完成。

阶段 12 完成标准：

1. 默认 local/Mongo 模式全量测试通过。
2. `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check` 仍显示默认 `storage.backend=local_pickle`。
3. 阶段 11 runner/CLI tests 通过。
4. 本机 UTF8 disposable PostgreSQL integration 和 local rehearsal CLI smoke 通过。
5. 生产服务 `fin-ops.service` 保持 active，且未被重启、未被修改。
6. 生产 PostgreSQL 只允许只读查询；不得写生产库、truncate、seed、contract write、dual write 或 cutover。
7. app Mongo `fin_ops_platform_app` 只允许只读读取；不得写入、清理、建索引、compact、repair 或 migration。
8. OA Mongo `form_data_db.form_data` 禁止触碰；不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
9. 服务器上只允许写入阶段 12 one-off 临时执行目录和脱敏 report artifact；不得修改 `/etc/systemd/*`、生产 release 目录、生产配置文件、Mongo/PostgreSQL 数据。
10. 所有输出、文档、日志、测试快照和 report 不得包含密码、token、secret、完整 Mongo/PostgreSQL URI 或业务敏感原文 payload。
11. production rehearsal report 必须包含：
    - `run_id`
    - `primary_backend`
    - `shadow_backend`
    - compared domains
    - matched/mismatched/error summary
    - P0/P1/P2/ignored counts
    - redacted mismatch samples up to bounded limit
    - gate recommendation
12. 文档更新为阶段 12 执行记录和 Gate 判定。

你必须使用子代理并行完成可并行任务：

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终集成、生产命令执行、临时代码同步、report 拉取、测试、文档和 Gate 判定。
- 子代理可以只读梳理，也可以作为 worker 修改本地代码/tests/docs；如果让 worker 写代码，必须给出明确文件所有权，避免多个 worker 修改同一文件。
- Worker 必须知道“不是独自在 codebase 中工作”，不得 revert 其他 worker 或用户改动。
- 如果当前 subagent 数量达到上限，先关闭不再需要的旧 agent。

硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；阶段 12 不实现 OA 数据写回，也不把 OA adapter/OA source data 纳入 app shadow-read rehearsal。
3. app Mongo `fin_ops_platform_app` 仅可作为 app primary state 的只读源；不得执行任何写入、清理、建索引、compact、repair、migration、metadata ensure 或 schema 修改。
4. 生产 PostgreSQL `fin_ops` 只能做只读 schema/count/snapshot/rehearsal 查询；不得写库、不得创建表、不得建索引、不得 truncate/delete/update/insert。
5. 阶段 12 不得修改或重启生产 `fin-ops.service`；不得修改 `/etc/systemd/system/fin-ops.service` 或 drop-in；不得修改生产运行配置；不得把生产 backend 切到 PostgreSQL/shadow/dual。
6. 阶段 12 授权范围仅包括 one-off 只读演练所需临时代码同步，例如写入 `/tmp/finops-stage12-shadow-read-<run_id>/`。除非用户另行明确授权，不得写 `/opt/fin-ops/current`、不得覆盖 production release。
7. 临时目录必须可清理。执行结束后如保留远端 report，路径必须记录；如清理远端代码，必须先确认本地已取回 report。
8. 所有 destructive integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；如果无法证明是 test DB，立即停止并记录 `BLOCKED`。
9. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码、prompt 或测试快照。所有 URI 输出必须脱敏。
10. 远端命令不得 `cat` 完整 env/config/secrets 文件。只允许输出 key names、安全状态、脱敏值或由 Python redaction 处理后的 report。
11. PostgreSQL 模式下所有 SQL 必须参数化；禁止用用户输入拼 SQL。只允许对受控 schema/table/domain 名使用白名单拼接。
12. 文件读取必须保持已有兼容：
    - app-owned local path
    - 旧 store：`gridfs://<file_id>/<name>`
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`
    但阶段 12 初始 rehearsal 禁止读取 file bytes；只允许 metadata domains。
13. 不修改前端 DTO、不改 API 返回结构。
14. 不新增 schema migration。
15. 不执行 dual-write、不执行 mirror-write、不执行 production cutover。

阶段 11 已完成事实：

- 阶段 11 Gate：`PARTIAL`。
- 已新增 `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`。
- 已新增 `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`。
- 已新增 `tests/test_shadow_read_rehearsal.py`。
- 本地 runner/CLI + 阶段 10 相关测试通过：`42 passed, 13 subtests passed`。
- 默认全量测试通过：`1197 passed, 16 skipped`。
- 本机 UTF8 disposable PostgreSQL integration 通过：`21 passed`。
- 本机 PostgreSQL shadow rehearsal CLI 通过：`gate=PASS matched=2 domains=2`。
- 生产只读复核：
  - `fin-ops.service=active`
  - `WorkingDirectory=/opt/fin-ops/current`
  - `health_storage_backend=mongo`
  - `health_storage_mode=mongo_only`
  - `health_storage_database=fin_ops_platform_app`
  - `stage10_shadow_file=absent`
  - `stage11_file=absent`
  - `schema_migrations=0001,0002,0003,0004,0005,0006,0007`
  - 核心 counts 顺序为 `import_batches, import_batch_rows, import_files, invoices, bank_transactions, search_index_rows`
  - counts 为 `6,897,31,391,431,822`
- 阶段 11 没有执行真实 production shadow-read rehearsal，因为生产服务器没有阶段 10/11 新增代码，且部署/同步代码当时未获授权。
- 用户现在已同意下一步授权生产只读演练路径。

必须先读的文档：

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `backend/README.md`
- `docs/index.md`
- `docs/dev/index.md`
- `docs/dev/backend.md`
- `docs/dev/testing.md`
- `docs/database-migration/README.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`
- `docs/database-migration/10-shadow-dualwrite-cutover-preflight.md`
- `docs/database-migration/11-production-shadow-read-rehearsal.md`
- `docs/database-migration/reports/stage11-production-shadow-read-rehearsal.blocked.json`

必须先读的代码：

- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `tests/test_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/state_store_diff.py`
- `backend/src/fin_ops_platform/services/shadow_state_store.py`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store_protocol.py`
- `backend/src/fin_ops_platform/tools/verify_cutover_preflight.py`
- `tests/test_state_store_diff.py`
- `tests/test_shadow_state_store.py`
- `tests/test_cutover_preflight.py`
- `tests/test_state_store_factory_preflight.py`
- `tests/test_postgres_state_store_integration.py`
- `tests/test_app_postgres_mode_integration.py`
- `tests/postgres_test_utils.py`

启动步骤：

1. 记录当前 git branch 和 `git status --short`。不要 revert 非本阶段改动。
2. 运行本地基线：
   - `python -m py_compile backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py tests/test_shadow_read_rehearsal.py`
   - `python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q`
   - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
   - `python -m pytest -q`
   - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
3. 检查本机 PostgreSQL 工具：
   - `command -v initdb && command -v pg_ctl && command -v createdb && command -v psql`
4. 如果可用，启动 UTF8 临时 cluster，创建 `fin_ops_stage12_test`，运行真实 integration 和 local rehearsal CLI；测试结束必须 stop cluster 并删除 temp dir。
5. 使用生产只读 smoke 重新确认服务、storage、schema/counts、stage12 临时目录不存在或可安全创建。
6. 使用子代理并行完成以下任务：
   - Explorer A：只读核验生产服务状态、Python/venv、生产 data dir、是否可构造 app Mongo readonly primary，禁止输出 secret。
   - Explorer B：核验 one-off 临时代码同步方案，确认不会写 production release、不会改 systemd、不会重启服务。
   - Worker C：必要时加固 CLI/runner 对 `mongo_readonly`、remote artifact、blocked report 的测试；只改本地代码/tests。
   - Worker D：准备阶段 12 文档模板和 report ingestion/checklist；只改 docs。
   - Explorer E：核验 production PostgreSQL read-only smoke 和 report redaction。
   - 主线程：执行远端临时代码同步、one-off rehearsal、artifact 拉取、最终验证和 Gate。

推荐文件结构：

- Modify: `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py` only if remote one-off needs safer flags or blocked report behavior.
- Modify: `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py` only if production report needs normalization that tests prove.
- Modify: `tests/test_shadow_read_rehearsal.py` for any code changes.
- Create: `docs/database-migration/12-production-shadow-read-oneoff.md`
- Create: `docs/database-migration/reports/<run_id>.stage12.shadow-read.json`
- Create: `docs/database-migration/reports/<run_id>.stage12.shadow-read.md` if markdown report is produced.
- Modify: `docs/database-migration/README.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only to link stage 12 outcome.

生产 one-off 建议执行策略：

1. 本地打包最小执行代码到临时 archive：
   - include `backend/src/fin_ops_platform/`
   - exclude `__pycache__`, `.pytest_cache`, local reports, secrets, `.env`
   - do not include server password or connection strings.
2. SSH 创建远端临时目录：
   - `/tmp/finops-stage12-shadow-read-<run_id>/`
3. 上传 archive 到远端临时目录并解压。
4. 在远端使用现有 venv：
   - `/opt/fin-ops/venv/bin/python`
5. 设置最小安全 env：
   - `PYTHONPATH=/tmp/finops-stage12-shadow-read-<run_id>/backend/src`
   - `FIN_OPS_DATA_DIR=/opt/fin-ops/data`
   - `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`
   - `FIN_OPS_SHADOW_REHEARSAL_RUN_ID=<run_id>`
   - `FIN_OPS_SHADOW_REHEARSAL_LIMIT=<small number, e.g. 10>`
   - production PostgreSQL URL must be provided via existing safe env only if available; do not print it. If not available, use local Postgres socket/peer access only if code supports it or write a temporary redacted-safe env file in `/tmp` with strict permissions and delete it after use. Do not persist secrets.
6. Execute only conservative domains first:
   - `app_settings`
   - `background_jobs`
   - `app_health_alerts`
   - `workbench_pair_relations`
   - `no_oa_bank_batches`
   - `bank_transaction_categories`
   - `turnover_relations`
7. CLI command shape:
   - `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 PYTHONPATH=<tmp>/backend/src /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.run_shadow_read_rehearsal --json --production --primary-backend mongo_readonly --shadow-backend postgres --domains app_settings,background_jobs,app_health_alerts,workbench_pair_relations,no_oa_bank_batches,bank_transaction_categories,turnover_relations --limit 10 --output <remote-report-path>`
8. Pull report back to local:
   - `docs/database-migration/reports/<run_id>.stage12.shadow-read.json`
9. Validate report locally:
   - JSON parse
   - `redacted=true`
   - no secret patterns
   - no raw URI patterns
   - no OA Mongo domain
   - summary/gate present
10. Optional: generate Markdown summary from JSON if not produced remotely.
11. Clean remote temp archive/code if report has been safely pulled back; if keeping remote report, document path.

Important: if constructing `mongo_readonly` cannot work without reading secrets/config values, do not dump secrets. Stop and mark `BLOCKED_MONGO_PRIMARY_READONLY_CONFIG_UNAVAILABLE`.

任务 12.0：安全基线和阶段文档

- [ ] 读完必读文档和代码。
- [ ] 记录 branch 和 dirty worktree。不要 revert 非 12 改动。
- [ ] 运行启动步骤中的本地基线测试。
- [ ] 创建 `docs/database-migration/12-production-shadow-read-oneoff.md`。
- [ ] 文档记录阶段边界：12 只授权临时 one-off 只读演练，不做 cutover，不启用 dual-write，不写生产 PostgreSQL，不写 app Mongo，不触碰 OA Mongo。
- [ ] 文档列出阶段 11 `PARTIAL` 事实、用户已授权 one-off 只读演练路径、本阶段目标。

Acceptance:

- 文档存在。
- 基线结果已记录。
- 如果基线失败，先判断是否与 12 范围相关；相关则修复，不相关则记录风险。

任务 12.1：生产只读预检

Requirements:

- [ ] 只读确认 `fin-ops.service` active。
- [ ] 只读确认 `WorkingDirectory=/opt/fin-ops/current`。
- [ ] 只读确认 `/health` storage 仍是 `mongo/mongo_only/fin_ops_platform_app`。
- [ ] 只读确认生产 PostgreSQL schema/counts：
  - `schema_migrations=0001..0007`
  - counts for six core tables.
- [ ] 只读确认 `/opt/fin-ops/venv/bin/python` 可用。
- [ ] 只读确认 `/tmp` 可创建 stage12 临时目录。
- [ ] 不输出 env values 或 secrets。

Acceptance:

- 预检结果写入阶段 12 文档。
- 如果无法确认 app primary 或 PostgreSQL shadow，停止并记录 `BLOCKED`。

任务 12.2：远端临时代码同步

Requirements:

- [ ] 构造 run id，例如 `stage12-shadow-read-YYYYMMDDHHMMSS`。
- [ ] 本地创建临时 archive，只包含阶段 12 one-off 所需源代码。
- [ ] 远端创建 `/tmp/finops-stage12-shadow-read-<run_id>/`。
- [ ] 上传 archive 并解压到远端临时目录。
- [ ] 验证远端临时目录中存在：
  - `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
  - `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
  - `backend/src/fin_ops_platform/services/state_store.py`
  - `backend/src/fin_ops_platform/services/postgres_state_store.py`
- [ ] 不写 `/opt/fin-ops/current`。
- [ ] 不修改 systemd。
- [ ] 不重启服务。

Acceptance:

- 远端临时代码存在。
- 生产服务仍 active，PID 未因本任务重启。
- 文档记录远端临时目录。

任务 12.3：远端 one-off CLI dry-run / help / import check

Requirements:

- [ ] 使用远端 venv Python 和临时 `PYTHONPATH` 运行：
  - `python -m fin_ops_platform.tools.run_shadow_read_rehearsal --help`
  - Python import check for `ApplicationStateStore`, `PostgresStateStore`, `ShadowReadRehearsalRunner`
- [ ] 设置 `PYTHONDONTWRITEBYTECODE=1`，避免在生产 release 或临时目录留下 pycache；如 pycache 产生在临时目录也可接受，结束清理。
- [ ] 不连接 Mongo/Postgres 做写入。

Acceptance:

- CLI/import 可运行。
- 若依赖缺失，记录 `BLOCKED_REMOTE_DEPENDENCY_MISSING`。

任务 12.4：生产 PostgreSQL shadow backend 只读连接确认

Requirements:

- [ ] 优先使用生产服务已有安全配置或本地 peer auth 构造 PostgreSQL read-only connection。
- [ ] 不输出完整 PostgreSQL URI。
- [ ] 运行 cutover preflight 或等价只读 query，确认 schema/counts。
- [ ] 如果 `FIN_OPS_POSTGRES_DATABASE_URL` 不存在且 CLI 不能连接生产 PostgreSQL，记录 `BLOCKED_POSTGRES_READONLY_CONFIG_UNAVAILABLE`。
- [ ] 如需临时 env 文件传递 PostgreSQL URL，必须：
  - 路径在 `/tmp/finops-stage12-shadow-read-<run_id>/`
  - 权限 `0600`
  - 不打印内容
  - 执行后删除或记录清理

Acceptance:

- 远端 one-off 环境能只读连接 production PostgreSQL。
- 或明确 blocked reason。

任务 12.5：生产 app Mongo primary readonly 构造确认

Requirements:

- [ ] 使用 `FIN_OPS_DATA_DIR=/opt/fin-ops/data` 和 `ApplicationStateStore(read_only=True)` 构造 app primary。
- [ ] 只允许读取 app Mongo `fin_ops_platform_app` state collections。
- [ ] 不调用 `save*`、`store*`、`delete*`、metadata ensure 或 migration repair。
- [ ] 运行一个最小 safe read smoke，例如 `load_app_settings()`，但输出只能是 shape/count/key names，不输出 payload values。
- [ ] 如果缺少 app Mongo config 或读取会触发写入，停止并记录 `BLOCKED_MONGO_PRIMARY_READONLY_CONFIG_UNAVAILABLE` 或 `BLOCKED_MONGO_PRIMARY_READONLY_UNSAFE`.

Acceptance:

- 能以 read-only 构造 primary。
- 或明确 blocked reason。

任务 12.6：执行 production shadow-read one-off rehearsal

Requirements:

- [ ] 设置 run id。
- [ ] 设置 `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`。
- [ ] 使用 conservative domains：
  - `app_settings`
  - `background_jobs`
  - `app_health_alerts`
  - `workbench_pair_relations`
  - `no_oa_bank_batches`
  - `bank_transaction_categories`
  - `turnover_relations`
- [ ] 使用小 limit，例如 `--limit 10`。
- [ ] 运行 CLI：
  - primary backend: `mongo_readonly`
  - shadow backend: `postgres`
  - output: remote JSON path under stage12 temp dir.
- [ ] CLI 退出码非 0 时也要尝试取回 JSON report；如果没有 JSON report，记录 stderr 的脱敏错误。
- [ ] 不运行任何 write/cutover/dual flags。
- [ ] 执行后再次确认 `fin-ops.service` active，且未重启。

Acceptance:

- 生成 remote JSON report。
- production service 未改动。
- 没有生产 DB 写入。

任务 12.7：拉取和校验 report artifact

Files:

- Create: `docs/database-migration/reports/<run_id>.stage12.shadow-read.json`
- Create: `docs/database-migration/reports/<run_id>.stage12.shadow-read.md` if useful

Requirements:

- [ ] 拉取 remote JSON report 到本地 reports 目录。
- [ ] JSON parse 成功。
- [ ] report 包含 `redacted=true`。
- [ ] report 不包含：
  - password
  - token
  - secret
  - raw `mongodb://...@`
  - raw `postgresql://...@`
  - SSH password
- [ ] report 不包含 OA Mongo `form_data_db.form_data` domain。
- [ ] 若 JSON report gate 是 `PASS/PARTIAL/BLOCKED`，按原样记录；不得人为改 gate。
- [ ] 生成 Markdown summary 时只汇总 counts/severity/path，不贴敏感 payload。

Acceptance:

- 本地 artifact 可审计。
- redaction check 通过。

任务 12.8：mismatch 分析和人工判定

Requirements:

- [ ] 汇总 report：
  - total domains
  - compared domains
  - matched domains
  - mismatched domains
  - primary errors
  - shadow errors
  - P0/P1/P2/ignored counts
- [ ] 列出 P0/P1 mismatch 的 domain/path/kind/摘要。
- [ ] 对 P2 mismatch 做分类汇总。
- [ ] 如果存在 P0/P1，判断是否可解释：
  - PostgreSQL backfill 旧差异
  - runtime metadata
  - transform known limitation
  - actual blocker
- [ ] 如无法解释任一 P0/P1，Gate 不能 PASS。

Acceptance:

- 文档中 mismatch analysis 清晰。
- 无敏感 payload。

任务 12.9：清理远端临时资源

Requirements:

- [ ] 确认本地已取回 report。
- [ ] 删除远端临时代码 archive。
- [ ] 删除临时 env 文件。
- [ ] 可保留远端 JSON report 副本，或删除；无论哪种都记录。
- [ ] 再次确认 `fin-ops.service` active。

Acceptance:

- 临时 secret/env 不残留。
- 远端临时代码清理或保留路径明确。

任务 12.10：最终验证矩阵

必须运行并记录：

- [ ] `python -m py_compile backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py tests/test_shadow_read_rehearsal.py`
- [ ] `python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q`
- [ ] `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
- [ ] `python -m pytest -q`
- [ ] `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
- [ ] 本机 UTF8 disposable PostgreSQL integration + local rehearsal CLI。
- [ ] production read-only service/PostgreSQL smoke before and after one-off rehearsal.
- [ ] report redaction scan.

任务 12.11：文档和 Gate

Files:

- Create: `docs/database-migration/12-production-shadow-read-oneoff.md`
- Modify: `docs/database-migration/README.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md`

Requirements:

- [ ] 文档记录：
  - run id
  - remote temp dir
  - production service before/after status
  - storage mode/backend/database
  - PostgreSQL schema/counts
  - domains run
  - report artifact path
  - mismatch summary
  - cleanup status
  - safety boundary
  - Gate
- [ ] Gate 判定：
  - `PASS`: 真实 production one-off shadow-read rehearsal 已执行；关键 conservative domains 无未解释 P0/P1；服务未改动/未重启；生产 DB 未写；测试通过。
  - `PARTIAL`: one-off rehearsal 执行但 domains 覆盖不全，或仅有可解释 P2/P1 需要扩大样本；没有未解释 P0。
  - `BLOCKED`: 无法构造 primary/ shadow，只能本地验证；或存在未解释 P0/P1；或需要写生产 DB/app Mongo/OA Mongo；或服务被迫需要重启/配置变更。
- [ ] 如果 Gate 为 `PASS`，建议下一阶段生成 13：controlled dual-write / mirror-write rehearsal planning。
- [ ] 如果 Gate 不是 `PASS`，列出用户需要做什么。

最终输出格式：

1. 阶段 12 Gate：`PASS` / `PARTIAL` / `BLOCKED`。
2. production one-off shadow-read 是否真实执行：是/否。
3. report artifact 本地路径。
4. 关键 matched/mismatch/error summary。
5. 如果无法完成，原因和用户需要做什么。
6. changed files。
7. 测试和 smoke 结果。
8. 是否触碰 OA Mongo：必须明确 `未触碰 form_data_db.form_data`。
9. 是否写 production PostgreSQL/app Mongo：必须明确没有。
10. 是否修改/重启生产服务：必须明确没有。
11. 下一阶段建议。
```
