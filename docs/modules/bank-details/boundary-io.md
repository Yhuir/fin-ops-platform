# 银行明细模块边界与 I/O

日期：2026-09-08（同时间顺序修复本地实施中，未发布）

## 模块化状态

- 状态：direct canonical read completed
- 当前边界可信度：high
- 页面查询 owner：`BankDetailsCanonicalQueryService`
- 页面 SQL owner：`PostgresBankDetailsCanonicalQueryRepository`
- 写 owner：`BankDetailsApplicationService` + `BankCategoryRelationClosureService` + canonical category/settings/relation writers
- 旧代码删除状态：页面 read-model reader、freshness/enqueue/status/polling/fallback、共享投影、worker、repository port、backfill 和下游 tagged-row consumer 已删除。

## 职责边界

### 负责

- 银行流水账户列表、余额、筛选、分页、统计、分类 facets、关系标签和 XLSX 导出。
- 自动标签规则展示、CAS 保存、文件替换、reapply 审计。
- 候选确认/撤销、人工分类覆盖/清除的 canonical category fact、event 和 audit；人工覆盖原子替换旧 active category/confirmation，并在所有消费端优先于当前自动规则；有效标签变化时，同一事务通过正式 relation command/repository 重冻结受影响 active 普通关系的配对要求。
- 当前页面写成功后的一次 direct GET 重新读取。
- 页面头部手动刷新重新读取账户、自动标签规则和当前筛选流水；不执行浏览器 reload，不触发其它页面或 read model I/O。
- 在同一只读快照中对完整候选日/同时间组判定余额衔接，统一列表、分页、账户末余额与导出顺序；判定结果仅属于本次请求，不写回 canonical facts。

### 不负责

- 不拥有银行流水导入和 canonical snapshot 同步。
- 不拥有任意 Workbench 配对、撤回或页面查询；只允许分类写闭环把当前标签和同版本规则重新冻结到既有 active 普通关系，ETC/批量账务关系明确排除。
- 不维护页面 read model、freshness、dirty scope、outbox、worker、Redis 或 RabbitMQ。
- 不在页面请求热路径读取 MongoDB、MySQL、OA、对象存储或其它页面 payload。
- 生产 duplicate 恢复工具不是页面分类写入口；它只能在已冻结的 8+1 修复合同中，用完整 CAS 字段删除错误副本独占的单条 category/event，且与 relation 撤回、import 审计修正和 duplicate 删除处于同一 serializable 事务。不得借此转移标签、清理 keeper 标签或绕过正常分类 writer。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 账户日期范围 | `GET /api/bank-details/accounts` | ISO 日期；`date_from <= date_to`。只影响账户 `transaction_count`，不改变账户最新余额。 |
| 页面默认年份 | `BankDetailsPage` | 首次且没有有效 session 选择时使用 `Asia/Shanghai` 当前业务年；用户已有选择继续按既有 session 合同恢复。 |
| 流水查询 | `GET /api/bank-details/transactions` | `account_key`、日期、keyword、分类层级、page、page_size；page 从 1 开始，page_size 为 1..500。所有过滤、排序和分页在 SQL 完成。 |
| 导出查询 | `GET /api/bank-details/transactions/export` | `mode=all|account` 与同一筛选合同；复用 canonical query，读取上限为 `BANK_DETAIL_EXPORT_ROW_LIMIT + 1`，超限返回业务错误。 |
| canonical 银行事实 | `app.bank_transactions` | 只读取 active/有效流水；保留 legacy/canonical identity、账户 identity、方向、numeric 金额/余额、银行文本和实际 `trade_time`/`txn_date`。排序证据由完整同账户、同币种候选日提供，不能先被 keyword、分类或分页截断。 |
| 分类与确认事实 | `app.bank_transaction_categories`、`app.bank_transaction_category_confirmations`、settings 标签规则 | active confirmation 只用于候选确认；`source=manual, manual_assignment=true` 是持久人工覆盖并优先于当前自动规则，清除后才重新暴露当前自动结果；不读取 `read_model.bank_detail_rows`。 |
| 分类写闭环 | 当前 effective category + 同一 settings snapshot + active relation | 分类事实、relation requirement metadata 与 relation history 在同一 PostgreSQL 事务提交；无标签变化或无 active relation 时短路。单独保存 OA/发票 requirement 时由 bank-flow settings-maintenance job 按变化 tag proof 增量更新关系，不进入本页面分类写事务。 |
| 正式关系事实 | `app.workbench_pair_relations` | 只读取 `status=active`；按当前可见/导出目标 legacy + canonical row IDs 做 bounded overlap；排除 `turnover_manual_closure`，不读取 `read_model.workbench_relation*`。 |
| 账户映射 | canonical app settings | 账户 identity/display mapping 与 active tag definitions 由 PostgreSQL snapshot 读取。 |
| 写请求 | route session + JSON body | 候选确认只接受当前候选；人工覆盖只接受当前 active 自动标签或系统 `internal_transfer`，可替换 unmatched/auto/confirmation 状态；保持权限、重复/冲突、审计和幂等合同，route 不做业务组合或 SQL。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| accounts payload | Bank Details 页面 | `accounts`、余额汇总、币种汇总与缺失余额计数来自有界 SQL 聚合。每账户必含 `balance_status`：confirmed、last_known、unresolved 或 missing；只有完整确认的币种返回总余额；不含 read-model status/source/job 字段。详见账户余额模块合同。 |
| transactions payload | Bank Details 页面 | `rows`、`statistics`、`category_counts`、pagination 和展示标签字典；rows/summary/facets/relations 在同一个 `REPEATABLE READ READ ONLY` snapshot 中一致。每行必含 `same_time_order_status`：time、balance_chain 或 unresolved；保留 effective/auto/candidate/relationship 字段。旧 `category_*` / `manual_category_*` 重复别名、自动规则 evidence 和标签匹配 rules/account scope 不进入页面 DTO。 |
| relation tags | 页面/导出 | 只反映 active canonical relation membership；候选、withdrawn relation、Workbench raw payload 和 relation projection 不进入页面事实。 |
| 导出文件 | 有导出权限的用户 | 复用同一筛选、顺序与 relation 语义；保留原列名称、相对顺序、原始金额和 sheet 分组，仅在末尾追加“同时间顺序说明”。服务端生成 XLSX；保留下载权限和下载审计。 |
| 分类/规则写响应 | 当前页面 | 保留 `changed`、`affected_months`、version、error/message 等业务字段；不返回 freshness target、refresh job、operation barrier 或 202 refreshing envelope。 |
| relation requirement delta | workbench-relations owner | 仅 changed case 的 canonical metadata/history；数据库提交后才发布同 case 进程镜像增量。失败整体回滚，不发页面通知、不写 dirty/outbox。 |
| 写后重读 | 当前页面 | 成功后只触发一次当前 query GET；不轮询、不等待 worker、不触发页面 RM fan-out。 |
| 页面手动刷新 | 当前页面 | 并发重新读取账户、自动标签规则和当前筛选流水；保留页面筛选条件，不写 canonical facts。 |

金额和余额的页面文本统一为无千分位两位小数；keyword 搜索直接包含 canonical 金额/余额文本，不生成分组格式的重复搜索值。

`statistics` 只包含流水总数、支出、收入、已分类和未分类数量；旧“已关联/未关联”统计字段不再属于页面输出合同。组内顺序状态不影响行数、金额统计、分类或关系。

## 同时间顺序合同

- `bank_account_balance_canonical_rows.py` 提供账户聚合及闭合锚点所需的既有账户事实输入，列表排序复用 classifier base；`bank_transaction_ordering_sql.py` 提供共享币种归一和固定内部别名的顺序 SQL CTE，不执行连接 I/O，不接受用户 SQL 标识符。
- 完整同时间组用 `balance - signed_amount → balance` 建边，验证正金额、方向与 signed amount 一致以及组连通性。逐笔顺序仅对每个余额节点出边不超过一条的无分支组遍历，覆盖全部且不重复时返回 `balance_chain`；分支组不搜索排列，可独立确认终点余额，逐笔顺序仍为 `unresolved`。
- 开放组的终点由完整组的进入/离开次数与连通性证明，不要求更早历史连续。闭合组只接受紧邻前一时点单笔、非空、同币种且具备具体时间的余额作为起点，不递归回溯补证据。
- 同账户、同币种、同日多笔且至少一笔缺具体时间时，该日各行均为 `unresolved`；只有日期的单笔保留真实日期，不制造午夜时间。更早日期歧义不否定更晚完整日期。
- 排序键依次为实际时间的展示排序键倒序、稳定账户/币种组键、已确认组内序号倒序及稳定 ID。page keys 与最终 rows 使用完全相同的键，导出不二次排序；UUID、serial、导入批次和源行号均不证明记账先后。
- 内容筛选可以定位候选组，但不能截断判定证据。列表先按时间倒序、账户键使用 `FETCH FIRST (offset + page_size) ROWS WITH TIES` 选覆盖本页前缀的完整时间/账户组，再从 classifier 的 `base` 补齐候选日期，完成日期精度检查后只对目标时间组判定；最终 page keys 才应用组内顺序与分页。summary/facets 仍统计全部命中行。
- 排序输入复用 classifier `base` 已有 `account_key`，币种归一共用 `BANK_NORMALIZED_CURRENCY_SQL`；不额外计算账户 hash。仅闭合组需要紧邻历史锚点时访问完整账户历史。按 canonical identity 一笔事实最多连接一条顺序结果，不丢弃未确认记录，不新增账户 key、持久化顺序、schema、cache 或 worker。
- 必填顺序字段仅在银行公共列表/导出的 `_ordered_transactions_payload` 添加；原业务 `_transactions_payload` 分类映射保持原状，Workbench 等分类消费者不需要该字段，也不产生顺序证据查询。
- 页面独立记录账户、流水、标签统计与规则请求错误，取消/过期请求不得提交结果。已覆盖切账户晚返回、账户失败被流水成功清除和旧 header 刷新覆盖新规则读取三种竞态。两个 HTTP 请求仍各自拥有数据库快照，不承诺并发写入期间跨请求的绝对同一时点。

## Snapshot 与查询次数

- 事务必须显式执行 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`。
- transactions 固定使用 settings/read query、set-based rows/summary/facets query 和一次 bounded active relation overlap query；不得逐行查 relation/category。
- 外部往来款可在自己的同一只读快照内复用 repository 的 set-based effective-category rows helper；该 helper 只返回指定 tag codes 的 canonical rows，不返回 Bank Details 页面 DTO、relation 标签或 freshness 状态。
- 外部往来闭环写前可在自己的 UoW 事务内调用 `turnover_bank_row_selection_rows(...)`，按本次 legacy/source IDs 一次返回 canonical 银行事实与有效分类。该 helper 只拥有分类 SQL I/O；Turnover 负责标签准入、selection version、金额校验和 relation 命令，不得回读 Bank Details 页面 DTO。
- 流水规则批量处理的 canonical repository 可复用公开的 `bank_category_classification_cte(...)` SQL compiler，在自己的只读 snapshot 内取得完整 effective category；调用方仍拥有自己的批次、关系、筛选和分页 I/O，不读取银行明细页面 payload。
- 批量账务可对精确业务流水 IDs 复用 `effective_category_projection_rows(...)`，取得 current effective code/label/source；筛选、分页、Settings 选择和提交资格仍由批量账务 owner 负责。
- 成本统计可在自己的只读快照内对当前银行流水 IDs 复用 `effective_category_projection_rows(...)`，取得 current effective code/主标签/子标签/source；成本筛选、归因、详情和导出仍由成本 owner 负责，禁止复制分类 SQL 或回退 Python 分类器。
- 关联台 direct page hydration 可对本页目标银行 identity 一次批量复用同一 canonical classifier，取得 effective category 与 resolution status；该调用由关联台 query owner 在同一只读请求内负责，银行明细写链不恢复跨页面 fan-out。
- Workbench matching fact repository 可对计划涉及的银行 IDs 一次批量复用同一 canonical classifier，冻结 relation requirement metadata；orchestrator/worker 不再装载 category snapshot 后自行运行 Python 分类。
- accounts 固定使用 settings、账户余额聚合和账户范围计数查询；不得在 Python 全量累计。
- 内部转账匹配使用 SQL `±2 days` bounded context；自动规则只为实际使用的匹配字段构建文本 normalization。
- 账户和精确日期先限定页面目标行；合法金额 keyword 在确认不可能命中配置标签文案后，可把 canonical 金额/余额及既有可搜索原始字段下推到规则分类候选。内部转账仍保留完整 bounded context，最终完整筛选不得删除。
- 查询次数 guard 位于 `tests/test_bank_details_canonical_query.py`。
- 候选组缩减是请求内 SQL 优化，不改变筛选/统计或证据完整性；实际扫描量、EXPLAIN 与尾延迟继续按修复计划验收，不能由固定查询数或局部测试推导性能通过。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/pages/BankDetailsPage.tsx`、`web/src/features/bankDetails/*` |
| Route | `backend/src/fin_ops_platform/app/routes_bank_details.py` |
| Query service/repository | `backend/src/fin_ops_platform/services/bank_details_canonical_query.py` |
| 共享排序/账户 SQL | `backend/src/fin_ops_platform/services/bank_transaction_ordering_sql.py`、`bank_account_balance_canonical_rows.py` |
| Export | `backend/src/fin_ops_platform/services/bank_details_export_service.py` |
| Application/write service | `bank_details_application_service.py`、`bank_category_relation_closure_service.py`、`bank_details_service.py`、`bank_transaction_category_mutation_writer.py`、`bank_transaction_auto_category_service.py` |
| Runtime wiring | `backend/src/fin_ops_platform/app/server.py`，只允许最小依赖组装 |
| Tests | `tests/test_bank_same_time_ordering_postgres.py`、`tests/test_bank_details_canonical_query.py`、`tests/test_bank_details_routes.py`、`tests/test_bank_details_export_service.py`、`tests/test_bank_auto_tag_rules_api.py`、`web/src/test/BankDetails*.test.*`、`web/e2e/bank-details-*.spec.ts` |

## 依赖方向

- 允许：route -> application/query service -> canonical query repository / canonical writers。
- 必须：active relation 通过 page-specific bounded canonical SQL；category/settings 写通过既有 owner service/repository；有效 category 变化通过单一 closure service 调用 relation owner changed-case I/O。
- 禁止：route/server 业务 SQL、Application 注入 service、页面 read model、跨页面 payload、逐行 relation lookup、全量 Python/浏览器过滤分页、缓存或 worker 补偿。

## 跨页面清理结果

- 全仓调用扫描后删除 `BankDetailsService.list_accounts`、`_latest_balance_transaction`、`PostgresCoreRepository.list_bank_transaction_accounts`、`PostgresStateStore` 对应 wrapper 及独占测试 fake；有效账户业务断言迁入 `tests/test_bank_same_time_ordering_postgres.py`，不保留并行本地余额算法。`label_consistent` metadata 选择继续保留。
- `bank_detail_*`、`bank_account_balance_*` projection/repository/refresh/backfill/derived lifecycle 已删除。
- manifest、scope policy、worker handlers/registry、App Status、RabbitMQ dispatcher 和 deploy env 中的两个页面 key 已删除。
- 原 tagged-row 消费者已迁移到各自 canonical query boundary；`BankTransactionTagReadFacade` 和旧 repository port 已删除。
- 未接线的 `after_category_mutation` 页面回调已删除；不得恢复写后跨页通知、refresh producer 或并行 requirement 更新路径。
- `read_model.bank_detail_*`、`read_model.bank_account_balances` 历史表暂留作可回滚迁移证据，没有运行时 reader/writer。

## 文档影响

- 同时间顺序、余额状态与完整合计口径更新 `docs/product-specs/bank-turnover-and-no-oa.md`；输入事实、分类/关系写 owner、导入身份和权限不变。
- 页面/API/运行时边界已变，更新本模块文档、`docs/app-architecture/` 与 `docs/dev/api-contracts.md`。
- 全局 `read-model-contracts.md` 与 worker/deploy 文档已同步为清理后的合同。

## 系统单层标签投影（2026-09-11）

批量 effective category projection 与银行分类 owner 使用同一系统语义：`internal_transfer` 输出“内部往来款”主标签与单层路径，子标签可空。保留有效人工分配/确认优先级。成本消费标准化 bank_tag 字段，不通过标签名称重跑分类，不复制一笔完整银行明细补值。
