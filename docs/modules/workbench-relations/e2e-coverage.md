# 关联台关系事实源 Spec-first E2E Coverage

本文件把 `workbench-relations` 的跨页面 relation Spec 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `WB-REL-E2E-001` | `covered` | `web/e2e/workbench-relation-fanout.spec.ts`、`tests/test_bank_details_service.py`、`tests/test_workbench_relation_read_facade.py` | Browser 已证明 confirm 后银行明细重新读取并显示 linked tags。 |
| `WB-REL-E2E-002` | `covered` | `web/e2e/pending-invoices-fanout.spec.ts`、`tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | Browser 已证明 pending invoice linked-only 状态变化。 |
| `WB-REL-E2E-003` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`tests/test_batch_accounting_api.py` | Browser 已覆盖 submit/withdraw、barrier 和 bucket recovery。 |
| `WB-REL-E2E-004` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`tests/test_turnover_workbench_integration.py` | Browser 已覆盖 turnover confirm/withdraw、barrier 和 grouped recovery。 |
| `WB-REL-E2E-005` | `covered` | `web/e2e/workbench-relations-candidate-semantics.spec.ts`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_input_invoice_usage_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_output_invoice_collection_service.py`、`tests/test_bank_details_service.py`、`tests/test_pending_invoice_service.py` | Browser 已证明 candidate 可以在银行明细、待找发票和 OA 待付款显示为证据/chip，但 pending invoice 状态仍为 `已支付待开票`、OA payment 状态仍为 `支付少了`，不会被 candidate 推成 linked-only 状态。 |
| `WB-REL-E2E-006` | `covered` | `web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`、`tests/test_workbench_relation_read_facade.py`、页面 Vitest | Browser 已证明 relation-backed pending invoice read model `refreshing` 时页面显示诊断、保留行检查和 canonical-safe 的选择发票入口；`stale` 且 rows 为空时仍显示读模型诊断并禁用导出，不把空结果当无上下文真实空。 |
| `WB-REL-E2E-007` | `covered` | `web/e2e/workbench-withdraw-flow.spec.ts`、`web/e2e/workbench-network-recovery-flow.spec.ts`、`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_idempotency_contract.py` | Browser 已覆盖 withdraw 正向 preview lock、submit payload 和 fresh refetch，也覆盖 confirm/split_candidate/withdraw 双击只产生一次 mutation、409 stale preview 不复用旧 expected_versions；后端/API 覆盖 idempotency 与版本冲突。 |
| `WB-REL-E2E-008` | `partial` | `web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/e2e/input-invoice-relation-fanout.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、多个后端 service/API tests | Browser 已证明销项收款红蓝票 relation 写入后 rows refresh 并展示人工依据，进项发票使用页面中 candidate 只作证据、Workbench confirm 后 linked 证据驱动 `已支付`，并证明成本统计 open candidate 不计入金额、confirmed 成本关系才进入项目/流水详情；仍缺税金、搜索等更多下游页面 fan-out。 |
| `WB-REL-E2E-009` | `partial` | `web/e2e/bank-details-export-download.spec.ts`、后端导出 service tests | Browser 已证明银行明细在 Workbench confirm 后可触发真实 download event，且文件名、当前默认筛选和 linked relation 字段一致；仍缺 `read_export_only` 导出权限和更多页面/筛选组合。 |
| `WB-REL-E2E-010` | `external-risk` | `tests/test_audit_workbench_relation_display_tool.py`、生产/staging runbook | 本地只覆盖工具逻辑；真实 production/staging 只读 audit 不属于 deterministic CI。 |

## 现有 E2E 审计结论

- 当前 relation fan-out / mutation Browser smoke、真实下载 smoke、candidate/linked 负面语义 smoke、non-fresh 诊断 smoke 以及 automatic candidate split smoke 都可保留，且应继续纳入 `npm run e2e:smoke`；其中 `split_candidate` 保护的是“不要把自动候选误当 active relation withdraw”，不计为 relation lifecycle 写入。
- 它们验证的是用户可见业务结果和后端重新读取，不是单纯照代码断言。
- 主要缺口是：更多下游页面、导出权限/筛选组合和生产 display audit。重复提交/409 stale preview、candidate/linked 负面语义、non-fresh 诊断、销项红蓝票 relation overlay、进项发票使用 fan-out、成本统计 candidate/confirmed fan-out，以及银行明细 relation 字段真实下载已由 Browser smoke 覆盖。

## 下一轮补测建议

1. 为更多下游页面补 Browser fan-out smoke：税金、搜索等至少覆盖一条 relation 写后最终显示；进项使用、销项收款和成本统计已各覆盖一条，仍可后续补撤销和更多 tax/search fan-out。
2. 为导出继续补 Browser download 场景：银行明细账户/关键字/分类筛选、`read_export_only` 权限，以及 pending invoice 等其他 relation 字段导出。
3. 把生产/staging display audit 保持为 `external-risk`，不要写成本地 CI 通过项。
