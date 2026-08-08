# 银行明细模块边界与 I/O

日期：2026-08-07

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

### 不负责

- 不拥有银行流水导入和 canonical snapshot 同步。
- 不拥有任意 Workbench 配对、撤回或页面查询；只允许分类写闭环把当前标签和同版本规则重新冻结到既有 active 普通关系，ETC/批量账务关系明确排除。
- 不维护页面 read model、freshness、dirty scope、outbox、worker、Redis 或 RabbitMQ。
- 不在页面请求热路径读取 MongoDB、MySQL、OA、对象存储或其它页面 payload。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 账户日期范围 | `GET /api/bank-details/accounts` | ISO 日期；`date_from <= date_to`。只影响账户 `transaction_count`，不改变账户最新余额。 |
| 流水查询 | `GET /api/bank-details/transactions` | `account_key`、日期、keyword、分类层级、page、page_size；page 从 1 开始，page_size 为 1..500。所有过滤、排序和分页在 SQL 完成。 |
| 导出查询 | `GET /api/bank-details/transactions/export` | `mode=all|account` 与同一筛选合同；复用 canonical query，读取上限为 `BANK_DETAIL_EXPORT_ROW_LIMIT + 1`，超限返回业务错误。 |
| canonical 银行事实 | `app.bank_transactions` | 只读取 active/有效流水；保留 legacy/canonical identity、账户 identity、方向、金额、余额、银行文本和时间语义。 |
| 分类与确认事实 | `app.bank_transaction_categories`、`app.bank_transaction_category_confirmations`、settings 标签规则 | active confirmation 只用于候选确认；`source=manual, manual_assignment=true` 是持久人工覆盖并优先于当前自动规则，清除后才重新暴露当前自动结果；不读取 `read_model.bank_detail_rows`。 |
| 分类写闭环 | 当前 effective category + 同一 settings snapshot + active relation | 分类事实、relation requirement metadata 与 relation history 在同一 PostgreSQL 事务提交；无标签变化或无 active relation 时短路。规则保存本身不追溯改写关系。 |
| 正式关系事实 | `app.workbench_pair_relations` | 只读取 `status=active`；按当前可见/导出目标 legacy + canonical row IDs 做 bounded overlap；排除 `turnover_manual_closure`，不读取 `read_model.workbench_relation*`。 |
| 账户映射 | canonical app settings | 账户 identity/display mapping 与 active tag definitions 由 PostgreSQL snapshot 读取。 |
| 写请求 | route session + JSON body | 候选确认只接受当前候选；人工覆盖只接受当前 active 自动标签或系统 `internal_transfer`，可替换 unmatched/auto/confirmation 状态；保持权限、重复/冲突、审计和幂等合同，route 不做业务组合或 SQL。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| accounts payload | Bank Details 页面 | `accounts`、余额汇总、币种汇总与缺失余额计数来自有界 SQL 聚合；不含 read-model/status/source/job 字段。 |
| transactions payload | Bank Details 页面 | `rows`、`statistics`、`category_counts`、pagination 和展示标签字典；rows/summary/facets/relations 在同一个 `REPEATABLE READ READ ONLY` snapshot 中一致。列表只输出 effective/auto/candidate/relationship 展示字段；旧 `category_*` / `manual_category_*` 重复别名、自动规则 evidence 和标签匹配 rules/account scope 不进入页面 DTO。 |
| relation tags | 页面/导出 | 只反映 active canonical relation membership；候选、withdrawn relation、Workbench raw payload 和 relation projection 不进入页面事实。 |
| 导出文件 | 有导出权限的用户 | 复用同一筛选与 relation 语义；服务端生成 XLSX，不先向浏览器加载全量 rows。 |
| 分类/规则写响应 | 当前页面 | 保留 `changed`、`affected_months`、version、error/message 等业务字段；不返回 freshness target、refresh job、operation barrier 或 202 refreshing envelope。 |
| relation requirement delta | workbench-relations owner | 仅 changed case 的 canonical metadata/history；数据库提交后才发布同 case 进程镜像增量。失败整体回滚，不发页面通知、不写 dirty/outbox。 |
| 写后重读 | 当前页面 | 成功后只触发一次当前 query GET；不轮询、不等待 worker、不触发页面 RM fan-out。 |
| 页面手动刷新 | 当前页面 | 并发重新读取账户、自动标签规则和当前筛选流水；保留页面筛选条件，不写 canonical facts。 |

金额和余额的页面文本统一为无千分位两位小数；keyword 搜索直接包含 canonical 金额/余额文本，不生成分组格式的重复搜索值。

## Snapshot 与查询次数

- 事务必须显式执行 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`。
- transactions 固定使用 settings/read query、set-based rows/summary/facets query 和一次 bounded active relation overlap query；不得逐行查 relation/category。
- 外部往来款可在自己的同一只读快照内复用 repository 的 set-based effective-category rows helper；该 helper 只返回指定 tag codes 的 canonical rows，不返回 Bank Details 页面 DTO、relation 标签或 freshness 状态。
- 批量账务可对精确业务流水 IDs 复用 `effective_category_projection_rows(...)`，取得 current effective code/label/source；筛选、分页、Settings 选择和提交资格仍由批量账务 owner 负责。
- 关联台 generation builder 可对目标银行 identity 一次批量复用同一 canonical classifier，取得 effective category 与 resolution status；该调用由关联台 read model owner 负责 freshness/publish，银行明细写链不恢复跨页面 fan-out。
- accounts 固定使用 settings、账户余额聚合和账户范围计数查询；不得在 Python 全量累计。
- 内部转账匹配使用 SQL `±2 days` bounded context；自动规则只为实际使用的匹配字段构建文本 normalization。
- 账户和精确日期先限定页面目标行；合法金额 keyword 在确认不可能命中配置标签文案后，可把 canonical 金额/余额及既有可搜索原始字段下推到规则分类候选。内部转账仍保留完整 bounded context，最终完整筛选不得删除。
- 查询次数 guard 位于 `tests/test_bank_details_canonical_query.py`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/pages/BankDetailsPage.tsx`、`web/src/features/bankDetails/*` |
| Route | `backend/src/fin_ops_platform/app/routes_bank_details.py` |
| Query service/repository | `backend/src/fin_ops_platform/services/bank_details_canonical_query.py` |
| Application/write service | `bank_details_application_service.py`、`bank_category_relation_closure_service.py`、`bank_details_service.py`、`bank_transaction_category_mutation_writer.py`、`bank_transaction_auto_category_service.py` |
| Runtime wiring | `backend/src/fin_ops_platform/app/server.py`，只允许最小依赖组装 |
| Tests | `tests/test_bank_details_canonical_query.py`、`tests/test_bank_details_routes.py`、`tests/test_bank_auto_tag_rules_api.py`、`web/src/test/BankDetails*.test.*`、`web/e2e/bank-details-*.spec.ts` |

## 依赖方向

- 允许：route -> application/query service -> canonical query repository / canonical writers。
- 必须：active relation 通过 page-specific bounded canonical SQL；category/settings 写通过既有 owner service/repository；有效 category 变化通过单一 closure service 调用 relation owner changed-case I/O。
- 禁止：route/server 业务 SQL、Application 注入 service、页面 read model、跨页面 payload、逐行 relation lookup、全量 Python/浏览器过滤分页、缓存或 worker 补偿。

## 跨页面清理结果

- `bank_detail_*`、`bank_account_balance_*` projection/repository/refresh/backfill/derived lifecycle 已删除。
- manifest、scope policy、worker handlers/registry、App Status、RabbitMQ dispatcher 和 deploy env 中的两个页面 key 已删除。
- 原 tagged-row 消费者已迁移到各自 canonical query boundary；`BankTransactionTagReadFacade` 和旧 repository port 已删除。
- 未接线的 `after_category_mutation` 页面回调已删除；不得恢复写后跨页通知、refresh producer 或并行 requirement 更新路径。
- `read_model.bank_detail_*`、`read_model.bank_account_balances` 历史表暂留作可回滚迁移证据，没有运行时 reader/writer。

## 文档影响

- 产品口径未变，不更新 `docs/product-specs/`。
- 页面/API/运行时边界已变，更新本模块文档、`docs/app-architecture/` 与 `docs/dev/api-contracts.md`。
- 全局 `read-model-contracts.md` 与 worker/deploy 文档已同步为清理后的合同。
