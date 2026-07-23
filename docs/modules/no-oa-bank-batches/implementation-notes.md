# 免 OA 流水批量处理实施说明

## 2026-07-22 Phase 27

- 删除只做持久化后固定返回 `false` 的 `after_mutation(...)` 旧壳。
- 删除误导性的 `workbench_rebuild_queued` API/前端兼容字段。
- bulk/single submit、withdraw 与 legacy migration repair 直接调用 `persist_mutation(...)`。
- scope 规范化集中在 persistence I/O；普通写不 enqueue read model，也不生成 Workbench read-model snapshot。
- 保留本模块是为了现有 legacy facts/API 回归，不作为 `/bank-flow-rule-batches` fallback。
