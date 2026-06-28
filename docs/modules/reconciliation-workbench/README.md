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

页面读取不再保留 active generation 原子发布模型，也不得机械套成普通 read model gateway。当前边界是 direct payload build：页面 DTO 从 canonical/OA/import facts、active relation、candidate/decision facts 和运行时 metadata 组装。

Workbench active pair relation 是 OA、银行流水、发票跨页面关系的唯一 confirmed relation fact，不等同于关联台已配对区展示事实。同一 active relation 内的 `row_ids` 必须按 row id 去重并保持 `row_types` 对齐；同一个 row 不能同时属于两个不同 active case。页面展示多 OA/多流水/多发票时应使用 relation summaries 和 `+N` 展开详情，不能把重复 row 当成两条业务事实。

Direct Workbench payload 必须把 active relation 的 `special_metadata`、`amount_check`、`display_tags` 和 `source_versions` 带入三栏分组后再做 grouped/open 分区。`完全关联`、`自动匹配`、`三栏已配对` 等展示 tag 只能作为 UI 证据，不能替代 canonical active relation ownership；没有 `app.workbench_pair_relations.status='active'` 的 row-set 不能被提升为 confirmed owner。普通 `manual_confirmed` 两栏 relation 仍是 canonical active relation，用于 row occupation、撤回、审计和下游 relation linked distribution，但在关联台 direct payload 中必须保留 canonical `case:<case_id>` open/candidate group，等待第三栏补齐；只有 OA + 银行 + 发票三栏完整，或显式业务例外，才能进入 paired 区。显式例外包括 no-OA 批次/内部转账、工资或个人自动闭合、个人暂借款还清、OA 附件发票冲抵、批量账务、ETC summary/batch relation 和 processed/closed exception projection。外部往来 `turnover_manual_closure` 是单独边界：它写入 active relation 后只证明外部往来收支闭环和 row ownership，未补齐 OA + 银行 + 发票三栏前必须保留 canonical `case:<case_id>` open/candidate group，三栏完整后才进入 paired 区。relation metadata 指定的 ETC summary/invoice summary 必须随同一 case 返回，不能在 open 区留下 standalone 残留。自动 decision 只有在 matching engine 产出 `decision_status=paired`、`display_state=paired` 且 `row_ids` 覆盖真实三栏 row set 时，才能作为 paired display group 进入已配对区；这仍不是 confirmed active relation fact。若该三栏自动 decision 覆盖且仅覆盖一个普通 `manual_confirmed` 两栏 active relation 的 row-set，并且补齐后的 OA、银行、发票金额核对为 `matched`，matching worker 可以通过 `WorkbenchRelationCommandService.confirm_relation(..., replace_existing=True)` 将原 case 原子升级为三栏 active relation，并把 decision 标记为 `consumed`。该升级是补充规则，不改变原有自动 decision 生成口径；它只允许 OA+银行、OA+发票、银行+发票任意两栏普通关系补齐第三栏，不适用于 turnover、no-OA、batch accounting、ETC、exception 等显式业务边界。旧 display tag、旧 `case_id`、两栏 `automatic_decision` 或只是 open 发票被同组展示的候选，仍留在 open 区等待人工确认或拆分。

OA 申请人列的时间 chip 必须来自后端规范化 OA 时间字段。Direct payload 应在 OA row 顶层输出 `apply_time` / `application_time` / `application_date`，以 OA 申请时间或申请日期优先，审批完成/修改时间只作为兜底；`—`、`--` 等占位符不能阻断后续有效时间字段。前端 mapper 只能消费该 contract 或兼容旧 `detail_fields.申请日期`，不能用占位的 `detail_fields.审批完成时间` 推断为无时间。

同一 active relation 内如果存在可证明的子对应关系，页面必须把对应 OA 与发票或银行流水显示在同一横向分段中。后端 relation metadata/direct payload 必须保留 `special_metadata.row_alignment`，并把确定归属投影为行级 `source_oa_id` / `source_oa_row_id`；OA 附件发票的 `derived_from_oa_id` / `source_oa_id` 可能带 `:item:*` 明细项后缀，后端和前端展示归一时都必须折叠到父 OA row id，例如 `oa-exp-1968:item:4:*` 对齐到 `oa-exp-1968`。source OA 是首选证据；没有确定 source OA 时，前端只允许在同一个已返回 group 内使用唯一精确金额或唯一 2 到 6 条金额合计闭合的 fallback 分段，把同金额/唯一闭合的 OA、银行流水和发票显示在同一行；金额不唯一或无法唯一闭合的行仍保持 group-level 展示，禁止按顺序或大组位置臆造同排关系。

`GET /api/workbench/summary`、`GET /api/workbench/groups` 和 `GET /api/workbench/groups/detail` 是 direct Workbench payload 的视图切片：后端先按当前事实组装 `/api/workbench` payload，再提取 summary、分页 groups 或完整 group detail。它们不得读取 Workbench SQL active generation 或返回 page read-model status，也不得把 `read_model_status`、scope/stale reasons 或 refresh flags 暴露为页面合同。公开 `/api/workbench/refresh-status` 和 Workbench SSE 已移除；后台状态只走 App Health、日志、数据库巡检或运维工具。

`GET /api/workbench/rows/{row_id}` 是 row detail 读接口。它必须优先使用当前 live service 和最近 direct payload cache；miss 后可以走明确的 legacy route fallback 条件，但不得通过 SQL active generation 兜底。opaque OA row id 不能仅依赖从 row id 解析月份。该接口不写 relation，不接入 `WorkbenchRelationCommandService`。

`confirm-link`、`cancel-link` 和 `withdraw-link` 的 relation 写入必须通过 `WorkbenchRelationCommandService`。缺少 command service 时 API fail fast，不得回退到 `WorkbenchPairRelationService` 直接写 pair snapshot；UoW 路径应通过 transaction-bound relation repository 保存。

关联台 selection 以 group 为操作上下文：已配对区和未配对区点击任意 OA、银行流水或发票 row，都会带入该 row 所在的完整 group。确认关联、异常处理和统一撤回/拆分入口都基于该 group context；统一撤回/拆分一次只能处理一个 group。已配对区只有撤回关联语义；未配对区的统一按钮由后端 preview 判定为 `withdraw_relation` 或 `split_candidate`。

关联预览的金额核对必须使用可付款/可核销金额，而不是盲目使用 OA 主表展示金额。日常报销等聚合 OA 如果 `amount_source=header` 且已记录主表金额与明细合计差异，OA row 应保留主表 `amount` 和“金额差异”详情用于审计展示，同时暴露 `reconciliation_amount` 给金额核对；旧 read model 只有 `detail_fields.明细金额合计` 与 `金额差异` 时，金额核对也应兼容使用该明细合计。

撤回 preview/submit 必须携带并锁定 `operation_type`、`preview_id` 和 `submit_expected_versions`。`withdraw_relation` 只恢复可证明的上一条 active relation snapshot：由 `WorkbenchPairRelationService` 当前 active before relation 生成的 history 会显式写入 `special_metadata.restorable_on_withdraw=true`；外部 preview、读侧显示归属、自动候选或历史污染传入的 `before_relations` 没有该标记时不能恢复。同一 row-set 的历史 snapshot 即使带标记也不能恢复，以避免撤回后仍显示成同一行。`relation_mode=existing_case` 代表读侧显示归属，不是可恢复关系，不能写入或恢复为 active relation，除非显式带有 `restorable_on_withdraw`。如果 active relation 没有可恢复 history，则撤到无关联状态，不再合成恢复 OA 附件关系。`split_candidate` 只 suppress 自动候选，不写 relation history。

撤回 preview 的“操作后”三栏必须按真实 after relation 分组；没有被恢复进 after relation 的 row 逐行独立展示，不能因为 row 上残留旧 `case_id` 又合成一行。确认/撤回 preview 提交后不关闭弹窗，也不切换到全局 overlay；预览弹窗自身进入阻塞状态，禁用关闭、取消、重复提交和备注编辑。写 API 成功后，若响应包含 `operation_projection`，前端应用该写后真实投影、关闭预览，并让 direct payload /真实后台任务收敛；若响应缺少有效 projection，前端直接重读当前关联台 payload 后释放。预览提交期间不得用本地 optimistic paired/open 重排；刷新失败时保留弹窗错误状态，提示 relation 已写入但页面刷新失败。历史 `workbench` month shard、`workbench:all` active generation 和跨页面下游 read model 只作为迁移/审计残留；当前验收使用 operation projection、direct refetch、canonical relation facts、relation outbox、真实后台任务和下游 direct API。确认/撤回预览不再等待 operation barrier、`workbench_relation` freshness target 或主 `workbench` active generation fresh 才释放。OA sync dirty/refreshing、无权限和 App Health write safety blocked 仍必须阻断写入；普通 legacy read model blocked/red 只作为历史读侧诊断和具体 API precondition，不能全局禁用无关写操作。

个人暂借款还清会创建 Workbench exception case 和 `relation_mode=personal_advance_repayment_settlement` 的 active relation。relation 写入同样必须通过 `WorkbenchRelationCommandService`；缺 command service、权限/session 不满足、DB/目标写模型不可用或 canonical relation 写安全冲突时不得先写本地 exception case。

Workbench exception closed apply 会创建 exception case，并通过 `WorkbenchRelationCommandService` 写入 `normal_match` 或 `oa_exempt` active relation。closed action 必须先通过 relation write safety；缺 command service、权限/session 不满足、DB/目标写模型不可用或 canonical relation 写安全冲突时不得先写本地 exception case，也不得回退到 `WorkbenchPairRelationService.create_active_relation`。

OA 附件发票冲抵自动闭环和 OA 附件上下文 repair 也必须通过 `WorkbenchRelationCommandService` 写 relation/history；Workbench payload build/repair 过程不得直接 mutate `WorkbenchPairRelationService`。

OA 附件发票解析缓存必须通过 `app.oa_attachment_invoice_cache_sources` 的 indexed source bridge 连接当前 `app.oa_attachments`。`attachment_identity_*` bridge 行用于把历史 parser cache 的 `source_expense_item_id + source_attachment_name` 映射到当前附件 key；Workbench direct payload 热路径不得回退到全量扫描 `app.oa_attachment_invoice_cache` 或旧 read model 才声明可读。

OA 附件发票 promotion 不是关联台读路径的无条件副作用。`OA附件发票晋级` 设置为 `disabled` 时必须完全跳过；默认 `link_existing_only` 只允许关联已有统一发票池记录，不创建缺失发票；只有 `create_missing` 才允许正式发票缺失时受控写入 `app.invoices`。OA 附件发票 source-linked 分组只是父 OA 归属证据的中间态，不能成为 paired 分区的阻断条件；当来源回挂后同一个候选上下文里存在唯一银行流水，且 OA 金额、银行金额与 OA 附件发票含税合计闭合时，后端 grouping 必须重新执行 auto-close promotion，使完整三栏进入 paired 区。缺少银行流水或金额不闭合时仍保持 source-linked open。

Workbench all-scope active generation 已退出页面读路径。当前性能边界是 direct payload build、matching row provider 和 canonical facts 查询；旧 `workbench_rows/groups/group_rows` 写入 profile 只作为历史迁移证据保留，不再作为页面 SLO、发布或调优入口。`0070_workbench_unused_write_indexes.sql` 的结论仍有效：不要在没有当前 direct query workload 证据时恢复已删除的大型旧投影索引。

`GET /api/workbench` 主视图当前走 direct payload build：按请求 month 从 canonical/OA/import facts 组装 raw payload，应用 canonical active relation、candidate matches、分组、运行时 metadata、OA retention、ETC summary、invoice inventory 和 tag derivation 后直接返回页面 DTO；不读取 `read_model.workbench*`，不返回 `read_model_status`/scope/stale fields。为了 action/row detail 热路径，主 GET 会保留进程内最近 direct payload cache，但该 cache 不作为 freshness proof，也不替代后续 direct refetch。summary/groups/group detail 是 direct payload 切片；refresh-status、SSE 和 worker active generation 已从页面合同移除，不能把它们重新引入页面 GET。

历史 Workbench all-scope 聚合曾承担跨月分片的展示归属权收敛；它已退出页面读路径。当前 `month=all` 和普通月份一样必须由 direct payload / query service 按 canonical facts、active relation occupancy、candidate/decision facts 和明确分页/筛选合同组装。旧 all-scope active generation、`scope:*:temp:*` owner、generation consistency 和 source-version proof 只作为迁移审计线索；不得恢复为页面 owner 发布、freshness proof 或 worker 完成条件。跨月去重和 owner 选择若仍有业务需求，必须落在 direct query/grouping service 或 matching facts 中，并由当前 API/页面测试保护。

自动匹配可以在后端以统一候选/决策引擎同时比较 OA、银行流水和发票，但这不是把三类源事实放进一个写模型或让前端本地“拼池子”。OA、银行流水、正式发票/OA 附件发票仍分别来自各自 repository/projection/import 边界；`WorkbenchFreeMatchingEngine` / legacy `WorkbenchMatchingRules` 只产出可审计 decision/candidate，`app.workbench_pair_relations` 才是人工确认后的 canonical paired fact。自动匹配文本处理使用确定性归一化：NFKC、去空白、去常见标点和大小写归一；不使用自然语言处理来猜测字段含义。字段值如果是纯空白，必须视为缺失并继续读取同义后备字段，例如 `counterparty_name` 为空白时继续读取 `counterparty`。发票方向必须先走统一归一化契约，`input` / `进项*` / OA 附件发票归为支出侧，`output` / `销项*` 归为收入侧；未知发票类型不得默认进入支出候选池。三方 free matching 不只允许 OA+银行作为入口：当银行流水与发票存在唯一强证据且金额闭合时，可以作为 anchor 补齐唯一有 OA-银行或 OA-发票业务证据的 OA，生成 `oa_bank_invoice_exact_amount` 三方 paired decision；仅金额相同但无业务文本、税号、名称或来源证据的 OA 仍不得被自动提升。通用 `oa_bank_invoice_exact_sum` 规则覆盖任意非空 OA/银行/发票三栏组合，包括 `1:1:1`、`N:1:1`、`1:N:1`、`1:1:N` 和 `N:M:K`，但每栏组合大小受上限保护；它只在方向一致、五个月窗口内、三栏总额严格相等、预约付款日期兼容、非 OA 附件正式发票、证据图连通且每个 row 至少有一条确定性证据边时生成 paired decision。现有更具体规则优先；通用规则只补缺口，遇到仅金额相等、组合过多、 competing candidates 或证据断裂时保持 open/conflict。`oa-exp-*:item:*` 等 OA 附件明细项 ID 必须通过统一父 OA helper 归一后参与 matching；禁止在 matching engine 内保留只接受父 OA row id 的旧判断。页面只消费 direct API 返回的真实 group，不做本地自动配对。

OA-bank 自动匹配中，“预约 X 月 X 日转款/付款/支付/打款”是强消歧证据：只有该预约付款日期与银行流水真实交易日期一致时，重复同金额候选才可继续唯一配对；没有明确预约付款日期或日期不一致时保持 open/conflict，不随机选择。匹配规则版本只约束 matching facts 和 `job.workbench_matching_dirty_scopes` 自愈；不得再依赖 Workbench SQL active generation `source_versions` 作为页面 fresh 证明。

`workbench-matching` 常驻 worker 每轮 claim 前必须检查 `job.workbench_matching_dirty_scopes.status='completed'` 的 scope run；只要 completed scope 的 `source_versions` 不包含当前 `workbench_matching_rules_version` 等 matching source versions，就通过 `WorkbenchReconciliationDirtyQueue` / repository 原子转回 `dirty`，再由同一 worker 正常重建候选/decision。不要依赖前端搜索、人工 SQL 改状态或只在 startup stale scan 中补救。Workbench `all` 视图不得恢复 active generation 规则版本证明；需要跨月 matching 结果时读取当前 matching facts/direct payload。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或 legacy freshness 字段删除/guard 变化。
- 业务状态、UI 状态、matching/background worker 状态或状态流转变化。
- 跨页面 direct refetch、domain event、derived lifecycle、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护关联台 Spec-first Browser e2e 验收合同。
- `e2e-coverage.md`：维护关联台 Spec ID 到现有测试的覆盖映射和缺口。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
