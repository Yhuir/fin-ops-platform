# 成本统计边界与 I/O

## 责任边界

| 层 | 输入 | 输出 | 禁止 |
| --- | --- | --- | --- |
| Route | HTTP query/body、权限 session | HTTP 状态、JSON 或文件 | SQL、业务聚合、队列写入 |
| Canonical repository | PostgreSQL connection | 单个一致性快照 | read model、Redis、RabbitMQ、HTTP |
| Policy | canonical snapshot、筛选参数 | 视图、统计、详情、导出行 | 数据库、网络、全局状态 |
| Query service | repository、policy、分页/游标 | 稳定 API DTO | freshness gate、worker、隐式 fallback |
| Manual allocation service | case ID、完整单元金额、actor、expected version | 当前有效人工分配与审计事件 | HTTP、页面状态、比例建议、跨事务半写入 |
| Manual allocation repository | PostgreSQL 写事务、versioned allocation | 乐观并发写入结果 | 业务推断、删除历史、独立提交 |
| Frontend | API DTO、用户筛选 | 页面、下载、错误/重试状态 | read-model polling、版本推断、跨页面 I/O |

## 统一事实源

一次请求在同一个 `REPEATABLE READ READ ONLY` 快照内读取：

- `app.bank_transactions`
- `app.oa_applications.normalized_payload` 中成本归因需要的 OA 字段及 canonical `expense_items`
- `app.workbench_pair_relations`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_confirmations`
- `app.app_settings`
- `app.cost_statistics_manual_allocations`（仅三种归因视图与人工分配闭环；原始流水视图禁止读取）
- `audit.events`（人工分配保存审计，与分配写入同事务）

银行有效标签不在成本模块内重新计算。Canonical repository 对本次银行流水 ID 一次批量调用
`PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows(...)`，复用银行分类 owner 的
同一 SQL 分类器和 legacy/canonical identity 语义；成本模块只把返回的 code/主标签/子标签映射到成本事实行。
禁止恢复成本专属 Python category provider 或 SQL 失败后的旧分类 fallback。
正式成本标签以 effective category code 为存在性边界；只有候选文案、但没有 effective code 的
`needs_confirmation` / `unmatched` 行必须归入“未标记”，候选标签不得污染正式标签分组。

正式配对关系只认 `app.workbench_pair_relations.status = 'active'`。成本页面不复制关联关系，也不读取 Workbench 或银行明细页面的 read model。

## 请求闭环

```text
HTTP GET
  -> CostStatisticsApiRoutes
  -> CostStatisticsQueryService
  -> PostgresCostStatisticsCanonicalRepository.load_snapshot()
  -> CostStatisticsPolicy
  -> 200 JSON / export file

HTTP GET /manual-allocations
  -> CostStatisticsManualAllocationService
  -> relation-only canonical task snapshot + stored allocations
  -> pending / stale / allocated tasks

HTTP PUT /manual-allocations/{case_id}
  -> CostStatisticsManualAllocationService
  -> lock current relation facts + validate source fingerprint/version/full unit set/sum
  -> versioned allocation + audit.events in one transaction
  -> 200 / 400 / 409
```

- 页面首次访问和浏览器刷新走同一条链。
- 页面首次且没有有效 session 选择时使用 `Asia/Shanghai` 当前业务月；用户选择与“全部时间”继续走既有 query/session 合同，不使用硬编码历史月份。
- 首次 explorer 内容请求发送 `include_statistics=false`，优先返回当前 scope 的表格/分组；内容可用后再以 `page_size=1` 非阻塞读取全局 `statistics`。统计失败不重新锁住已可用内容；手动刷新会重试两条职责分离的读链。
- 全局 `statistics` 保留流水总数、支出、收入、未标记流水、项目、费用类型、银行标签和成本明细数量；旧 `cost_group_count` 与 `tagged_transaction_count` 字段已删除。
- `include_statistics=false` 且范围不是 `all` 时，五个视图都先以 `bank_transactions.txn_month` 下推银行范围。`time|bank_tag` 到此直接读取原始银行事实，不查询 OA/关系；三种归因视图再批量读取范围内流水命中的 active relation，并扩展这些关系的全部银行/OA 成员作为完整资格与退款证据，最终只输出真实支出流水日期落在请求范围内的归因行。跨月退款回溯冲减原支出流水所在月，不在退款月份生成负成本行；原始视图仍按退款真实日期展示收入。
- 银行流水详情与 OA 分摊详情分别把当前 `scope`、`view` 和 `include_statistics=false` 下推到同一个 canonical repository；禁止为单条详情重新加载全期间 snapshot。所有视图都可能出现银行流水行，详情类型必须读行级 `row_kind`，不得按 view 推断。
- explorer 的 `query` 在 service 中折叠空白、将纯金额归一为无千分位文本并限制为 200 字符，写入 cursor identity；policy 先过滤当前视图事实行，再计算 summary、facets、row count 和分页。`project|bank|expense_type` 搜索银行事件拆出的归因行，`time|bank_tag` 搜索独立标签规则过滤后的原始银行事实；输出金额统一使用无千分位两位小数。
- 前端将后续请求限制在内容区：范围/视图只替换统计 surface，左栏选择只加载中/右栏，中栏选择只加载右栏；只有首次数据尚未验证时才使用页面内交互锁。
- 前端搜索使用 IME-safe 200ms debounce 和请求取消；搜索、下钻和时间范围变化都只替换受影响内容区。明细表在内部滚动容器距底部 160px 内复用现有 cursor 追加请求，正常态无手动加载按钮，下一页失败保留已有 rows 并提供局部重试。
- API 失败时明确返回错误；用户再次刷新会重新打开数据库快照并完整重试。
- `CostStatisticsPolicy` 将支付申请整张 OA 原始金额作为一个权重单元，将日常报销 canonical `expense_items` 逐项作为权重单元。项目或正数权重缺失时整组不分摊；费用类型缺失不再排除，而是进入“未填写 OA 费用类型”。权重合计非正只做内部除零保护，不新增产品状态。
- active relation 中只要有一张 OA 不是明确完成态，整组银行流水从三种归因视图排除，也不得作为无 OA 流水；原始 `time|bank_tag` 仍展示这些银行事实。关系声明的 OA 成员没有被 canonical snapshot 完整加载时同样整组 fail closed，且银行成员继续受 OA 保护。全部 OA 完成时，关系净支出 `N = 支出合计 B - 同关系明确“付错退款”R`；普通收入不进入净额，退款不生成独立归因行。
- OA 原额合计 `O` 与净支出 `N` 相等时，先按真实支出原额权重把 `N` 分到各支出流水，再按 OA 原额权重分到 OA 单元，两级都使用确定性最大余数法按分闭合；`sum(outflow bank transaction × OA unit) = N`。
- `O != N` 时禁止自动比例缩放。没有当前有效人工分配的关系只生成 pending/stale task，并从三种归因视图、详情人口和归因导出中排除；导出预览/文件必须明确给出待分配/已失效数量，禁止静默漏数。人工输入必须覆盖完整稳定单元集合、非负、精确两位小数且合计严格等于 `N`。有效人工列边界与按支出原额计算的行边界通过确定性按分矩阵闭合，禁止把全部金额默认到首个项目或任一 fallback。
- source fingerprint 覆盖关系版本/成员、OA 单元、银行支出/退款金额、账户与标签事实；任一输入变化后旧记录只保留为历史证据并标记 stale，不再参与归因。同一银行流水或 OA 单元跨 active relation 重复时整次响应报冲突，不能重复计入。
- `project / bank / expense_type`、allocation detail 和归因导出共享逐流水归因结果；每行银行账户来自该条真实流水，不再生成“混合支付账户”。`time / bank_tag` 与 bank transaction detail 共享独立原始银行事实集合。三种归因视图彼此可对账，两个原始银行视图彼此可对账；两个集合的总额不要求相等。
- OA 分摊详情同时展示 OA 原始金额/权重、本笔支出流水原额，以及关系 OA 总额、银行总支出、负数“付错退款”、关系净支出、差额和现金比例；退款冲减只在同一 active 关系内成立，API 证据金额保持正数加方向，前端成本抽屉负责按负数展示退款。
- 无 active OA 关系的支出流水只有在其标签被分配给有效虚拟项目时才进入成本事件，费用类型固定为“无 OA 分类”。候选标签从当前全历史实际无 OA 支出逐笔计算；执行纳入时再次逐笔排除所有 active OA 关系成员。配置默认 `projects=[]` 并对全部历史期间生效；项目 ID、名称、至少一个标签及 tag→project 单一归属由服务端校验。前端只按候选标签现有 `path` 分组展示：非叶子主标签无选择 I/O，叶子选择继续只提交稳定 tag code；单层 path 直接作为可选叶子。
- `project / bank / expense_type` 统一输出 `oa_applicant`：支付申请取 canonical 申请人，日常报销取 canonical 报销成员；页面和导出标题统一为“申请/报销人”。缺失值保持空字符串，禁止回退为对方户名、“—”或其他伪造内容。`expense_type` 视图同时展示项目名与申请/报销人。
- `time` 行只映射银行交易时间、对方户名、标签、真实方向和原始银行金额、银行账户与流水摘要；OA 分摊字段只在归因详情显示。
- 主标签和子标签复用同一个“仅支出、混合、仅收入、零金额”排序键；同组再按总金额、笔数和标签名稳定排序。
- 右上角有两套独立抽屉和 App Settings：`time-tag-rules` 默认 `mode=all`，仅控制 `time|bank_tag`；`no-oa-rules` 默认空项目数组，仅控制三种归因视图。两套设置使用独立 version CAS 与 audit，保存成功只刷新受影响的当前视图。时间/标签候选包含 active 标签、仍被历史流水引用的 code 与 `__uncategorized__`；无 OA 候选只来自实际无 OA 支出。标签归档不得静默删除已保存配置；不可用选择必须可见并允许用户取消。
- 不产生 `cost_statistics.read_model.refresh`、dirty scope、readiness 或 Cost worker I/O。
- 两类详情使用全站 `AppDrawer` 作为唯一容器；选择行后先打开抽屉，再按 row kind 发起 bank transaction 或 allocation 单次详情 GET。详情的 loading/error/retry 状态不写入 explorer、导出或页级 loading 状态。

## 统一详情展示合同

- OA、银行流水和发票详情统一使用共享 `EntityDetailContent` 与 HeroUI `Table`/`Chip`；标签在左、真实值在右，禁止页面再包一层圆角卡片或私有详情表。
- 单条详情和多条详情使用同一字段合同；多条只按 `OA N`、`银行流水 N`、`发票 N` 重复单条分区，不输出关系概况、关系数量或“是否多条”。
- 仅展示 canonical API 实际返回且已登记为用户可见的字段；内部 ID、raw payload、source batch、关系元数据和推导字段必须在共享展示边界过滤。
- 详情按需加载；一次打开只发起一个有界详情请求，不得逐成员 N+1。所有详情日期时间统一为 `Asia/Shanghai` 的 `YYYY-MM-DD`、`YYYY-MM` 或 `YYYY-MM-DD HH:mm:ss`，不得显示 `T`、`Z` 或 `+08:00`。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/CostStatisticsPage.tsx`、`web/src/components/cost-statistics/*`、`web/src/features/cost-statistics/*` |
| Route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Query / policy | `cost_statistics_query_service.py`、`cost_statistics_policy.py`、`cost_statistics_bank_tags.py`、`cost_statistics_manual_allocation_service.py` |
| Canonical repository | `cost_statistics_canonical_repository.py` |
| Manual allocation repository | `postgres_repositories/cost_statistics_manual_allocation.py` |
| Settings owner | `app_settings_service.py` |
| Audit | `postgres_repositories/cost_statistics_page_audit.py` |
| Migration | `postgres/migrations/0126_cost_statistics_direct_canonical_read.sql`、`postgres/migrations/0157_cost_statistics_manual_allocations.sql` |

## 已删除旧链路

以下模块及其 worker/registry/manifest/scope/status 入口不得恢复：

- `cost_statistics_read_model_refresh.py`
- `cost_statistics_read_model_repository.py`
- `cost_statistics_runtime_service.py`
- `cost_statistics_source_versions.py`
- `cost_statistics_sql_projection.py`
- `cost_statistics_derived_lifecycle_executor.py`
- Cost worker env、Cost read-model 表与 Cost refresh event

migration `0126` 负责停止遗留运行时事件并删除旧表。除该迁移的清理语句与回归门禁外，生产 runtime 不得再出现旧 Cost read-model 符号。

## 性能边界

- 一次 API 请求只建立一个数据库快照，不轮询、不等待后台任务。
- 用户可观察的首屏合同以 `include_statistics=false` 的 scoped 内容请求计时；全局 statistics 是随后发出的非阻塞辅助请求，必须单独记录延迟，不能冒充首屏成功或失败。
- 归集计算按 relation 成员和 OA 付款明细线性遍历；repository 批量读取 relation、OA、流水与人工分配，不做逐明细 I/O。人工分配只在三种归因视图读取一次，`time|bank_tag` 热路径在进入 OA/关系前返回并完全跳过该表。
- 待分配 Popover 只在用户打开时请求一个有界任务页；repository 使用专用 relation-only 快照，只读取 active relation 的银行/OA 成员及其人工记录，不扫描无关系流水。保存只锁定当前 case 的关系成员和事实，不重算或写入其它关系。
- OA 查询只映射当前范围银行流水命中的 active relation OA，并只读取 policy 消费的父单字段、明细字段和明细金额；不递归复制附件/发票树，附件仍由其 owner 页面读取。
- 常规 scoped 请求保持有界批量查询，关系筛选先使用 `row_ids` GIN overlap 缩小候选，再以 `row_ids/row_types` 配对做精确类型校验；全量范围直接批量读取 active relation 后在同一快照内按已加载银行身份过滤，禁止把全量银行 ID 数组送入逐关系 `unnest`。禁止按关系、银行流水或 OA 明细执行 N+1 I/O；两个规则候选的全历史读取只在打开/保存对应抽屉时执行，不进入普通 explorer 热路径。`time|bank_tag` 请求必须跳过 OA 与 relation 查询。
- 有银行流水时只执行一次有界有效分类投影；空银行集合不查询分类/确认表。投影必须携带内部转账所需的有界上下文，不能退回逐行或全量 Python 分类。
- “无 OA 成本范围”候选使用 repository 的专用只读快照：一次读取全量银行事实和 active OA/流水关系，先排除已有 OA 关系及收入流水，再只对剩余支出做同一 canonical 标签投影；不得读取 OA payload、构建成本组或回退普通 explorer 快照。
- 分页和详情按当前 scope 有界读取；导出仍受 `COST_STATISTICS_EXPORT_ROW_LIMIT` 保护。
- 查询只对已加载 snapshot 做一次线性文本匹配，不新增 SQL、cache、worker 或逐行 I/O；前端搜索取消过期请求，避免竞态回写。
- 候选发布必须记录各视图多次请求的 p50/p95/max，并确认无 Cost queue/worker I/O；若生产数据暴露慢查询，只依据实测 SQL 证据单独优化，不预先增加索引或缓存。
- 已测的后续请求热点只在 repository 内做等价 scope/identity 下推；不得恢复 Cost read model、添加页面 cache 或建立页面间依赖。
