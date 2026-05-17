# Prompt 11：双写、切读、回滚与旧系统冻结

```text
/goal
你是 Codex 子代理：切换和回滚负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
制定并在授权后执行 Axum/PostgreSQL 切换方案：影子读、双写、验证、小流量切读、全量切读、停止旧写、冻结 app Mongo。该 prompt 不在首轮直接执行生产切流，除非用户明确授权并且所有门禁通过。

必须读取：
- AGENTS.md
- docs/architecture/backend-refactor/migration-roadmap.md
- docs/operations/backend-refactor/mongo-backup.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- docs/operations/backend-refactor/production-readiness-checklist.md，如果存在
- docs/operations/backend-refactor/migration-validation-report-template.md，如果存在

硬性门禁：
- app Mongo 备份和恢复演练通过。
- PostgreSQL 备份和 PITR 演练通过。
- 迁移对账无无法解释差异。
- GridFS 到 MinIO/S3 checksum 抽样通过。
- Axum API staging 测试通过。
- read model 可从事实表重建。
- 核销确认/撤销/异常处理有审计日志。
- 回滚路径已经演练。

切换阶段：
1. 影子读
   - Axum 查询 PostgreSQL。
   - 用户仍看旧 Python API。
   - 记录差异，不影响生产。

2. 小流量读切换
   - 只切低风险只读 API。
   - 监控 P95/P99、错误率、差异。

3. 双写
   - 关键写路径同时写旧 Mongo 和 PostgreSQL。
   - 同一 idempotency key。
   - 定时差异报告。

4. 读全量切换
   - 前端/Nginx/API route 指向 Axum。
   - 旧 Python 保持回滚窗口。

5. 停止旧写
   - 旧 Python 写路径只读或禁用。
   - app Mongo 冻结归档。

6. 收尾
   - 归档迁移日志。
   - 更新 runbook。
   - 删除迁移期兼容开关要单独计划。

回滚策略：
- 读回滚：Nginx/API route 回旧 Python。
- 写回滚：双写阶段暂停切换，补偿 PostgreSQL 或 Mongo 差异。
- 文件回滚：从 MinIO/S3 版本或 GridFS 归档恢复。
- PostgreSQL 已成为事实源后，不允许旧 Mongo 全量覆盖新库。

交付物：
- docs/operations/backend-refactor/cutover-and-rollback-runbook.md。
- 切换检查表。
- 差异报告模板。
- 回滚命令模板，不含 secret。

验收：
- 每一步有进入条件、执行步骤、验证方式、回滚方式。
- 生产切流不是隐式动作，必须单独获得用户确认。
- 明确不操作 OA 源数据库。
- 明确 app Mongo 冻结而非立即删除。
```

