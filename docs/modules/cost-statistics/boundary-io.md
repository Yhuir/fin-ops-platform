# 成本统计模块边界与 I/O

日期：2026-07-19

## 模块化状态

- 状态：READY_FOR_UNIFIED_DEPLOYMENT / DEPLOYMENT_HOLD
- 当前边界可信度：high
- 目标边界：成本统计页面读取 `cost_statistics` SQL read model，经 query gateway 暴露 parent rollup fresh 状态。
- 当前结论：local/non-SQL explorer fallback、route-owner live service fallback、live export workbook helper 和旧 `ProjectDetailExportService` 已删除。成本统计页不再暴露项目范围切换按钮，页面查询固定使用 `project_scope=active`；`project_scope=all` 仍是后端 API/export/read model 合同。按银行统计的银行全集来自 settings owner 输出的银行账户映射，由成本统计 read model payload 暴露给页面；成本统计标签规则来自 app settings owner，页面与导出都从 dependency-bound freshness gate 取得选择 token，再由各自 cost-owned SQL query 过滤，不进入 read model source_versions，也不触发全量重建。`按项目`、`按银行`、`按OA费用类型` 只统计被规则选中的 OA 配对支出流水；`按标签`、`按时间` 统计被规则选中的全部银行收入与支出流水。
- 旧代码删除状态：legacy `CostStatisticsService`、`CostStatisticsReadModelService`、warmup job、旧 root/project HTTP contract、full-view loader、无版本 Redis writer、全量 load/save 和 `cost_tax_sql_projection.py` 混合 owner 均已删除。route、Application、query、runtime、projection、repository、worker assembly、API fixture、App Health/runtime registry 与前端 type/mock 不保留对应 field、callback、compat dependency、fallback 或 shim。系统 owner 已确认旧 HTTP contract 无已知外部 consumer 且从未公开承诺；生产只读证据确认 warmup active/attention 均为 0。当前页面只使用 explorer、export-preview/export、transaction 和 tag-rules 合同；query miss/stale 只返回 refreshing 并入队 durable refresh。前端 5 分钟 explorer Map、首屏 `active:all` 预取和零调用 clients 也保持删除。

## 职责边界

### 负责

- 成本统计页面汇总、筛选、父聚合和明细读取。
- OA 配对统计继续展示自身支出汇总；全流水的按时间、按标签视图不展示收入与支出的合并总金额。summary、方向金额/笔数和 percentages 均由当前 fresh page query 的完整筛选集合在 SQL 中计算，页面不得从当前页重算或回读源表。
- 成本统计页面的按银行统计；银行账户全集来自 `app.app_settings.bank_account_mappings` 经后端 owner read port 进入 gate 的小型 metadata，再由 page repository 与结构化成本行生成银行 facets。页面不做全量账户聚合，也不调用设置页 API。
- 成本统计页面的 `按标签` 三栏视图；主/子标签 facets 与选中层级 rows 只由 cost-owned page repository 从 `cost_statistics_bank_flow_rows.bank_tag_*` 计算，不直接读取银行明细页 read model，也不把完整 bank-flow rows 传到浏览器派生。
- 成本统计页面的紧凑展示合同：五个分类与标题同排，范围控件位于金额摘要行最左；OA 配对金额显式标注支出，收支标签左对齐、金额右对齐；页面摘要、列表、详情和导出预览中的金额统一保留两位小数；四种 explorer 下钻表把时间合并到户名/项目名复合单元格，桌面端各栏等高且独立滚动。该合同只改变展示，不改变 explorer/API DTO 或计算精度。
- 成本统计标签规则抽屉；抽屉读取 app settings owner 归一后的银行主/子标签与虚拟 `__uncategorized__` 未分类标签，保存后等待当前成本统计 scope fresh 再关闭。
- `cost_statistics` read model 的 parent rollup 投影。
- 与税金抵扣共享 cost/tax 投影 worker 时保持明确 event/scope。

### 不负责

- 不拥有税金抵扣业务状态。
- 不直接处理发票导入和 ETC 源事实。
- 不把 `all` 当成无界重建入口；`all` 是 queryable parent aggregate 合同。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面筛选/月份/父级聚合查询 | `CostStatisticsPage.tsx`、`features/cost-statistics/api.ts` | 进入成本统计 API/query service；页面主时间范围只暴露单一按钮选择 `all` / `year` / `month`，不再暴露主页面自定义日期范围；精确日期范围只属于导出中心 |
| 页面交互鲜度 | explorer request lifecycle + explorer freshness envelope + `AppHealthStatusContext` 的 App Status overview + operation barrier | relation confirm/withdraw 事件必须立即进入成本页面私有 barrier，并只等待当前精确 `cost_statistics` scope：month=`active:YYYY-MM`，year/all=`active:all`。等待期间取消页面自有 explorer/detail/export 请求并保持 cost-local inert overlay；barrier fresh 后只发一次 explorer 读取。App Status 仅作异常恢复/状态展示，不能作为 relation 写后可见性的 5 秒轮询主路径；其他月份/其他 read model 不得锁当前页面。focus、hidden→visible 和 BFCache restore 只触发当前 explorer 重校验，不产生新的 freshness 事实或 cost-specific polling/SSE。 |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API / `cost_statistics_page_audit.py` | admin-only 调用 `page-audit?page=cost-statistics`；registry 使用唯一 `cost_statistics` executor，通用只读 CLI 与 System Audit 也只到达同一个成本 owner。该 owner 显式复用 caller-owned repeatable-read read-only snapshot、完整 Workbench integrity proof 与银行明细 canonical/字段/version proof。canonical paired-cost expected-set 从已证明的 Workbench active generation group/member payload 形成；full bank-flow identity/month/direction/amount expected-set 必须直接从 active `app.bank_transactions` 的收入与支出事实形成，不能由 `bank_detail_rows` 反推完整性。cost rows、project/expense summaries，以及 bank-flow 的收支金额与收支笔数必须重算一致；任一缺失、额外、旧版或字段漂移均 blocking；审计只读，不能触发 rebuild/export 或读取旧 live service。共享 `page_business_audit.py` 不再拥有任何成本 runtime 分支。05-09 后 summary/dirty/outbox 共用一次查询，relation equality 只由 Workbench 正式 owner 执行一次；05-10 后 row/scope、月度上游和 parent shard source-version proof 共用一次集合查询，三分支仍各自 bounded；05-16 后五类业务值/summary/account proof 共用一次 `fetch_all`，五分支仍各自 bounded；05-17 后 bank-flow canonical set、字段和 summary proof 只读 `cost_statistics_bank_flow_rows`，不展开 metadata 中的旧 row array，parent 按 month rows 逻辑 rollup；05-18 后 scope count、missing scope、duplicate identity 与 canonical set 由一次 `cost_exact_set_proofs` I/O 返回，四分支独立 bounded。成本 owner 现在固定为四组集合 SQL；active-relation 场景总 query budget 为 23，只用于防回退，不代表生产 SLO。响应的 cost-local `proof_timings` 只计量这四组与既有 Workbench/Bank Detail collector 的耗时和 issue count，不新增查询、不改变其它页面 envelope，也不能作为缓存绿色结论。 |
| 银行账户全集 | `AppSettingsService.get_cost_statistics_source_settings_payload()` / `app.app_settings.bank_account_mappings` | 投影层读取 settings owner 输出并写入 explorer metadata；query gate 在同一 SQL statement 只读取成本所需 settings JSON 片段，用于当前 fingerprint 与 bank facets metadata，不再次调用 settings service。页面不得直接读取 settings API 或设置页面状态 |
| 银行自动标签规则版本 | `AppSettingsService.get_cost_statistics_source_settings_payload()` / `app.app_settings.bank_transaction_tags` | 进入 `source_versions.bank_auto_tag_rules_version`；规则更新由 `bank_auto_tag_rules_changed` lifecycle 入队 `cost_statistics.read_model.refresh` |
| 银行明细有效标签 | `BankTransactionTagReadFacade` / fresh `bank_detail` read model | 成本统计 projection 先读取当前 Workbench 月份分片并提取正式 OA+bank 关系中的流水 ID，再通过 `snapshot_for_month(...)` 做一次 `REPEATABLE READ READ ONLY` 快照 I/O：同时取得目标月全部银行流水和关系引用的跨月流水。目标月 rows 生成 `bank_flow_time_rows`，完整 rows 只为关系成员补 `time_rows.bank_tag_*`，禁止把跨月补充行混入目标月全流水统计。该读取必须使用 `require_fresh=False`，projection 显式校验全部涉及 scope 的状态并在非 fresh 时抛出 `bank_detail_read_model_not_fresh`；read facade 不得在 worker 内部读取链路 enqueue，依赖刷新只由 runtime worker 的异常边界统一调度。成本月份自身的 `bank_detail_source_versions` 继续纳入成本统计 source_versions，保持 API/Audit fresh gate 与目标月 scope 合同一致。 |
| 成本统计标签规则 | `AppSettingsService.get_cost_statistics_tag_selection_payload()` / `app.app_settings.cost_statistics_tag_selection` | route 只暴露归一后的收入/支出主子标签、`__uncategorized__` 未分类标签和已选 leaf codes；默认未配置时等价于全选当前有效收入与支出标签 + 未分类，显式空数组表示全部不进入成本统计。legacy 显式选择升级到 schema v2 时保留原支出选择并一次性加入当前有效收入标签。保存规则不写 read model、不写 dirty scope |
| 全流水标签统计输入 | `CostStatisticsSqlProjectionBuilder` + `BankDetailsApplicationService` | 月度投影在 read model 边界内批量读取 fresh `bank_detail` 收入与支出流水，将逻辑 DTO `bank_flow_time_rows` 写入 `read_model.cost_statistics_bank_flow_rows`；parent metadata 不保存该大数组。父 scope 只从已物化月份结构化 rows 汇总，禁止读取 child/parent JSON array 或页面直接读银行明细 API |
| 流水标签三栏统计 | `CostStatisticsPage.tsx` | 输入是 page API 的 `facets.bank_tag_primary`、`facets.bank_tag_sub` 与当前层级 bounded `rows`；不存在旧 `bank_flow_time_rows -> time_rows` fallback，详情接口失败也不得从列表行拼装本地详情 |
| 项目明细/流水详情/导出请求 | `routes_cost_statistics.py` | 只调用 `CostStatisticsQueryService`；read model 不 fresh 时返回 `409 cost_statistics_read_model_not_fresh`，不得同步扫描旧 live service 或读取完整 explorer payload 伪装成功。bulk preview 只读 SQL summary + 8 行，下载按最多 1,000 行批次读取；成本统计页面默认透传 `project_scope=active` |
| Refresh scope | `cost_statistics` manifest | active/all month + parent aggregate |
| Workbench 月度输入 | `read_model.workbench_generations` active generation + `read_model.workbench_groups` | 先定位 active generation，再按 `generation_id + scope_key` 读取 groups；禁止按裸 `scope_key` 扫描历史 generation |
| 关系变更 | relation transaction 的 bounded delta + `WorkbenchReadModelRefreshService` 收敛发布 | relation transaction 只向 `active:YYYY-MM` 投递 `cost_statistics_relation_delta`，metadata 必须是按 `case_id` 分区的 `{status,row_ids}` 显式 I/O；同月并发事件按 case 合并，同 case 后写覆盖前写，禁止用一个共享状态污染多个 case。成本 worker 在 Workbench 当前 active generations 中按 row identity 有界点读；跨月关系可从各成员原生月份取得行，并在 Workbench 新 generation 发布后优先使用目标月份副本。随后结合成本自有 bank-flow 标签行，原子删除/替换受影响成本行；成功 Workbench publish 仍以 `workbench_shard_published` 触发 active/all 月份最终收敛。两条路径共用同一 queue、worker、scope policy、source-version CAS 和 parent fan-out，不新增 worker、表、HTTP 或 fallback。 |
| 导入确认 | import processing service/job result | 返回规范化后的 cost_statistics operation barrier targets，月份输入经 scope policy 展开为 active/all shards 与 parent aggregate |
| ETC 页面刷新提示 | `invoiceFactUpdated` | 只在 ETC invoice facts 真正导入或成功删除时重校验当前 Cost scope；明确忽略 `etcBusinessBatchUpdated`。OA 草稿、提交/未提交决定和标题等 batch-only 状态不得让成本页面进入 overlay。事件只作提示，是否 fresh 仍由 Cost query gate 决定 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 成本统计 rows/summary | 前端页面 | query gateway 后返回 freshness；请求合同是 `scope + view + project_scope + 当前层级 filters + cursor + page_size<=100`。响应只含完整 summary、available years、当前 view 必需的小型 facets、当前层级 bounded rows、row count 和 next cursor。页面切换 identity 时取消旧请求、清除旧可操作数据，只允许最后一代响应写入；不得恢复 full explorer DTO mapper、浏览器全量 group-by 或当前页 summary 反推。 |
| 页面交互锁 | 仅 `/cost-statistics` 成本业务区域 | 唯一 effective state 只有 `fresh` 解锁；其他状态在视图/范围/header actions/content 与 drawer body/footer 使用原生 `inert`、`aria-busy` 和 cost-local pointer layer。标题、Audit、App Shell、导航不锁。锁定时关闭 detail/export、自有 range popover 并取消可取消的详情/导出参考请求；不得修改共享 overlay、StatePanel、App Status 或其他页面。 |
| 页面 Audit 状态 | 标题附件 | 只有 audit status 与 explorer read model 均明确 fresh/pass 才显示成功；问题数量是有上限 sample。response 的 contract/issue code/snapshot identity 由唯一成本 Audit owner 输出，operations 层只添加 page registry envelope。 |
| Explorer bank accounts | 前端页面 | `view=bank` 的 `facets.bank_accounts` 合并设置中的银行账户全集与当前 scope 聚合；零金额账户仍可见。页面只消费 facet，不读取独立 `bank_accounts` full DTO |
| Source versions | read model/query gateway | 月份 scope 的业务 `source_versions` 必须包含当前 Workbench active generation 的完整 `workbench_source_versions`、`bank_detail_source_versions`、`bank_auto_tag_rules_version` 和 `bank_account_mappings_fingerprint`。projection 与 query 共用 `cost_statistics_source_versions(...)` 纯 helper；query 的当前依赖来自同一 gate SQL 的 settings/Workbench/Bank Detail snapshot，禁止 Application/runtime 逐个回调 owner。Bank Detail 的 `source_version` 是 worker 执行计数，嵌套 `workbench_relation_source_versions` 是 Bank Detail 自身 lineage；Cost 不消费这两个 provenance 字段。Cost fresh gate/cache/Audit 只排除这两个已知键，仍精确比较 `bank_detail_source_signature`、row count、schema、标签规则及任何未知新增字段，并且 Bank Detail dirty/fresh 状态仍必须收敛。Cost 直接依赖的 Workbench 版本和其它 Cost 依赖继续精确比较。runtime dirty `source_version` 独立保存在 parent metadata 的 `published_source_version`，只作为发布竞态与 cache namespace token，不得混入常规全量投影的业务 `source_versions`。任一语义上游变化都使旧 payload fail-closed 为 refreshing 并入队刷新，禁止只在 Audit 中识别漂移而让页面继续显示 fresh |
| Project/detail/export payload | 前端页面 / 下载 | 页面 project 由 bounded page query 输出；bulk export-preview/export 经相同 PostgreSQL gate 后调用成本专属 `get_cost_statistics_export_page(...)`，从两张结构化行表执行同一组 month/range/project/expense/tag filters。preview 只返回完整 summary + 8 行；下载先判 20,000 行门槛，再以每批最多 1,000 行直接追加到 write-only workbook，禁止完整 entries/rows list。生成后再次校验 schema/source versions/published version，中途变化则丢弃并 409。time/bank-tag 导出不读取 `active:all`；transaction detail/export 保持 gate 后 identity 点查。filename/sheet/error/permission 合同不变。 |
| Parent rollup | read model repository | scoped parent aggregate |
| Dirty scope | runtime queue | relation transaction 与 Workbench publish 都只能经正式 gateway 写 durable cost scope。delta metadata 只允许 `action_name/row_ids/case_ids/relation_deltas`，队列合并最多 200 个 case；超限或无有效 delta 时 worker 回到既有全月重建，不猜状态。成本 worker 必须携带非负整数 `source_version` 与 tenant/priority/trace：repository 在同一事务锁定精确 dirty 版本后，delta 只删除/插入目标行、同步该 scope 全部成本行的版本证明，并从事务内最终 Cost rows 重新计算完整 `summary/project_rows/expense_type_rows/bank_flow_summary` 月份 metadata；完成成功后才 fan-out parent。任一竞态失败保持 `refreshing`，不得完成新 dirty、投递 parent或写 Redis。旧无身份的 relation direct full rebuild、repository 隐藏 fan-out 和第二队列路径禁止恢复。 |
| Write-after-read proof | 生产 smoke / Cost explorer | relation mutation receipt 必须包含 `cost_statistics_relation_delta` 月份事件；causal timeline 从该 exact event（旧事件仅允许 `workbench_shard_published` 收敛证明）追到 `active:all` parent done。月份事件没有 caller trace 时，parent 必须继承该月份 event id，禁止失去直接因果链。最终要求 explorer `200 + fresh + source_versions changed + business assertion changed`；event done 不能冒充页面可见。 |

## 持久化与投影

- Read model：`cost_statistics`
- Projection：`partitioned_scoped_parent_rollup`
- `all` 语义：`queryable_parent_aggregate`
- Worker：`cost-statistics`；旧 `cost-tax` 成本统计消费链路已移除
- Relation-origin 入口只有两种且职责不重叠：事务内 identity-bound `cost_statistics_relation_delta` 提供低延迟，Workbench successful publish 的 `workbench_shard_published` 提供最终收敛。relation repository、自动匹配/lifecycle registry 不拥有成本 I/O；旧无 `relation_deltas` 的 direct full rebuild、`workbench_relation_changed` / `turnover_relation_changed` 成本 reason、HTTP consumer 与隐藏 scope expansion 均已删除并由 architecture guard 阻止回归。
- Query owner：`CostStatisticsQueryService`；项目明细、流水详情、export-preview、export 都归属该 owner。
- Miss/stale owner：`CostStatisticsQueryService` 必须先经 `CostStatisticsReadModelRepositoryPort.get_cost_statistics_freshness_gate(...)` 执行一次 dependency-bound PostgreSQL gate；gate missing/non-fresh 时返回空的 `refreshing` envelope 并入队，禁止访问 Redis 或 full rows。只有 gate fresh 且同一 snapshot 的业务 source/schema 完全匹配后，才委托现有 `ReadModelQueryGateway` 处理 Redis 与 payload shape，禁止同步 rebuild。
- 发布边界：`publish_cost_statistics_read_models(...)` 负责全月/parent 条件发布，`publish_cost_statistics_relation_delta(...)` 负责受影响行条件替换，`acknowledge_unchanged_cost_statistics_scope(...)` 只确认内容未变。三者复用同一 active-scope partial unique index并在单事务锁定精确 dirty 版本。delta 不重建全月业务 DTO，但必须同步 scope 内未受影响成本行的 `source_versions`，并在同一事务从最终 Cost 结构化 rows 重算完整月份小型聚合 metadata；否则 Page Audit 行、summary/group 与月份证明会分裂。delta 不得修改 bank-flow 业务行。任一路径拒绝必须不完成 dirty、不 fan-out、不写 Redis。
- Unchanged 判定边界：`CostStatisticsReadModelRepositoryPort.get_cost_statistics_scope_metadata(...)` 只按规范 scope point lookup parent `scope_key/entry_count/source_versions`，并用一个 JSON path 布尔值证明 `:all` parent 已发布标题统计；不加载 payload 内容。projection 只在完整 `source_versions` 精确相等，且 parent 统计已存在时请求 unchanged CAS；旧 parent 缺统计必须重建一次。repository 必须再次验证当前 dirty `source_version` 与 parent `source_versions`，确认成功才返回 `published=true/skipped_rebuild=true`，使 readiness 记录本事件版本。missing/mismatch 必须重建；CAS 失败必须返回未发布并保持 refreshing。旧“直接返回 `skipped=true`、但不推进 `published_source_version`”路径已删除，禁止恢复，否则 month/parent 会互相重复补投。metadata I/O 本身不承担页面 freshness，不得读取 payload 内容、两张结构化 rows、dirty queue、Workbench、Bank Detail 或 App Settings，也不得新增 full-view fallback。
- 失效边界：runtime 不拥有进程内 read model、local snapshot 或 persistence callback。global invalidation 只投递 `active:all/all:all`，month invalidation 只投递规范化后的 `active/all:YYYY-MM`；只有 gateway 可用并接受 scope 时才返回 `invalidated_scopes`。SQL 旧 rows 不在请求线程删除，而由新的 dirty version 在 gate 处阻断，直到 worker 条件发布成功。
- 读取边界：`get_cost_statistics_freshness_gate(...)` 用单条 SQL 读取成本 metadata/current dirty、成本所需 App Settings 片段，并对 concrete month 读取 Workbench active generation/current dirty 与 Bank Detail scope/current dirty。cost/WB/Bank Detail pending、processing、failed，已发布版本未追上 dirty version，依赖缺失/非法 settings shape、Bank Detail schema/status/source versions 异常，或成本 schema/source mismatch 均 fail-closed；`all` parent 不读取虚构的 Workbench/Bank Detail `all`。页面 explorer 在 gate 之后才允许 ETag short-circuit、cost-local versioned Redis 和 `get_cost_statistics_page(...)`；cache miss 以一个 set-based SQL 返回 summary/facets/row count/`page_size+1` rows。cursor/ETag/cache key 绑定 published version、业务 source versions、tag token 与规范 query。bulk 导出只允许 `get_cost_statistics_export_page(...)` 的 SQL summary + bounded rows，并在文件生成后重新 gate；不存在 full-view read path。
- 行存储边界：`0107` 新增 `read_model.cost_statistics_bank_flow_rows`，`0108` 补齐生产 `fin_ops_app_runtime` 与本地 `fin_ops_app` 的结构化行读写授权。月份 shard 的 OA 配对成本行只写 `read_model.cost_statistics_rows`，全银行收支行只写 `read_model.cost_statistics_bank_flow_rows`；`read_model.cost_statistics_read_models.payload` 只保留 metadata/小型字段，禁止保存 `time_rows` 或 `bank_flow_time_rows`。页面 API 直接查询结构化行，不重建旧 DTO；内部 full loader 暂可从两张表重建，但不得回退 parent JSON array。
- `time_rows.bank_tag_*` 的全月来源是 `BankTransactionTagReadFacade` 暴露的 fresh `bank_detail` scoped read model；relation delta 为避免与同事务 bank-detail refresh 竞态，只点查同 scope 的成本自有 `cost_statistics_bank_flow_rows` 标签列。两者都经 `cost_statistics_bank_tags.bank_tag_context_from_row(...)` 归一化；禁止回读 Workbench 行内旧标签字段、银行明细 HTTP 或 canonical tag 表。
- 成本 projection 内的 bank-detail source version、transaction tags、month rows 必须由一次 `snapshot_for_month(...)` 快照读取共同提供；旧 `source_versions_for_scope_keys(...) + get_by_transaction_ids(...) + list_by_month(...)` 三段读取链路已删除。快照在 repository 内使用 `REPEATABLE READ READ ONLY`，同时覆盖目标月 rows 与正式关系引用的跨月流水 ID；projection 只做纯内存拆分和归一化。禁止恢复三个独立 freshness gate、`require_fresh=True` 或任何 read-side enqueue；否则并发 fan-out 会让一次成本事件在多个时间点观察 dependency，重新形成不收敛的移动目标。唯一 dependency enqueue owner 是 `RuntimeWorker._enqueue_dependency_refreshes(...)`。
- `bank_flow_time_rows.bank_tag_*` 的来源是成本统计投影层通过银行明细 read facade 批量读取的 fresh 收入与支出流水；它是 `按标签`、`按时间` 的全流水统计输入。金额均以正数绝对值输出，方向决定进入支出或收入汇总，不计算净额，也不向页面展示合并总额。`time_rows` 继续是 OA 配对支出输入。
- Audit 不把上述投影依赖误当成 canonical 完整性来源：银行收入与支出集合直接对 `app.bank_transactions` 做双向 equality，标签内容再与通过独立 bank-detail proof 的有效标签比较；同时复用 Workbench 全页面 proof。
- 银行支出 canonical identity 与页面 payload 一律使用 `coalesce(legacy_mongo_id, id::text)`；无标签流水的 code 为空，但 label/primary/sub/path 统一为 `未标记` 语义。Audit 不得拿内部 UUID 与 legacy 页面 ID 比较，也不得把空标签与 `未标记` 误判为业务差异。
- 成本统计标签规则由 `AppSettingsService` 持久化；`CostStatisticsQueryService` 只调用 settings owner 的无 I/O mapper，从本次 gate 已读取的 settings snapshot 生成 selected leaf codes 和 cache token，再在 query/export 层过滤。该规则不是投影 source version，保存时不触发 read model rebuild；禁止为标签筛选再次 reload settings。
- `bank_accounts` 的来源是 settings owner 的银行账户映射，投影层通过 `cost_statistics_bank_accounts.py` 归一为 parent 小型 metadata，并以 `bank_account_mappings_fingerprint` 纳入 source version。page repository 合并该 metadata 与结构化 rows 输出银行 facets；禁止恢复浏览器端 `bank_accounts + time_rows` 全量合并。
- Upstream read model 输入：全月月份 shard消费 Workbench active generation；relation delta 只按事件 row IDs 点查该 active generation。父 scope 只读取月份 metadata，并以两次 SQL aggregate 生成完整小型 metadata：一次覆盖 Cost summary + project/expense groups，一次覆盖 bank-flow summary；不加载/重组月份业务 rows，不读 Workbench `all`、历史 generation 或 child JSON arrays。
- Relation identity：delta event 的 `case_id` 是 canonical relation identity；写入 `cost_statistics_rows.group_id` 与删除用的 affected group identity 必须使用 Workbench 正式展示合同 `case:<case_id>`，与 full month projection 和 Page Audit expected-set 完全一致。禁止把裸 `case_id` 写入业务行、兼容双 identity 或放宽 Audit。
- Audit lineage：月份 scope 已保存的 `workbench_source_versions` 必须与同一 snapshot 中当前 active generation 精确相等；`bank_detail_source_versions` 只排除 Cost 不消费的执行计数 `source_version` 与嵌套 `workbench_relation_source_versions`，其余已知及未来新增字段必须与当前 bank-detail scope 精确相等，且 Bank Detail 本身仍须 fresh/drained。父 scope 的 `cost_statistics_parent_source=materialized_shards`、`source_shard_count`、`source_shards` 必须直接来自当前同 project scope 的全部 concrete month metadata，而不是从非空业务 rows 反推，确保合法空月份也进入精确证明。无需新增 lineage 表。
- 父 scope 正式重建会删除不再存在于 Workbench active month shard 集合中的旧 cost_statistics month scopes 及两张结构化行表记录；旧 shard 不得继续进入 Audit、parent rollup 或页面月份集合。projection 不再写删旧无版本 Redis key；scope 缺失/non-fresh 的 PostgreSQL gate 会阻止读取残留 query cache，versioned cache 由 namespace/TTL 自然淘汰。
- `active:all` / `all:all` 的 summary 与 project/expense 聚合从当前 concrete `cost_statistics_rows` 重算，全流水摘要从 `cost_statistics_bank_flow_rows` 重算；父模型不重复物化 parent rows，也不保存两类 row array。Audit 必须使用同一 child-union 口径，不能以 parent row 表为空误报 summary。
- 页面标题 `statistics` 只由对应 `active:all` / `all:all` 成本 parent 在发布时从上述两张结构化行表聚合，并通过同一 freshness gate、ETag 与 Redis namespace 绑定 parent published version；它固定表示未筛选完整页面集合，不随 explorer view、月份、标签、项目、费用类型、cursor 或分页变化。parent/任一 child 非 fresh 时只返回 `statistics=null` 并入队 parent，禁止查询 canonical/统一事实源填数；Page Audit 另从结构化页面行独立重算后比较 parent metadata。
- 成本 bank-flow 字段证明按银行流水 canonical legacy/public transaction id 连接 `bank_detail_rows.transaction_id`；不得只用 PostgreSQL UUID 连接后把完整投影误报为缺失。
- Read-model schema version：`2026-07-cost-statistics-structured-rows-v10`。v10 固化 relation `case_id` 到 Workbench display `group_id=case:<case_id>` 的成员身份合同，并确保部署后触发一次真实重投影；物理存储是两张结构化行表，parent JSON 不含两类大数组。旧 schema 必须经 gate fail-closed 并重新投影，禁止 dual-read/JSON/HTTP-shape fallback。
- Audit 重算结构化 bank-flow rows 时，bank-detail identity 必须同时接受 PostgreSQL UUID 与 legacy public transaction id；两者都只能归一到同一 canonical `app.bank_transactions` 对象。投影月份直接使用 `cost_statistics_bank_flow_rows.scope_month`，与 bank-detail 的 `scope_key` owner 比较（仅 bank-detail owner 缺失时回退 `trade_date`）；不得展开 parent metadata 中已禁止的 `bank_flow_time_rows`。禁止只按其中一种 ID 连接或只按可空日期字段校验而把完整投影误报为明细缺失。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/CostStatisticsPage.tsx` |
| Frontend components | `web/src/components/cost-statistics/*`、`web/src/features/cost-statistics/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Backend service | `cost_statistics_query_service.py`、`cost_statistics_runtime_service.py`、`cost_statistics_source_versions.py`、`cost_statistics_sql_projection.py`、`cost_statistics_bank_tags.py`、`cost_statistics_bank_accounts.py`、`app_settings_service.py` |
| Repository / SQL | `cost_statistics_read_model_repository.py`、`cost_statistics_sql_projection.py`、`postgres_repositories/read_models.py`、`postgres/migrations/0105_cost_statistics_freshness_gate.sql`、`postgres/migrations/0107_cost_statistics_structured_bank_flow_rows.sql`、`postgres/migrations/0108_cost_statistics_bank_flow_runtime_grant.sql` |
| Worker/read model | `cost_statistics_read_model_refresh.py`、`cost_statistics_derived_lifecycle_executor.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_cost_statistics*.py`、`web/src/test/CostStatistics*.test.*`、`web/e2e/cost-statistics-*.spec.ts` |

## 依赖方向

- 允许依赖：workbench active generation read model、workbench relation read model、settings owner read port、`BankTransactionTagReadFacade`、银行明细 fresh read facade、成本专属 projection、query gateway。
- 必须通过：CostStatisticsQueryService 和 read model query gateway。
- 禁止绕过：页面/API 直接扫描源表伪装 fresh；页面直接调用 settings 或银行明细页面 API；projection 依赖读取直接 enqueue bank-detail refresh；route/query 恢复旧 live service；Application/runtime 恢复 cost expected-source provider、进程内 `CostStatisticsReadModelService`、local snapshot/persist callback、多 owner 串行读取或无版本 Redis delete；runtime service 持有 `explorer_loader`、`_upsert_read_model` 或 worker writer；成本投影按裸 `scope_key` 扫描 Workbench 历史 generation；把税金抵扣状态写入成本模块。

## 测试与验证

- `tests/test_cost_statistics_sql_runtime.py`
- `tests/test_cost_statistics_api.py`
- `tests/test_app_settings_service.py`
- `tests/test_cost_statistics_runtime_service.py`
- `tests/test_import_processing_service.py`
- `tests/test_derived_data_lifecycle_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `web/src/test/CostStatisticsPage.test.tsx`
- `web/src/test/CostStatisticsApi.test.ts`
- `web/e2e/cost-statistics-flow.spec.ts`
- `web/e2e/cost-statistics-relation-fanout.spec.ts`
- 页面测试必须锁定顶部分类位置、范围控件左置、收支金额对齐、OA“支出”标签、四种下钻表复合时间 chip 和桌面 explorer 等高；Browser 测试至少真实量测一组三栏高度。

## 当前缺口和删除条件

- 模块边界已 closed；后续若恢复 local fallback、live export helper、旧 warmup writer 或页面项目范围切换，必须重新打开本模块状态并补全 UAT。
- 成本统计页面旧 UI 已删除：标题下解释文案、三张顶部 summary card、项目范围切换按钮、主页面自定义日期范围和旧范围 tab 不再作为页面 I/O；导出中心仍保留精确日期范围。
- 按时间统计旧 ISO/T 字符串直出已关闭；页面展示统一格式化为 `YYYY-MM-DD HH:mm:ss`，过滤仍使用原始 `trade_time`。
- 按银行统计旧“只从当前流水分组得出银行列表”的逻辑已删除；银行全集由 read model payload 的 `bank_accounts` 输入决定。
- 成本统计标签规则是本模块唯一写入口；route 仍保持 thin owner，只委托 `AppSettingsService` 持久化并返回当前 `cost_statistics` scope 的 operation barrier target。页面保存时必须等待该 target fresh 后再关闭抽屉；等待范围只能是当前 scope，禁止保存规则后触发全量 read model rebuild。
- 性能边界：首屏 API/read model 只能走 PostgreSQL gate + cost-local fresh Redis/page SQL；API miss 不同步扫描 Workbench/live service。前端不得恢复 TTL payload cache、full DTO、浏览器全量聚合或首屏 `active:all`。项目/费用类型导出筛选仅在用户动作后并行请求两个 bounded all-scope facets；time/bank-tag 不发该 I/O。当前 view-specific cursor 已本地闭环，但生产 EXPLAIN/SLO 尚未验证；不得在无证据时增加索引或修改共享 pool。
