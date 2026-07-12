# 关联台关系事实源 Spec-first E2E Coverage

本文件把 `workbench-relations` 的跨页面 relation Spec 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `WB-REL-E2E-001` | `covered` | `web/e2e/workbench-relation-fanout.spec.ts`、`tests/test_bank_details_service.py`、`tests/test_workbench_relation_read_facade.py` | Browser 已证明 confirm 后银行明细重新读取并显示 linked tags。 |
| `WB-REL-E2E-002` | `covered` | `web/e2e/pending-invoices-fanout.spec.ts`、`tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | Browser 已证明 pending invoice linked-only 状态变化。 |
| `WB-REL-E2E-003` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`tests/test_batch_accounting_api.py` | Browser 已覆盖 submit/withdraw、barrier 和 bucket recovery。 |
| `WB-REL-E2E-004` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`tests/test_turnover_workbench_integration.py` | Browser 已覆盖 turnover confirm/withdraw、barrier 和 grouped recovery。 |
| `WB-REL-E2E-005` | `covered` | `web/e2e/workbench-relations-candidate-semantics.spec.ts`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_input_invoice_usage_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_output_invoice_collection_service.py`、`tests/test_bank_details_service.py`、`tests/test_pending_invoice_service.py` | Browser/API 回归证明未正式化自动决策不会被推成 linked-only 状态；pending invoice、OA payment、成本等业务状态只按 active linked relation 计算。 |
| `WB-REL-E2E-006` | `covered` | `web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`、`tests/test_workbench_relation_read_facade.py`、页面 Vitest | Browser 已证明 relation-backed pending invoice read model `refreshing` 时页面显示诊断、保留行检查和 canonical-safe 的选择发票入口；`stale` 且 rows 为空时仍显示读模型诊断并禁用导出，不把空结果当无上下文真实空。 |
| `WB-REL-E2E-007` | `covered` | `web/e2e/workbench-withdraw-flow.spec.ts`、`web/e2e/workbench-network-recovery-flow.spec.ts`、`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_idempotency_contract.py` | Browser 已覆盖 withdraw 正向 preview lock、submit payload 和 fresh refetch，也覆盖 confirm/withdraw 双击只产生一次 mutation、409 stale preview 不复用旧 expected_versions；后端/API 覆盖 idempotency、版本冲突，以及无 active relation 时不把 automatic decision 当作可撤回 relation。 |
| `WB-REL-E2E-008` | `covered` | `web/e2e/workbench-relation-fanout.spec.ts`、`web/e2e/pending-invoices-fanout.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/e2e/input-invoice-relation-fanout.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/workbench-relations-oa-pending-fanout.spec.ts`、`web/e2e/workbench-relations-tax-offset-isolation.spec.ts`、`tests/test_workbench_relation_repository.py`、`tests/test_search_pending_sql_runtime.py` | Relation 消费页面证明 confirmed relation 的用户可见 fan-out；税金抵扣是明确非消费者，Browser 证明 relation 前后税金 item 不变，repository 证明不产生 `tax_offset` dirty/outbox。 |
| `WB-REL-E2E-009` | `covered` | `web/e2e/bank-details-export-download.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/e2e/pending-invoices-export-download.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/e2e/input-invoice-usage-flow.spec.ts`、后端导出 service tests | Browser 已证明银行明细在 Workbench confirm 后可触发真实 download event，且文件名、当前默认筛选和 linked relation 字段一致；也已证明账户/自定义日期/关键字/分类筛选会带入导出、分页状态不会限制导出范围、`read_export_only` 可下载且银行明细写入口禁用并零 mutation。待找发票 Browser 已证明 Workbench confirm 后 export-preview/export 带当前筛选和排序、不带分页，并下载包含 OA 申请人、进项发票号、relation case 和 linked 状态。银行明细和待找发票下载成功节点都会检查没有导出失败、同步失败或 read model 失败残留。销项收款 Browser 已证明红蓝票人工关系确认后 export-preview 和真实 download event 均包含 `红蓝票关系`、`红蓝票来源`、`红蓝票依据`、红字发票号、`manual` 和确认依据。进项发票使用 Browser 已证明当前筛选导出不带分页，真实 download event 内容包含 OA 申请人、relation case 和 payment 字段。真实 XLSX 完整解析仍归 export service/后续真实文件 smoke，不作为本地 Browser covered 前提。 |
| `WB-REL-E2E-010` | `external-risk` | `tests/test_audit_workbench_relation_display_tool.py`、生产/staging runbook | 本地只覆盖工具逻辑；真实 production/staging 只读 audit 不属于 deterministic CI。 |
| `WB-REL-E2E-011` | `covered` | `tests/test_write_operation_e2e_smoke.py`、`tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_impact_matrix.py`、`tests/test_reversible_relation_closure_postgres.py`、`web/e2e/workbench-withdraw-flow.spec.ts` | 三组 profile pair 共用一个 checkpoint runner，但 mutation contract 保持真实边界：bank+invoice/full 走 Workbench，bank+turnover 走 turnover closure。confirm/withdraw 分别绑定精确 durable event IDs、affected fixture identity、non-consumer before/after equality 和新 System Audit；首次写前另有 admin preflight。withdraw Browser 代表性验证银行明细、待找发票、进项使用、OA 待付款、成本统计恢复，税金抵扣另由 isolation spec 保持不变。 |

## 现有 E2E 审计结论

- 当前 relation fan-out / mutation Browser smoke、真实下载 smoke、candidate/linked 负面语义 smoke、non-fresh 诊断 smoke 和 Workbench display audit 都应继续纳入验证；其中 automatic decision/candidate 负向覆盖保护的是“未正式化建议不驱动 linked-only 状态，也不显示成同一行 linked group”。Workbench relation fan-out 下游成功节点还必须保留 UI 错误残留 guard，防止成功刷新后仍出现操作失败、同步失败或 read model 失败提示。
- 它们验证的是用户可见业务结果和后端重新读取，不是单纯照代码断言。
- 本地 deterministic 主要 Spec ID 已覆盖。剩余风险是生产/staging display audit、真实历史半迁移、大数据 worker drain、未来 Browser 外层 search 入口和真实 XLSX 完整解析；这些不应被标成本地 CI covered。

## 下一轮补测建议

1. 本模块本地 Spec IDs 已覆盖；后续新增 Browser 外层 search 入口、更多撤销业务入口或新 relation 字段导出页面时，再补对应 Spec-first E2E。
2. 真实 XLSX 完整解析、真实大数据下载性能和代理层真实权限仍归 export service 测试、staging smoke 或发布前手动 gate。
3. 把生产/staging display audit 保持为 `external-risk`，不要写成本地 CI 通过项。
