# 待找发票状态机

> 修改 `待找发票` 相关业务状态、UI 状态或后台任务状态前必须读取本文件。待找发票状态必须由后端 policy/read boundary 给出，页面不得自行推断，也不得消费页面级 read model freshness 字段。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 方向 | `expense` | API query / direct rows payload | 支出流水查找进项发票，规则组包含 `requires_invoice`、`bank_statement_as_invoice`、`no_invoice_required`。 |
| 方向 | `income` | API query / direct rows payload | 收入流水查找销项发票，规则组包含 `requires_invoice`、`no_invoice_required`、`cash_income`。 |
| 规则组 | `requires_invoice` | active bank tag complement | 由 active 标签减去可编辑 no-invoice/cash/statement 分组实时派生，不作为请求事实保存。 |
| 规则组 | `bank_statement_as_invoice` | expense pending invoice rules | 只适用于支出；最终仍为流水代替发票的行才出现在该筛选。 |
| 规则组 | `no_invoice_required` | expense/income rules | 支出或收入都可配置；改变发票生命周期和待找发票口径。 |
| 规则组 | `cash_income` | income rules | 只适用于收入现金场景；不得污染支出规则。 |
| 行状态 | `pending_invoice` / `paid_invoiced` / `no_invoice_required` 等 | `InvoiceLifecyclePolicy`、direct pending invoice query | 列表只展示后端返回的 `invoice_acquisition_status`；页面不补推 primary action。 |
| 选择已有发票 | `attach_previewed` / `attach_confirmed` | application service | 只允许 expense 行选择 input invoice；支持单条或多条流水选择一张或多张进项发票；confirm 写一条 Workbench active relation、audit、command log 和 finalizer。 |
| 收入状态覆盖 | `income_no_invoice_required` / `cash_income` | income status override command | 只适用于收入行；支持单条兼容 API 和批量 API；写后页面直接重读 rows，Search 通过 direct payload 反映结果。 |
| command log | `created` / `relation_created` / `finalized` / `failed_terminal` | command repository | confirm 中断后可重试恢复，不得重复创建发票或关系。 |

关键规则：

- `pending_invoice_tag_groups.version` 只代表支出规则版本；`pending_output_invoice_tag_groups.version` 只代表收入规则版本。
- 保存规则只递增当前 direction 的规则版本，不递增 `bank_transaction_tags.version`。
- `requires_invoice` 即使出现在请求中也必须忽略；后端始终按 active tag complement 派生。
- 列表 `filter=requires_invoice` 是“需要开票”状态桶，不是 `filter_group='requires_invoice'` 条件。支出包含 `paid_pending_invoice`、`paid_invoiced`、`paid_pending_future_invoice`、`invoice_not_fully_paid`；收入包含 `income_pending_invoice`、`income_invoiced`。`filter_group` / `matched_rule` 只解释规则命中，不能把生产中 `filter_group=all` 但最终状态待/已开票的行排除。
- rows/filter-options/export-preview/export 的前端页面合同是 direct API payload；API 不返回页面级 read model freshness 字段。
- 历史 manual invoice service/command 只作为旧数据恢复和迁移兼容能力保留；待找发票页面和 HTTP API 不再提供新建 manual invoice 写入口。
- 选择已有发票批量 preview 不写事实；confirm 必须返回 affected transaction/invoice arrays。已存在兼容的 bank+invoice 或 OA+invoice relation 时应把既有 rows 与本次选择的银行流水/发票合并到同一 active case，不创建复用同一 row 的第二条 active case。后续从关联台 withdraw 该 active case 时，应通过 workbench relation history 恢复 confirm 前的上一 active 状态，而不是取消所有历史关系。
- 待找发票列表中的 OA、银行流水和发票关系成员必须来自 `workbench_relation` distribution。任一分区成员数大于 1 时，该分区进入 `detail_mode=list`，用 `+N` 表达全部 N 个成员；`N` 不是 extra count，且分区内不得再展示 primary 成员。
- 收入批量状态覆盖必须先全量校验：transaction ids 非空且不重复、全部为收入流水、状态码属于 `income_no_invoice_required` / `cash_income`、当前行未关联销项发票；任一失败不得写 command/audit/finalizer。
- invoice lifecycle facts 必须先于待找发票、税金、成本、OA/进项/销项下游 direct API 可见性。

禁止流转：

- 禁止前端根据缺失字段猜测 `invoice_acquisition_status` 或 primary action。
- 禁止前端把旧 `read_model_status` / stale reasons 作为页面 direct refetch、禁用导出或写入阻断依据。
- 禁止保存规则时接受未知标签、归档标签或重复映射。
- 禁止收入规则污染支出规则，或支出规则污染收入规则。
- 禁止候选 relation case id 被当作真实 OA id 请求详情。
- 禁止把已经包含在 `+N` 明细里的 OA、银行流水或发票继续作为同栏 primary 单独呈现；同一多流水 relation 的成员也不得再作为 standalone 待找发票行重复出现。
- 禁止 attach existing 或历史 manual command 恢复时重复创建发票或 relation。
- 禁止待找发票页面或 HTTP route 暴露 manual invoice preview/confirm 新写入口。
- 禁止 pending invoice 规则变更触发 `turnover_ledger`、`no_oa_bank_batch` 或 `bank_account_balance` 的页面同步路径。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | rows/filter-options/detail/rules 请求进行中 | 展示加载态；请求 abort 后清理 loading。 |
| direct rows | rows API 返回业务 payload | 展示 rows/summary；不依赖 freshness 字段。 |
| empty | direct payload 且 total 为 0 | 表示当前 direction/filter/query 没有行。 |
| error | rows/detail/rules/attach/income status/export 请求失败 | 展示业务错误，不暴露底层 SQL/worker internals。 |
| rules drawer | 用户打开规则配置 | 读取当前 direction 规则和 active tags；支持 stale version conflict 反馈。 |
| attach existing drawer/dialog | 用户从选中流水工具栏选择候选发票 | 单条或多条支出流水共用右侧抽屉；候选列表支持多选进项发票；候选表以 `bank_relation_status` / `linked_bank_transaction_count` 渲染“流水关联”chip，不展示“待支付”候选列；抽屉展示已选流水金额、已选发票金额和本次选择差额，preview 后展示关联后待付；preview 展示 conflicts/warnings 和影响；confirm 成功后 direct refetch 行和关系详情。 |
| expense transaction selection | 用户在支出列表勾选流水 | 仅允许有 `attach_existing_invoice` action 的支出流水进入批量选择；筛选、排序、分页、搜索或确认后清理选择；选择发票入口只在表格上方选中工具栏出现。 |
| income transaction selection | 用户在收入列表勾选流水 | 仅允许有 `mark_income_status` action 的收入流水进入批量选择；选中后工具栏显示“标记无需开票”“标记现金收入”“清除选择”。 |
| income status batch action | 收入选中工具栏提交 | 提交时禁用批量状态按钮；成功后以响应 rows 或 refetch 为准，并清理选择。 |
| relation member list | 用户点击 `+N` | 仅展示点击分区对应的 OA、银行流水或发票成员；请求可带 `kind=oa|bank|invoice`，默认全量详情只作为兼容路径。 |
| permission disabled/hidden | session permissions | 只读用户隐藏或禁用保存规则、attach、income override 等 mutation。 |

前端事件：

- `invoiceFactUpdated`、`workbenchRelationUpdated`、`bankTransactionCategoryUpdated`、`bankAutoTagRulesUpdated` 只能触发 refetch 或规则刷新。
- 前端事件不是事实源；后端 canonical facts、lifecycle、真实 outbox/cache warmup 和 direct API payload 才证明待找发票已收敛。
- 页面卸载后不 replay 事件；返回页面重新通过 API/read boundary 加载。

## Runtime / Guard 状态

待找发票页面没有 read-model freshness 状态机。rows、filter-options、export-preview 和 export 都是 direct API payload；后端按 `PendingInvoiceQueryService`、invoice lifecycle policy、canonical relation facts、规则版本和当前银行/发票事实组装响应。

当前后台/诊断边界：

- `pending_invoice.read_model.refresh` worker、registry、manifest、deploy env 已下线。
- `search_pending_sql_projection.py`、`PendingInvoiceReadModelRepositoryPort`、`PostgresReadModelRepository` 的 pending-invoice row/scope 方法和当前运行脚本/监控中的 `read_model.pending_invoice_rows/scopes` 访问已删除。
- `invoice_lifecycle_sql_projection.py` 的待找发票 lifecycle 行改为 direct `PendingInvoiceQueryService` 分页读取后映射；不再复用 pending-invoice SQL projection。
- 历史 scope 名如 `expense:all`、`income:requires_invoice` 或 `<direction>:<filter>:YYYY-MM` 只作为迁移/删除清单和旧测试上下文；不得恢复为页面 API freshness proof。
- App Status 只报告真实 runtime、worker、job、dependency、session 或 import/lifecycle 问题；不得把 pending-invoice legacy scope readiness 提升为全局状态字段。

Direct refetch / lifecycle 触发来源：

- 发票导入确认。
- Workbench 关系确认/撤回、历史 manual command 恢复、attach existing confirm。
- 待找发票规则保存。
- 收入状态 override。
- 银行标签保存、重命名、归档或自动分类版本变化。
- invoice lifecycle direct recalculation、OA rebuild、App Health 运维诊断。
- `startup_stale_scan` 默认关闭，且不直接刷新待找发票 read model；只有后续 matching 结果真实变化并触发业务 lifecycle 时才间接影响 direct rows。

失败恢复：

1. 先看页面 direct API、invoice lifecycle scope 和 command/audit/finalizer；不再恢复 `pending-invoice` worker 或 `pending_invoice.read_model.refresh`。
2. 对 rule version conflict，让页面重新读取规则 payload，再基于新 version 保存。
3. 对 attach command 或历史 manual command 中断，优先用 command log 重试恢复，不手工删除已创建发票或 relation。
4. 对 bank tag source mismatch，按后端兼容投影诊断处理；页面 rows 仍以 direct payload 验收。
5. 对 invoice lifecycle lag，先恢复 invoice lifecycle 事实/后台任务，再通过待找发票 direct API 重读验证；不要重跑 pending read-model scope。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-28 | 关闭 pending-invoice 页面/生命周期 producer | `PendingInvoiceRulesApplicationService` 不再接受 read model invalidation callback；`DerivedDataLifecycleService` 不再规划 `pending_invoice_read_model`；`Application` 和 runtime worker import-state 不再从页面/导入/设置/生命周期事件入队 `pending_invoice.read_model.refresh`。 | `tests/test_pending_invoice_api.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` |
| 2026-06-28 | 删除 pending-invoice legacy worker/projection/repository | 后端 producer 清零后，删除 `SearchPendingReadModelRefreshService`、`pending-invoice` worker registry、AppStatus read-model/job、RabbitMQ dispatch event、deploy env、manifest entry、`SearchPendingSqlProjectionBuilder`、`PendingInvoiceReadModelRepositoryPort` 和 `PostgresReadModelRepository` pending row/scope 方法；invoice lifecycle 改用 direct pending query。 | `tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_rabbitmq_runtime.py`、`tests/test_invoice_lifecycle_sql_projection.py`、`tests/test_read_model_manifest.py`、`tests/test_postgres_repositories_boundaries.py` |
| 2026-06-27 | 关联写入前置错误移除 read model freshness 语义 | manual/attach 写入只接受 canonical active relation conflict、version conflict 和权限/幂等失败；不再把 `workbench_relation_context_not_ready` 翻译为待找发票页面错误，失败 payload 不返回 read model freshness 字段。 | `tests/test_pending_invoice_service.py` |
| 2026-06-27 | 页面 API 移除 read model freshness 字段 | rows/filter-options/export-preview/export 不返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_key(s)` 或 `refresh_enqueued`；mutation 返回 `affected_scope_keys` 而不是 `read_model_scope_keys` | `tests/test_pending_invoice_api.py`、`tests/test_pending_invoice_service.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` |
| 2026-06-23 | 补 `pending_invoice` / `oa_pending_payment` manifest 合同守卫 | 不改变状态机；锁定待找发票拒绝裸 `all`、page-first-screen force refresh、与 OA 待付款 repository port 隔离，防止旧 scope 或旧 read path 污染内部 freshness | `tests.test_read_model_manifest.ReadModelManifestTests.test_pending_invoice_and_oa_payment_manifest_preserve_page_scope_contracts` |
| 2026-06-23 | 待找发票 rows 补齐 `bank_transactions` 分区，多 OA/多流水/多发票按 `workbench_relation` 聚合为一行并用 `+N` 展开对应类型明细 | PendingInvoiceQueryService、PendingInvoicesTable、PendingInvoiceRelationDrawer、API mapper | `tests/test_pending_invoice_service.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` |
| 2026-06-17 | 选择已有进项发票候选表改为后端事实驱动的“流水关联”chip，并允许已有 OA+发票关系并入同一 attach active case；关联台撤回恢复上一状态 | PendingInvoiceQueryService candidates、PendingInvoiceApplicationService attach existing、PendingInvoiceInvoicePickerDrawer、API mapper | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` |
| 2026-06-15 | `requires_invoice` 父筛选改为最终状态桶，解除对 `filter_group` 的可见性依赖 | Pending invoice status helper、service fallback、API/product/module docs；旧 SQL projection 覆盖已随 legacy projection 删除 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py` |
| 2026-06-15 | 移除待找发票行内三点菜单和 manual invoice HTTP/UI 新写入口；收入侧增加多选批量标记 | PendingInvoiceApplicationService batch income override、pending invoice routes/API、PendingInvoicesPage/Table、SQL projection、API mapper | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` |
| 2026-06-11 | 补齐测试闭环状态机 | 历史记录：当时覆盖支出/收入规则、manual/attach/income status、UI、read model 和 worker 状态边界；当前页面已迁移为 direct API 和 deleted-worker guards | `tests.test_pending_invoice_service`、`tests.test_pending_invoice_api`、`tests.test_invoice_lifecycle_page_integration`、历史 SQL/runtime 测试、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` 通过 |
| 2026-06-11 | 选择已有进项发票支持多流水、多发票批量 preview/confirm，状态菜单新增已支付待开票/已支付已开票快捷筛选 | Pending invoice application service、Workbench active relation、PendingInvoicesPage、候选抽屉、API mapper | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_workbench_pair_relation_service.py`、`tests/test_workbench_api.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` |
