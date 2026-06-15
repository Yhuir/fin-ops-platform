# 待找发票状态机

> 修改 `待找发票` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。待找发票状态必须由后端 policy/read model 给出，页面不得自行推断。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 方向 | `expense` | API query / pending invoice read model | 支出流水查找进项发票，规则组包含 `requires_invoice`、`bank_statement_as_invoice`、`no_invoice_required`。 |
| 方向 | `income` | API query / pending invoice read model | 收入流水查找销项发票，规则组包含 `requires_invoice`、`no_invoice_required`、`cash_income`。 |
| 规则组 | `requires_invoice` | active bank tag complement | 由 active 标签减去可编辑 no-invoice/cash/statement 分组实时派生，不作为请求事实保存。 |
| 规则组 | `bank_statement_as_invoice` | expense pending invoice rules | 只适用于支出；最终仍为流水代替发票的行才出现在该筛选。 |
| 规则组 | `no_invoice_required` | expense/income rules | 支出或收入都可配置；改变发票生命周期和待找发票口径。 |
| 规则组 | `cash_income` | income rules | 只适用于收入现金场景；不得污染支出规则。 |
| 行状态 | `pending_invoice` / `paid_invoiced` / `no_invoice_required` 等 | `InvoiceLifecyclePolicy`、pending invoice read model | 列表只展示后端返回的 `invoice_acquisition_status`；页面不补推 primary action。 |
| 选择已有发票 | `attach_previewed` / `attach_confirmed` | application service | 只允许 expense 行选择 input invoice；支持单条或多条流水选择一张或多张进项发票；confirm 写一条 Workbench active relation、audit、command log 和 finalizer。 |
| 收入状态覆盖 | `income_no_invoice_required` / `cash_income` | income status override command | 只适用于收入行；支持单条兼容 API 和批量 API；事件只刷新 pending/search。 |
| command log | `created` / `relation_created` / `finalized` / `failed_terminal` | command repository | confirm 中断后可重试恢复，不得重复创建发票或关系。 |

关键规则：

- `pending_invoice_tag_groups.version` 只代表支出规则版本；`pending_output_invoice_tag_groups.version` 只代表收入规则版本。
- 保存规则只递增当前 direction 的规则版本，不递增 `bank_transaction_tags.version`。
- `requires_invoice` 即使出现在请求中也必须忽略；后端始终按 active tag complement 派生。
- filter-options、export-preview 和 export 必须先读 fresh read model；非 fresh 时返回 accepted/refreshing。
- 历史 manual invoice service/command 只作为旧数据恢复和迁移兼容能力保留；待找发票页面和 HTTP API 不再提供新建 manual invoice 写入口。
- 选择已有发票批量 preview 不写事实；confirm 必须返回 affected transaction/invoice arrays。已存在兼容的 bank+invoice relation 时应合并/扩展同一 active relation，不创建复用同一 row 的第二条 active case。
- 收入批量状态覆盖必须先全量校验：transaction ids 非空且不重复、全部为收入流水、状态码属于 `income_no_invoice_required` / `cash_income`、当前行未关联销项发票；任一失败不得写 command/audit/finalizer。
- invoice lifecycle 必须先于待找发票、税金、成本、OA/进项/销项下游页面刷新。

禁止流转：

- 禁止前端根据缺失字段猜测 `invoice_acquisition_status` 或 primary action。
- 禁止 read model miss/stale 时把空 rows 当作真实“没有待找发票”。
- 禁止保存规则时接受未知标签、归档标签或重复映射。
- 禁止收入规则污染支出规则，或支出规则污染收入规则。
- 禁止候选 relation case id 被当作真实 OA id 请求详情。
- 禁止 attach existing 或历史 manual command 恢复时重复创建发票或 relation。
- 禁止待找发票页面或 HTTP route 暴露 manual invoice preview/confirm 新写入口。
- 禁止 pending invoice 规则变更刷新 `turnover_ledger`、`no_oa_bank_batch` 或 `bank_account_balance`。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | rows/filter-options/detail/rules 请求进行中 | 展示加载态；请求 abort 后清理 loading。 |
| refreshing | API 返回 `read_model_status=refreshing` 或 202 | 展示刷新语义；若有旧 rows 可继续展示，但不能把空 accepted payload 当最终空结果。 |
| stale | API 返回 stale/source/schema mismatch 或 App Status 暴露 stale scope | 展示陈旧/同步提示；写操作按后端权限和版本控制。 |
| empty | fresh payload 且 total 为 0 | 表示当前 direction/filter/query 真实没有行。 |
| error | rows/detail/rules/attach/income status/export 请求失败 | 展示业务错误，不暴露底层 SQL/worker internals。 |
| rules drawer | 用户打开规则配置 | 读取当前 direction 规则和 active tags；支持 stale version conflict 反馈。 |
| attach existing drawer/dialog | 用户从选中流水工具栏选择候选发票 | 单条或多条支出流水共用右侧抽屉；候选列表支持多选进项发票；抽屉展示已选流水金额、已选发票金额和差额；preview 展示冲突和影响；confirm 成功后刷新行和关系详情。 |
| expense transaction selection | 用户在支出列表勾选流水 | 仅允许有 `attach_existing_invoice` action 的支出流水进入批量选择；筛选、排序、分页、搜索或确认后清理选择；选择发票入口只在表格上方选中工具栏出现。 |
| income transaction selection | 用户在收入列表勾选流水 | 仅允许有 `mark_income_status` action 的收入流水进入批量选择；选中后工具栏显示“标记无需开票”“标记现金收入”“清除选择”。 |
| income status batch action | 收入选中工具栏提交 | 提交时禁用批量状态按钮；成功后以响应 rows 或 refetch 为准，并清理选择。 |
| permission disabled/hidden | session permissions | 只读用户隐藏或禁用保存规则、attach、income override 等 mutation。 |

前端事件：

- `invoiceFactUpdated`、`workbenchRelationUpdated`、`bankTransactionCategoryUpdated`、`bankAutoTagRulesUpdated` 只能触发 refetch 或规则刷新。
- 前端事件不是事实源；后端 lifecycle/dirty scope/outbox/readiness 才证明待找发票已收敛。
- 页面卸载后不 replay 事件；返回页面重新通过 API/read boundary 加载。

## Read Model / Worker 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `fresh` | scope schema/source/readiness 与当前事实一致，且没有 active dirty scope | rows/filter-options/export 可使用当前 payload。 |
| `missing` | 没有对应 scope read model 或 readiness | 入队 `pending_invoice.read_model.refresh`；API 返回 refreshing。 |
| `refreshing` | dirty scope pending/processing，或 parent scope 正 fan-out month shards | worker 继续处理；页面展示同步中。 |
| `stale` / `source_mismatch` / `schema_mismatch` | bank tags、relation、invoice lifecycle、schema source version 落后 | 入队重建；可展示旧 rows 但必须暴露 stale reason。 |
| `failed` | projection/worker refresh 失败 | App Status busy/blocked，页面显示失败或等待运维重试。 |
| `unavailable` | repository、queue、worker dependency 不可用 | API 返回 unavailable/refreshing；不得返回 fake fresh。 |

Scope 形态：

- `expense:all`、`expense:requires_invoice`、`expense:bank_statement_as_invoice`、`expense:no_invoice_required`
- `income:all`、`income:requires_invoice`、`income:no_invoice_required`、`income:cash_income`
- 月份 shard 形态为 `<direction>:<filter>:YYYY-MM`

Refresh 触发来源：

- 发票导入确认。
- Workbench 关系确认/撤回、历史 manual command 恢复、attach existing confirm。
- 待找发票规则保存。
- 收入状态 override。
- 银行标签保存、重命名、归档或自动分类版本变化。
- invoice lifecycle refresh、OA rebuild、App Health/backfill 运维任务。
- `startup_stale_scan` 默认关闭，且不直接刷新待找发票 read model；只有后续 matching 结果真实变化并触发业务 lifecycle 时才间接影响。

父 scope / filter scope fan-out：

1. 收到 `pending_invoice.read_model.refresh`，scope 可能是 direction/filter 父 scope 或月份 shard。
2. 父 scope 通过 projection builder 列出需要的月份 shard。
3. 通过 `ReadModelRefreshGateway` 入队每个 `<direction>:<filter>:YYYY-MM`。
4. 父 scope 完成 dirty scope；月份 shard worker 发布真实 rows/scope readiness。
5. API 读父 scope 时由 repository 聚合或读取对应 scope payload，不能同步扫描旧事实。

失败恢复：

1. 先看 `/api/app-health.app_status` 中 `pending_invoice` 和 `search` read model scopes、dirty scopes、outbox，以及 `pending-invoice` / `search` worker；旧 `search-pending` 只是兼容消费者。
2. 对 rule version conflict，让页面重新读取规则 payload，再基于新 version 保存。
3. 对 attach command 或历史 manual command 中断，优先用 command log 重试恢复，不手工删除已创建发票或 relation。
4. 对 bank tag source mismatch，先确认 bank detail read model freshness，再重跑 pending scope。
5. 对 invoice lifecycle lag，先恢复 `invoice_lifecycle` scope，再重跑 pending/search scope。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-15 | 移除待找发票行内三点菜单和 manual invoice HTTP/UI 新写入口；收入侧增加多选批量标记 | PendingInvoiceApplicationService batch income override、pending invoice routes/API、PendingInvoicesPage/Table、SQL projection、API mapper | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` |
| 2026-06-11 | 补齐测试闭环状态机 | 支出/收入规则、manual/attach/income status、UI、read model 和 worker 状态边界 | `tests.test_pending_invoice_service`、`tests.test_pending_invoice_api`、`tests.test_invoice_lifecycle_page_integration`、`tests.test_search_pending_sql_runtime`、`tests.test_pending_invoice_relation_identity`、`tests.test_pending_invoice_oa_identity_backfill`、`tests.test_derived_data_lifecycle_service`、`tests.test_app_status_overview_service`、`tests.test_runtime_worker_registry`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` 通过 |
| 2026-06-11 | 选择已有进项发票支持多流水、多发票批量 preview/confirm，状态菜单新增已支付待开票/已支付已开票快捷筛选 | Pending invoice application service、Workbench active relation、PendingInvoicesPage、候选抽屉、API mapper | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_workbench_pair_relation_service.py`、`tests/test_workbench_api.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` |
