# Prompt 02：app Mongo 备份与恢复演练

```text
/goal
你是 Codex 子代理：app Mongo 备份负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
基于 docs/operations/backend-refactor/mongo-backup.md，为 app 关联 Mongo 数据库建立生产级备份、checksum、恢复演练和验收记录。只处理 app Mongo，不处理 OA 源库。

必须读取：
- AGENTS.md
- docs/operations/backend-refactor/mongo-backup.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- backend/README.md
- backend/src/fin_ops_platform/services/state_store.py

最高优先级禁止事项：
- 不备份 OA 源数据库。
- 不导出 OA 源数据库。
- 不恢复 OA 源数据库。
- 不修改 OA 源数据库。
- 不执行包含 OA_MONGO_URI、OA_DB、oa-mongo-readonly、nsInclude OA collection 的命令。
- 不把 app Mongo URI、密码、token 写入 git。

如果缺少信息，先问用户：
- app Mongo URI 如何安全获取。
- app Mongo 数据库名，默认 fin_ops_platform_app 但必须验证。
- 备份根目录。
- 是否有 staging Mongo 用于恢复演练。
- 是否当前只写 runbook，不实际进入服务器。

任务拆分：
1. runbook 细化
   - 新建 docs/operations/backend-refactor/app-mongo-backup-runbook.md。
   - 包含变量、命令、日志路径、checksum、恢复演练、保留周期。

2. 备份脚本模板
   - 如 repo 有 scripts/operations 约定，按现有风格新增脚本模板。
   - 脚本必须从环境变量读取 URI，不硬编码 secret。
   - 脚本必须 set -euo pipefail。
   - 输出日志不打印密码。

3. 统计和校验
   - 记录 collection counts。
   - 记录 db.stats。
   - 记录 GridFS collections 统计。
   - 生成 SHA-256 checksum。

4. staging 恢复演练
   - 只有用户提供 staging Mongo 后执行。
   - 使用 mongorestore 到恢复测试库。
   - 比对恢复前后集合数量。
   - 抽样验证 GridFS 文件可读。

5. 结果记录
   - 新增或更新 docs/operations/backend-refactor/app-mongo-backup-runbook.md。
   - 如实际执行，记录日志路径和结果摘要，不记录 secret。

验收：
- app Mongo archive 文件有 checksum。
- 恢复演练通过或明确说明未执行原因。
- 核心集合数量一致或差异有解释。
- 文档明确禁止 OA 源库操作。
- git diff 中没有 secret。
```

