# 权限写入口 Inventory

本文维护 `PERM-E2E-003` 的页面级写入口清单。目标是让后续新增页面按钮、抽屉、批量动作时，能明确判断它是否已经被 Browser role matrix 覆盖，而不是只依赖后端 guard 或组件测试。`tests/test_permissions_write_entry_inventory.py` 会双向校验 `pageRegistry.tsx` 与本清单 row 一致、`pageRegistry.tsx` 与 role matrix readable route 一致、每个非 admin route 都进入 role matrix read-export smoke、`covered-*` row 必须引用 Browser E2E 证据，并校验源码高风险写控件文案 sentinel 仍与关键词 registry 同步。

Phase 27 的 read-model fan-out 迁移另有一份测试时全量合同：`.planning/phases/27-read-model-fan-out/27-COVERAGE-MATRIX.md`。它把本清单扩展到当前注册页面、导出的 POST/PUT/PATCH/DELETE 客户端函数、业务 `Drawer.tsx`、Browser dynamic opener、manifest read model 和直接 lifecycle/enqueue/barrier 调用点，并由本文件对应测试与 `tests/test_read_model_manifest.py` 双向校验。该矩阵只用于规划、测试和删除审计，不进入生产 I/O，也不建立第二套 runtime registry；新增发票录入 Drawer 的 OCR/preview 属于 read-like command，最终确认复用既有 import explicit-batch 权限与审计边界。

后端独立 fail-closed 合同由 `route_access_policy.py` 和 `tests/test_route_access_policy.py`/`tests/test_auth_guard.py` 维护：除明确登记的纯读取 POST 外，受保护的 unsafe method 默认要求 mutation 权限。浏览器 inventory 证明 UI 不暴露写控件，后端合同证明手工构造 HTTP 请求也不能越权，二者不能互相替代。

状态说明：

- `covered-browser`：已有 Browser E2E 证明 `read_export_only` 下入口隐藏/禁用，且 durable mutation 为 0。
- `covered-mixed`：Browser 覆盖页面读取或主流程，组件/API/后端覆盖权限，但 Browser 尚未逐按钮点击或选择。
- `partial`：已知有写入口，尚未达到页面级按钮矩阵闭环。
- `external-risk`：真实 OA、代理、生产审计或 staging 环境才能证明。

## Write control keyword registry

`permissions-role-matrix` 会扫描真实 Chromium DOM 中可见且 enabled 的 button、`role=button`、`role=menuitem` 和 file input。`tests/test_permissions_write_entry_inventory.py` 会校验本节登记的关键词都包含在 `enabledWriteControlPattern`，防止新增深层写动作文案后没有进入 read-export 禁用扫描。

| Keyword | 典型入口 |
| --- | --- |
| `保存` | generic drawer save buttons |
| `保存设置` | settings 普通配置保存 |
| `保存计划` | tax offset 计划保存 |
| `保存规则` | pending/OA/input/output 规则保存 |
| `保存并刷新` | input invoice usage 支付状态规则保存并刷新 read model |
| `保存外部往来款` | turnover extra save |
| `保存补充信息` | bank details 人工补分类 |
| `保存凭据` | settings OA 申请人凭据 |
| `清空密码` | settings OA 申请人凭据 |
| `新增账户` | settings 访问账户管理 |
| `重新应用规则` | bank auto tag rules |
| `新增标签` | bank auto tag rules |
| `拖动 .* 列` | workbench column layout reorder, saves `/api/workbench/settings` for writable users |
| `确认导入` | import confirm |
| `确认对账` | ETC reconciliation |
| `确认闭环` | turnover closure |
| `确认关联` | workbench relation |
| `确认买票` | cash ticket/cost confirmation |
| `确认为买票` | cash ticket/cost confirmation |
| `确认为过账` | cash posting confirmation |
| `确认已支付` | OA pending payment |
| `确认拆分` | workbench candidate split |
| `确认撤回` | withdraw confirmation |
| `确认已审阅` | Workbench 已退役逐项人工审阅复选入口的防回流扫描关键词 |
| `进入已配对` | Workbench 异常接受后进入已配对的通用动作关键词 |
| `留在未配对` | Workbench 异常决定保持未配对 |
| `接受异常并进入已配对` | Workbench 接受当前系统异常并进入已配对 |
| `撤回到未配对` | Workbench 已配对异常撤回未配对 |
| `留在未配对` | Workbench 异常人工保留 |
| `撤回` | AppHealth 导入历史单批次撤回入口 |
| `取消现金处理` | cash ticket/cost rollback |
| `写回` | OA writeback |
| `撤回批次` | no-OA batch withdraw |
| `撤回关联` | workbench/batch relation withdraw |
| `撤回` | Workbench 已配对异常撤回放行 |
| `忽略` | workbench 行级忽略 |
| `删除` | ETC/settings destructive actions |
| `新建批次` | ETC batch |
| `创建 OA 草稿` | input/OA/ETC draft |
| `创建OA草稿` | compact OA draft label |
| `上传` | import/upload controls |
| `关联OA项` | batch accounting |
| `关联支出流水` | OA pending payment |
| `关联所选记录` | ETC manual reconciliation |
| `接受推荐票根` | ETC manual reconciliation |
| `选择发票` | pending invoice attachment |
| `标记无需开票` | pending income status |
| `标记现金收入` | pending income status |
| `标记异常` | workbench/ETC exception |
| `异常处理` | Workbench 统一异常抽屉标题及其它仍登记的异常能力；不代表未配对工具栏人工动作 |
| `取消异常处理` | workbench exception recovery |
| `提交异常` | workbench exception submit |
| `继续报异常` | workbench exception continue |
| `排除非ETC` | ETC manual reconciliation |
| `手工确认` | ETC manual reconciliation |
| `已认证发票导入` | tax certified import |
| `开始预览` | import preview |
| `数据重置` | settings data reset |
| `重置数据` | settings data reset |
| `提交OA` | ETC OA draft submit |
| `提交 OA` | ETC OA draft submit |
| `提交审批` | ETC approval submit |
| `提交批次` | no-OA/batch submit |
| `人工提交` | ETC manual submit |
| `打印收据` | Workbench 无 OA 收入＋销项发票 active relation 在编辑抽屉生成并请求打印收据 |

## Source write-control keyword sentinels

本节把一组高风险写控件文案绑定到当前源码文件。`tests/test_permissions_write_entry_inventory.py` 会校验这些文案仍存在于对应源码中，且仍登记在 `Write control keyword registry`。如果按钮文案改名，必须同步更新本节、关键词 registry 和 `permissions-role-matrix` 扫描 pattern。

| Keyword | Source file | 说明 |
| --- | --- | --- |
| `保存设置` | `web/src/components/settings/SettingsPageContent.tsx` | settings 普通保存入口。 |
| `新增账户` | `web/src/components/settings/SettingsAccessAccountsSection.tsx` | settings 访问账户管理。 |
| `保存凭据` | `web/src/components/settings/SettingsOaApplicantCredentialsSection.tsx` | settings OA 申请人凭据保存。 |
| `清空密码` | `web/src/components/settings/SettingsOaApplicantCredentialsSection.tsx` | settings OA 申请人凭据清空。 |
| `创建 OA 草稿` | `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx` | 进项发票反提 OA 草稿创建。 |
| `OA 草稿预填管理` / `保存` | `web/src/components/common/OaDraftPrefillDrawer.tsx` | ETC 与进项发票使用页面对所有已授权 App 账户展示 versioned 预填设置入口；非 admin 只读且不展示保存操作，后端 PUT 再校验 admin。 |
| `关联支出流水` | `web/src/pages/OaPendingPaymentsPage.tsx` | OA pending 关联支出流水。 |
| `关联OA项` | `web/src/pages/BatchAccountingPage.tsx` | 批量账务关联 OA 项与流水。 |
| `确认为过账` | `web/src/components/workbench/RowActions.tsx` | 关联台现金过账行级菜单。 |
| `确认为买票` | `web/src/components/workbench/RowActions.tsx` | 关联台现金买票行级菜单。 |
| `取消现金处理` | `web/src/components/workbench/RowActions.tsx` | 关联台现金特殊处理回滚行级菜单。 |
| `确认买票` | `web/src/pages/ReconciliationWorkbenchPage.tsx` | 关联台买票成本确认弹窗。 |
| `留在未配对` | `web/src/components/workbench/WorkbenchExceptionDrawer.tsx` | 关联台异常决定保持未配对。 |
| `打印收据` | `web/src/components/workbench/WorkbenchReceiptDrawer.tsx` | 关联台无 OA 收入＋销项发票 active relation 在编辑抽屉生成并请求打印收据。 |
| `接受异常并进入已配对` | `web/src/components/workbench/WorkbenchExceptionDrawer.tsx` | 接受服务端当前异常证据并进入已配对。 |
| `撤回到未配对` | `web/src/components/workbench/WorkbenchExceptionDrawer.tsx` | 已配对异常撤回未配对。 |
| `留在未配对` | `web/src/components/workbench/WorkbenchExceptionDrawer.tsx` | 关联台异常人工保留。 |
| `确认对账` | `web/src/pages/EtcTicketManagementPage.tsx` | ETC 对账任务确认。 |
| `接受推荐票根` | `web/src/pages/EtcTicketManagementPage.tsx` | ETC 人工核对处理。 |
| `关联所选记录` | `web/src/pages/EtcTicketManagementPage.tsx` | ETC 人工核对处理。 |
| `排除非ETC` | `web/src/pages/EtcTicketManagementPage.tsx` | ETC 人工核对处理。 |
| `手工确认` | `web/src/pages/EtcTicketManagementPage.tsx` | ETC 人工核对处理。 |
| `重新应用规则` | `web/src/features/bankDetails/AutoTagRulesDrawer.tsx` | 银行明细自动标签规则重新应用。 |
| `新增标签` | `web/src/features/bankDetails/AutoTagRulesDrawer.tsx` | 银行明细自动标签规则新增。 |
| `开始预览` | `web/src/components/imports/ImportWorkflowPage.tsx` | 导入 preview。 |
| `确认导入` | `web/src/components/imports/ImportWorkflowPage.tsx` | 导入确认。 |
| `保存` | `web/src/components/cost-statistics/CostStatisticsNoOaRulesDrawer.tsx` | 无 OA 虚拟项目与互斥标签归属保存；只影响三个成本归因视图。 |
| `保存` | `web/src/components/cost-statistics/CostStatisticsManualAllocationDrawer.tsx` | 成本人工分配按关系逐组保存或修改；请求携带关系版本与事实指纹，保存逐 OA 单元成本、可选不计入成本金额及说明。 |

## Mutating feature API coverage map

`tests/test_permissions_write_entry_inventory.py` 会扫描 `web/src/features/*/api.ts` 中的 POST/PUT/PATCH/DELETE client，并校验每个 mutating feature API 文件都在本节登记、且登记的模块存在于页面写入口矩阵。它还会递归解析当前文件内 helper，按导出函数粒度与 Phase 27 矩阵双向核对，并区分 preview/calculate/barrier 等 `read-like-command`。shared API 应映射到实际消费该写操作的页面或运维模块。

| Feature API | Inventory modules | 说明 |
| --- | --- | --- |
| `backgroundJobs/api.ts` | `app-health-operations`, `settings` | 后台任务用于运维、数据重置和长任务轮询/控制。 |
| `appHealth/api.ts` | `app-health-operations` | 管理员从导入历史撤回可证明为单批次独占创建的银行流水。 |
| `bankDetails/api.ts` | `bank-details` | 银行明细分类、自动标签、关系入口等写入口。 |
| `batchAccounting/api.ts` | `batch-accounting` | 批量账务标签规则保存、提交和撤回。 |
| `cost-statistics/api.ts` | `cost-statistics` | 无 OA 规则 PUT 与配对金额人工分配写入；导出仍为只读能力。 |
| `etc/api.ts` | `etc-tickets`, `imports-etc-invoices` | ETC 票据管理、ETC 导入、对账和业务批次写入口；清空仅放弃当前用户尚未确认的预览，不触碰业务事实。 |
| `imports/api.ts` | `imports-bank-transactions`, `imports-invoices`, `imports-etc-invoices` | 文件导入 preview/confirm/template；人工流水 preview 仅创建当前用户的临时预览 session，属于 read-like command，确认/放弃复用既有 import batch/session 边界。 |
| `inputInvoiceUsage/api.ts` | `input-invoice-usage` | 支付规则、OA reverse 草稿/批次/状态写入口。 |
| `bankFlowRuleBatches/api.ts` | `bank-flow-rule-batches` | 流水规则批量处理标签规则、提交、撤回和内部往来迁移底座写入口。 |
| `oaPendingPayments/api.ts` | `oa-pending-payments` | 关联支出流水；支付状态由 relation event 自动同步，无人工写回 API。 |
| `pendingInvoices/api.ts` | `pending-invoices` | 待找发票规则、选择发票和收入状态写入口。 |
| `tax/api.ts` | `tax-offset` | 税金计划保存和已认证发票导入。 |
| `turnoverLedger/api.ts` | `turnover-ledger` | 外部往来标签、闭环、撤回和 extra 写入口。 |
| `workbench/api.ts` | `reconciliation-workbench`, `settings` | 关联台 relation/异常/发票 OA 明细归属 command、关系级收据生成与打印请求审计、settings 保存和访问控制写入口。 |

后端兼容 `POST /api/workbench/exception/apply` 仍属于 `reconciliation-workbench` mutation 边界，用于既有自动异常/行级异常流程，不代表恢复已删除的未配对工具栏人工“异常处理”入口。其 actor 只来自服务端认证 session，request body 的 `actor` / `confirmed_by` 不属于身份或审计事实源。

## Role matrix 动态 opener registry

`web/e2e/permissions-role-matrix.spec.ts` 中的 role matrix opener registry 维护已安全打开并复扫 DOM 写控件候选的动态区域；不同初始数据态可以拆成独立 opener 数组和独立测试。`tests/test_permissions_write_entry_inventory.py` 会双向校验 opener id：Playwright 里的 opener 必须在本节登记，本节登记的 opener 也必须在 Playwright 实现，防止权限文档声明了不存在的 Browser 覆盖。

| Opener ID | Module | 已打开区域 | 当前证明 |
| --- | --- | --- | --- |
| `reconciliation-workbench:unpaired-actions` | `reconciliation-workbench` | 未配对行选择后的确认/关系级撤回入口、旧人工异常入口缺席断言和列顺序拖拽设置保存入口 | read-export 下列拖拽 handle 全部 disabled，尝试拖拽不会进入 column-layout dragging 或触发 `POST /api/workbench/settings`；选择未配对行后确认关联和关系级撤回禁用，未配对工具栏精确文案“异常处理”以及行级旧异常/确认入口不存在，且复扫写控件。统一异常抽屉由 `reconciliation-workbench:exception-drawer` 单独覆盖。 |
| `reconciliation-workbench:paired-withdraw-actions` | `reconciliation-workbench` | 已配对 active relation 选择后的关系级撤回入口 | read-export 下选择已配对关系后撤回关联禁用，行级更多/取消关联/人工异常入口不存在，withdraw durable mutation 零调用，且复扫当前关系。 |
| `reconciliation-workbench:cash-special-actions` | `reconciliation-workbench` | 已配对银行行的现金过账、现金买票和取消现金处理行级菜单 | deterministic mock 暴露 `confirm_cash_pass_through`、`confirm_cash_ticket_purchase`、`cancel_cash_special` 后，read-export 下更多菜单不可见，确认为过账/确认为买票/取消现金处理 menuitem 和确认买票成本弹窗均不可见，三个现金处理 durable mutation 零调用，且复扫候选。 |
| `bank-details:auto-tag-rules` | `bank-details` | 自动标签规则抽屉 | read-export 下新增标签、重新应用规则、保存禁用，且复扫 visible enabled 写控件候选。 |
| `cost-statistics:no-oa-rules` | `cost-statistics` | 无 OA 成本范围抽屉 | read-export 下可查看候选与虚拟项目，但新增、编辑、删除、标签选择与 `保存` disabled，`PUT /api/cost-statistics/no-oa-rules` 零调用，并复扫 visible enabled 写控件候选。 |
| `cost-statistics:manual-allocations` | `cost-statistics` | 成本人工分配抽屉 | read-export 下可打开并展开确定性关系组，但分配金额输入、不计入成本复选框与逐关系 `保存分配` 均 disabled，`PUT /api/cost-statistics/manual-allocations/CASE-COST-MANUAL-READONLY` 零调用，并复扫 visible enabled 写控件候选。 |
| `bank-details:category-confirmation` | `bank-details` | 银行明细行内分类确认入口 | read-export 下待确认分类按钮禁用，分类菜单不打开，category-confirmation durable mutation 零调用，且复扫候选。 |
| `bank-details:manual-category-assignment` | `bank-details` | 银行明细待分类/待确认/自动标签人工覆盖入口 | read-export 下待分类与自动标签“撤销”按钮禁用，人工分类菜单不打开，category-assignment durable mutation 零调用，且复扫候选。 |
| `bank-flow-rule-batches:tag-drawer` | `bank-flow-rule-batches` | 流水规则批量处理标签规则抽屉 | read-export 下提交/撤回入口不可见，标签规则 OA/发票复选框和保存禁用，且复扫候选。 |
| `pending-invoices:expense-rules` | `pending-invoices` | 支出待找发票规则抽屉 | read-export 下选择发票禁用、规则保存禁用，且复扫候选。 |
| `pending-invoices:income-rules` | `pending-invoices` | 收入待找发票规则抽屉 | read-export 下收入规则保存禁用、规则 PUT 零调用，且复扫候选。 |
| `pending-invoices:income-batch` | `pending-invoices` | 收入批量状态区 | read-export 下标记无需开票/现金收入禁用，且复扫候选。 |
| `input-invoice-usage:payment-rules` | `input-invoice-usage` | 发票与支付状态规则抽屉 | read-export 下规则只读、无保存/还原，且复扫候选。 |
| `input-invoice-usage:oa-reverse` | `input-invoice-usage` | 以发票反提 OA 工作流抽屉 | read-export 下允许 read-like preview POST，返回 `canCreateDraft=false`，创建 OA 草稿禁用，durable write endpoints 零调用，且复扫候选。 |
| `output-invoice-collections:canonical-read-only` | `output-invoice-collections` | canonical 三组只读表格 | read-export、full-access、admin 均只提供查询、详情和导出；旧状态/红蓝票/收据写入口不存在，durable mutation 为 0。 |
| `oa-pending-payments:in-progress` | `oa-pending-payments` | 进行中 OA 区域 | read-export 下关联支出流水禁用、确认写回和 OA 选择不可见，且复扫候选。 |
| `oa-pending-payments:expense-rules` | `oa-pending-payments` | 支出流水无需开票规则抽屉 | read-export 下规则只读、保存规则禁用，且复扫候选。 |
| `etc-tickets:reconciliation-workflow` | `etc-tickets` | ETC 对账流程区 | read-export 下上传信用卡账单/票根网、确认对账、人工核对处理动作禁用，且复扫候选。 |
| `batch-accounting:oa-selection` | `batch-accounting` | OA 选择后批量关联区 | read-export 下关联 OA 项与流水禁用，且复扫候选。 |
| `batch-accounting:submitted-withdraw` | `batch-accounting` | 已提交 bucket 撤回入口 | read-export 下已提交 bucket 的撤回关联禁用，withdraw durable mutation 零调用，且复扫候选。 |
| `turnover-ledger:tag-drawer` | `turnover-ledger` | 外部往来款标签设置抽屉 | read-export 下标签全选/清空/保存禁用，且复扫候选。 |
| `turnover-ledger:detail-controls` | `turnover-ledger` | 外部往来款流水明细区 | read-export 下流水选择、编辑、确认闭环禁用，且复扫候选。 |
| `reconciliation-workbench:exception-drawer` | `reconciliation-workbench` | 异常处理右侧抽屉；未配对/已配对异常切换、接受异常进入已配对、留在未配对和撤回 | read-export 下抽屉只读，无决定或撤回按钮，相关 mutation 为零。 |

## Role matrix 页面级静态覆盖 registry

`covered-browser` 页面如果没有动态 opener，必须在本节说明为什么首屏或专门 Browser flow 已足够证明 read-export 零 mutation。`tests/test_permissions_write_entry_inventory.py` 会要求每个 `covered-browser` row 要么有动态 opener，要么登记在本节，避免后续页面跳过动态区域审计。

| Module | 静态覆盖原因 | 当前证明 |
| --- | --- | --- |
| `imports-bank-transactions` | 文件导入写入口位于首屏；人工流水录入 opener 本身受 mutation 权限保护，read-export 下不存在，因此不需要动态打开 Drawer。 | `permissions-role-matrix.spec.ts` 的 import controls 循环在 read-export 下断言文件 input、开始预览和确认导入禁用，并断言 `流水录入` opener 不存在且零 mutation；人工流水 full-access preview/confirm/dedupe 由现有组件/API 测试覆盖。 |
| `imports-invoices` | 导入页写入口集中在首屏上传、开始预览和确认导入控件，不需要额外抽屉 opener。 | `permissions-role-matrix.spec.ts` 的 import controls 循环在 read-export 下打开该 route，断言文件 input、开始预览和确认导入禁用且零 mutation；`imports-invoices-flow.spec.ts` 覆盖 full-access 主链路。 |
| `imports-etc-invoices` | 导入页写入口集中在首屏上传、开始预览和确认导入控件，不需要额外抽屉 opener。 | `permissions-role-matrix.spec.ts` 的 import controls 循环在 read-export 下打开该 route，断言文件 input、开始预览和确认导入禁用且零 mutation；`imports-etc-invoices-flow.spec.ts` 覆盖 full-access 主链路。 |
| `tax-offset` | read-export 下保存计划和已认证发票导入入口在页面首屏直接可判定，深层导入流程由 full-access Browser flow 覆盖。 | `permissions-role-matrix.spec.ts` 直接断言 read-export 下无保存计划/已认证发票导入入口；`tax-offset-flow.spec.ts` 覆盖 full-access 保存、导入、冲突和 read model 非 fresh。 |
| `settings` | read-export、full-access、admin 的关键写入口在 role matrix 顶层测试中逐项断言，不通过动态 opener registry 执行。 | `permissions-role-matrix.spec.ts` 断言 read-export 保存禁用且 admin-only 区隐藏，full-access 普通保存 POST/200，admin 访问账户、OA 凭据保存/清空密码，并打开数据重置影响确认和 OA 密码复核弹窗但取消在创建 reset job 之前。 |
| `app-health-operations` | AppHealth 是 admin-only 运维页面；导入历史包含受二次确认保护的银行流水批次撤回入口，非管理员不能进入页面或调用接口。 | `app-shell.spec.ts` 与 `permissions-role-matrix.spec.ts` 覆盖 admin dashboard、read-export/forbidden/expired route gate；组件/API 测试覆盖撤回按钮、二次确认、管理员成功和非管理员 403。 |
| `operation-history` | 操作历史是 005 管理员专用只读页面；页面没有业务 mutation。 | 组件/API 测试覆盖管理员可读、非管理员 403、侧栏隐藏和详情 Drawer；后端 route guard 是最终权限边界。 |

## 页面写入口矩阵

| Module | 写入口 | 当前状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- | --- |
| `reconciliation-workbench` | manual confirm、paired/unpaired active-relation withdraw、异常接受进入已配对/留在未配对/撤回、待归属发票显式选择 OA 明细、无 OA 收入收据编辑/打印、行级忽略、no-OA withdraw、cash pass-through/ticket purchase/cancel、column layout reorder/settings save；未配对工具栏人工“异常处理”已删除 | `covered-browser` | `web/e2e/workbench-permissions-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/workbench-receipt-flow.spec.ts`；role matrix 在 read-export 下断言列拖拽 handle 全部 disabled、尝试拖拽不进入 dragging 且 `POST /api/workbench/settings` 零调用，也会选择未配对/已配对关系并打开统一异常抽屉，断言确认和关系级撤回禁用、未配对工具栏人工“异常处理”不存在、异常决定/撤回入口隐藏；receipt flow 另以双分区合格关系证明收据入口禁用且 draft/print 零调用；现金处理 mutation 同样为零。 | 新增 relation、异常审阅、发票明细归属、收据、现金处理 command 或隐式 settings 写入口时补同类 Browser 断言。 |
| `bank-details` | 分类保存/清除、候选确认/撤回、人工待分类、自动标签规则保存/reapply | `covered-browser` | `web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/e2e/bank-details-auto-tag-rules-flow.spec.ts`；本轮 `web/e2e/permissions-role-matrix.spec.ts` 会在 read-export 下打开自动标签规则抽屉并分别进入待确认分类和未匹配待分类状态，断言新增标签/reapply/保存禁用、待确认/待分类按钮禁用、分类菜单不打开、category-confirmation/category-assignment 零 mutation，并复跑 DOM 写控件候选扫描 | 新增批量分类或规则入口时补 read-export 零 mutation。 |
| `imports-bank-transactions` | 文件选择、文件 preview/confirm import、账户冲突确认、人工流水 preview/discard/confirm | `covered-browser` | `web/e2e/permissions-role-matrix.spec.ts` 覆盖 read-export 文件导入 controls disabled，并证明 `流水录入` opener 不存在；`web/e2e/imports-bank-transactions-flow.spec.ts` 覆盖 full_access 文件导入主链路，人工流水组件/API 测试覆盖 preview/confirm/dedupe | 人工流水 Drawer 若改为只读可打开，必须补动态 opener 和内部控件扫描。 |
| `imports-invoices` | 文件选择、preview、confirm import | `covered-browser` | `web/e2e/permissions-role-matrix.spec.ts` 覆盖 import controls disabled；`web/e2e/imports-invoices-flow.spec.ts` 覆盖 full_access 主链路 | 同上。 |
| `imports-etc-invoices` | zip 选择、preview、confirm import | `covered-browser` | `web/e2e/permissions-role-matrix.spec.ts` 覆盖 import controls disabled；`web/e2e/imports-etc-invoices-flow.spec.ts` 覆盖 full_access 主链路 | 同上。 |
| `pending-invoices` | 选择已有发票、收入批量状态、规则保存 | `covered-browser` | 本轮 `web/e2e/permissions-role-matrix.spec.ts` 覆盖 read-export 下选择已有发票、支出/收入规则保存、收入状态按钮禁用且零 mutation；`web/e2e/pending-invoices-*` 覆盖 full_access 主链路；后端/API guard 覆盖 mutation 拒绝 | 新增待找发票写入口时补同类 Browser 断言。 |
| `tax-offset` | 保存计划、已认证发票导入 | `covered-browser` | `web/e2e/tax-offset-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 新增税金 mutation 时补。 |
| `bank-flow-rule-batches` | 标签规则保存、提交批次、撤回批次、内部往来迁移底座提交 | `covered-browser` | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`、组件/API tests | 新增 batch command 时补。 |
| `batch-accounting` | 标签规则保存、关联 OA 项与流水、撤回关联 | `covered-browser` | `web/e2e/permissions-role-matrix.spec.ts` 覆盖 read-export 下选择 OA 后 submit disabled、已提交 bucket 撤回关联 disabled 且 submit/withdraw 零 mutation；`web/src/test/BatchAccountingPage.test.tsx` 覆盖 read-export 标签规则只读与 full-access CAS 保存；`web/e2e/batch-accounting-flow.spec.ts` 覆盖 full_access 标签规则、submit/withdraw 主链路 | 新增 batch accounting command 时补同类 Browser 断言。 |
| `turnover-ledger` | 标签准入保存、确认闭环、撤回闭环、extra 保存/confirm/withdraw、导出 | `covered-browser` | 本轮 `web/e2e/permissions-role-matrix.spec.ts` 覆盖标签抽屉保存 disabled、flow checkbox disabled、extra 编辑入口 disabled、确认闭环 disabled 且零 mutation；extra 抽屉内部保存/confirm/withdraw 因只读角色无法进入写入口，组件/API 覆盖内部按钮和 guard；`web/e2e/turnover-ledger-flow.spec.ts` 覆盖 full_access 主链路 | 新增 turnover 写入口或把 extra 改成只读可打开时，必须补对应 Browser 断言。 |
| `input-invoice-usage` | 支付规则保存、OA reverse 草稿创建 | `covered-browser` | `web/e2e/input-invoice-usage-flow.spec.ts`；本轮 `web/e2e/permissions-role-matrix.spec.ts` 会在 read-export 下打开支付状态规则抽屉和以发票反提 OA 工作流，断言规则只读、OA reverse preview 不可创建草稿、durable write endpoints 零调用并复跑 DOM 写控件候选扫描 | 新增 payment/OA 写入口时补。 |
| `output-invoice-collections` | 无业务写入口；仅 canonical 查询、详情和导出 | `covered-browser` | `web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、API tests；`web/e2e/permissions-role-matrix.spec.ts` 通过 `output-invoice-collections:canonical-read-only` 证明三种角色均无旧状态/提醒/人工红蓝票/收据写入口且 durable mutation 为 0。 | 若新增写入口，必须先恢复权限、API、审计和回滚合同；当前保持只读。 |
| `oa-pending-payments` | link-bank、支出流水无需开票规则保存；支付状态由 relation event 自动同步、无页面写入口 | `covered-browser` | `web/e2e/permissions-role-matrix.spec.ts` 覆盖 read-export 下 link-bank disabled、OA 选择隐藏、规则 drawer 只读且保存禁用，并保持零 mutation；页面/API tests 锁定人工 writeback/confirm 入口不存在 | 新增 OA command 时补。 |
| `cost-statistics` | 无 OA 成本范围保存、成本人工分配逐关系保存、导出 | `covered-browser` | `web/e2e/permissions-role-matrix.spec.ts` 在 read-export 下打开两套 Drawer；人工分配使用确定性关系组，证明分配金额输入、不计入成本复选框和逐关系保存均 disabled，相关 PUT 零调用并复扫写控件；`web/src/test/CostStatisticsPage.test.tsx` 覆盖金额闭合校验、逐关系保存与保存后刷新；API/service tests 覆盖权限、版本/事实指纹冲突、审计与持久化 | 新增成本规则、分配字段或写入口时同步扩展 opener；生产环境仍只做只读列表/口径与性能验证，不以真实财务关系执行写入 smoke。 |
| `etc-tickets` | OA 草稿、人工提交、delete/reset、source file/upload/import/manual reconciliation | `covered-browser` | 本轮 `web/e2e/permissions-role-matrix.spec.ts` 覆盖 read-export 下提交 OA、新建批次、删除按钮、source file 上传、确认对账和人工核对动作禁用且零 mutation；`web/e2e/etc-tickets-flow.spec.ts` 覆盖 full_access OA 草稿和人工提交主链路；组件/API tests 覆盖 source file/upload/manual reconciliation guard | 新增 ETC 写入口时补同类 Browser 断言。 |
| `settings` | 保存设置、访问账户、OA 凭据、数据重置 | `covered-browser` | `web/e2e/permissions-role-matrix.spec.ts` 覆盖 read-export 保存禁用、full-access 普通 settings 保存 POST/200 且 direct ACL 攻击被 generic 400/dedicated 403 拒绝、admin 通过独立 versioned access-control PUT 保存账户；普通 settings payload 无 ACL。OA 凭据与数据重置继续覆盖 admin-only 和 secret 不泄漏；`web/e2e/settings-data-reset-flow.spec.ts` 覆盖 admin data reset 主链路 | 真实 admin/OA 凭据登录有效性由 production evidence 验证。 |
| `app-health-operations` | dashboard/admin runtime read、write-safety blockers、导入历史银行流水批次撤回 | `covered-browser` | `web/e2e/app-shell.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` 覆盖 admin-only route；`web/src/test/AppHealthOperationsPage.test.tsx` 与 `tests/test_app_health_api.py` 覆盖撤回交互和 admin fail-closed | 发布后验证真实撤回事务、审计、账户纠正以及 systemd/RabbitMQ/Redis。 |
| `operation-history` | 无业务写入口；只读筛选、游标翻页和详情 Drawer | `covered-browser` | `web/e2e/app-shell.spec.ts` 覆盖管理员页面/API、非管理员侧栏隐藏与 route gate；组件/API 测试覆盖详情和输入校验 | 发布后验证真实审计事件与数据库 append-only trigger。 |

## 本轮发现并修复的前端 gate

- `oa-pending-payments`：人工 confirm/writeback 已退役；`read_export_only` 下继续禁用关联支出流水并隐藏 OA 选择。
- `batch-accounting`：submit/withdraw 前端未消费 session mutation 权限；已改为 `read_export_only` 下 submit/withdraw disabled，并显示只读提示。
- `turnover-ledger`：标签准入抽屉保存、全选/清空和 flow 选择未完全禁用；已改为 `read_export_only` 下禁用并显示只读提示。

## 仍未完全闭合

`PERM-E2E-003` 仍不能标记为全量 `covered`：新增页面/route 漏登记、非 admin route 漏进 role matrix、covered row 缺 Browser 证据、dynamic opener 与 Playwright/inventory 不一致已由 `tests/test_permissions_write_entry_inventory.py` 自动拦截，read-export 首屏 visible enabled 写控件和当前 role matrix 已打开的关联台列顺序拖拽 settings 保存入口、关联台未配对确认/关系级撤回与旧人工异常入口缺席断言、关联台已配对关系级撤回、关联台现金处理行级菜单、关联台统一异常抽屉审阅/放行/撤回、银行分类确认、银行人工待分类、银行自动标签、成本标签/no-OA/人工分配、pending 规则、收入批量、进项支付规则、进项 OA reverse、销项 canonical 只读区域、OA pending 进行中/规则、ETC 对账流程、batch accounting 选择与已提交撤回、turnover 等动态区域已由 DOM 候选扫描拦截；但尚未由 role matrix 自动打开的页面特定抽屉/弹窗深层爬取尚未完成，真实 OA/代理/生产审计也不能由本地 Browser mock 证明。后续每轮新增按钮时，必须先更新本文件，再补对应 Browser 断言。
