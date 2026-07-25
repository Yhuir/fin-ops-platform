# 成本统计模块边界与 I/O

日期：2026-07-25

## 模块化状态

- 状态：READY_FOR_UNIFIED_DEPLOYMENT / DEPLOYMENT_HOLD
- 当前边界可信度：high
- 目标边界：成本统计页面按视图选择唯一事实投影。`time|bank_tag` 直接读取 fresh `bank_detail` 结构化行；`project|bank|expense_type` 读取 `cost_statistics` OA allocation SQL read model。query gateway 在任何 payload I/O 前执行与视图一致的 exact-scope freshness proof。
- 当前结论：local/non-SQL explorer fallback、route-owner live service fallback、live export workbook helper 和旧 `ProjectDetailExportService` 已删除。成本统计页不再暴露项目范围切换按钮，页面查询固定使用 `project_scope=active`；`project_scope=all` 仍是后端 API/export/read model 合同。按银行统计的银行全集来自 settings owner 输出的银行账户映射；成本统计标签规则来自 app settings owner，页面与导出从 dependency-bound freshness gate 取得选择 token，再由 query owner 过滤，不进入 read model source versions，也不触发全量重建。`按项目`、`按银行`、`按OA费用类型` 只统计被规则选中、位于银行原生月份且属于 active 正式 OA+bank relation 的支出流水；relation 在 `paired` / `unpaired`、是否有发票均不改变资格。`按标签`、`按时间` 统计 fresh Bank Detail 中被规则选中的全部银行收入与支出流水。
- 旧代码删除状态：legacy `CostStatisticsService`、`CostStatisticsReadModelService`、warmup job、旧 root/project HTTP contract、full-view loader、无版本 Redis writer、全量 load/save、`cost_tax_sql_projection.py` 混合 owner，以及复制 Bank Detail 的 `read_model.cost_statistics_bank_flow_rows` writer/query/Audit 路径均已删除。migration `0123_drop_legacy_cost_statistics_bank_flow_rows.sql` 删除该物理表，不保留 dual-read、fallback 或兼容 shim。当前页面只使用 explorer、export-preview/export、transaction 和 tag-rules 合同；query miss/stale 只返回 non-fresh 并经统一 gateway 入队当前视图真正需要的 exact scope。前端 5 分钟 explorer Map、首屏 `active:all` 预取和零调用 clients 也保持删除。

## 职责边界

### 负责

- 成本统计页面汇总、筛选、父聚合和明细读取。
- OA 配对统计继续展示自身支出汇总；全流水的按时间、按标签视图不展示收入与支出的合并总金额。summary、方向金额/笔数和 percentages 均由当前 fresh page query 的完整筛选集合在 SQL 中计算，页面不得从当前页重算或回读源表。
- 成本统计页面的按银行统计；银行账户全集来自 `app.app_settings.bank_account_mappings` 经后端 owner read port 进入 gate 的小型 metadata，再由 page repository 与结构化成本行生成银行 facets。页面不做全量账户聚合，也不调用设置页 API。
- 成本统计页面的 `按标签` 三栏视图；主/子标签 facets 与选中层级 rows 由 cost-owned query repository 从 fresh `read_model.bank_detail_rows` 计算，不调用银行明细 HTTP/API，也不复制第二份 bank-flow read model，更不把完整 rows 传到浏览器派生。
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
| 页面交互鲜度 | explorer request lifecycle + explorer freshness envelope + 页面 activation/event hint | 页面首次访问、focus、hidden→visible、BFCache restore 或 relation 轻量提示后，都通过同一正常 explorer GET 重校验当前 scope。响应为 refreshing 时，页面立即显示 cost-local inert overlay，并以 150ms 间隔有界重试、最长 3s；fresh 即解锁，超时保持明确 non-fresh。不调用 operation barrier、不轮询全局 App Status、不引入 cost-specific SSE。隐藏页面不主动发 explorer I/O；隐藏→可见后立即重校验。另一个已经可见的窗口经现有轻量事件后独立 GET。 |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API / `cost_statistics_page_audit.py` | admin-only 调用 `page-audit?page=cost-statistics`；registry 使用唯一 `cost_statistics` executor，通用只读 CLI 与 System Audit 也只到达同一个成本 owner。该 owner 在 caller-owned repeatable-read read-only snapshot 内，从 active generation 中的正式 OA+bank group 独立重算 OA allocation exact-set；`time|bank_tag` 的全银行 expected-set、金额、方向和标签直接由 canonical bank facts 与已验证的 Bank Detail projection证明，不审计、读取或修复已删除的 Cost bank-flow 表。任一缺失、额外、跨月重复、金额/字段漂移均 blocking。Audit 只读、不入队、不修复、不拥有第二份投影。 |
| 银行账户全集 | `AppSettingsService.get_cost_statistics_source_settings_payload()` / `app.app_settings.bank_account_mappings` | 投影层读取 settings owner 输出并写入 explorer metadata；query gate 在同一 SQL statement 只读取成本所需 settings JSON 片段，用于当前 fingerprint 与 bank facets metadata，不再次调用 settings service。页面不得直接读取 settings API 或设置页面状态 |
| 银行自动标签规则版本 | `AppSettingsService.get_cost_statistics_source_settings_payload()` / `app.app_settings.bank_transaction_tags` | 进入 `source_versions.bank_auto_tag_rules_version`；普通规则更新不再通过 `bank_auto_tag_rules_changed all` 主动 fan-out，成本 query dependency gate 在页面访问时比较当前 settings snapshot 与投影版本并精确 enqueue 当前 scope |
| 银行明细有效标签 | fresh `bank_detail` read model / `BankTransactionTagReadFacade` | `time|bank_tag` query 直接读取 `read_model.bank_detail_rows`，并用 Bank Detail scope status、schema、row count、业务 source signature 与标签规则版本证明 fresh；不经过 Cost worker。OA allocation projection 仍可通过 `snapshot_for_month(...)` 一次取得目标月流水和关系引用的跨月流水，用于 `cost_statistics_rows` 的标签与原生月份证据；跨月补充行不得进入错误月份。 |
| 成本统计标签规则 | `AppSettingsService.get_cost_statistics_tag_selection_payload()` / `app.app_settings.cost_statistics_tag_selection` | route 只暴露归一后的收入/支出主子标签、`__uncategorized__` 未分类标签和已选 leaf codes；默认未配置时等价于全选当前有效收入与支出标签 + 未分类，显式空数组表示全部不进入成本统计。legacy 显式选择升级到 schema v2 时保留原支出选择并一次性加入当前有效收入标签。保存规则不写 read model、不写 dirty scope |
| 全流水标签统计输入 | `CostStatisticsQueryService` + cost-owned PostgreSQL query repository | `time|bank_tag` 在 Bank Detail exact-scope gate fresh 后，直接从 `read_model.bank_detail_rows` 计算 summary/facets/bounded rows；`year|all` 只组合 fresh 月 scope。禁止调用银行明细 HTTP、扫描 canonical live facts、复制到 Cost 表或回退旧 JSON array。 |
| 流水标签三栏统计 | `CostStatisticsPage.tsx` | 输入是 page API 的 `facets.bank_tag_primary`、`facets.bank_tag_sub` 与当前层级 bounded `rows`；不存在旧 `bank_flow_time_rows -> time_rows` fallback，详情接口失败也不得从列表行拼装本地详情 |
| 项目明细/流水详情/导出请求 | `routes_cost_statistics.py` | 只调用 `CostStatisticsQueryService`。流水详情必须携带 `view + scope + project_scope`；规范 scope同时约束 freshness gate与 point SQL，不能跨 scope读取未证明 fresh的行。缺失或非法参数返回 `400`，non-fresh返回 `409 cost_statistics_read_model_not_fresh`。bulk preview只读 summary+8行，下载每批最多1,000行；`time|bank_tag`走 Bank Detail profile，其余走 OA allocation profile。 |
| Refresh scope | `cost_statistics` manifest | active/all month + queryable parent aggregate。普通 parent event 只重建廉价 rollup，不能读取 `app_status_readiness` 后补投全部历史月份；精确 child 判定只属于 query repository gate。显式 maintenance/reset 的 `force_refresh=true` parent 才枚举全部当前月份 shard并传播 force；月份 worker执行完整重建，只有非 force 且业务 `source_versions` 完全一致时才允许 unchanged CAS。 |
| Workbench 月度输入 | `read_model.workbench_generations` active generation + `read_model.workbench_groups` | 先定位 active generation，再按 `generation_id + scope_key` 读取 `group_type=relation` 且含 OA+bank 的 `paired` / `unpaired` groups；candidate、unpaired singleton、无 OA relation 和显式 `in_progress` OA 不进入 OA 成本。OA 顶层 `workflow_status` 复用 canonical completed aliases，空值仅作为历史 completed 兼容；发票成员不参与资格判断。禁止按裸 `scope_key` 扫描历史 generation。 |
| 关系变更 | canonical relation source version + Cost query owner | relation transaction和Workbench generation publish都不投递Cost。`project|bank|expense_type`请求先读取现有Cost gate；gate已non-fresh时跳过canonical全量证明并ensure其exact upstream/child。只有gate可fresh时才比较canonical Workbench；Workbench stale时，同次ensure exact Workbench month并stage当前project/page所需的exact Cost child，不stage parent或sibling。Cost worker复用manifest dependency fail closed/defer，依赖fresh后发布child并由成功child收敛parent；Workbench access和Cost parent使用稳定target token，在共享advisory lock内消除poll/完成窗口重复任务。`time|bank_tag`只消费Bank Detail语义proof与成本settings，因此跳过Workbench/Cost row pre-gate，绝不入队Cost。Workbench dirty不得阻塞这两个全流水视图。标题global statistics可保留完整parent lineage并独立返回`statistics=null/refreshing`，不能反向阻塞已经fresh的rows。 |
| 导入确认 | import processing service/job result | 只推进 canonical import facts/source version 并返回信息性 affected months；不返回 cost targets、不写页面 queue。成本页访问时由两阶段 dependency gate 收敛 requested active/all scope |
| ETC 页面刷新提示 | `invoiceFactUpdated` | 只在 ETC invoice facts 真正导入或成功删除时重校验当前 Cost scope；明确忽略 `etcBusinessBatchUpdated`。OA 草稿、提交/未提交决定和标题等 batch-only 状态不得让成本页面进入 overlay。事件只作提示，是否 fresh 仍由 Cost query gate 决定 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 成本统计 rows/summary | 前端页面 | query gateway 后返回 freshness；请求合同是 `scope + view + project_scope + 当前层级 filters + cursor + page_size<=100`。一笔银行流水可有多条 OA allocation row；金额按 allocation 求和，所有 transaction count 按 `transaction_id` 去重。`statistics.cost_transaction_count` 在同一 page SQL 中按 parent 全期间集合 + 标签选择统计唯一 OA 成本流水，不增加 HTTP 或 repository 往返，也不随当前时间范围变化。响应仍只含完整 summary、必要 facets、bounded rows、row count 和 next cursor。 |
| 页面交互锁 | 仅 `/cost-statistics` 成本业务区域 | 唯一 effective state 只有 `fresh` 解锁；其他状态在视图/范围/header actions/content 与 drawer body/footer 使用原生 `inert`、`aria-busy` 和 cost-local pointer layer。标题、Audit、App Shell、导航不锁。锁定时关闭 detail/export、自有 range popover 并取消可取消的详情/导出参考请求；不得修改共享 overlay、StatePanel、App Status 或其他页面。 |
| 页面 Audit 状态 | 标题附件 | 只有 audit status 与 explorer read model 均明确 fresh/pass 才显示成功；问题数量是有上限 sample。response 的 contract/issue code/snapshot identity 由唯一成本 Audit owner 输出，operations 层只添加 page registry envelope。 |
| Explorer bank accounts | 前端页面 | `view=bank` 的 `facets.bank_accounts` 合并设置中的银行账户全集与当前 scope 聚合；零金额账户仍可见。页面只消费 facet，不读取独立 `bank_accounts` full DTO |
| Source versions | read model/query gateway | OA allocation月份 scope 的完整业务 `source_versions` 包含当前 Workbench scope 业务 proof、Bank Detail 业务 proof、标签规则和账户映射。语义比较排除 Workbench active-generation `source_version`；`time|bank_tag` 使用 `cost_statistics_bank_flow_source_versions(...)` 移除未消费的 Workbench/OA provenance，只保留 Bank Detail exact-scope signatures、schema、row count、业务 source signature、标签规则、账户映射及未来未知语义键。Bank Detail 的执行计数、canonical gate 专用 context/update proof 和其内部 relation lineage不参与 Cost 语义相等。runtime dirty `source_version` 只用于 Cost 条件发布，不得混入业务 source versions。 |
| Project/detail/export payload | 前端页面 / 下载 | 页面 project 由 bounded page query 输出；OA transaction detail 从 `cost_statistics_rows` 返回 additive `cost_allocations`。`time|bank_tag` detail 从 fresh Bank Detail row point query返回，不伪造 allocation。bulk export-preview/export 使用与 `view` 相同的 freshness profile 和结构化来源；preview 只返回 summary + 8 行，下载每批最多 1,000 行写 write-only workbook，生成后用同一 profile 再次校验版本。 |
| Parent rollup | read model repository | scoped parent aggregate |
| Dirty scope | runtime queue | `project|bank|expense_type` GET发现Workbench stale时，同次只enqueue exact Workbench与当前project/page所需的exact Cost child；不直接enqueue parent或sibling project scope。这是访问时dependency-ordered exact fan-in，不是写后fan-out。两个event复用本次gate已计算的Workbench expected proof；Workbench worker和Cost worker分别验证token/scope后使用，避免相同canonical proof重复SQL。Cost child在依赖non-fresh时由worker短延迟defer，依赖fresh后发布；Workbench own token可原子去重active与最新成功同target，Cost child的Workbench依赖token只合并active waiter。target变化必须保留follow-up，dirty orphan/failed必须可恢复，不能被历史done吞掉。`time|bank_tag`只可ensure non-fresh Bank Detail scope。普通import只推进canonical source version，不直投Cost。worker用event `source_version`做条件发布；竞态失败保持`refreshing`。relation direct delta、Workbench publish fan-out、repository隐藏fan-out和第二队列路径禁止恢复。 |
| Access-to-fresh proof | 生产 smoke / Cost explorer | 从每个 consumer 首次 Cost explorer GET 开始计时。OA allocation view 必须证明 Workbench→Bank Detail→Cost exact scopes依次收敛；全流水 view 必须证明仅 Bank Detail exact scopes收敛且零 Cost event。最终 explorer 必须 `200 + fresh + source_versions changed + business assertion changed`；任一 event done 都不能冒充页面可见。mutation 成功到页面可见只作观察值，不得把页面尚未访问的时间计入访问 SLO。 |

## 持久化与投影

- Read model：`cost_statistics`
- Projection：`partitioned_scoped_parent_rollup`
- `all` 语义：`queryable_parent_aggregate`
- Worker：`cost-statistics` 与 `cost-statistics-secondary` 复用同一 event/scope/handler 合同并从同一 PostgreSQL durable queue 竞争 claim；旧 `cost-tax` 成本统计消费链路已移除。secondary 不拥有第二套事实、投影或发布路径。
- Relation-origin 写入入口为零：relation repository、UoW、turnover writer、自动匹配/lifecycle registry 与 Workbench publish 都不拥有成本 I/O。成本只在页面访问中执行 Workbench dependency gate 与 Cost gate。旧 `cost_statistics_relation_delta` / `workbench_shard_published` producer、worker handler、projection/repository、write-trace smoke、`workbench_relation_changed` / `turnover_relation_changed` 成本 reason、HTTP consumer 与隐藏 scope expansion均已从 production runtime 删除；SLO audit 只保留其字符串作为“出现即失败”的旧 fan-out signature，不是执行路径。
- Query owner：`CostStatisticsQueryService`；项目明细、流水详情、export-preview、export 都归属该 owner。
- Miss/stale owner：`CostStatisticsQueryService`对`project|bank|expense_type`先读取repository gate。gate已non-fresh时直接使用其exact dependency/child scopes并跳过canonical Workbench proof；只有gate可fresh时才比较canonical Workbench expected versions与active generation。不匹配时，同次ensure exact Workbench并batch stage当前project/page所需的exact Cost child；不stage parent或sibling。Cost worker沿manifest依赖fail closed/defer，成功child经已有month→parent路径收敛；共享target-token去重消除页面poll与完成窗口放大。`time|bank_tag`直接进入Bank Detail profile，只为non-fresh Bank Detail exact month入队，不入队Workbench或Cost。repository gate可同时返回独立global statistics状态；statistics drift只置空statistics并精确ensure其自身依赖，不能阻塞当前视图rows。
- 发布边界：`publish_cost_statistics_read_models(...)` 只负责 OA allocation 月份/parent 条件发布，`acknowledge_unchanged_cost_statistics_scope(...)` 只确认内容未变。月份正常重建原子替换 `cost_statistics_rows` 与 metadata，parent只发布小型 rollup。任一路径拒绝必须不完成 dirty、不 fan-out、不写 Redis。不存在 bank-flow Cost writer、行级 delta publisher、第二发布路径或兼容 fallback。
- Unchanged 判定边界：`CostStatisticsReadModelRepositoryPort.get_cost_statistics_scope_metadata(...)` 只按规范 scope point lookup parent `scope_key/entry_count/source_versions`，并证明 `:all` parent 已发布标题统计；不加载 payload/rows。projection 只在完整 source versions 精确相等且 parent统计存在时请求 unchanged CAS。repository 必须再次验证当前 dirty version 与 parent source versions；CAS失败保持 refreshing。该 I/O 不承担页面 freshness，也不得读取 Bank Detail rows或新增 full-view fallback。
- 失效边界：runtime 不拥有进程内 read model、local snapshot 或 persistence callback。显式 global invalidation 只投递带 `force_refresh=true` 的 `active:all/all:all`，由 parent 枚举当前全部月份；month invalidation 只投递规范化后的 `active/all:YYYY-MM`。只有 gateway 可用并接受 scope 时才返回 `invalidated_scopes`。SQL 旧 rows 不在请求线程删除，而由新的 dirty version 在 gate 处阻断，直到 worker 条件发布成功。
- 读取边界：`get_cost_statistics_freshness_gate(scope_key, dependency_profile)` 只有两个显式 profile。`workbench` 保护 OA allocation Cost rows；`bank_flow` 保护 `time|bank_tag` 的 Bank Detail rows。页面 explorer/detail/export都必须透传由 `view` 决定的相同 profile；ETag、cache、page SQL、point query和 workbook I/O 只能发生在对应 gate fresh 后。global statistics是独立 envelope，不得反向阻塞 fresh rows。
- 行存储边界：月份 OA 配对 allocation 只写 `read_model.cost_statistics_rows`。`time|bank_tag` 直接读取 `read_model.bank_detail_rows`；migration `0123` 删除旧 `read_model.cost_statistics_bank_flow_rows`。`read_model.cost_statistics_read_models.payload` 只保留 metadata/小型字段，禁止保存业务 row arrays。不存在 dual-read、内部 full loader或 parent JSON row fallback。
- OA allocation行的 `bank_tag_*` 来源仍是 `BankTransactionTagReadFacade` 对 fresh Bank Detail snapshot 的归一化结果；禁止点查旧 Cost bank-flow 行、回读 Workbench 行内旧标签字段、银行明细 HTTP 或 canonical tag 表。
- 成本projection内的bank-detail source version、transaction tags、month rows必须由一次`snapshot_for_month(...)`快照读取共同提供；旧`source_versions_for_scope_keys(...) + get_by_transaction_ids(...) + list_by_month(...)`三段读取链路已删除。快照在repository内使用`REPEATABLE READ READ ONLY`，同时覆盖目标月rows与正式关系引用的跨月流水ID；projection只做纯内存拆分和归一化。访问入口的dependency ordering owner是`CostStatisticsQueryService`：Workbench stale时同次投递exact Workbench与当前project/page所需的exact Cost child，parent只由成功child完成路径收敛；禁止sibling project scope、直接parent staging或写后producer。已运行Cost job遇到non-fresh依赖时，由`RuntimeWorker._enqueue_dependency_refreshes(...)`按manifest精确补投并defer。
- `time|bank_tag` 的全流水输入就是 fresh Bank Detail rows。金额以正数绝对值输出，方向决定进入支出或收入汇总，不计算净额，也不展示合并总额。`project|bank|expense_type` 继续使用 OA 配对支出 allocation rows。
- Audit 不把 Bank Detail 投影误当成 canonical 完整性来源：银行收入与支出集合对 `app.bank_transactions` 做双向 equality，标签内容与独立 Bank Detail proof 比较；OA allocation proof再复用 Workbench dependency collector。
- 银行支出 canonical identity 与页面 payload 一律使用 `coalesce(legacy_mongo_id, id::text)`；无标签流水的 code 为空，但 label/primary/sub/path 统一为 `未标记` 语义。Audit 不得拿内部 UUID 与 legacy 页面 ID 比较，也不得把空标签与 `未标记` 误判为业务差异。
- 成本统计标签规则由 `AppSettingsService` 持久化；`CostStatisticsQueryService` 只调用 settings owner 的无 I/O mapper，从本次 gate 已读取的 settings snapshot 生成 selected leaf codes 和 cache token，再在 query/export 层过滤。该规则不是投影 source version，保存时不触发 read model rebuild；禁止为标签筛选再次 reload settings。
- `bank_accounts` 的来源是 settings owner 的银行账户映射，投影层通过 `cost_statistics_bank_accounts.py` 归一为 parent 小型 metadata，并以 `bank_account_mappings_fingerprint` 纳入 source version。page repository 合并该 metadata 与结构化 rows 输出银行 facets；禁止恢复浏览器端 `bank_accounts + time_rows` 全量合并。
- Upstream read model 输入：全月月份 shard 消费 Workbench active generation；当前访问必须先证明该 active generation 已追上 canonical expected versions。访问owner把同次已计算且受queue大小限制的expected proof交给exact Cost child；worker重新计算token并校验Workbench scope后，只读取active generation actual versions做依赖比较，不再次加载canonical proof。没有proof的显式维护/旧event仍走原fail-closed canonical provider。父 scope 只读取月份 metadata，并以两次 SQL aggregate 生成小型 metadata，不加载月份业务 rows、Workbench `all`、历史 generation 或 child JSON arrays。
- Relation identity：普通访问收敛只消费 Workbench active generation 中的正式 `case:<case_id>` identity；禁止行级历史 delta、裸 `case_id`、双 identity 或放宽 Audit。
- Audit lineage：月份 scope 已保存的 `workbench_source_versions` 与同一 snapshot 中当前 active generation 按 Cost consumer semantic proof 比较，只排除执行游标 `source_version`，其余当前及未来业务字段必须精确相等；`bank_detail_source_versions` 只排除 Cost 不消费的执行计数 `source_version`、嵌套 `workbench_relation_source_versions` 与 canonical gate 专用 context/update proof，其余已知及未来新增字段必须与当前 bank-detail scope 精确相等，且 Bank Detail 本身仍须 fresh/drained。query gate、month worker、parent/child SQL 与 System Audit 必须使用同一语义。父 scope 的 `cost_statistics_parent_source=materialized_shards`、`source_shard_count`、`source_shards` 必须直接来自当前同 project scope 的全部 concrete month metadata，而不是从非空业务 rows 反推，确保合法空月份也进入精确证明。无需新增 lineage 表。
- 父 scope 正式重建会删除不再存在于 Workbench active month shard 集合中的旧 Cost month metadata与 `cost_statistics_rows`；旧 shard 不得继续进入 Audit、parent rollup 或页面月份集合。projection不写删旧无版本 Redis key；versioned cache 由 namespace/TTL 自然淘汰。
- `active:all` / `all:all` 的 OA summary 与 project/expense聚合从 current concrete `cost_statistics_rows` 重算；全流水统计直接从 fresh Bank Detail month rows聚合，不在 Cost parent重复物化。Audit必须使用相同边界。
- 页面标题 `statistics` 的银行总数、收支、项目/费用/标签数继续由 `active:all` / `all:all` parent 提供并绑定同一 freshness gate；`statistics.cost_transaction_count` 例外由当前 explorer 单条 SQL按 parent 全期间集合与标签规则覆盖为唯一 OA 成本流水数，不随 view、时间范围、下钻 filter、cursor 或 pagination 变化，也不按 allocation row 重复计数。parent/child 非 fresh 时仍返回 `statistics=null`。
- Read-model schema version 仍为 `2026-07-cost-statistics-oa-bank-flow-v11`，用于 OA allocation contract；`0123` 只删除不再需要的复制表，不改变 OA allocation DTO。旧 scope 仍经 gate fail-closed 后重投影，禁止 dual-read/fallback。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/CostStatisticsPage.tsx` |
| Frontend components | `web/src/components/cost-statistics/*`、`web/src/features/cost-statistics/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Backend service | `cost_statistics_query_service.py`、`cost_statistics_runtime_service.py`、`cost_statistics_source_versions.py`、`cost_statistics_sql_projection.py`、`cost_statistics_bank_tags.py`、`cost_statistics_bank_accounts.py`、`app_settings_service.py` |
| Repository / SQL | `cost_statistics_read_model_repository.py`、`cost_statistics_sql_projection.py`、`postgres_repositories/read_models.py`、`postgres/migrations/0105_cost_statistics_freshness_gate.sql`、历史创建/grant migration `0107`/`0108`、`postgres/migrations/0122_cost_statistics_access_convergence_hot_paths.sql`、`postgres/migrations/0123_drop_legacy_cost_statistics_bank_flow_rows.sql` |
| Worker/read model | `cost_statistics_read_model_refresh.py`、`cost_statistics_derived_lifecycle_executor.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_cost_statistics*.py`、`web/src/test/CostStatistics*.test.*`、`web/e2e/cost-statistics-*.spec.ts` |

## 依赖方向

- 允许依赖：workbench active generation read model、workbench relation read model、settings owner read port、`BankTransactionTagReadFacade`、fresh Bank Detail repository、成本专属 OA projection、query gateway。
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
- Cost source-version 相等必须使用 consumer-semantic proof：忽略 Workbench active generation 的易变 `source_version` 和 Bank Detail 的执行游标/内部 relation lineage/canonical gate-only context proof，但保留 Cost 直接消费的 builder/schema、业务 signature、row count、标签规则和账户映射。Workbench 发布新 generation 不得单独令全部历史 Cost 月份 stale；真实业务字段变化仍必须精确阻断对应月份。
- 性能边界：首屏 API/read model 只能走 profile-specific PostgreSQL gate + bounded page SQL；API miss 不同步扫描 live facts。`time|bank_tag` 不等待 Workbench/Cost rebuild，标题 statistics 单独收敛；生产 test-owned fixture 必须证明写快速返回、写后零 fan-out、首次访问只触发必要 scope 且 rows 在 3 秒内 fresh。前端不得恢复 TTL payload cache、full DTO、浏览器全量聚合或首屏 `active:all`。项目/费用类型导出筛选仅在用户动作后并行请求两个 bounded all-scope facets；time/bank-tag 不发该 I/O。当前 view-specific cursor 已本地闭环；在生产 SLO 证据前不得宣称通过，也不得在无 EXPLAIN/证据时增加索引或修改共享 pool。
