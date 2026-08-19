# 成本统计实施决策

## 2026-08-20：无 OA 成本范围层级与有效项目边界

- 候选事实、GET/PUT、成本归集 policy 和 canonical 查询保持不变；前端直接按已有标签 `path` 展示主子层级，不新增 DTO、接口、组件层、依赖或 I/O。非叶子主标签只显示一次且没有 checkbox，叶子按稳定 code 选择；单层 path 本身就是可选叶子。
- 服务端现有 AppSettings 归一化边界增加“每个已提交虚拟项目至少一个标签”的写入校验；`projects=[]` 继续合法，历史读取继续保留不可用选择。校验失败不写设置、不推进 CAS version、不产生部分状态。
- 删除旧 `leafLabel()` 和扁平双列渲染合同，不保留隐藏 fallback。前端保存按钮与行内提示提前阻止空项目，后端校验仍是最终事实边界。
- 性能边界不变：候选只在打开/保存抽屉时读取，前端线性分组并 memoize，不增加网络、SQL、worker、cache 或跨页面刷新。

## 2026-08-18：付错退款收口为关系净支出

- 三种归因视图先在 active 关系内计算 `净支出 N = 支出原额 B - 明确付错退款 R`；普通收入不参与。删除把退款收入独立拆成负成本行的旧路径，右栏、搜索、汇总、分页和导出统一只消费净归因行。
- 为保留多支出、多账户的真实日期和账户，先按支出原额权重将 `N` 分回真实支出流水，再按 OA 原始金额权重分到 OA 单元；两级复用同一个确定性最大余数算法按分闭合。无退款关系的输出不变。
- OA 合计等于净支出时，OA 单元成本等于 OA 原额；不等时使用 `OA 单元原额 × N / OA 合计`。1050 支出、35 退款、OA 合计 1015 的住宿费 710 只输出一条 710 成本行。
- allocation detail API shape 不变，付款证据仍保留原始正金额和方向；成本抽屉把退款显示为 `-35.00`，同时展示本项净成本、支出原额和关系净支出。`time|bank_tag` 仍展示真实 1050 支出与 35 收入。
- 未新增数据库、repository 查询、worker、read model、cache、兼容分支或前端隐藏逻辑；旧的独立退款成本事件循环已从唯一 policy 链删除。

## 2026-08-18：成本统计复用银行规范分类投影

- 生产 PostgreSQL 路径删除成本专属 `_postgres_category_provider`、分类/确认表重复装载和 Python 自动重分类。
- `PostgresCostStatisticsCanonicalRepository` 在原有 `REPEATABLE READ READ ONLY` 快照内，对当前银行流水 ID 一次调用银行分类 owner 的 `effective_category_projection_rows(...)`；`time|bank_tag` 仍不读取 OA/关系，三种归因视图仍只扩展命中关系的完整成员。
- canonical-only confirmation 通过规范分类 SQL 的 UUID/legacy identity 连接解析为公开流水 ID；人工确认不再错误落入“未标记”，内部转账也不再由成本模块维护第二套算法。
- 自动识别和人工覆盖的 `internal_transfer` 统一形成一个“内部往来款”主/子标签；无 effective code 的外部往来候选即使携带展示文案也继续归入“未标记”。
- API shape、五视图人口和金额口径不变；空银行集合跳过分类查询，不新增 cache、read model、worker、migration 或 fallback。

## 2026-08-18：五视图银行事实边界与无 OA 范围

> 本节“退款作为独立负成本事件”的金额实现已由同日“付错退款收口为关系净支出”决策取代；原始视图边界和无 OA 范围仍有效。

- 五个视图统一消费银行成本事件并按银行交易日期筛选。已完成 OA 关系中的支出为正成本；同一 active 关系中明确标记“付错退款”的收入为负成本；普通收入不进入成本统计。
- 每条银行事件独立按关系内 OA 原始金额比例拆到 OA 归集单元，按分采用最大余数法闭合。详情公开 OA 原始金额、比例、银行事件原额，以及关系总支出、退款、实际现金成本、差额和现金比例。
- 关系中存在进行中 OA 时整组不统计；零/缺失权重只保留内部防除零判断，不新增“待分摊”或“数据异常”产品状态。真实 OA 费用类型缺失时进入“未填写 OA 费用类型”，不再用质量排除隐藏。
- 原有“成本统计标签规则”抽屉原位收敛为“无 OA 成本范围”：虚拟项目名和标签默认空；候选仅来自当前实际无 active OA 关系的支出流水标签；命中选中标签后仍按每笔流水复核无 OA。设置对全部历史期间生效。
- `按 OA 费用类型`更名为`按费用类型`，无 OA 行进入“无 OA 分类”。三种归因视图右栏更名为“成本明细”，详情请求由行级 `row_kind` 决定。
- 删除旧 OA-first 金额、OA 完成日期范围、混合支付账户、完整银行收支 time/tag、默认全选标签、按页签推断详情类型和标签归档时静默移除成本选择等旧链路；不新增表、read model、worker、cache、endpoint 或第二个抽屉。

## 2026-08-18：支付申请费用类型读取修复

- OA Mongo 归一化按表单读取权威字段：支付申请读取可配置 `category`，日常报销明细读取 `purposeType`；删除两种表单共用候选键和递归同名字段扫描。
- OA projection 版本提升至 `2026-08-18-form-specific-expense-type-v8`，通过既有幂等同步重投影历史 OA；不直接修改 PostgreSQL 投影数据，也不按申请事由猜测费用类型。
- 修复验收以源字段真实有效数量为准：有效 `category` 必须恢复为标准费用类型，空值或非法值继续显示“未填写 OA 费用类型”，不承诺无证据地把历史缺失数强制归零。

## 2026-08-16：详情抽屉统一公开字段视图

- OA 成本与付款流水详情继续使用共享 HeroUI `AppDrawer`，内容收敛为紧凑的分区 label/value 行；抽屉宽度统一为 800px，并保留窄屏自适应。
- 删除用户无须知晓的 `OA 单号`、`子付款项 ID`、`关系组`，将关系校验改为业务可理解的“金额核对”；不改变成本归集、金额计算、详情 API 或导出 I/O。
- 没有新增 backend、数据库、read model、worker、缓存或兼容链路；旧详情字段和旧排版不再参与渲染。

## 2026-08-14：OA 当前金额归集与详情链路拆分

> 本节的 OA-first 金额、OA 日期、混合账户和收入隔离口径已由 2026-08-18 决策取代；仅保留当时的详情 endpoint 拆分历史。

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

> 本节的两套事实域描述已由 2026-08-18 的统一银行成本事件取代；搜索和自动分页交互合同仍有效。

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
