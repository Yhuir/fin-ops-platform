# 进项发票使用情况 Spec-first E2E Coverage

本文件把 `input-invoice-usage` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

> 2026-07-11 合同纠正：进项 relation confirm 继续影响本页、OA pending 与 cost consumer；不再声称或 mock relation→tax-offset fan-out。税金页面只消费 canonical invoices/certified facts。

> 2026-07-22 Phase 27：上述“影响”表示 consumer 在访问时从 canonical source/version 发现变化，不表示 writer 投递。所有普通 relation/rule/OA reverse 写均为零页面 fan-out；当前页 normal GET、其它页访问/重新激活时分别收敛。

> 2026-07-27：本页 rows/detail/export 已改为 canonical PostgreSQL 直读；旧 read-model refreshing/worker 证据只保留历史价值，不再是本页验收合同。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `IN-USAGE-E2E-001` | `covered` | `web/e2e/input-invoice-usage-flow.spec.ts`、`web/e2e/input-invoice-relation-fanout.spec.ts`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`tests/test_input_invoice_usage_api.py` | Browser 覆盖 canonical rows 首屏、发票/支付状态/OA/流水列、首屏 `page_size=20`、rows 内 filter options、销方筛选 URL contract、开票日期排序、page-size 切换和可见行同步；也覆盖 rows 暂时 503 时错误 alert、错误态空行、普通空态消失、导出禁用和点击刷新后 rows/pagination/export 恢复。Vitest/API 覆盖搜索、筛选、排序、分页和 response shape。 |
| `IN-USAGE-E2E-002` | `covered` | `web/e2e/input-invoice-relation-fanout.spec.ts`、`tests/test_input_invoice_usage_service.py`、`tests/test_workbench_relation_read_facade.py` | Browser 已证明未正式化自动匹配不驱动已支付，Workbench confirm 后重新进入页面显示 linked 证据和 `已支付`。 |
| `IN-USAGE-E2E-003` | `covered` | `web/e2e/input-invoice-relation-fanout.spec.ts`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py` | Browser/Vitest 已证明 linked 发票在 OA reverse 预览中显示 `已关联oa` 且不可勾选；旧 candidate 兼容数据归入 `未关联oa`，不显示独立候选 OA 筛选，搜索可正常过滤候选发票清单。 |
| `IN-USAGE-E2E-004` | `covered` | `web/e2e/input-invoice-usage-flow.spec.ts`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py` | Browser 已覆盖候选子集重新 preview、创建 OA 草稿、确认已提交、manual status、submitted history 不暴露内部 batch id，并在成功节点检查没有操作/保存/同步错误残留；这些本地 batch 状态动作不触发 rows 请求，evidence relation 写成功后重跑当前 canonical GET。 |
| `IN-USAGE-E2E-005` | `covered` | `tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`web/e2e/input-invoice-usage-flow.spec.ts` | API/Vitest 固定 rows/detail 只返回 canonical `200` 或结构化错误且无旧状态字段；Browser 覆盖 rows 暂时 503 时错误态不伪空态、导出禁用、无自动 polling，并由用户刷新恢复 rows。 |
| `IN-USAGE-E2E-006` | `covered` | `tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/e2e/input-invoice-usage-flow.spec.ts` | 单元/API/Vitest 覆盖 active component 多关系和 `+N`；Browser 覆盖点击 `+N` 后从 canonical detail endpoint 展开两条 OA 摘要、断言 `200`、零 mutation。 |
| `IN-USAGE-E2E-007` | `covered` | `web/e2e/input-invoice-usage-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`tests/test_input_invoice_usage_api.py` | Browser 覆盖 `read_export_only` 用户可读列表/导出、支付规则 drawer 只读且无保存控件、OA reverse preview 只返回不可创建草稿、创建草稿/批次/manual status/payment rules save 等 durable write endpoint 零调用；role matrix/API/Vitest 覆盖页面读取、权限字段和只读 drawer mapper。 |
| `IN-USAGE-E2E-008` | `covered` | `tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/e2e/input-invoice-usage-flow.spec.ts` | Browser 覆盖当前筛选导出预览、真实 download event、导出请求不带分页、relation/OA/payment 字段和 row-limit 错误零下载；页面不等待 read model。 |
| `IN-USAGE-E2E-009` | `covered` | `web/e2e/input-invoice-relation-fanout.spec.ts`、`web/e2e/input-invoice-usage-flow.spec.ts`、`web/e2e/tax-offset-flow.spec.ts`、`tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_payment_rules.py`、相关下游 API/Vitest 测试 | Browser 已覆盖未正式化自动匹配不驱动已支付、Workbench confirm 后进项页 canonical GET 展示 active linked 事实，以及支付规则保存后当前 GET 展示新规则；其它 consumer 保持自己的读取边界，税金页面只消费 canonical invoices/certified facts。 |

## Operation latency baseline

本轮已为 `web/e2e/input-invoice-usage-flow.spec.ts` 和历史命名的 `web/e2e/input-invoice-relation-fanout.spec.ts` 接入 Playwright latency 附件。当前记录页面打开、读失败恢复、筛选/排序/分页、导出、规则/OA reverse Drawer、canonical GET 刷新和 Workbench confirm 后逐页访问消费者等操作。

## 下一轮补测建议

1. 本模块本地 Spec-first ID 已覆盖；本页真实 PostgreSQL EXPLAIN/锁等待和大文件下载保留到 staging/runtime gate。worker drain 只适用于仍使用 read model 的下游 consumer。
2. 如后续新增 OA reverse 撤销/刷新外部状态入口、全局 search UI 或支付规则下游 UI 入口，再补对应 Browser 权限和 access-convergence 组合。
