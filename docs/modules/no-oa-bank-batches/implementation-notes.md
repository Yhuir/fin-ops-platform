# 免 OA 流水批量处理实施说明

## 2026-07-22 Phase 27

- 删除只做持久化后固定返回 `false` 的 `after_mutation(...)` 旧壳。
- 删除误导性的 `workbench_rebuild_queued` API/前端兼容字段。
- bulk/single submit、withdraw 与 legacy migration repair 直接调用 `persist_mutation(...)`。
- scope 规范化集中在 persistence I/O；普通写不 enqueue read model，也不生成 Workbench read-model snapshot。
- 保留本模块是为了现有 legacy facts/API 回归，不作为 `/bank-flow-rule-batches` fallback。

## 2026-08-01 Phase 39 canonical query

- `GET /api/no-oa-bank-batches` 复用现有 `NoOaBankBatchService.refresh_batches(...)` 与 application service，在请求内按 month/all 精确 scope 更新并分页读取 canonical batch facts；不再读取 projection、readiness、dirty scope 或 refresh job。
- submit、submit-selection、withdraw、审计、幂等、事务、legacy facts 与 Workbench internal-transfer relation owner 保持原合同；只删除派生 read-model repository/refresh/producer/repair/worker 链。
- API 响应删除 freshness/read-model/queue 元数据，失败直接按 canonical repository/service 错误返回，不增加旧 projection fallback 或并行路径。
