# Workbench 正式关系 E2E 覆盖

日期：2026-07-14

| Spec | 状态 | 证据 |
| --- | --- | --- |
| `WB-REL-E2E-001` | covered | `web/e2e/workbench-relation-fanout.spec.ts`：confirm 后 bank details linked tags |
| `WB-REL-E2E-002` | covered | `web/e2e/pending-invoices-fanout.spec.ts`：confirm 后 pending invoices linked status |
| `WB-REL-E2E-003` | covered | `web/e2e/batch-accounting-flow.spec.ts`：submit/withdraw 与 relation barrier |
| `WB-REL-E2E-004` | covered | `web/e2e/turnover-ledger-flow.spec.ts`：closure/withdraw 与 grouped recovery |
| `WB-REL-E2E-005` | API/service covered | `tests/test_bank_details_service.py`、`tests/test_pending_invoice_service.py`、`tests/test_input_invoice_usage_oa_reverse_service.py`：非正式输入不驱动 linked-only 状态 |
| `WB-REL-E2E-006` | covered | `web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts` |
| `WB-REL-E2E-007` | covered | `web/e2e/workbench-network-recovery-flow.spec.ts`：幂等与冲突保护 |
| `WB-REL-E2E-008` | covered | `web/e2e/workbench-relations-oa-pending-fanout.spec.ts`、`output-invoice-red-relation-fanout.spec.ts`、`input-invoice-relation-fanout.spec.ts`、`cost-statistics-relation-fanout.spec.ts`、`workbench-relations-tax-offset-isolation.spec.ts` |
| `WB-REL-E2E-009` | covered | `web/e2e/bank-details-export-download.spec.ts`、`pending-invoices-export-download.spec.ts` |
| `WB-REL-E2E-010` | production audit covered | `tests/test_audit_workbench_relation_display_tool.py`、`scripts/audit-workbench-relation-display.sh` |

旧 Browser candidate mock 不是当前业务状态，不再作为正式关系 E2E 事实源。生产发布以 canonical counts、fresh read models、520 fixed case 和页面 Audit 为最终数据证据。
