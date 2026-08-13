# 成本统计实施决策

## 2026-08-14：OA 当前金额归集与详情链路拆分

- `按项目`、`按银行`、`按 OA 费用类型` 改为 OA-first：年/月按 OA 完成时间，支付申请按 OA 当前金额，日常报销逐个按子付款项当前金额、项目、费用类型和内容归集。多 OA、多流水关系不按流水做比例或顺序拆分。
- active 正式关系只证明付款关联。关系内单一账户用于银行归属；多个账户统一显示 `混合支付账户`。收入不进入 OA 成本，关系组金额差异只在详情中如实展示，不修改归集金额。
- 旧单一 `/transactions/{id}` 详情链删除，改为银行事实 `/bank-transactions/{id}` 与 OA 成本 `/allocations/{id}` 两条有界读接口。页面右栏统一命名为“OA 成本归集明细”，并显示“归集金额”；真实流水只出现在“关联付款流水”证据区。
- OA 投影补齐 `approved_at`，来源为已完成 Mongo 文档的 `modifiedTime`；版本提升后原子重建当前投影。未新增表、索引、read model、worker、cache 或 fallback。
- 缺少完成时间、项目、费用类型、正数金额或子付款项 ID 的归集单元明确排除并返回质量统计；重复归集单元跨 active relation 时返回完整性冲突。不存在“成本待分配”或表头金额回退。
- 口径限制：这是“有付款关系证据的已完成 OA 当前成本”，不是部分实付或退款净额。没有 canonical 部分付款/退款分摊事实时，不从 N:M 关系猜测。

## 2026-08-10：紧凑筛选栏与按时间双栏布局

- 五个视图改用共享 HeroUI 切换控件；非时间视图复用共享搜索和“全部 + 年/月”控件，标题筛选带收敛为 52px 紧凑高度。按时间视图使用固定高度的 `15% / 85%` 永久展开时间栏与内部滚动明细表。
- 删除页面私有搜索、scope picker 与旧 CSS；canonical API、scope 参数、下钻、导出和 direct-read I/O 不变。

## 2026-08-07：流水详情右侧抽屉与完成态 OA 回归锁定

> 详情 endpoint 与 OA 金额分配口径已由 2026-08-14 决策取代；本节只保留抽屉交互和 scoped canonical read 的历史决策。

- 删除成本统计专属详情 modal 及其大卡片样式，复用全站 HeroUI `AppDrawer`、`Chip`、`Separator` 和 `Button`；详情内容改为扁平分区与字段行，不保留解释性文案。
- 点击流水先打开抽屉，再发起既有单次详情请求；loading 使用无文字 skeleton，失败与重试只在抽屉内处理，不占用 explorer/导出状态。
- 生产性能探针发现单条详情仍走全期间 snapshot 后，将详情请求已有的 `scope/view` 下推到 canonical repository，并固定 `include_statistics=false`；不增加缓存、read model、endpoint 或兼容路径。
- 保留 policy 中共享的完成态 OA 判定作为唯一业务入口，不新增过滤器、API、查询或状态；补齐 project、bank、expense_type 的 policy/API 回归，明确进行中 OA 不进入成本视图，time/bank_tag 继续只读银行事实。
- 删除 `CostTransactionDetailModal` 和旧 `.cost-detail-modal*` 样式，不保留兼容容器或双路径。

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
- 按标签桌面列宽为 `20% / 20% / 60%`；支出在上、收入在下，零金额方向项不进入金额区。

## 2026-07-28：日常报销付款明细级成本分配

> 本节的“仅精确等额才拆分、否则流水金额只计一次”已由 2026-08-14 OA-first 口径取代，不再是当前业务事实。

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

## 2026-07-29：按标签零金额方向项清理

- 主标签和子标签的金额区复用同一个 `DirectionAmount` 合同：对应金额为零时，方向字样、金额值和无障碍标签整体不渲染；非零金额的颜色、顺序和格式保持不变。
- 笔数区继续显示 `支出/收入 N 笔`，包括零笔；页面总计、排序、搜索、下钻和 API DTO 不变。
- 删除旧 `hideZeroValue` 语义，不保留 CSS 隐藏、调用方分支或兼容属性；本次没有新增 I/O、状态、依赖或跨页面行为。
## 2026-08-10 - 导出中心原生控件收敛

- 成本导出中心的按钮、复选框、单选组和日期输入统一为 HeroUI 原生组件，普通导出抽屉从 `xl` 收敛为 `lg`。
- 导出类型、列选择、日期范围、预览和下载 API 合同不变；删除原生 input 的旧私有样式，不保留双控件路径。
- 成本页继续 direct canonical read，不引入 read model、worker、cache 或跨页面 I/O。
