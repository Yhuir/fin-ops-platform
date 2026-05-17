# Prompt 08：读模型、搜索表与增量重建

```text
/goal
你是 Codex 子代理：读模型和搜索负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
为工作台、全局搜索、成本统计、税金抵扣等重查询建立 PostgreSQL read model 设计和增量重建方案，避免页面请求实时拼全量数据。

必须读取：
- AGENTS.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/architecture/persistence-and-read-models.md
- backend/src/fin_ops_platform/services/workbench_read_model_service.py
- backend/src/fin_ops_platform/services/workbench_query_service.py
- backend/src/fin_ops_platform/services/search_service.py
- backend/src/fin_ops_platform/services/cost_statistics_read_model_service.py
- backend/src/fin_ops_platform/services/tax_offset_read_model_service.py

原则：
- 事实表是 source of truth。
- read model 可以冗余，但必须可重建。
- 单月优先，all-time 不阻塞单月。
- 重建按影响范围增量触发。
- 搜索走 search_index_rows，不跨多事实表实时模糊查。

任务拆分：
1. 工作台读模型
   - read_model.workbench_rows 行级投影。
   - read_model.workbench_snapshots 页面级快照。
   - scope_month、row_type、status、relation_case_id、candidate_match_id、payload。

2. 搜索索引
   - read_model.search_index_rows。
   - pg_trgm/GIN 索引。
   - entity_type、entity_id、scope_month、title、searchable_text、amount、status。

3. 统计读模型
   - cost_statistics_read_models。
   - tax_offset_read_models。
   - ETC/税金专题口径。

4. 失效和重建
   - 导入确认/撤回。
   - OA 同步。
   - 核销确认/撤销。
   - 异常处理。
   - 银行流水分类。
   - ETC/税金导入。

5. API 查询口径
   - 单月命中 read model。
   - stale 时返回旧数据还是触发重建，需要明确。
   - all-time 后台聚合。

交付物：
- docs/architecture/backend-refactor/read-models-and-search.md。
- 如已有 schema migration，补充 read_model 表和索引。
- 压测数据规模和 P95 目标。

验收：
- 每个 read model 都有事实来源、重建触发、失效条件。
- 不要求请求路径扫描 OA Mongo。
- 不要求实时全量拼装工作台。
- 搜索有独立表和索引方案。
```

