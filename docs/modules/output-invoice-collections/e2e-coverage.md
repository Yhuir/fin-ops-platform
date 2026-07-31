# 销项发票收款情况 Spec-first E2E Coverage

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 |
| --- | --- | --- |
| `OUT-COLL-E2E-001` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`tests/test_output_invoice_collection_api.py` |
| `OUT-COLL-E2E-002` | `covered` | `web/e2e/output-invoice-red-relation-fanout.spec.ts`、`tests/test_workbench_free_matching_engine.py`、`tests/test_output_invoice_collection_service.py` |
| `OUT-COLL-E2E-003` | `covered` | `tests/test_workbench_free_matching_engine.py`、`tests/test_output_invoice_collection_service.py` |
| `OUT-COLL-E2E-004` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx` |
| `OUT-COLL-E2E-005` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/output-invoice-collections-flow.spec.ts`、`tests/test_platform_runtime_boundary_guards.py` |
| `OUT-COLL-E2E-006` | `covered` | `web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`tests/test_output_invoice_collection_api.py` |
| `OUT-COLL-E2E-007` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`tests/test_output_invoice_collection_api.py` |

## 发布验证

本地覆盖证明 deterministic 合同；release gate 和生产 smoke 继续验证真实 PostgreSQL、正式关系、页面 canonical audit、关键 GET 性能及 T+0/T+60/T+300 稳定性。
