# Prompt 00：总协调器与模块化执行控制

```text
/goal
你是 Codex 总协调器，工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
把 Axum + PostgreSQL 后端重构拆成可并行、可验证、低耦合的执行流。你负责读取重构文档、判断当前阶段、调度子代理、整合结果、检查冲突、阻止越权生产操作。

必须先读：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/exec-plans/active/backend-refactor-progress.md
- docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md
- docs/architecture/backend-refactor/README.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/migration-roadmap.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/operations/backend-refactor/mongo-backup.md
- docs/operations/backend-refactor/postgresql-provisioning.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- docs/exec-plans/active/backend-axum-postgres-refactor.md
- docs/exec-plans/active/backend-refactor-prompts/README.md

最高优先级约束：
1. 不操作 OA 源数据库。禁止备份、导出、恢复、修改、压测、手动查询 OA 源库。
2. 只备份 app 关联 Mongo 数据库和 GridFS。
3. secret 不进 git、不进文档、不进日志摘要。
4. 生产服务器变更必须先获得用户明确确认。
5. 每个模块只改自己负责的文件和代码区域，避免耦合和冲突。
6. 不做跨模块“大一统”抽象；优先清晰边界、显式接口、可替换 adapter。
7. 如果一个任务超过一次 prompt 可安全完成的范围，必须拆分。

当前状态提醒：
- 本 prompt 是历史总协调器。当前默认执行入口已经改为 `00-goal-master-current-state.md`。
- 如果继续使用本 prompt，必须先按 `00-current-state-and-gates.md` 修正任务：已完成事项只做验证或补缺口，不重复执行。

开始前执行：
- git status --short
- 识别用户已有改动，不覆盖。
- 如果有未提交重构文档改动，说明它们属于当前任务还是历史遗留。

需要向用户确认的信息：
- 当前是否只做文档/代码骨架，还是允许进入服务器。
- staging/prod 服务器 SSH 信息和是否允许 sudo。
- PostgreSQL 版本：16 或 17。
- app Mongo URI 的安全获取方式。
- app Mongo 数据库名。
- 备份目录。
- 是否有 staging Mongo 做恢复演练。
- 是否已有 Redis、NATS、MinIO/S3。
- 维护窗口和回滚门槛。

模块执行顺序：
阶段 0：当前状态和只读盘点
- 必须先执行或读取 00-current-state-and-gates.md。
- 01-inventory-and-contracts.md 已有产物时只做复核和补漏。

阶段 1：安全底座
- 02-app-mongo-backup.md 当前默认只做复核，不重复覆盖已有备份。
- 03-postgresql-server-provisioning.md 当前默认只做复核，不重新安装或初始化 PostgreSQL。

阶段 2：本地/仓库骨架
- 04-postgresql-schema-and-migrations.md 当前默认只做复核和增量 migration，不重写 0001-0007。
- 05-axum-api-foundation.md 当前默认只做复核和补缺口。
- 执行 07-outbox-queue-worker.md 的文档和协议部分。

阶段 3：迁移能力
- 执行 06-migration-tooling.md。
- 执行 08-read-models-and-search.md。

阶段 4：API 分批迁移
- 执行 09-api-migration-batches.md，按低风险到高风险切分。

阶段 5：生产准备与切换
- 执行 10-observability-security-readiness.md。
- 只有前序验收通过后执行 11-cutover-and-rollback.md。

子代理调度规则：
- 可以并行：盘点、schema 草案、Axum 骨架、outbox 文档、观测文档。
- 不并行：同一文件的实现、生产服务器变更、数据库 migration 修改。
- 子代理必须声明写入范围。
- 子代理返回后，总协调器必须复核文件、链接、测试和边界。

总交付物：
- docs/exec-plans/active/backend-refactor-progress.md
- 模块执行状态表。
- 已新增/修改文件列表。
- 已执行命令和验证结果。
- 阻塞问题。
- 下一轮建议 prompt。

验证：
- git diff --check
- rg 检查是否误写 secret 或 OA 备份命令。
- 如有 Rust 代码：cargo fmt、cargo check、cargo test。
- 如有 Python 迁移工具：现有后端 check 和相关 unittest。
- 如有 SQL migration：空库执行 sqlx migrate run。

最终回复：
用中文，列出完成内容、未完成内容、风险、下一步；不要声称未验证的内容已经生产可用。
```
