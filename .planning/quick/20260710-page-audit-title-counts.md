# 2026-07-10 页面 Audit 与标题统计闭环

## 目标

- 借鉴 `进项发票使用情况` 的 source version mismatch，检查其它页面是否存在同类 read model / relation source version 污染。
- 在发票使用类页面标题右侧显示稳定全量票数，不随表格筛选改变。
- 将页面 Audit 改为 icon-only 入口，点击后显示 Audit 是否通过、全部数据/配对关系是否正确以及 Fresh 状态。

## Grillme 结论

1. 目标事实源是什么？
   - 进项：`app.invoices`、`read_model.input_invoice_usage_*`、`read_model.workbench_relation_*`、`app.workbench_pair_relations`、`job.read_model_dirty_scopes`。
   - 销项：`app.invoices`、`read_model.output_invoice_collection_*`、`read_model.workbench_relation_*`、`app.workbench_pair_relations`、`job.read_model_dirty_scopes`。
2. 同类 bug 是否存在？
   - 存在于 `output_invoice_collection` expected source versions：它曾经从 output read model 窄端口读取 workbench relation source versions，和进项 bug 同型。
   - 已修复为使用 `_workbench_relation_sql_read_repository`，并补回归测试。
3. 其它页面是否同型？
   - `oa_pending_payment` 已有测试保护，source versions 使用 workbench relation repository。
   - `pending_invoice` 使用独立 pending invoice relation source provider。
   - `bank_detail`、`cost_statistics`、`tax_offset`、`turnover_ledger` 的 freshness/source version 入口不同，未发现同一 narrow-port 取错 relation source version 的结构。
4. 页面 Audit 是否应该全站泛化？
   - 当前只给 `input_invoice_usage` 和 `output_invoice_collection` 做生产级 Audit。它们都有完整 read model + Workbench relation 三边对账事实源。
   - 其它页面若要展示同等级 Audit，需要先定义各自 canonical facts 和 relation/read model invariant，不能复用进销票审计硬套。

## 实施决策

- 新增只读 `GET /api/operations/app-health/output-invoice-collection-audit`。
- 前端复用 `PageScaffold.titleAccessory` 与 `PageAuditIcon`，不给每个页面复制状态逻辑。
- 标题统计只在未筛选的 rows 请求返回时更新；keyword/filter/month 改变后不覆盖标题全量票数。
- AppHealth 既有进项 Audit 按钮改为 icon-only，和页面标题 Audit 入口保持一致。

## 验收

- 后端回归证明进/销 expected source versions 都来自 workbench relation repository。
- 销项 audit 工具只读对账 canonical 销项发票、output read model 和 workbench relation projection。
- 前端 Vitest 覆盖进/销标题总数不随搜索变化，以及 admin 点击 Audit icon 后展示数据、配对关系和 Fresh 状态。

## 未纳入

- 未给 bank detail、pending invoice、tax offset、cost statistics 等页面新增通用 Audit icon，因为缺少同等级 audit invariant 合同。
- 未执行真实生产库销项 audit；部署后需用 Admin Token 调用 output audit API，以 `overall_status=pass` 且 `blocking_issue_count=0` 作为生产证据。
