# Prompt 12：正式数据迁移和切换前门禁

```text
/goal
你是 Codex 子代理：正式迁移门禁负责人，工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
在 dry-run、对账、备份、恢复、压测和安全检查全部通过后，制定并执行正式 app Mongo -> PostgreSQL 数据迁移的门禁流程。该 prompt 不能单独触发生产切流；切流必须由用户明确授权并结合 `11-cutover-and-rollback.md` 执行。

必须读取：
- AGENTS.md
- docs/exec-plans/active/backend-refactor-progress.md
- docs/operations/backend-refactor/production-readiness-checklist.md
- docs/operations/backend-refactor/cutover-and-rollback-runbook.md
- docs/operations/backend-refactor/data-migration-runbook.md，如果存在
- docs/operations/backend-refactor/migration-dry-run-report-*.md，如果存在
- docs/exec-plans/active/backend-refactor-prompts/11-cutover-and-rollback.md

硬性前置条件：
- app Mongo 最新备份存在并校验通过。
- app Mongo 恢复演练通过。
- PostgreSQL schema migration 在目标环境通过。
- PostgreSQL 备份和恢复演练通过。
- MinIO/S3 文件迁移 dry-run 和抽样校验通过。
- 数据 dry-run count/hash/amount/month/status/file checksum 报告无未解释差异。
- API 影子读或契约比对通过。
- 生产维护窗口已确认。
- 回滚方案已确认。

禁止：
- 不访问 OA 源数据库。
- 不开放 PostgreSQL 公网。
- 不删除 app Mongo。
- 不在 PostgreSQL 成为事实源后用旧 Mongo 全量覆盖 PostgreSQL。
- 不跳过失败记录。

任务拆分：

1. 迁移窗口准备
   - 明确开始时间、冻结范围、负责人、观察窗口、回滚截止点。
   - 确认备份时间点。
   - 确认所有服务版本和配置。

2. 最终增量策略
   - 明确 app Mongo 从备份到切换间的增量来源。
   - 决定停写窗口、双写窗口或增量重放方式。
   - 明确无法重放时的人工处理策略。

3. 正式迁移批次
   - 批次 1：基础导入和文件元数据。
   - 批次 2：银行流水。
   - 批次 3：发票和税金。
   - 批次 4：OA 归一化缓存和附件映射。
   - 批次 5：核销、异常、免 OA、往来款。
   - 批次 6：read model 和 search index 重建。
   - 批次 7：job/outbox 需要保留的任务状态。

4. 正式对账
   - 每批次执行 count/hash/amount/month/status 对账。
   - 文件批次执行 checksum 抽样。
   - 差异阻断，不允许继续后续批次。

5. 切换前验收
   - Axum API readiness。
   - PostgreSQL 连接池和慢查询监控。
   - Worker 消费和 outbox backlog。
   - read model freshness。
   - 搜索索引覆盖率。
   - 权限和审计日志。

6. 输出切换决策
   - 可以切换。
   - 不能切换，列出阻塞项。
   - 需要人工确认，列出确认问题。

交付物：
- 正式迁移检查清单。
- 正式迁移批次计划。
- 正式迁移对账报告模板。
- 切换前 go/no-go 结论。

验收：
- 所有差异都有明确状态。
- 失败时能回滚到迁移前服务状态。
- app Mongo 冻结是归档冻结，不是删除。
- 最终报告不包含 secret。
```

