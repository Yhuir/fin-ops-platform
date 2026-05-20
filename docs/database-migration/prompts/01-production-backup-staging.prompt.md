# 01 阶段 Codex 执行 Prompt：生产只读盘点、备份和 staging 准备

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 01：基于阶段 00 已完成的代码证据索引，对服务器生产环境做受控只读盘点，完成 app Mongo 可恢复备份和 staging restore 演练，确认 PostgreSQL 基础环境、账号/权限/扩展和备份恢复策略，并更新 `docs/database-migration/` 下的阶段 01 文档。阶段 01 完成后，后续阶段才允许进入 PostgreSQL schema migration、backfill 或 dual-write 设计。

本阶段的目标不是迁移业务数据到 PostgreSQL；目标是证明当前生产 app Mongo 可备份、可恢复，OA Mongo 仍保持只读，PostgreSQL 具备后续 migration 的基础条件。

你必须遵守以下硬约束：

1. OA Mongo 数据库 `form_data_db` 和 collection `form_data` 禁止写入、建索引、修复、清洗、drop、rename、compact、repair 或保存 app 迁移状态；只允许只读统计和只读抽样。
2. 生产 app Mongo 数据库 `fin_ops_platform_app` 禁止 insert/update/delete/drop/createIndex/collMod/repair/cleanup；只允许只读统计、`mongodump` 备份和校验。
3. staging restore 只能写入新建的恢复测试库，库名必须带时间戳或明确后缀，例如 `fin_ops_platform_app_restore_YYYYMMDDHHMMSS`；禁止覆盖 `fin_ops_platform_app`。
4. PostgreSQL 本阶段只允许做基础准备：连接检查、扩展检查/启用、迁移账号/权限准备、备份恢复 runbook；禁止创建 app 业务 schema/table，禁止 backfill，禁止切换应用读写路径。
5. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、prompt 或代码。服务器登录凭据由执行者在执行时通过安全方式提供；本文档不能包含密码。
6. 所有服务器命令必须先打印或记录“将要执行什么、影响哪个库/目录、为什么安全”，再执行；危险命令必须有明确库名保护。
7. 不修改业务代码。本阶段只允许新增/修改 `docs/database-migration/` 下阶段 01 文档，以及必要的 docs 索引。
8. 如果发现没有可用备份工具、权限不足、磁盘空间不足、无法确认 restore 目标库安全，立即停止，不要尝试绕过。
9. 如果任何命令需要写 OA Mongo，立即停止并说明违反约束。

服务器连接信息：

- 主机 IP：`139.155.5.132`
- 用户：`root`
- 协议：SSH
- 密码不写入 prompt 或文档；执行时由用户安全提供或使用已有 SSH 凭据。

阶段 00 已完成成果必须先读：

- `docs/database-migration/README.md`
- `docs/database-migration/00-current-state-inventory.md`
- `docs/database-migration/code-evidence-index.md`
- `docs/database-migration/01-target-postgresql-design.md`
- `docs/database-migration/02-execution-plan.md`
- `docs/database-migration/prompts/00-code-evidence-inventory.prompt.md`
- `docs/index.md`
- `README.md`
- `ARCHITECTURE.md`
- `backend/README.md`
- `docs/operations/index.md`
- `docs/dev/backend.md`
- `docs/dev/testing.md`

建议新增文档：

- `docs/database-migration/01-production-backup-staging.md`

如需要，也可更新：

- `docs/database-migration/README.md`
- `docs/database-migration/02-execution-plan.md`
- `docs/index.md`

执行方式：

- 可以使用并行子代理做本地只读代码/文档复核、命令草案审查、风险清单审查。
- 子代理不得连接服务器，不得执行数据库命令，不得写文件；只返回摘要给主线程。
- 所有服务器 SSH、Mongo/PostgreSQL 命令、备份、restore、文档写入必须由主线程串行执行。
- 优先使用只读命令：`ssh`、`df -h`、`du -sh`、`systemctl status`、`ss -ltnp`、`mongosh --eval` 只读查询、`mongo --eval` 只读查询、`pg_isready`、`psql` 只读查询。
- MongoDB 4.2 环境可能使用 `mongo` 而不是 `mongosh`；执行前先探测工具版本。

串行步骤：

Step 0：建立工作基线

- 运行 `git status --short`。
- 读取阶段 00 文档和本阶段参考文档。
- 确认当前已有未提交文件；不得回滚用户或上一阶段改动。
- 创建阶段 01 文档草稿 `docs/database-migration/01-production-backup-staging.md`，记录执行时间、操作者、只读/写入边界、待执行清单。

Step 1：并行本地只读复核

可并行任务 1A：阶段 00 结果复核

- 读取 `00-current-state-inventory.md` 和 `code-evidence-index.md`。
- 输出：生产 app Mongo 名称、OA Mongo 名称、GridFS bucket、当前服务模式、禁止触碰边界、阶段 01 必须验证的事实。

可并行任务 1B：目标设计和阶段 gate 复核

- 读取 `01-target-postgresql-design.md` 和 `02-execution-plan.md`。
- 输出：阶段 01 成功 gate、PostgreSQL 扩展/账号需求、备份恢复和 staging restore 验收标准。

可并行任务 1C：服务器命令风险审查

- 根据本文 prompt 草拟命令清单。
- 标记每条命令是否只读、是否写文件、是否写 staging DB、是否可能误伤生产库。
- 输出必须包含：禁止执行的命令模式，例如 `dropDatabase`、`deleteMany`、`updateMany`、`createIndex`、`mongorestore --drop` 指向生产库等。

主线程汇总并写入阶段 01 文档的“执行前风险控制”章节。

Step 2：SSH 登录和服务器基础只读盘点

- 尝试 SSH 登录服务器。
- 只读确认：
  - 当前用户、主机名、系统版本。
  - `fin-ops.service` 状态。
  - MongoDB、PostgreSQL、Redis、Nginx 监听端口。
  - `/opt/fin-ops/current`、`/opt/fin-ops/data`、`/data/backups/fin_ops` 是否存在。
  - 磁盘空间：`df -h`，重点关注 Mongo 数据目录、备份目录、PostgreSQL 数据目录所在分区。
  - 备份目录剩余空间是否足够容纳至少 2 份 app Mongo 压缩备份和 staging restore 临时数据。
- 禁止读取或输出 `.env` 中密码值；如果必须确认变量名，只输出变量名和是否存在，不输出值。
- 将结果写入阶段 01 文档。

Step 3：Mongo 工具和生产 app Mongo 只读盘点

- 探测 Mongo 工具：
  - `mongo --version` 或 `mongosh --version`
  - `mongodump --version`
  - `mongorestore --version`
- 对生产 app Mongo `fin_ops_platform_app` 做只读统计：
  - `db.version()`
  - `db.stats()`
  - `db.getCollectionNames().sort()`
  - 每个 collection 的 `countDocuments()` 或 Mongo 4.2 兼容 count。
  - `import_file_blobs.files` count、总 length、`import_file_blobs.chunks` count。
  - 核心集合金额合计：`bank_transactions`、`invoices` 如能通过只读聚合安全计算，则记录；如果 payload/pickle 无法直接聚合，记录“需通过 Python 导出工具后再校验”。
- 禁止任何写操作。
- 将统计结果写入阶段 01 文档。

Step 4：OA Mongo 只读边界确认

- 只读统计 `form_data_db.form_data`：
  - count。
  - `form_id` 分布。
  - `modifiedTime` 最小/最大值。
  - 样本字段列表，只输出字段名，不输出敏感业务正文。
- 不对 OA Mongo 执行备份、restore、索引、repair、清洗。
- 如果执行环境账号不是只读账号，在文档中标记为风险：后续必须拆分只读账号，不能依赖人为约束。
- 将结果写入阶段 01 文档的“OA 只读确认”章节。

Step 5：app Mongo 全量备份

执行前检查：

- 备份目录必须是 `/data/backups/fin_ops/<timestamp>/` 或同等明确目录。
- 目录不存在则创建。
- 确认目标目录不在 app 代码目录、不覆盖已有备份。
- 确认磁盘空间足够。

执行：

- 对生产 app Mongo `fin_ops_platform_app` 执行 `mongodump --archive --gzip`。
- 只备份 app Mongo；不要备份 OA Mongo。
- 生成 SHA-256 checksum。
- 保存命令 stdout/stderr 到不含密码的日志文件。
- 记录 archive 路径、大小、checksum、开始/结束时间、退出码。

验收：

- archive 文件存在且 size > 0。
- checksum 文件存在。
- `mongodump` 退出码为 0。
- 文档中不得出现完整 Mongo URI 或密码。

Step 6：app Mongo staging restore 演练

执行前保护：

- restore 目标库必须是新库，例如 `fin_ops_platform_app_restore_YYYYMMDDHHMMSS`。
- 运行 restore 前，用只读命令确认目标库不存在或为空。
- 禁止使用 `--drop` 指向 `fin_ops_platform_app`。
- 如果无法确认目标库安全，立即停止。

执行：

- 将 Step 5 的备份 restore 到目标恢复测试库。
- restore 完成后，对恢复库执行只读统计：
  - collection list。
  - 每个 collection count。
  - GridFS files/chunks count。
  - `db.stats()`。
- 与生产 app Mongo Step 3 统计对比：
  - collection 数一致。
  - 每个 collection count 一致。
  - GridFS files/chunks count 一致。
  - 核心集合 count 一致。
- 不删除恢复库，除非用户明确要求；文档记录恢复库名和后续清理建议。

验收：

- 恢复库和生产库 count 对账通过。
- 如有差异，必须记录差异 collection、生产 count、恢复 count、可能原因，并阻断进入阶段 2。

Step 7：PostgreSQL 基础环境检查和最小准备

只读检查：

- `pg_isready`。
- PostgreSQL version。
- database list，确认 `fin_ops` 是否存在。
- `fin_ops` 当前 size。
- 当前 extension list。
- 当前 role list，只输出 role 名、login 属性和权限摘要，不输出密码。

允许的最小写入准备：

- 如 `pgcrypto`、`pg_trgm`、`btree_gin` 缺失，可在 `fin_ops` 中启用扩展。
- 如用户已确认允许，可创建或调整后续迁移账号：
  - `fin_ops_migrator`
  - `fin_ops_api`
  - `fin_ops_worker`
  - `fin_ops_readonly`
- 如果需要设置密码，使用交互/安全输入，不把密码写入命令日志或文档。
- 本阶段不要创建 `app`、`read_model`、`job`、`audit`、`staging` schema；schema 创建属于阶段 2。

账号权限目标：

- `fin_ops_migrator`：后续 migration owner，可创建 schema/table/index/extension。
- `fin_ops_api`：后续应用读写 app/read_model 必要表，不拥有 DDL 权限。
- `fin_ops_worker`：后续后台任务读写 job/outbox/read_model/app 必要表。
- `fin_ops_readonly`：只读查询和报表。

验收：

- PostgreSQL 可连接。
- 扩展状态明确。
- 角色状态明确。
- 如未创建账号，文档必须说明原因和阶段 2 前置动作。

Step 8：PostgreSQL 备份恢复策略 runbook

只做文档和只读检查，除非用户明确要求立即配置：

- 记录当前是否已有 PostgreSQL 备份目录、cron/systemd timer、备份脚本。
- 设计 `pg_dump` 逻辑备份命令模板，使用占位符，不写密码。
- 评估 PITR：
  - `wal_level`
  - `archive_mode`
  - `archive_command`
  - base backup 存放路径
  - 恢复演练缺口
- 输出 runbook：
  - 每日逻辑备份。
  - migration 前手动备份。
  - restore 到临时库验证。
  - PITR 后续配置建议。

Step 9：更新文档

只允许修改：

- `docs/database-migration/01-production-backup-staging.md`
- `docs/database-migration/README.md`，如需加入阶段 01 文档入口。
- `docs/database-migration/02-execution-plan.md`，如阶段 01 发现 gate 或风险需要补充。
- `docs/index.md`，如索引缺失。

`01-production-backup-staging.md` 必须包含：

1. 执行摘要：执行时间、服务器、执行者、是否完成备份、是否完成 restore、是否完成 PostgreSQL 检查。
2. 安全边界：明确生产 app Mongo 只读备份、OA Mongo 只读、PostgreSQL 本阶段不建业务 schema。
3. SSH 和服务器基础盘点。
4. app Mongo 生产只读统计。
5. OA Mongo 只读统计。
6. app Mongo 备份记录：路径、大小、checksum、退出码、日志路径。
7. staging restore 记录：目标库名、统计对比表、差异。
8. PostgreSQL 检查：version、database、extensions、roles、允许/未执行的准备动作。
9. PostgreSQL 备份恢复 runbook。
10. 阶段 01 gate 结果：
    - `PASS`：可进入阶段 2。
    - `BLOCKED`：列出阻断项。
11. 后续阶段 2 前置条件。
12. 敏感信息检查结果：确认未写入密码、token、secret、完整 URI。

Step 10：验证

在本地运行：

```bash
find docs/database-migration -maxdepth 2 -type f -name '*.md' | sort
rg -n "(PASSWORD|SECRET|TOKEN|KEY|URI)=.*[A-Za-z0-9]|DATABASE_URL=.*[:][/][/]|mongodb:[/][/]|postgres:[/][/]" docs/database-migration docs/index.md || true
rg -n 'mongodb:[/][/][^`[:space:]]+@|postgres:[/][/][^`[:space:]]+@' docs/database-migration docs/index.md || true
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
git diff -- docs/database-migration docs/index.md
git status --short
```

如果 `rg` 发现密码、token、secret、完整 URI，必须立即移除并重新运行扫描。

如服务器执行了备份/restore，还必须在阶段 01 文档记录服务器侧验证命令和结果摘要，但不要粘贴含敏感变量的完整环境文件。

Step 11：最终输出

最终回答必须包含：

- 修改了哪些文件。
- 阶段 01 完成了哪些动作。
- 是否连接服务器。
- 是否写入数据库：
  - 生产 app Mongo：只允许 `mongodump` 读取。
  - OA Mongo：只允许只读统计。
  - staging restore DB：如执行，列出恢复测试库名。
  - PostgreSQL：如启用扩展/创建角色，列出动作；如未执行，说明未写入。
- 备份路径、checksum 文件路径、restore 目标库名。
- 验证命令和结果。
- 阶段 gate：`PASS` 或 `BLOCKED`。
- 如果 `PASS`，说明可以进入阶段 2：PostgreSQL schema 和 migration 基础。

停止条件：

- 任何命令需要写 OA Mongo。
- `mongodump` 失败或备份 checksum 生成失败。
- restore 目标库名无法确认不是生产库。
- restore 后核心 collection count 与生产不一致。
- PostgreSQL 无法连接且无法确认原因。
- 文档扫描发现敏感信息且无法清理。
```
