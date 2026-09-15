# 右侧抽屉关闭行为

2026-09-15。所有右侧弹出抽屉统一由 X 发起主动关闭；遮罩点击、触摸及 Esc 不关闭。关闭仍执行业务 owner 的未保存确认、提交保护和资源清理。内部菜单、确认框、页面跳转及权限失效按各自生命周期处理。税金抵扣的已认证结果是内嵌折叠区，左侧导航和居中弹窗不属于本规则。

## 边界与完成状态

- `AppDrawer` 只消费 `open/onClose/closeDisabled` 和展示内容。新增可选 `completion: ReactNode`，用于展示调用方确认的完成结果，替换旧表单、头部动作和底部提交按钮；不发请求、不推断成功、不自动关开抽屉。
- 各业务 owner 持有完成状态。一次性录入/导入/归属/闭环完成后移除旧提交入口；可连续编辑的设置使用最新返回版本继续编辑。请求失败保留错误及已有恢复路径。
- 手工录入 editor 输出 `onBusyChange`，父抽屉据此禁用 X，避免预览/提交中卸载。移除旧的整层取消回调和按钮。
- 非模态反提 OA 保留背景操作；其他工作流入口在当前工作流未退出前禁用，同一反提 OA 入口重复点击不重置状态。
- 现金结算 editor 的内部取消仍可结束局部编辑；直接作为抽屉正文时不传局部关闭回调。现金事项创建后需要跳转详情的通知延后到 X 关闭，避免保存自动替换父层。
- 现金详情编辑与个人专账录入在进入表单时保存本次编辑上下文，后台查询刷新不会重建表单或丢失完成结果；关闭后释放，不作为查询结果缓存。
- 完成状态不跨 route/session 持久化；后端 API、权限、金额、版本、事务、worker 与 canonical 查询合同不变。

## 验证

新增 `web/src/test/ManualBankTransactionEntryDrawer.test.tsx` 验证预览清理失败保留草稿、X 显式重试及 busy 保护；现金测试覆盖刷新不重挂编辑器。新增 `web/src/test/AppDrawer.test.tsx` 验证外部点击/Esc、键盘 X、关闭保护、完成后不可重复提交、父子层及非模态背景操作。受影响页面测试同步验证保存后保留、失败后重试及原查询次数。`web/e2e/drawer-motion.spec.ts` 使用真实鼠标检查遮罩与跨边界释放，并保留动画测量。现金新增/删除、OA 关联、待找发票归属、往来标签/闭环用既有浏览器用例验证完整流程。

七类测试：前端交互、端到端受影响业务流、既有回归适用；不修改业务核心规则、Service、API 合同、read model/cache/worker，不新增这些层的测试。生产验证只操作可逆 UI，实际财务写入在合成测试中完成。

## 抽屉清单

按业务模板计数，新增/编辑或不同详情种类不重复计数；共用包装层不计入。55 个模板如下。此清单用于维护定位，不是冻结清单或发布门禁。

| 文件 | 抽屉标题/模式 |
| --- | --- |
| `web/src/components/batchAccounting/BatchAccountingTagRulesDrawer.tsx` | "批量账务标签规则" |
| `web/src/components/cash/CashBooks.tsx` | {drill.month + " 实际发生本金"} |
| `web/src/components/cash/CashBooks.tsx` | {settlementLabels[editing.kind]} |
| `web/src/components/cash/CashBooks.tsx` | "个人专账录入" |
| `web/src/components/cash/CashBooks.tsx` | "事项管理" |
| `web/src/components/cash/CashFlowDrawer.tsx` | {flow ? "编辑现金流水" : task ? `办理任务 · ${task.title}` : "新增现金流水"} |
| `web/src/components/cash/CashFlowDrawer.tsx` | {mode === "delete" ? "删除现金流水" : "现金流水详情"} |
| `web/src/components/cash/CashFlowTable.tsx` | "账户期间余额" |
| `web/src/components/cash/CashItems.tsx` | {item ? "更正事项" : "新建事项"} |
| `web/src/components/cash/CashItems.tsx` | "事项详情" |
| `web/src/components/cash/CashSettings.tsx` | {account ? "编辑现金账户" : "新增现金账户"} |
| `web/src/components/cash/CashSettings.tsx` | {category ? "编辑费用类型" : "新增费用类型"} |
| `web/src/components/cash/CashSettings.tsx` | "账单分组" |
| `web/src/components/cash/CashSettings.tsx` | "设置个人账起算" |
| `web/src/components/cash/CashSettings.tsx` | {row ? "编辑账单分组" : "新增账单分组"} |
| `web/src/components/cash/CashSettings.tsx` | {detail.category} |
| `web/src/components/cash/CashTasks.tsx` | {title} |
| `web/src/components/cash/CashTasks.tsx` | "关联已录现金" |
| `web/src/components/cash/CashTasks.tsx` | "月任务处理明细" |
| `web/src/components/cash/CashTasks.tsx` | {template ? "编辑每月任务" : "新增每月任务"} |
| `web/src/components/common/OaDraftPrefillDrawer.tsx` | "OA 草稿预填管理" |
| `web/src/components/cost-statistics/CostEntryDetailDrawer.tsx` | {title} |
| `web/src/components/cost-statistics/CostStatisticsManualAllocationDrawer.tsx` | "成本人工分配" |
| `web/src/components/cost-statistics/CostStatisticsNoOaRulesDrawer.tsx` | "无 OA 成本范围" |
| `web/src/components/cost-statistics/CostStatisticsProjectCostScopeDrawer.tsx` | "项目成本范围" |
| `web/src/components/imports/ImportWorkflowPage.tsx` | "未处理明细" |
| `web/src/components/imports/ManualBankTransactionEntryDrawer.tsx` | "流水录入" |
| `web/src/components/imports/ManualInvoiceEntryDrawer.tsx` | "发票录入" |
| `web/src/components/imports/SupportingDocumentGalleryDrawer.tsx` | {title} |
| `web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx` | {title} |
| `web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx` | "筛选内容导出" |
| `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx` | "以发票反提 OA" |
| `web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx` | "发票与支付状态规则设置" |
| `web/src/components/oaPendingPayments/OaPendingPaymentExportDrawer.tsx` | "导出 OA 事实源" |
| `web/src/components/operations/OperationHistoryDetailDrawer.tsx` | "操作详情" |
| `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx` | {title} |
| `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionExportDrawer.tsx` | "筛选内容导出" |
| `web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx` | {title} |
| `web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx` | "导出预览" |
| `web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx` | "选择已有进项发票" |
| `web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx` | {drawerTitles[detailKind]} |
| `web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx` | {title} |
| `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx` | "编辑流水补充信息" |
| `web/src/components/workbench/DetailDrawer.tsx` | {title} |
| `web/src/components/workbench/WorkbenchExceptionDrawer.tsx` | "异常处理" |
| `web/src/components/workbench/WorkbenchInvoiceAssignmentDrawer.tsx` | "选择 OA 明细" |
| `web/src/components/workbench/WorkbenchInvoiceEntryDrawer.tsx` | {mode === "upload" ? "管理凭证" : "录入发票"} |
| `web/src/components/workbench/WorkbenchReceiptDrawer.tsx` | "编辑收据" |
| `web/src/features/bankDetails/AutoTagRulesDrawer.tsx` | "自动标签规则" |
| `web/src/pages/AppHealthOperationsPage.tsx` | "导入历史" |
| `web/src/pages/BankFlowRuleBatchPage.tsx` | "流水规则标签管理" |
| `web/src/pages/OaPendingPaymentsPage.tsx` | "关联支出流水" |
| `web/src/pages/ReconciliationWorkbenchPage.tsx` | {operationCopy.title} |
| `web/src/pages/TurnoverLedgerPage.tsx` | "外部往来款标签设置" |
| `web/src/pages/TurnoverLedgerPage.tsx` | "确认外部往来闭环" |
