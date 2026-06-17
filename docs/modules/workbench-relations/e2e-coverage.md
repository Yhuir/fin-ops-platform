# 关联台关系事实源 Spec-first E2E Coverage

本文件把 `workbench-relations` 的跨页面 relation Spec 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `WB-REL-E2E-001` | `covered` | `web/e2e/workbench-relation-fanout.spec.ts`、`tests/test_bank_details_service.py`、`tests/test_workbench_relation_read_facade.py` | Browser 已证明 confirm 后银行明细重新读取并显示 linked tags。 |
| `WB-REL-E2E-002` | `covered` | `web/e2e/pending-invoices-fanout.spec.ts`、`tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | Browser 已证明 pending invoice linked-only 状态变化。 |
| `WB-REL-E2E-003` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`tests/test_batch_accounting_api.py` | Browser 已覆盖 submit/withdraw、barrier 和 bucket recovery。 |
| `WB-REL-E2E-004` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`tests/test_turnover_workbench_integration.py` | Browser 已覆盖 turnover confirm/withdraw、barrier 和 grouped recovery。 |
| `WB-REL-E2E-005` | `partial` | `tests/test_workbench_relation_sql_projection.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_input_invoice_usage_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_output_invoice_collection_service.py`、`tests/test_bank_details_service.py`、`tests/test_pending_invoice_service.py` | 后端覆盖 candidate/linked 语义；Browser 只通过银行明细候选 chip 间接覆盖，缺更多下游候选不参与 linked-only 计算的浏览器断言。 |
| `WB-REL-E2E-006` | `partial` | `tests/test_workbench_relation_read_facade.py`、页面 Vitest | 缺 Browser non-fresh relation read model 诊断。 |
| `WB-REL-E2E-007` | `partial` | `tests/test_workbench_relation_command_service.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_idempotency_contract.py` | 后端/API 覆盖强；Browser 未覆盖重复点击/版本冲突。 |
| `WB-REL-E2E-008` | `missing` | 多个后端 service/API tests | 缺 relation 写后到进项/销项/OA pending/cost/tax/search 的 Browser fan-out smoke。 |
| `WB-REL-E2E-009` | `missing` | 后端导出 service tests | 缺真实浏览器 download event 和导出字段断言。 |
| `WB-REL-E2E-010` | `external-risk` | `tests/test_audit_workbench_relation_display_tool.py`、生产/staging runbook | 本地只覆盖工具逻辑；真实 production/staging 只读 audit 不属于 deterministic CI。 |

## 现有 E2E 审计结论

- 当前四条 relation fan-out Browser smoke 都可保留，且应继续纳入 `npm run e2e:smoke`。
- 它们验证的是用户可见业务结果和后端重新读取，不是单纯照代码断言。
- 主要缺口是：candidate/linked 负面语义、non-fresh 诊断、重复提交/冲突、更多下游页面、真实下载和生产 display audit。

## 下一轮补测建议

1. 为候选关系状态补 Browser 场景：至少覆盖银行明细候选 chip 和待找发票/OA 待付款 linked-only 计算不受 candidate 影响。
2. 为 relation read model non-fresh 补 Browser 场景：页面必须显示诊断，不把空结果当真实空。
3. 为导出补 Browser download 场景：银行明细或 pending invoice 导出包含 relation 字段，权限正确。
4. 把生产/staging display audit 保持为 `external-risk`，不要写成本地 CI 通过项。

