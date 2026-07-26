# 税金抵扣 E2E 覆盖

| Spec ID | 状态 | 自动化证据 |
| --- | --- | --- |
| `TAX-E2E-001` | covered | `tests/test_tax_offset_canonical_repository.py`、`tests/test_tax_offset_api.py`、`web/src/test/TaxApi.test.ts`、`web/e2e/tax-offset-flow.spec.ts` |
| `TAX-E2E-002` | covered | `tests/test_tax_offset_service.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts` |
| `TAX-E2E-003` | covered | `tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts` |
| `TAX-E2E-004` | covered | `tests/test_tax_certified_import_service.py`、`tests/test_import_job_queue.py`、Tax Vitest/Playwright |
| `TAX-E2E-005` | covered | `tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx`；负向 guard 证明 legacy polling 不再发生 |
| `TAX-E2E-006` | covered | `web/e2e/workbench-relations-tax-offset-isolation.spec.ts`、`tests/test_workbench_relation_repository.py` |
| `TAX-E2E-007` | covered | `tests/test_tax_offset_api.py`、`web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/tax-offset-flow.spec.ts` |
| `TAX-E2E-008` | covered | Tax Vitest/Playwright 大表测试 |

真实生产 PostgreSQL 最大月数据耗时和生产发布验证由主控在合并后执行；本分支不部署。
