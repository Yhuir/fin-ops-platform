# Prompt 07：Outbox、NATS JetStream 与 Python Worker 协议

```text
/goal
你是 Codex 子代理：异步任务与 Worker 协议负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
把导入解析、OA 同步、文件处理、read model 重建等重任务从 API 请求路径移出，设计 PostgreSQL outbox + NATS JetStream + Python Worker 的低耦合协议。

必须读取：
- AGENTS.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/architecture/backend-refactor/migration-roadmap.md
- backend/src/fin_ops_platform/services/background_job_service.py
- backend/src/fin_ops_platform/services/oa_sync_service.py
- backend/src/fin_ops_platform/services/import_file_service.py
- backend/src/fin_ops_platform/services/workbench_read_model_service.py

设计原则：
- PostgreSQL outbox 是可靠投递事实。
- Redis 不保存最终任务事实。
- NATS JetStream 用于投递、ack、重放。
- Python Worker 只做解析和异步计算，不直接绕开业务一致性。
- 任务必须有 idempotency key。
- 任务状态、attempt、dead letter 可审计。

任务拆分：
1. outbox 事件设计
   - event_type、aggregate_type、aggregate_id、payload、status、available_at、attempt_count、last_error。
   - 业务事务和 outbox 写入同一事务。

2. NATS 设计
   - stream 命名。
   - subject 命名。
   - consumer durable name。
   - ack/retry/backoff/dead-letter。

3. Worker 协议
   - 文件解析任务。
   - OA 同步任务，只走既有只读同步逻辑，不操作 OA 源库。
   - read model 重建任务。
   - 搜索索引更新任务。

4. 状态模型
   - queued、running、succeeded、failed、retrying、dead_lettered、cancelled。
   - attempt 记录。
   - 错误码和用户可读错误摘要。

5. 实现边界
   - Rust API 负责写事实和 outbox。
   - outbox publisher 负责发布。
   - Python Worker 负责消费和写结果。
   - API 查询任务状态只读 PostgreSQL。

交付物：
- docs/architecture/backend-refactor/outbox-and-jobs.md。
- 如进入实现：最小 outbox publisher skeleton。
- Python Worker message schema 示例。

验收：
- 每类任务有明确输入/输出。
- 失败可重试、可 dead-letter、可人工重放。
- 不依赖 Redis 保存最终状态。
- 不把 OA 源库纳入备份或迁移范围。
```

