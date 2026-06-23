# 进项发票使用情况跨月配对关系显示不全

## Symptom

- Workbench 中 75,799 元进项发票已和 OA、银行流水配对。
- `进项发票使用情况` 按 `良固阀门集团` 搜索时，同一发票的 OA、流水、发票配对列为空。

## Hypothesis

- 该发票开票日期在 2026-05，但关联的 OA/流水发生在 2026-04。
- 页面 read model 重建 2026-05 shard 时，先按 `workbench_relation:2026-05` 读分发模型。
- 如果 2026-05 scope 返回了该发票的 unlinked row，查询上下文会把 row id 标记为已加载，不再按 row id 回查，从而漏掉另一个 scope 中的 linked relation group。

## Acceptance

- 当月 scope 中存在 unlinked row、跨月 scope 中存在 linked relation group 时，进项发票使用情况仍显示 OA、银行流水、关联发票摘要。
- row-id fallback 只能补全指定发票相关关系，不能改成全量拉取全部 relation。
- 重建 input invoice usage read model 时，source versions 仍按当前 input shard 的 workbench relation scope 记录，避免因跨月 fallback 造成当前 shard 持续 stale。
- 增加后端回归测试并更新模块文档。

## Result

- 修复 `DistributedInvoiceRelationContext`：按月加载后不直接返回；对当前请求中仍为空关系的 row id 做一次定向 `get_by_row_ids` fallback，并记录已回查 id 防止重复查询。
- 修复 `InvoiceUsageCollectionSqlProjectionBuilder`：保存 input/output/OA usage read model 时优先从当前 scope 的 `workbench_relation_source_versions` 读取依赖版本，避免 fallback scope 覆盖当前 shard source versions。
- 新增回归测试：
  - `tests.test_input_invoice_usage_service.InputInvoiceUsageQueryServiceTests.test_month_scope_unlinked_row_does_not_hide_cross_month_linked_relation`
  - `tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_projection_keeps_current_scope_relation_versions_after_cross_month_fallback`
- 已更新 `docs/modules/input-invoice-usage/state-machine.md`、`docs/modules/input-invoice-usage/tests.md`、`docs/modules/input-invoice-usage/implementation-notes.md`。
