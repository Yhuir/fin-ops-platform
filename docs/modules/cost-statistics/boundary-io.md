# 成本统计模块边界与 I/O

日期：2026-07-23

## 模块化状态

- 状态：READY_FOR_UNIFIED_DEPLOYMENT / DEPLOYMENT_HOLD
- 当前边界可信度：high
- 目标边界：成本统计页面读取 `cost_statistics` SQL read model，经 query gateway 暴露 parent rollup fresh 状态。
- 当前结论：local/non-SQL explorer fallback、route-owner live service fallback、live export workbook helper 和旧 `ProjectDetailExportService` 已删除。成本统计页不再暴露项目范围切换按钮，页面查询固定使用 `project_scope=active`；`project_scope=all` 仍是后端 API/export/read model 合同。按银行统计的银行全集来自 settings owner 输出的银行账户映射；成本统计标签规则来自 app settings owner，页面与导出从 dependency-bound freshness gate 取得选择 token，再由 cost-owned SQL query 过滤，不进入 read model source_versions，也不触发全量重建。`按项目`、`按银行`、`按OA费用类型` 只统计被规则选中、位于银行原生月份且属于 active 正式 OA+bank relation 的支出流水；relation 在 `paired` / `unpaired`、是否有发票均不改变资格。`按标签`、`按时间` 统计被规则选中的全部银行收入与支出流水。
- 旧代码删除状态：legacy `CostStatisticsService`、`CostStatisticsReadModelService`、warmup job、旧 root/project HTTP contract、full-view loader、无版本 Redis writer、全量 load/save 和 `cost_tax_sql_projection.py` 混合 owner 均已删除。route、Application、query、runtime、projection、repository、worker assembly、API fixture、App Health/runtime registry 与前端 type/mock 不保留对应 field、callback、compat dependency、fallback 或 shim。系统 owner 已确认旧 HTTP contract 无已知外部 consumer 且从未公开承诺；生产只读证据确认 warmup active/attention 均为 0。当前页面只使用 explorer、export-preview/export、transaction 和 tag-rules 合同；query miss/stale 只返回 refreshing 并入队 durable refresh。前端 5 分钟 explorer Map、首屏 `active:all` 预取和零调用 clients 也保持删除。

## 职责边界

### 负责

- 成本统计页面汇总、筛选、父聚合和明细读取。
- OA 配对统计继续展示自身支出汇总；全流水的按时间、按标签视图不展示收入与支出的合并总金额。summary、方向金额/笔数和 percentages 均由当前 fresh page query 的完整筛选集合在 SQL 中计算，页面不得从当前页重算或回读源表。
- 成本统计页面的按银行统计；银行账户全集来自 `app.app_settings.bank_account_mappings` 经后端 owner read port 进入 gate 的小型 metadata，再由 page repository 与结构化成本行生成银行 facets。页面不做全量账户聚合，也不调用设置页 API。
- 成本统计页面的 `按标签` 三栏视图；主/子标签 facets 与选中层级 rows 只由 cost-owned page repository 从 `cost_statistics_bank_flow_rows.bank_tag_*` 计算，不直接读取银行明细页 read model，也不把完整 bank-flow rows 传到浏览器派生。
- 成本统计页面的紧凑展示合同：五个分类与标题同排，范围控件位于金额摘要行最左；OA 配对金额显式标注支出，收支标签左对齐、金额右对齐；页面摘要、列表、详情和导出预览中的金额统一保留两位小数；四种 explorer 下钻表把时间合并到户名/项目名复合单元格，桌面端各栏等高且独立滚动。该合同只改变展示，不改变 explorer/API DTO 或计算精度。
- 成本统计标签规则抽屉；抽屉读取 app settings owner 归一后的银行主/子标签与虚拟 `__uncategorized__` 未分类标签。保存只提交 settings version/audit，立即关闭并重跑当前 explorer query，不等待或触发 read model rebuild。
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
| 页面交互鲜度 | explorer request lifecycle + explorer freshness envelope + 页面 activation/event hint | 页面首次访问、focus、hidden→visible、BFCache restore 或 relation 轻量提示后，都通过同一正常 explorer GET 重校验当前 scope。响应为 refreshing 时，页面立即显示 cost-local inert overlay，并以 150ms 间隔有界重试、最长 3s；fresh 即解锁，超时保持明确 non-fresh。不调用 operation barrier、不轮询全局 App Status、不引入 cost-specific SSE。隐藏页面不发 explorer I/O，另一个可见窗口经现有轻量事件后独立 GET。 |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API / `cost_statistics_page_audit.py` | admin-only 调用 `page-audit?page=cost-statistics`；registry 使用唯一 `cost_statistics` executor，通用只读 CLI 与 System Audit 也只到达同一个成本 owner。该 owner在 caller-owned repeatable-read read-only snapshot 内，从 active generation 中 `group_type=relation` 且含 OA+bank 的正式 group 独立重算银行原生月份、支出资格、OA 明确金额拆分、fallback 维度和 stable row key；不得只接受 `paired`、要求发票或沿用旧 OA 排除标记。full bank-flow expected-set 仍直接来自 active `app.bank_transactions`。cost allocation rows/唯一 transaction counts/project-expense summaries 与 bank-flow 收支必须一致；任一缺失、额外、跨月重复、金额/字段漂移均 blocking。审计保持四组 cost-local 集合 SQL和既有 Workbench/Bank Detail collector，不新增写入、修复或另一 owner。 |
| 银行账户全集 | `AppSettingsService.get_cost_statistics_source_settings_payload()` / `app.app_settings.bank_account_mappings` | 投影层读取 settings owner 输出并写入 explorer metadata；query gate 在同一 SQL statement 只读取成本所需 settings JSON 片段，用于当前 fingerprint 与 bank facets metadata，不再次调用 settings service。页面不得直接读取 settings API 或设置页面状态 |
| 银行自动标签规则版本 | `AppSettingsService.get_cost_statistics_source_settings_payload()` / `app.app_settings.bank_transaction_tags` | 进入 `source_versions.bank_auto_tag_rules_version`；普通规则更新不再通过 `bank_auto_tag_rules_changed all` 主动 fan-out，成本 query dependency gate 在页面访问时比较当前 settings snapshot 与投影版本并精确 enqueue 当前 scope |
| 银行明细有效标签 | `BankTransactionTagReadFacade` / fresh `bank_detail` read model | 成本统计 projection 先读取当前 Workbench 月份分片中 `group_type=relation`、包含 OA+bank 的 `paired` / `unpaired` 正式关系，再通过 `snapshot_for_month(...)` 一次取得目标月全部银行流水和关系引用的跨月流水。目标月 rows 生成 `bank_flow_time_rows`；完整 rows 只补关系成员标签和原生月份证据。OA 成本行只允许写入银行流水原生月份，跨月补充行禁止进入当前月份 `cost_statistics_rows`。该读取使用 `require_fresh=False` 并由 projection 显式校验全部涉及 scope 的 fresh 状态；依赖刷新仍由 runtime worker 异常边界调度。 |
| 成本统计标签规则 | `AppSettingsService.get_cost_statistics_tag_selection_payload()` / `app.app_settings.cost_statistics_tag_selection` | route 只暴露归一后的收入/支出主子标签、`__uncategorized__` 未分类标签和已选 leaf codes；默认未配置时等价于全选当前有效收入与支出标签 + 未分类，显式空数组表示全部不进入成本统计。legacy 显式选择升级到 schema v2 时保留原支出选择并一次性加入当前有效收入标签。保存规则不写 read model、不写 dirty scope |
| 全流水标签统计输入 | `CostStatisticsSqlProjectionBuilder` + `BankDetailsApplicationService` | 月度投影在 read model 边界内批量读取 fresh `bank_detail` 收入与支出流水，将逻辑 DTO `bank_flow_time_rows` 写入 `read_model.cost_statistics_bank_flow_rows`；parent metadata 不保存该大数组。父 scope 只从已物化月份结构化 rows 汇总，禁止读取 child/parent JSON array 或页面直接读银行明细 API |
| 流水标签三栏统计 | `CostStatisticsPage.tsx` | 输入是 page API 的 `facets.bank_tag_primary`、`facets.bank_tag_sub` 与当前层级 bounded `rows`；不存在旧 `bank_flow_time_rows -> time_rows` fallback，详情接口失败也不得从列表行拼装本地详情 |
| 项目明细/流水详情/导出请求 | `routes_cost_statistics.py` | 只调用 `CostStatisticsQueryService`；read model 不 fresh 时返回 `409 cost_statistics_read_model_not_fresh`，不得同步扫描旧 live service 或读取完整 explorer payload 伪装成功。bulk preview 只读 SQL summary + 8 行，下载按最多 1,000 行批次读取；成本统计页面默认透传 `project_scope=active` |
| Refresh scope | `cost_statistics` manifest | active/all month + queryable parent aggregate。普通 parent event 只重建廉价 rollup，不能读取 `app_status_readiness` 后补投全部历史月份；精确 child 判定只属于 query repository gate。显式 maintenance/reset 的 `force_refresh=true` parent 才枚举全部当前月份 shard并传播 force；月份 worker执行完整重建，只有非 force 且业务 `source_versions` 完全一致时才允许 unchanged CAS。 |
| Workbench 月度输入 | `read_model.workbench_generations` active generation + `read_model.workbench_groups` | 先定位 active generation，再按 `generation_id + scope_key` 读取 `group_type=relation` 且含 OA+bank 的 `paired` / `unpaired` groups；candidate、unpaired singleton、无 OA relation 和显式 `in_progress` OA 不进入 OA 成本。OA 顶层 `workflow_status` 复用 canonical completed aliases，空值仅作为历史 completed 兼容；发票成员不参与资格判断。禁止按裸 `scope_key` 扫描历史 generation。 |
| 关系变更 | canonical relation source version + Cost query owner | relation transaction 和 Workbench generation publish 都不投递 Cost。具体月份 GET 比较该月 canonical Workbench expected versions 与 active generation；`scope=all` GET 先对 exact active outbox 做轻量检查：已有 Workbench、Bank Detail 或当前 project Cost refresh 时直接返回 `refreshing`，不重复执行全月份 canonical/gate SQL，也不再 enqueue。队列无 active event 后，通过 Workbench builder 的 set-based 多月份证明比较全部 canonical month proofs 与 active generations。Workbench stale 时只 enqueue 真正漂移的月份，返回 `refresh_dependency=workbench`，不同时 enqueue Cost。Workbench 全部 fresh 后，Cost parent gate 再把每个 concrete Cost shard 嵌入的 Workbench/Bank Detail versions、dependency dirty state 和 parent `source_shards` 与当前值比较；只 enqueue 漂移的 Cost child。child 完成后沿 month→parent 发布最终 rollup；普通 parent 不再二次扫描 readiness 或扩张 scope。该两阶段依赖收敛复用现有 query/refresh gateway、queue、两个 bounded PostgreSQL consumer 和 repository；不新增表、HTTP、协调器、缓存或 fallback。 |
| 导入确认 | import processing service/job result | 只推进 canonical import facts/source version 并返回信息性 affected months；不返回 cost targets、不写页面 queue。成本页访问时由两阶段 dependency gate 收敛 requested active/all scope |
| ETC 页面刷新提示 | `invoiceFactUpdated` | 只在 ETC invoice facts 真正导入或成功删除时重校验当前 Cost scope；明确忽略 `etcBusinessBatchUpdated`。OA 草稿、提交/未提交决定和标题等 batch-only 状态不得让成本页面进入 overlay。事件只作提示，是否 fresh 仍由 Cost query gate 决定 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 成本统计 rows/summary | 前端页面 | query gateway 后返回 freshness；请求合同是 `scope + view + project_scope + 当前层级 filters + cursor + page_size<=100`。一笔银行流水可有多条 OA allocation row；金额按 allocation 求和，所有 transaction count 按 `transaction_id` 去重。`statistics.cost_transaction_count` 在同一 page SQL 中按 parent 全期间集合 + 标签选择统计唯一 OA 成本流水，不增加 HTTP 或 repository 往返，也不随当前时间范围变化。响应仍只含完整 summary、必要 facets、bounded rows、row count 和 next cursor。 |
| 页面交互锁 | 仅 `/cost-statistics` 成本业务区域 | 唯一 effective state 只有 `fresh` 解锁；其他状态在视图/范围/header actions/content 与 drawer body/footer 使用原生 `inert`、`aria-busy` 和 cost-local pointer layer。标题、Audit、App Shell、导航不锁。锁定时关闭 detail/export、自有 range popover 并取消可取消的详情/导出参考请求；不得修改共享 overlay、StatePanel、App Status 或其他页面。 |
| 页面 Audit 状态 | 标题附件 | 只有 audit status 与 explorer read model 均明确 fresh/pass 才显示成功；问题数量是有上限 sample。response 的 contract/issue code/snapshot identity 由唯一成本 Audit owner 输出，operations 层只添加 page registry envelope。 |
| Explorer bank accounts | 前端页面 | `view=bank` 的 `facets.bank_accounts` 合并设置中的银行账户全集与当前 scope 聚合；零金额账户仍可见。页面只消费 facet，不读取独立 `bank_accounts` full DTO |
| Source versions | read model/query gateway | 月份 scope 的业务 `source_versions` 必须包含当前 Workbench active generation 的完整 `workbench_source_versions`、`bank_detail_source_versions`、`bank_auto_tag_rules_version` 和 `bank_account_mappings_fingerprint`。projection 与 query 共用 `cost_statistics_source_versions(...)` 纯 helper；query 的当前依赖来自同一 gate SQL 的 settings/Workbench/Bank Detail snapshot，禁止 Application/runtime 逐个回调 owner。Bank Detail 的 `source_version` 是 worker 执行计数，嵌套 `workbench_relation_source_versions` 是 Bank Detail 自身 lineage；Cost 不消费这两个 provenance 字段。Cost fresh gate/cache/Audit 只排除这两个已知键，仍精确比较 `bank_detail_source_signature`、row count、schema、标签规则及任何未知新增字段，并且 Bank Detail dirty/fresh 状态仍必须收敛。Cost 直接依赖的 Workbench 版本和其它 Cost 依赖继续精确比较。runtime dirty `source_version` 独立保存在 parent metadata 的 `published_source_version`，只作为发布竞态与 cache namespace token，不得混入常规全量投影的业务 `source_versions`。任一语义上游变化都使旧 payload fail-closed 为 refreshing 并入队刷新，禁止只在 Audit 中识别漂移而让页面继续显示 fresh |
| Project/detail/export payload | 前端页面 / 下载 | 页面 project 由 bounded page query 输出；transaction detail 在同一 indexed point SQL 中返回 additive `cost_allocations`，多 allocation 的顶层金额为合计、项目/费用维度按一致或多值展示，不新增 endpoint/待归因操作。bulk export-preview/export 经相同 PostgreSQL gate 从两张结构化行表执行相同 filters；金额按 allocation 求和，transaction count 去重。preview 只返回 summary + 8 行；下载每批最多 1,000 行写 write-only workbook，生成后再次校验版本。 |
| Parent rollup | read model repository | scoped parent aggregate |
| Dirty scope | runtime queue | 只有 Cost GET 在 Workbench 依赖 fresh 后发现当前 Cost scope stale，或显式 reapply/repair 合同，才可经正式 gateway 写 durable cost scope。普通 import 只推进 canonical source version，不直投 Cost。worker 继续用 event `source_version` 做条件发布，完成 month 后才 fan-out 必需 parent；竞态失败保持 `refreshing`，不得写 Redis。relation direct delta、Workbench publish fan-out、repository 隐藏 fan-out 和第二队列路径禁止恢复。 |
| Access-to-fresh proof | 生产 smoke / Cost explorer | 从 relation mutation 成功到首次 Cost explorer GET 开始计时；必须证明上游 Workbench 及 Cost 依次收敛，最终 explorer `200 + fresh + source_versions changed + business assertion changed`。任一 event done 都不能冒充页面可见。 |

## 持久化与投影

- Read model：`cost_statistics`
- Projection：`partitioned_scoped_parent_rollup`
- `all` 语义：`queryable_parent_aggregate`
- Worker：`cost-statistics` 与 `cost-statistics-secondary` 复用同一 event/scope/handler 合同并从同一 PostgreSQL durable queue 竞争 claim；旧 `cost-tax` 成本统计消费链路已移除。secondary 不拥有第二套事实、投影或发布路径。
- Relation-origin 写入入口为零：relation repository、UoW、turnover writer、自动匹配/lifecycle registry 与 Workbench publish 都不拥有成本 I/O。成本只在页面访问中执行 Workbench dependency gate 与 Cost gate。旧 `cost_statistics_relation_delta` / `workbench_shard_published` producer、worker handler、projection/repository、write-trace smoke、`workbench_relation_changed` / `turnover_relation_changed` 成本 reason、HTTP consumer 与隐藏 scope expansion均已从 production runtime 删除；SLO audit 只保留其字符串作为“出现即失败”的旧 fan-out signature，不是执行路径。
- Query owner：`CostStatisticsQueryService`；项目明细、流水详情、export-preview、export 都归属该 owner。
- Miss/stale owner：`CostStatisticsQueryService` 先比较 canonical Workbench expected versions 与 active Workbench versions；月份使用单 scope proof，parent 使用 set-based scope 映射。随后 `get_cost_statistics_freshness_gate(...)` 在一个 cost-owned SQL gate 内把 dependency drift 分成精确的 Workbench 月份、Bank Detail 月份和 Cost child scope。query 依次只 enqueue `workbench_refresh_scope_keys`、`bank_detail_refresh_scope_keys` 或 `child_refresh_scope_keys`，只有 child 全 fresh但 parent lineage 落后时才 enqueue parent。旧 broad active-dependency query 已删除：系统中不相关 scope 的 active queue event 不得阻塞 Cost。Cost worker 读取 Bank Detail 时使用 `require_fresh=true`，因此 Cost 首次 missing 也能补投 exact Bank Detail dependency。只有全部 proof fresh 且 parent `source_shards` 等于当前 concrete shards 后，才允许 Redis/payload I/O。
- 发布边界：`publish_cost_statistics_read_models(...)` 负责月份/parent 条件发布，`acknowledge_unchanged_cost_statistics_scope(...)` 只确认内容未变。两者复用同一 active-scope partial unique index并在单事务锁定精确 dirty 版本；月份正常重建原子替换该 scope 的成本行、bank-flow 行与 metadata，parent 只发布小型 rollup。任一路径拒绝必须不完成 dirty、不 fan-out、不写 Redis。不存在行级 delta publisher、第二发布路径或兼容 fallback。
- Unchanged 判定边界：`CostStatisticsReadModelRepositoryPort.get_cost_statistics_scope_metadata(...)` 只按规范 scope point lookup parent `scope_key/entry_count/source_versions`，并用一个 JSON path 布尔值证明 `:all` parent 已发布标题统计；不加载 payload 内容。projection 只在完整 `source_versions` 精确相等，且 parent 统计已存在时请求 unchanged CAS；旧 parent 缺统计必须重建一次。repository 必须再次验证当前 dirty `source_version` 与 parent `source_versions`，确认成功才返回 `published=true/skipped_rebuild=true`，使 readiness 记录本事件版本。missing/mismatch 必须重建；CAS 失败必须返回未发布并保持 refreshing。旧“直接返回 `skipped=true`、但不推进 `published_source_version`”路径已删除，禁止恢复，否则 month/parent 会互相重复补投。metadata I/O 本身不承担页面 freshness，不得读取 payload 内容、两张结构化 rows、dirty queue、Workbench、Bank Detail 或 App Settings，也不得新增 full-view fallback。
- 失效边界：runtime 不拥有进程内 read model、local snapshot 或 persistence callback。显式 global invalidation 只投递带 `force_refresh=true` 的 `active:all/all:all`，由 parent 枚举当前全部月份；month invalidation 只投递规范化后的 `active/all:YYYY-MM`。只有 gateway 可用并接受 scope 时才返回 `invalidated_scopes`。SQL 旧 rows 不在请求线程删除，而由新的 dirty version 在 gate 处阻断，直到 worker 条件发布成功。
- 读取边界：`get_cost_statistics_freshness_gate(...)` 用单条 SQL 读取成本 metadata/current dirty、成本所需 App Settings 片段、当前 concrete month 的 Workbench/Bank Detail proof，并聚合全部 active Workbench month、Cost child、Bank Detail 与 latest dirty proof来校验同页全期间 statistics。`0122_cost_statistics_access_convergence_hot_paths.sql` 只为该证明补充 Workbench/Bank Detail latest-dirty 与 Workbench scoped source timestamp 的四个窄索引，不改变 freshness 语义。cost/WB/Bank Detail pending、processing、failed，已发布版本未追上 dirty version，依赖缺失/非法 settings shape、Bank Detail schema/status/source versions 异常、child 嵌入版本漂移，或 parent `source_shards` 不等于当前 concrete shards 均 fail-closed。concrete month 的主 rows 只受当前月 proof 阻断；parent drift 只把 global statistics 置为 non-fresh 并精确 ensure child。`all` parent 不读取虚构的 Workbench/Bank Detail `all`，也不因 parent 自身 readiness 为 `done` 跳过 child proof。页面 explorer 在 gate 之后才允许 ETag short-circuit、cost-local versioned Redis 和 `get_cost_statistics_page(...)`；cache miss 以一个 set-based SQL 返回 summary/facets/row count/`page_size+1` rows。cursor/ETag/cache key 绑定 published version、业务 source versions、tag token 与规范 query。bulk 导出只允许 `get_cost_statistics_export_page(...)` 的 SQL summary + bounded rows，并在文件生成后重新 gate；不存在 full-view read path。
- 行存储边界：`0107` 新增 `read_model.cost_statistics_bank_flow_rows`，`0108` 补齐生产 `fin_ops_app_runtime` 与本地 `fin_ops_app` 的结构化行读写授权。月份 shard 的 OA 配对成本行只写 `read_model.cost_statistics_rows`，全银行收支行只写 `read_model.cost_statistics_bank_flow_rows`；`read_model.cost_statistics_read_models.payload` 只保留 metadata/小型字段，禁止保存 `time_rows` 或 `bank_flow_time_rows`。页面 API 直接查询结构化行，不重建旧 DTO；内部 full loader 暂可从两张表重建，但不得回退 parent JSON array。
- `time_rows.bank_tag_*` 的全月来源是 `BankTransactionTagReadFacade` 暴露的 fresh `bank_detail` scoped read model，并经 `cost_statistics_bank_tags.bank_tag_context_from_row(...)` 归一化；禁止点查旧 Cost 行拼装增量、回读 Workbench 行内旧标签字段、银行明细 HTTP 或 canonical tag 表。
- 成本 projection 内的 bank-detail source version、transaction tags、month rows 必须由一次 `snapshot_for_month(...)` 快照读取共同提供；旧 `source_versions_for_scope_keys(...) + get_by_transaction_ids(...) + list_by_month(...)` 三段读取链路已删除。快照在 repository 内使用 `REPEATABLE READ READ ONLY`，同时覆盖目标月 rows 与正式关系引用的跨月流水 ID；projection 只做纯内存拆分和归一化。访问入口的 Workbench 依赖 enqueue owner 是 `CostStatisticsQueryService`，正在执行的 Cost job 遇到其他 non-fresh 依赖时仍由 `RuntimeWorker._enqueue_dependency_refreshes(...)` 精确补投；两者不能同时投递 Workbench 与 Cost。
- `bank_flow_time_rows.bank_tag_*` 的来源是成本统计投影层通过银行明细 read facade 批量读取的 fresh 收入与支出流水；它是 `按标签`、`按时间` 的全流水统计输入。金额均以正数绝对值输出，方向决定进入支出或收入汇总，不计算净额，也不向页面展示合并总额。`time_rows` 继续是 OA 配对支出输入。
- Audit 不把上述投影依赖误当成 canonical 完整性来源：银行收入与支出集合直接对 `app.bank_transactions` 做双向 equality，标签内容再与通过独立 bank-detail proof 的有效标签比较；同时复用 Workbench 全页面 proof。
- 银行支出 canonical identity 与页面 payload 一律使用 `coalesce(legacy_mongo_id, id::text)`；无标签流水的 code 为空，但 label/primary/sub/path 统一为 `未标记` 语义。Audit 不得拿内部 UUID 与 legacy 页面 ID 比较，也不得把空标签与 `未标记` 误判为业务差异。
- 成本统计标签规则由 `AppSettingsService` 持久化；`CostStatisticsQueryService` 只调用 settings owner 的无 I/O mapper，从本次 gate 已读取的 settings snapshot 生成 selected leaf codes 和 cache token，再在 query/export 层过滤。该规则不是投影 source version，保存时不触发 read model rebuild；禁止为标签筛选再次 reload settings。
- `bank_accounts` 的来源是 settings owner 的银行账户映射，投影层通过 `cost_statistics_bank_accounts.py` 归一为 parent 小型 metadata，并以 `bank_account_mappings_fingerprint` 纳入 source version。page repository 合并该 metadata 与结构化 rows 输出银行 facets；禁止恢复浏览器端 `bank_accounts + time_rows` 全量合并。
- Upstream read model 输入：全月月份 shard 消费 Workbench active generation；当前访问必须先证明该 active generation 已追上 canonical expected versions。父 scope 只读取月份 metadata，并以两次 SQL aggregate 生成小型 metadata，不加载月份业务 rows、Workbench `all`、历史 generation 或 child JSON arrays。
- Relation identity：普通访问收敛只消费 Workbench active generation 中的正式 `case:<case_id>` identity；禁止行级历史 delta、裸 `case_id`、双 identity 或放宽 Audit。
- Audit lineage：月份 scope 已保存的 `workbench_source_versions` 必须与同一 snapshot 中当前 active generation 精确相等；`bank_detail_source_versions` 只排除 Cost 不消费的执行计数 `source_version` 与嵌套 `workbench_relation_source_versions`，其余已知及未来新增字段必须与当前 bank-detail scope 精确相等，且 Bank Detail 本身仍须 fresh/drained。父 scope 的 `cost_statistics_parent_source=materialized_shards`、`source_shard_count`、`source_shards` 必须直接来自当前同 project scope 的全部 concrete month metadata，而不是从非空业务 rows 反推，确保合法空月份也进入精确证明。无需新增 lineage 表。
- 父 scope 正式重建会删除不再存在于 Workbench active month shard 集合中的旧 cost_statistics month scopes 及两张结构化行表记录；旧 shard 不得继续进入 Audit、parent rollup 或页面月份集合。projection 不再写删旧无版本 Redis key；scope 缺失/non-fresh 的 PostgreSQL gate 会阻止读取残留 query cache，versioned cache 由 namespace/TTL 自然淘汰。
- `active:all` / `all:all` 的 summary 与 project/expense 聚合从当前 concrete `cost_statistics_rows` 重算，全流水摘要从 `cost_statistics_bank_flow_rows` 重算；父模型不重复物化 parent rows，也不保存两类 row array。Audit 必须使用同一 child-union 口径，不能以 parent row 表为空误报 summary。
- 页面标题 `statistics` 的银行总数、收支、项目/费用/标签数继续由 `active:all` / `all:all` parent 提供并绑定同一 freshness gate；`statistics.cost_transaction_count` 例外由当前 explorer 单条 SQL按 parent 全期间集合与标签规则覆盖为唯一 OA 成本流水数，不随 view、时间范围、下钻 filter、cursor 或 pagination 变化，也不按 allocation row 重复计数。parent/child 非 fresh 时仍返回 `statistics=null`。
- 成本 bank-flow 字段证明按银行流水 canonical legacy/public transaction id 连接 `bank_detail_rows.transaction_id`；不得只用 PostgreSQL UUID 连接后把完整投影误报为缺失。
- Read-model schema version：`2026-07-cost-statistics-oa-bank-flow-v11`。v11 固化银行中心资格、原生月份去重、多 OA 精确拆分、stable allocation row key 与唯一流水计数，并移除 Cost 对 OA 附件发票 parser version 的依赖。物理表不变、无 migration；旧 v10 scope 必须经 gate fail-closed 后全量重投影，禁止 dual-read/fallback。
- Audit 重算结构化 bank-flow rows 时，bank-detail identity 必须同时接受 PostgreSQL UUID 与 legacy public transaction id；两者都只能归一到同一 canonical `app.bank_transactions` 对象。投影月份直接使用 `cost_statistics_bank_flow_rows.scope_month`，与 bank-detail 的 `scope_key` owner 比较（仅 bank-detail owner 缺失时回退 `trade_date`）；不得展开 parent metadata 中已禁止的 `bank_flow_time_rows`。禁止只按其中一种 ID 连接或只按可空日期字段校验而把完整投影误报为明细缺失。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/CostStatisticsPage.tsx` |
| Frontend components | `web/src/components/cost-statistics/*`、`web/src/features/cost-statistics/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Backend service | `cost_statistics_query_service.py`、`cost_statistics_runtime_service.py`、`cost_statistics_source_versions.py`、`cost_statistics_sql_projection.py`、`cost_statistics_bank_tags.py`、`cost_statistics_bank_accounts.py`、`app_settings_service.py` |
| Repository / SQL | `cost_statistics_read_model_repository.py`、`cost_statistics_sql_projection.py`、`postgres_repositories/read_models.py`、`postgres/migrations/0105_cost_statistics_freshness_gate.sql`、`postgres/migrations/0107_cost_statistics_structured_bank_flow_rows.sql`、`postgres/migrations/0108_cost_statistics_bank_flow_runtime_grant.sql`、`postgres/migrations/0122_cost_statistics_access_convergence_hot_paths.sql` |
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
- 成本统计标签规则是本模块唯一写入口；route 保持 thin owner，只委托 `AppSettingsService` 持久化 canonical selection/version/audit，不返回 `freshness_targets` / `operation_barrier_targets`。页面保存成功后清除当前 explorer/export 派生状态、递增 query nonce 并关闭抽屉；规则在 query/export 层过滤，因此不写 dirty scope、不等待 worker，也不触发全量 read model rebuild。relation 等真实投影 source mutation 只在当前 Cost GET 时通过两阶段 gate 收敛。
- 性能边界：首屏 API/read model 只能走 PostgreSQL gate + cost-local fresh Redis/page SQL；API miss 不同步扫描 Workbench/live service。前端不得恢复 TTL payload cache、full DTO、浏览器全量聚合或首屏 `active:all`。项目/费用类型导出筛选仅在用户动作后并行请求两个 bounded all-scope facets；time/bank-tag 不发该 I/O。当前 view-specific cursor 已本地闭环，但生产 EXPLAIN/SLO 尚未验证；不得在无证据时增加索引或修改共享 pool。
