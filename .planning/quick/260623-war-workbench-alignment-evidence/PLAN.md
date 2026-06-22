# 260623-war - Workbench 多 OA 行级归属证据闭环

## 目标

修复关联台三栏配对区域中，多 OA active relation 只有大组 row set、缺少后端行级 source evidence 的问题。最终效果是：可证明归属由后端发布 `source_oa_id` / `source_oa_row_id`，前端按 source OA 同排；不可证明或旧 generation 缺证据由审计工具暴露，不再静默错排。

## GSD 阶段

1. Phase 0：冻结契约和影响面，不实现。
2. Phase 1：新增 `WorkbenchRelationAlignmentService`，用 TDD 覆盖唯一同金额、唯一银行流水组合、附件发票父 OA 归一、歧义不猜。
3. Phase 2：接入 `WorkbenchSqlProjectionBuilder`，在 active generation 投影阶段写入 row-level source evidence，并 bump schema version。
4. Phase 3：确认 `WorkbenchRelationCommandService` 保留显式 `special_metadata.row_alignment`。
5. Phase 4：增强 `audit_workbench_relation_display`，阻断多 OA active relation 中 bank row 缺 source OA 的旧 generation。
6. Phase 5：补前端 API mapper 和现有三栏分段回归。
7. Phase 6：更新模块文档并运行验证。

## 验收标准

- 截图类场景中，29,350 bank row 可由后端投影 `source_oa_id=oa-29350`。
- 88,050 OA 对应的多条银行流水可由唯一合计闭合投影到同一 OA。
- 重复金额或多个可选组合不自动猜测，进入 unresolved/diagnostics。
- SQL active generation schema version 变化会让旧 generation stale。
- 审计工具能发现多 OA active relation 中 bank row 缺 source OA 的旧 generation。
- 前端 mapper 能消费后端 `source_oa_id`，现有 source-first 分段继续工作。

