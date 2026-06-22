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

Workbench active pair relation 是 OA、银行流水、发票跨页面关系的唯一 confirmed relation fact，不等同于关联台已配对区展示事实。同一 active relation 内的 `row_ids` 必须按 row id 去重并保持 `row_types` 对齐；同一个 row 不能同时属于两个不同 active case。页面展示多 OA/多流水/多发票时应使用 relation summaries 和 `+N` 展开详情，不能把重复 row 当成两条业务事实。

Workbench SQL active generation 必须把 active relation 的 `special_metadata`、`amount_check`、`display_tags` 和 `source_versions` 带入三栏投影后再做 grouped/open 分区。`完全关联`、`自动匹配`、`三栏已配对` 等展示 tag 只能作为 UI 证据，不能替代 canonical active relation ownership；没有 `app.workbench_pair_relations.status='active'` 的 row-set 不能被提升为 confirmed owner。普通 `manual_confirmed` 两栏 relation 仍是 canonical active relation，用于 row occupation、撤回、审计和下游 `workbench_relation` linked distribution，但在关联台 active generation 中必须保留 canonical `case:<case_id>` open/candidate group，等待第三栏补齐；只有 OA + 银行 + 发票三栏完整，或显式业务例外，才能进入 paired 区。显式例外包括 no-OA 批次/内部转账、工资或个人自动闭合、个人暂借款还清、OA 附件发票冲抵、批量账务、ETC summary/batch relation 和 processed/closed exception projection。外部往来 `turnover_manual_closure` 是单独边界：它写入 active relation 后只证明外部往来收支闭环和 row ownership，未补齐 OA + 银行 + 发票三栏前必须保留 canonical `case:<case_id>` open/candidate group，三栏完整后才进入 paired 区。relation metadata 指定的 ETC summary/invoice summary 必须随同一 case 发布，不能在 open 区留下 standalone 残留。自动 decision 只有在 matching engine 产出 `decision_status=paired`、`display_state=paired` 且 `row_ids` 覆盖真实三栏 row set 时，才能作为 paired display group 进入已配对区；这仍不是 confirmed active relation fact，不能写入 `app.workbench_pair_relations` 或作为可恢复 history。旧 display tag、旧 `case_id`、两栏 `automatic_decision` 或只是 open 发票被同组展示的候选，仍留在 open 区等待人工确认或拆分。

同一 active relation 内如果存在可证明的子对应关系，页面必须把对应 OA 与发票或银行流水显示在同一横向分段中。OA 附件发票的 `derived_from_oa_id` / `source_oa_id` 可能带 `:item:*` 明细项后缀；前端展示归一时必须折叠到父 OA row id 后再分段，例如 `oa-exp-1968:item:4:*` 对齐到 `oa-exp-1968`。没有确定 source OA 的发票或流水只能作为 group-level 行展示，禁止按金额、顺序或大组位置臆造同排关系。

`GET /api/workbench/rows/{row_id}` 是 row detail 读接口。它必须优先使用当前 live service/cache，miss 后通过 `WorkbenchQueryFacade` 读取 SQL active generation；opaque OA row id 不能仅依赖从 row id 解析月份。该接口不写 relation，不接入 `WorkbenchRelationCommandService`。

`GET /api/workbench/groups/detail` 是 group detail 读接口。它可以读取 Workbench SQL active generation，但必须携带并校验 active generation `source_versions`、`read_model_status` 和 `read_model_version`；source version stale、同 scope dirty scope pending/processing/failed，或缺少等价 freshness proof 时，不能返回旧 group 并标 `fresh`。该接口只读 group detail，不写 relation，也不能用 active generation 来源本身替代 freshness gate。

`confirm-link`、`cancel-link` 和 `withdraw-link` 的 relation 写入必须通过 `WorkbenchRelationCommandService`。缺少 command service 时 API fail fast，不得回退到 `WorkbenchPairRelationService` 直接写 pair snapshot；UoW 路径应通过 transaction-bound relation repository 保存。

关联台 selection 以 group 为操作上下文：已配对区和未配对区点击任意 OA、银行流水或发票 row，都会带入该 row 所在的完整 group。确认关联、异常处理和统一撤回/拆分入口都基于该 group context；统一撤回/拆分一次只能处理一个 group。已配对区只有撤回关联语义；未配对区的统一按钮由后端 preview 判定为 `withdraw_relation` 或 `split_candidate`。

撤回 preview/submit 必须携带并锁定 `operation_type`、`preview_id` 和 `submit_expected_versions`。`withdraw_relation` 只恢复可证明的上一条 active relation snapshot：由 `WorkbenchPairRelationService` 当前 active before relation 生成的 history 会显式写入 `special_metadata.restorable_on_withdraw=true`；外部 preview、读侧显示归属、自动候选或历史污染传入的 `before_relations` 没有该标记时不能恢复。同一 row-set 的历史 snapshot 即使带标记也不能恢复，以避免撤回后仍显示成同一行。`relation_mode=existing_case` 代表读侧显示归属，不是可恢复关系，不能写入或恢复为 active relation，除非显式带有 `restorable_on_withdraw`。如果 active relation 没有可恢复 history，则撤到无关联状态，不再合成恢复 OA 附件关系。`split_candidate` 只 suppress 自动候选，不写 relation history。

撤回 preview 的“操作后”三栏必须按真实 after relation 分组；没有被恢复进 after relation 的 row 逐行独立展示，不能因为 row 上残留旧 `case_id` 又合成一行。确认/撤回 preview 提交后不关闭弹窗，也不切换到全局 overlay；预览弹窗自身进入阻塞状态，禁用关闭、取消、重复提交和备注编辑。写 API 成功后只等待后端返回的操作级 freshness targets（受影响月份的 `workbench_relation`）达到 fresh。若响应包含 `operation_projection`，前端应用该写后真实投影、关闭预览，并后台刷新当前关联台 `/api/workbench*`；不得继续强制等待主 `workbench` active generation fresh 后才释放。若响应缺少有效 projection，才等待当前关联台 fresh refetch 后释放。预览提交期间不得用本地 optimistic paired/open 重排；刷新失败时保留弹窗错误状态，提示 relation 已写入但关联台刷新未完成。该 barrier 必须按目标月份 scope 判定 readiness/outbox，其他月份的 `workbench_relation` pending 不得阻塞当前操作；前端等待窗口必须覆盖真实 worker 尾延迟，不能把 2 秒目标当作失败阈值。`workbench` month shard、`workbench:all` active generation 和跨页面下游 read model 继续后台追赶，并由 cross-page SLO profile/监控单独验收；它们仍必须最终 fresh，不能伪装同步，但确认/撤回预览不会额外等待这些下游模型才释放。OA sync dirty/refreshing、无权限和 App Health write safety blocked 仍必须阻断写入；普通 read model blocked/red 只影响读侧诊断和具体 API precondition，不应全局禁用无关写操作。

个人暂借款还清会创建 Workbench exception case 和 `relation_mode=personal_advance_repayment_settlement` 的 active relation。relation 写入同样必须通过 `WorkbenchRelationCommandService`；缺 command service、权限/session 不满足、DB/目标写模型不可用或 canonical relation 写安全冲突时不得先写本地 exception case。

Workbench exception closed apply 会创建 exception case，并通过 `WorkbenchRelationCommandService` 写入 `normal_match` 或 `oa_exempt` active relation。closed action 必须先通过 relation write safety；缺 command service、权限/session 不满足、DB/目标写模型不可用或 canonical relation 写安全冲突时不得先写本地 exception case，也不得回退到 `WorkbenchPairRelationService.create_active_relation`。

OA 附件发票冲抵自动闭环和 OA 附件上下文 repair 也必须通过 `WorkbenchRelationCommandService` 写 relation/history；Workbench payload build/repair 过程不得直接 mutate `WorkbenchPairRelationService`。

OA 附件发票解析缓存必须通过 `app.oa_attachment_invoice_cache_sources` 的 indexed source bridge 连接当前 `app.oa_attachments`。`attachment_identity_*` bridge 行用于把历史 parser cache 的 `source_expense_item_id + source_attachment_name` 映射到当前附件 key；Workbench read model 热路径不得回退到全量扫描 `app.oa_attachment_invoice_cache` 才声明 fresh。

OA 附件发票 promotion 不是关联台读路径的无条件副作用。`OA附件发票晋级` 设置为 `disabled` 时必须完全跳过；默认 `link_existing_only` 只允许关联已有统一发票池记录，不创建缺失发票；只有 `create_missing` 才允许正式发票缺失时受控写入 `app.invoices`。

Workbench all-scope publish 的性能边界是 active generation 下的结构化投影写入，不是页面读旧 snapshot。生产 profile 显示 `read_model.workbench_group_rows` 适合走 chunked multi-row VALUES，`read_model.workbench_rows` 和 `read_model.workbench_groups` 在相同优化下会变慢，应继续走事务内 `executemany`。`0070_workbench_unused_write_indexes.sql` 删除生产基线中大且零扫描的 `workbench_rows_payload_gin`、`workbench_groups_searchable_text_trgm`、`workbench_group_rows_column_values_gin`；不要在没有新 query workload 证据时恢复这些写入放大型索引。

`GET /api/workbench?month=all` 的当前事实源是已发布的 `workbench:all` active generation。未分页主视图必须优先读取 active all snapshot；分页/过滤视图必须优先读取 active all summary 并从 `read_model.workbench_rows` 做 bounded page query。临时拼接 month snapshots 只允许作为没有 active all generation 时的 legacy fallback，不能在已有 active all generation 时绕过 all-scope 聚合器、source_versions freshness 证明、唯一 visible owner 和 active relation occupancy 不变量。

Workbench all-scope 聚合还承担跨月分片的展示归属权收敛。统一事实源只保证正式 OA、银行流水、发票事实写入唯一；当 month shard 因补行、standalone row、自动候选或 source-linked 关系把同一事实带入多个 open group 时，all-scope 必须在写 active generation 前选出唯一 visible/operable owner。已配对 group 优先于 open；open 内部保留 source-linked/exception/auto-closed/decision/candidate 等证据更强、跨 pane 更多的 group，standalone 只能保留未被更强 group 认领的事实。发票 open/open 可用强发票 identity 去重；银行流水 open/open 只按 row id 去重，避免把真实重复交易按稳定 business-fields identity 折叠。

all-scope 聚合必须同时读取 canonical active relation occupancy。即使某个月度 active generation 因历史污染或补投顺序仍把 active relation row 带入 open zone，`app.workbench_pair_relations.status='active'` 中占用的 row 也不得在 all-scope open 区继续由 `scope:*:temp:*`、standalone 或 candidate 残留作为可操作 owner 发布；合法的 active relation open/display owner 只能是 `case:<case_id>`。generation consistency 只把非 canonical owner 标成 inconsistent，不能把合法 `case:<case_id>` 撤回/显示 group 误判为失败，也不能让 worker 把污染 generation 完成成 fresh。

自动匹配可以在后端以统一候选/决策引擎同时比较 OA、银行流水和发票，但这不是把三类源事实放进一个写模型或让前端本地“拼池子”。OA、银行流水、正式发票/OA 附件发票仍分别来自各自 repository/projection/import 边界；`WorkbenchFreeMatchingEngine` / legacy `WorkbenchMatchingRules` 只产出可审计 decision/candidate，`app.workbench_pair_relations` 才是人工确认后的 canonical paired fact。`oa-exp-*:item:*` 等 OA 附件明细项 ID 必须通过统一父 OA helper 归一后参与 matching；禁止在 matching engine 内保留只接受父 OA row id 的旧判断。页面只能消费 active generation 发布后的真实 group，不做本地自动配对。

OA-bank 自动匹配中，“预约 X 月 X 日转款/付款/支付/打款”是强消歧证据：只有该预约付款日期与银行流水真实交易日期一致时，重复同金额候选才可继续唯一配对；没有明确预约付款日期或日期不一致时保持 open/conflict，不随机选择。匹配规则版本必须进入 Workbench SQL active generation 的 `source_versions`，否则规则变化后旧 generation 会继续被当作 fresh 发布。

`workbench-matching` 常驻 worker 每轮 claim 前必须检查 `job.workbench_matching_dirty_scopes.status='completed'` 的 scope run；只要 completed scope 的 `source_versions` 不包含当前 `workbench_matching_rules_version` 等 matching source versions，就通过 `WorkbenchReconciliationDirtyQueue` / repository 原子转回 `dirty`，再由同一 worker 正常重建候选/decision。不要依赖前端搜索、人工 SQL 改状态或只在 startup stale scan 中补救。Workbench `all` active generation 从 month shards 聚合时也必须传播 `workbench_matching_rules_version`，否则 all 视图会缺少规则 freshness 证明。

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
- `e2e-spec.md`：维护关联台 Spec-first Browser e2e 验收合同。
- `e2e-coverage.md`：维护关联台 Spec ID 到现有测试的覆盖映射和缺口。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
