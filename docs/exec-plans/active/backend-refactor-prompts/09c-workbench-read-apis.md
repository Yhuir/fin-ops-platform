# Prompt 09C：工作台与搜索只读 API 迁移

```text
你是 Codex 子代理：工作台和搜索只读 API 迁移负责人。

目标：
迁移单月工作台 read model 命中路径和全局搜索 API。禁止在请求路径实时拼全量数据或扫描 OA Mongo。

必须读取：
- docs/exec-plans/active/backend-refactor-prompts/08-read-models-and-search.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- backend/src/fin_ops_platform/services/workbench_query_service.py
- backend/src/fin_ops_platform/services/search_service.py

范围：
- 单月 workbench read。
- read model freshness/status。
- global search。
- row detail lookup。

禁止：
- 不迁移核销确认写操作。
- 不做 all-time 全量实时拼装。
- 不在 API 请求里访问 OA Mongo。

要求：
- 优先查 read_model.workbench_rows/workbench_snapshots。
- search 只查 search_index_rows。
- stale 策略明确：返回旧数据 + trigger rebuild，或返回明确状态。

交付物：
- Axum workbench read routes。
- Axum search routes。
- read model repository。
- 契约测试。

验收：
- 单月查询有索引计划。
- 搜索有 pg_trgm/GIN 使用说明。
- 不破坏前端工作台契约。
```

