# 进项发票使用情况 Spec-first E2E Coverage

本文件把 `input-invoice-usage` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `IN-USAGE-E2E-001` | `partial` | `web/e2e/input-invoice-usage-flow.spec.ts`、`web/e2e/input-invoice-relation-fanout.spec.ts`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`tests/test_input_invoice_usage_api.py` | Browser 覆盖首屏 rows；筛选/排序/page-size 主要由 Vitest/API 覆盖，缺更多真实浏览器筛选排序组合。 |
| `IN-USAGE-E2E-002` | `covered` | `web/e2e/input-invoice-relation-fanout.spec.ts`、`tests/test_input_invoice_usage_service.py`、`tests/test_workbench_relation_read_facade.py` | Browser 已证明 candidate OA/流水证据显示但支付状态保持 `待处理`，Workbench confirm 后重新进入页面显示 linked 证据和 `已支付`。 |
| `IN-USAGE-E2E-003` | `covered` | `web/e2e/input-invoice-relation-fanout.spec.ts`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py` | Browser 已证明 candidate/linked 发票在 OA reverse 预览中分别显示 `候选oa`/`已关联oa`，且不可勾选、不触发创建草稿 API。 |
| `IN-USAGE-E2E-004` | `covered` | `web/e2e/input-invoice-usage-flow.spec.ts`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py` | Browser 已覆盖候选子集重新 preview、创建 OA 草稿、确认已提交和 submitted history 不暴露内部 batch id；Vitest/API/service 覆盖关闭确认弹窗后暂存恢复且暂存列表不展示 OA 草稿链接。 |
| `IN-USAGE-E2E-005` | `partial` | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx` | API/Vitest 覆盖 refreshing/stale 和 relation detail 单行 read model lookup；缺 Browser negative 场景。 |
| `IN-USAGE-E2E-006` | `partial` | `tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx` | 单元/API/Vitest 覆盖多关系和 `+N`；缺 Browser 点击 `+N` 展开全明细。 |
| `IN-USAGE-E2E-007` | `partial` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`tests/test_input_invoice_usage_api.py` | 全页面 role matrix 覆盖高风险入口；缺本页每按钮 Browser 零 mutation 断言。 |
| `IN-USAGE-E2E-008` | `missing` | `tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx` | 缺真实浏览器 download event 和导出字段断言。 |
| `IN-USAGE-E2E-009` | `missing` | 相关下游 API/Vitest 测试 | 缺 relation/支付规则/OA reverse/认证状态变化后到 tax/cost/OA pending/search 的 Browser fan-out。 |

## 下一轮补测建议

1. 为 `IN-USAGE-E2E-005` 补 Browser refreshing/stale/false-empty 负面场景。
2. 为 `IN-USAGE-E2E-006` 补真实浏览器 `+N` relation detail 展开。
3. 为 `IN-USAGE-E2E-008` 补真实下载事件。
4. 为 `IN-USAGE-E2E-009` 补 tax/cost/OA pending/search downstream fan-out。
