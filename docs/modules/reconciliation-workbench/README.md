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

撤回 preview/submit 必须携带并锁定 `operation_type`、`preview_id` 和 `submit_expected_versions`。`withdraw_relation` 只恢复可证明的上一条 active relation snapshot：由 `WorkbenchPairRelationService` 当前 active before relation 生成的 history 会显式写入 `special_metadata.restorable_on_withdraw=true`；外部 preview、读侧显示归属、自动候选或历史污染传入的 `before_relations` 没有该标记时不能恢复。同一 row-set 的历史 snapshot 即使带标记也不能恢复，以避免撤回后仍显示成同一行。`relation_mode=existing_case` 代表读侧显示归属，不是可恢复关系，不能写入或恢复为 active relation，除非显式带有 `restorable_on_withdraw`。如果 active relation 没有可恢复 history，则撤到无关联状态，不再合成恢复 OA 附件关系。`split_candidate` 只 suppress 自动候选，不写 relation history。

撤回 preview 的“操作后”三栏必须按真实 after relation 分组；没有被恢复进 after relation 的 row 逐行独立展示，不能因为 row 上残留旧 `case_id` 又合成一行。提交成功后前端不再用本地 optimistic paired/open 重排伪造结果；写操作进入 `GlobalOperationOverlayProvider` 全屏等待，先等 `workbench_relation` operation barrier fresh，再重新读取 Workbench active generation，只有目标页面 payload fresh 后才释放操作。OA sync dirty/refreshing、无权限和 App Health write safety blocked 仍必须阻断写入；普通 read model blocked/red 只影响读侧诊断和具体 API precondition，不应全局禁用无关写操作。

个人暂借款还清会创建 Workbench exception case 和 `relation_mode=personal_advance_repayment_settlement` 的 active relation。relation 写入同样必须通过 `WorkbenchRelationCommandService`；缺 command service、权限/session 不满足、DB/目标写模型不可用或 canonical relation 写安全冲突时不得先写本地 exception case。

Workbench exception closed apply 会创建 exception case，并通过 `WorkbenchRelationCommandService` 写入 `normal_match` 或 `oa_exempt` active relation。closed action 必须先通过 relation write safety；缺 command service、权限/session 不满足、DB/目标写模型不可用或 canonical relation 写安全冲突时不得先写本地 exception case，也不得回退到 `WorkbenchPairRelationService.create_active_relation`。

OA 附件发票冲抵自动闭环和 OA 附件上下文 repair 也必须通过 `WorkbenchRelationCommandService` 写 relation/history；Workbench payload build/repair 过程不得直接 mutate `WorkbenchPairRelationService`。

OA 附件发票解析缓存必须通过 `app.oa_attachment_invoice_cache_sources` 的 indexed source bridge 连接当前 `app.oa_attachments`。`attachment_identity_*` bridge 行用于把历史 parser cache 的 `source_expense_item_id + source_attachment_name` 映射到当前附件 key；Workbench read model 热路径不得回退到全量扫描 `app.oa_attachment_invoice_cache` 才声明 fresh。

Workbench all-scope publish 的性能边界是 active generation 下的结构化投影写入，不是页面读旧 snapshot。生产 profile 显示 `read_model.workbench_group_rows` 适合走 chunked multi-row VALUES，`read_model.workbench_rows` 和 `read_model.workbench_groups` 在相同优化下会变慢，应继续走事务内 `executemany`。`0070_workbench_unused_write_indexes.sql` 删除生产基线中大且零扫描的 `workbench_rows_payload_gin`、`workbench_groups_searchable_text_trgm`、`workbench_group_rows_column_values_gin`；不要在没有新 query workload 证据时恢复这些写入放大型索引。

Workbench all-scope 聚合还承担跨月分片的展示归属权收敛。统一事实源只保证正式 OA、银行流水、发票事实写入唯一；当 month shard 因补行、standalone row、自动候选或 source-linked 关系把同一事实带入多个 open group 时，all-scope 必须在写 active generation 前选出唯一 visible/operable owner。已配对 group 优先于 open；open 内部保留 source-linked/exception/auto-closed/decision/candidate 等证据更强、跨 pane 更多的 group，standalone 只能保留未被更强 group 认领的事实。发票 open/open 可用强发票 identity 去重；银行流水 open/open 只按 row id 去重，避免把真实重复交易按稳定 business-fields identity 折叠。

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
