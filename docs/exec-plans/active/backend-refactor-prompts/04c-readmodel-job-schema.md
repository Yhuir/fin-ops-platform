# Prompt 04C：Read Model、Outbox、任务与 Staging Schema

```text
你是 Codex 子代理：read model/job/staging schema 负责人。

目标：
在 04A/04B 基础上创建 read_model、job、staging 的表结构，为异步任务、迁移导入、搜索和工作台读模型提供数据库基础。

必须读取：
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/exec-plans/active/backend-refactor-prompts/07-outbox-queue-worker.md
- docs/exec-plans/active/backend-refactor-prompts/08-read-models-and-search.md

范围：
- job.outbox_events
- job.worker_tasks
- job.worker_attempts
- job.dead_letters
- read_model.workbench_rows
- read_model.workbench_snapshots
- read_model.workbench_candidate_matches
- read_model.search_index_rows
- read_model.cost_statistics_read_models
- read_model.tax_offset_read_models
- staging.mongo_export_manifest
- staging.mongo_* 导入暂存表

关键要求：
- search_index_rows 使用 pg_trgm/GIN。
- workbench_rows 支持 scope_month 分区。
- outbox 可按 status/available_at 查询。
- staging 表保留 legacy id 和 raw payload，但正式查询不依赖 staging。

不做：
- 不实现 NATS publisher。
- 不实现 read model 重建算法。
- 不导入生产数据。

交付物：
- read_model/job/staging migration。
- 索引和分区说明。

验收：
- 空库按 04A -> 04B -> 04C 顺序可执行。
- read model 可从事实表重建的边界清晰。
- outbox 状态可恢复、可重试。
```

