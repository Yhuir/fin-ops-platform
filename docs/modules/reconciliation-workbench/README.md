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

`GET /api/workbench/rows/{row_id}` 是 row detail 读接口。它必须优先使用当前 live service/cache，miss 后通过 `WorkbenchQueryFacade` 读取 SQL active generation；opaque OA row id 不能仅依赖从 row id 解析月份。该接口不写 relation，不接入 `WorkbenchRelationCommandService`。

`confirm-link`、`cancel-link` 和 `withdraw-link` 的 relation 写入必须通过 `WorkbenchRelationCommandService`。缺少 command service 时 API fail fast，不得回退到 `WorkbenchPairRelationService` 直接写 pair snapshot；UoW 路径应通过 transaction-bound relation repository 保存。

关联台 selection 以 group 为操作上下文：已配对区和未配对区点击任意 OA、银行流水或发票 row，都会带入该 row 所在的完整 group。确认关联、异常处理和统一撤回/拆分入口都基于该 group context；统一撤回/拆分一次只能处理一个 group。已配对区只有撤回关联语义；未配对区的统一按钮由后端 preview 判定为 `withdraw_relation` 或 `split_candidate`。

撤回 preview/submit 必须携带并锁定 `operation_type`、`preview_id` 和 `submit_expected_versions`。`withdraw_relation` 恢复上一状态；如果 active relation 没有 history，则撤到无关联状态，不再合成恢复 OA 附件关系。`split_candidate` 只 suppress 自动候选，不写 relation history。

撤回 preview 的“操作后”三栏必须按真实 after relation 分组；没有被恢复进 after relation 的 row 逐行独立展示，不能因为 row 上残留旧 `case_id` 又合成一行。提交成功后前端先做本地 optimistic update，并只锁定刚操作 row/group；Workbench active generation 后台 stale/loading 只提示刷新，不全局禁用无关写操作。OA sync dirty/refreshing、无权限和 App Health blocked 仍必须阻断写入。

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
