# 销项发票收款情况 Spec-first E2E Coverage

本文件把 `output-invoice-collections` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `OUT-COLL-E2E-001` | `partial` | `web/e2e/output-invoice-collections-flow.spec.ts`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`tests/test_output_invoice_collection_api.py` | Browser 覆盖首屏表格；筛选/排序/page-size 主要由 Vitest/API 覆盖，缺更多真实浏览器筛选排序组合。 |
| `OUT-COLL-E2E-002` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`tests/test_output_invoice_collection_lifecycle.py` | Browser 已证明状态/提醒保存后 rows refresh 并显示 `待冲红`。 |
| `OUT-COLL-E2E-003` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`tests/test_output_invoice_collection_lifecycle.py`、`tests/test_output_invoice_collection_api.py` | Browser 已证明 receipt preview/create/history，后端覆盖幂等和真实 history。 |
| `OUT-COLL-E2E-004` | `covered` | `web/e2e/output-invoice-red-relation-fanout.spec.ts`、`tests/test_output_invoice_collection_lifecycle.py`、`tests/test_output_invoice_collection_api.py` | Browser 已证明红蓝票关系确认后 rows refresh，并在重新打开 drawer 时展示人工依据、source 和 evidence。撤销路径仍由 API/service 覆盖，缺 Browser 撤销。 |
| `OUT-COLL-E2E-005` | `partial` | `tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx` | API/Vitest 覆盖 refreshing/stale，不把 stale rows 当 fresh；缺 Browser negative 场景。 |
| `OUT-COLL-E2E-006` | `partial` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`tests/test_output_invoice_collection_api.py` | 全页面 role matrix 覆盖高风险入口，缺本页每个按钮的 Browser 零 mutation 断言。 |
| `OUT-COLL-E2E-007` | `missing` | `tests/test_output_invoice_collection_api.py` | 缺真实浏览器 download event 和导出字段断言。 |
| `OUT-COLL-E2E-008` | `missing` | `tests/test_invoice_lifecycle_page_integration.py`、`web/src/test/TaxOffsetPage.test.tsx` | 缺红蓝票/收款/receipt 写后到 tax/cost/search 的 Browser fan-out。 |

## 下一轮补测建议

1. 为 `OUT-COLL-E2E-005` 补 Browser refreshing/stale 负面场景。
2. 为 `OUT-COLL-E2E-004` 补撤销人工红蓝票关系的 Browser recovery。
3. 为 `OUT-COLL-E2E-007` 补真实下载事件。
4. 为 `OUT-COLL-E2E-008` 补 tax/cost/search downstream fan-out。
