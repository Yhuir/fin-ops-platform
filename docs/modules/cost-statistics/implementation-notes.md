# 成本统计实施决策

## 2026-07-26：改为直接 canonical read

- 保留现有 API、视图、标签规则和导出业务合同。
- 删除 Cost 专属 read model、投影、worker、scope、source version、runtime service 与生命周期入口。
- 每个请求从一个 PostgreSQL `REPEATABLE READ READ ONLY` 快照读取统一事实源。
- 业务计算集中在无 I/O 的 `CostStatisticsPolicy`；repository 只负责读取，route 只负责 HTTP。
- Audit 改为直接 canonical proof，Cost 不再出现在 App Status read-model/worker 诊断中。
- migration `0126` 终止遗留 Cost runtime 行并删除旧 Cost read-model 表。

这是本模块当前唯一读链。历史的 parent/shard、freshness gate、dependency defer、conditional publish 和 Redis cache 设计已经被本决策取代，不再作为实现依据。

## 2026-07-28：局部加载与 canonical scope 下推

- 删除后续 explorer 请求中的 `setLoadedExplorer(null)` 全页清空链路；保留已加载的上游栏位，按 `surface / children / rows` 只替换受影响区域。
- 页头统计仅在本次页面会话的首次 explorer 请求计算；后续请求使用 `include_statistics=false`，页头沿用同一 canonical 响应得到的统计值。
- repository 只在后续非 `all` 请求下推 `txn_month` 范围；成本视图以命中银行流水筛 active relation 后扩展全部 relation 成员，避免破坏跨月份配对。
- `time / bank_tag` 后续请求不读取 OA 与配对关系。所有路径仍在单个 `REPEATABLE READ READ ONLY` 快照内直接读取 canonical tables，没有 read model、cache、worker 或 fallback。
- 按标签桌面列宽为 `20% / 20% / 60%`；支出在上、收入在下，零金额只隐藏金额数值。

## 2026-07-28：日常报销付款明细级成本分配

- repository 和 API 保持不变；现有 canonical OA payload 已包含稳定 `expense_item_id`、项目、费用类型、内容和金额，不新增表、read model、worker 或查询。
- 支付申请继续作为一个 OA 分配单元；日常报销在 `CostStatisticsPolicy` 内展开为 `expense_items` 分配单元。
- 单流水仅在全部单元 ID 有效唯一、金额为正且合计按分等于流水金额时拆分。其它情况不做比例、顺序或子集推断，流水金额只计一次。
- 歧义场景仅保留所有单元完全一致的共同项目/费用维度，否则使用 `未归集项目` / `未分类`；删除成本统计运行时的 `多项目` / `多费用类型` 合成口径。
- project、bank、expense_type、详情与导出共享同一组分配行；`transaction_count` 继续按银行流水去重，详情 `linked_oa_count` 按 OA 去重而不是按付款明细计数。
- canonical repository 直接从同一 snapshot 的 `app.oa_applications.normalized_payload` 映射成本 policy 所需父单/付款明细字段，避免 OA repository 构造完整 record 并递归复制成本页面不消费的附件与发票树；不减少成本归因字段，也不新增查询或缓存。

## 2026-07-29：direct-read 热路径与交互请求收敛

- 保持 canonical API 直读，不引入 Redis、read model、新 endpoint 或 fallback。
- bank snapshot 不再读取成本计算未消费的 `raw_payload`；账户解析器按 snapshot 构造一次，不再按流水逐行构造。
- explorer route/service 删除从未命中的 ETag/304 占位合同，响应继续使用 `private, no-cache` 并每次读取当前事实源。
- 时间范围选择在一次 session state 更新中同时提交 mode/year/month，并在发请求前清除下游选择；项目、银行、OA 费用类型、标签视图不再先携带旧选择请求一次、随后再补发清理后的请求。
- 页面切换和三栏下钻继续局部加载；同一次用户操作最多产生一个 explorer 请求，不清空整页。

## 2026-07-29：当前视图搜索、真实时间字段与自动分页

- explorer 增加一个最长 200 字符的规范化 `query`，并将其绑定 cursor；policy 在聚合、facets、summary 和分页之前过滤当前视图事实行，不增加 repository 查询。
- `project / bank / expense_type` 只搜索 OA 配对 allocation；`time / bank_tag` 只搜索完整 canonical 银行事实。`time` 不再渲染“未配对OA / 未分类”占位字段。
- 主标签和子标签复用同一个仅支出、混合、仅收入、零金额排序键；UI 将支出放在收入上方，用独立笔数字段和既有方向颜色表达。
- 五个视图复用一个紧凑搜索框，使用 200ms debounce、IME composition 保护和 AbortController；项目/银行三栏采用 `24% / 24% / 52%`，右侧明细禁止横向滚动。
- 删除手动“加载更多”按钮和死样式；复用现有 cursor API，在表格原生滚动容器接近底部时自动追加，失败只在当前明细区重试。
- 保持 canonical API 直读，不引入 Redis、read model、worker、新 endpoint、依赖或跨页面 I/O。
