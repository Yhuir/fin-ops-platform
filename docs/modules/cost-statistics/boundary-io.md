# 成本统计边界与 I/O

## 责任边界

| 层 | 输入 | 输出 | 禁止 |
| --- | --- | --- | --- |
| Route | HTTP query/body、权限 session | HTTP 状态、JSON 或文件 | SQL、业务聚合、队列写入 |
| Canonical repository | PostgreSQL connection | 单个一致性快照 | read model、Redis、RabbitMQ、HTTP |
| Policy | canonical snapshot、筛选参数 | 视图、统计、详情、导出行 | 数据库、网络、全局状态 |
| Query service | repository、policy、分页/游标 | 稳定 API DTO | freshness gate、worker、隐式 fallback |
| Frontend | API DTO、用户筛选 | 页面、下载、错误/重试状态 | read-model polling、版本推断、跨页面 I/O |

## 统一事实源

一次请求在同一个 `REPEATABLE READ READ ONLY` 快照内读取：

- `app.bank_transactions`
- `app.oa_applications.normalized_payload` 中成本归因需要的 OA 字段及 canonical `expense_items`
- `app.workbench_pair_relations`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_confirmations`
- `app.app_settings`

正式配对关系只认 `app.workbench_pair_relations.status = 'active'`。成本页面不复制关联关系，也不读取 Workbench 或银行明细页面的 read model。

## 请求闭环

```text
HTTP GET
  -> CostStatisticsApiRoutes
  -> CostStatisticsQueryService
  -> PostgresCostStatisticsCanonicalRepository.load_snapshot()
  -> CostStatisticsPolicy
  -> 200 JSON / export file
```

- 页面首次访问和浏览器刷新走同一条链。
- 页面首次且没有有效 session 选择时使用 `Asia/Shanghai` 当前业务月；用户选择与“全部时间”继续走既有 query/session 合同，不使用硬编码历史月份。
- 首次 explorer 内容请求发送 `include_statistics=false`，优先返回当前 scope 的表格/分组；内容可用后再以 `page_size=1` 非阻塞读取全局 `statistics`。统计失败不重新锁住已可用内容；手动刷新会重试两条职责分离的读链。
- `include_statistics=false` 且范围不是 `all` 时，`time|bank_tag` 用 `bank_transactions.txn_month` 下推范围且不读取 OA 配对关系；`project|bank|expense_type` 用 `oa_applications.approved_at` 下推 OA 完成时间范围，再扩展命中 active relation 的全部银行/OA 成员。三种 OA 视图不得用银行流水时间决定期间。
- 银行流水详情与 OA 归集详情分别把当前 `scope`、`view` 和 `include_statistics=false` 下推到同一个 canonical repository；禁止为单条详情重新加载全期间 snapshot。OA 归集详情扩展命中关系成员，银行事实详情跳过 OA/关系 I/O。
- explorer 的 `query` 在 service 中折叠空白、将纯金额归一为无千分位文本并限制为 200 字符，写入 cursor identity；policy 先过滤当前视图事实行，再计算 summary、facets、row count 和分页。`project|bank|expense_type` 搜索域只包含 OA 配对 allocation，`time|bank_tag` 搜索域只包含 canonical 银行事实；输出金额同样使用无千分位两位小数。
- 前端将后续请求限制在内容区：范围/视图只替换统计 surface，左栏选择只加载中/右栏，中栏选择只加载右栏；只有首次数据尚未验证时才使用页面内交互锁。
- 前端搜索使用 IME-safe 200ms debounce 和请求取消；搜索、下钻和时间范围变化都只替换受影响内容区。明细表在内部滚动容器距底部 160px 内复用现有 cursor 追加请求，正常态无手动加载按钮，下一页失败保留已有 rows 并提供局部重试。
- API 失败时明确返回错误；用户再次刷新会重新打开数据库快照并完整重试。
- `CostStatisticsPolicy` 将支付申请当前金额作为一个 OA 归集单元，将日常报销的 canonical `expense_items` 逐项作为归集单元。金额、项目或费用类型缺失时明确排除并返回质量统计；费用类型必须来自 OA 显式枚举或已有确定性文本规则，未知值保持缺失，禁止改写成“其他”。同时禁止回退到流水金额、报销表头、按比例、顺序或子集猜测。
- OA 成本归集在 policy 边界使用明确完成状态和 `approved_at`；进行中或无完成时间 OA 在聚合前排除，因此 `project / bank / expense_type` 的 summary、facets、rows、allocation detail 和导出使用同一口径。`time / bank_tag` 仍是纯银行事实视图，不受 OA 流程状态影响。
- 同一 relation 只有一个付款账户时归入该账户；多个账户或账户不明时归入 `混合支付账户`。同一 OA 归集单元出现在多个 active relation 时整次响应报冲突，不能重复计入。
- `project / bank / expense_type`、allocation detail 和导出共享同一归集结果；关联付款流水只是证据，不作为右栏归集金额。`time / bank_tag` 与 bank transaction detail 共享未拆分银行事实。
- `time` 行只映射银行交易时间、对方户名、标签、方向、金额、银行账户和流水摘要，不用 OA 占位值伪装项目或费用类型。
- 主标签和子标签复用同一个“仅支出、混合、仅收入、零金额”排序键；同组再按总金额、笔数和标签名稳定排序。
- 标签规则保存只修改 App Settings；保存成功后的页面 reload 重新应用最新规则。
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
| Query / policy | `cost_statistics_query_service.py`、`cost_statistics_policy.py`、`cost_statistics_bank_tags.py` |
| Canonical repository | `cost_statistics_canonical_repository.py` |
| Settings owner | `app_settings_service.py` |
| Audit | `postgres_repositories/cost_statistics_page_audit.py` |
| Migration | `postgres/migrations/0126_cost_statistics_direct_canonical_read.sql` |

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
- 归集计算按 relation 成员和 OA 付款明细线性遍历；repository 批量读取 relation、OA 和流水，不做逐明细 I/O。
- OA 查询只映射成本 policy 消费的父单字段、明细字段和明细金额，不递归复制附件/发票树；附件仍由其 owner 页面读取，不进入 Cost 请求内存。
- 分页和详情按当前 scope 有界读取；导出仍受 `COST_STATISTICS_EXPORT_ROW_LIMIT` 保护。
- 查询只对已加载 snapshot 做一次线性文本匹配，不新增 SQL、cache、worker 或逐行 I/O；前端搜索取消过期请求，避免竞态回写。
- 候选发布必须记录各视图多次请求的 p50/p95/max，并确认无 Cost queue/worker I/O；若生产数据暴露慢查询，只依据实测 SQL 证据单独优化，不预先增加索引或缓存。
- 已测的后续请求热点只在 repository 内做等价 scope/identity 下推；不得恢复 Cost read model、添加页面 cache 或建立页面间依赖。
