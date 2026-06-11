# 关联台 模块维护入口


- Module key: `reconciliation-workbench`
- 类型: 页面模块
- Route: `/`
- Page key: `reconciliation-workbench`

## 修改前必读

- `docs/app-architecture/pages.md`
- `docs/product-specs/reconciliation-and-workbench.md`
- `docs/dev/api-contracts.md`

## 代码入口

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/components/workbench/*`

## 当前边界

保留 active generation 原子发布模型；不要机械套成普通 read model gateway。

Workbench active pair relation 是 OA、银行流水、发票跨页面关系的唯一已配对事实。同一 active relation 内的 `row_ids` 必须按 row id 去重并保持 `row_types` 对齐；同一个 row 不能同时属于两个不同 active case。页面展示多 OA/多流水/多发票时应使用 relation summaries 和 `+N` 展开详情，不能把重复 row 当成两条业务事实。

`confirm-link` 和 `cancel-link` 的 relation 写入必须通过 `WorkbenchRelationCommandService`。缺少 command service 时 API fail fast，不得回退到 `WorkbenchPairRelationService` 直接写 pair snapshot；UoW 路径应通过 transaction-bound relation repository 保存。

个人暂借款还清会创建 Workbench exception case 和 `relation_mode=personal_advance_repayment_settlement` 的 active relation。relation 写入同样必须通过 `WorkbenchRelationCommandService`；缺 command service 或 relation read model non-fresh 时不得先写本地 exception case。

Workbench exception closed apply 会创建 exception case，并通过 `WorkbenchRelationCommandService` 写入 `normal_match` 或 `oa_exempt` active relation。closed action 必须先通过 relation write precondition；缺 command service 或 relation read model non-fresh 时不得先写本地 exception case，也不得回退到 `WorkbenchPairRelationService.create_active_relation`。

OA 附件发票冲抵自动闭环和 OA 附件上下文 repair 也必须通过 `WorkbenchRelationCommandService` 写 relation/history；Workbench payload build/repair 过程不得直接 mutate `WorkbenchPairRelationService`。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
