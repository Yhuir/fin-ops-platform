# Prompt 09D：核销、异常与高风险写 API 迁移

```text
你是 Codex 子代理：核销和异常写 API 迁移负责人。

目标：
迁移确认核销、撤销核销、异常处理、免 OA 批次等高风险写 API。该 prompt 只能在 schema、outbox、audit、read model 基础完成后执行。

前置条件：
- app Mongo 备份和恢复演练通过。
- PostgreSQL schema migration 通过。
- audit.events 可写。
- job.outbox_events 可写。
- read model rebuild 任务协议已定义。
- API 低风险批次已通过。

必须读取：
- docs/exec-plans/active/backend-refactor-prompts/09-api-migration-batches.md
- docs/exec-plans/active/backend-refactor-prompts/07-outbox-queue-worker.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py
- backend/src/fin_ops_platform/services/workbench_action_service.py
- backend/src/fin_ops_platform/services/workbench_exception_application_service.py

范围：
- confirm relation。
- revoke relation。
- exception create/resolve/revert。
- no-OA batch submit/revert。
- row override write。

要求：
- 每个写操作必须有事务边界。
- 每个写操作必须有 idempotency key。
- 每个写操作必须写 audit.events。
- 每个写操作必须写 outbox 触发 read model rebuild。
- 使用 optimistic lock 或 row_version 防并发覆盖。

禁止：
- 不直接更新 read model 当事实源。
- 不物理删除业务事实。
- 不吞掉金额不一致或状态冲突。

交付物：
- Axum write routes。
- service/repository 实现。
- transaction tests。
- concurrency/idempotency tests。

验收：
- 重复提交不会重复核销。
- 并发冲突能明确返回。
- 撤销可审计。
- read model rebuild 被可靠触发。
```

