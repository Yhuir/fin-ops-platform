# 关联台关系事实源 Spec-first E2E Coverage

本文件把 `workbench-relations` 的跨页面 relation Spec 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `WB-REL-E2E-001` | `covered` | `web/e2e/workbench-relation-fanout.spec.ts`、`tests/test_bank_details_service.py`、`tests/test_workbench_relation_read_facade.py` | Browser 已证明 confirm 后银行明细重新读取并显示 linked tags。 |
| `WB-REL-E2E-002` | `covered` | `web/e2e/pending-invoices-fanout.spec.ts`、`tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | Browser 已证明 pending invoice linked-only 状态变化。 |
| `WB-REL-E2E-003` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`tests/test_batch_accounting_api.py` | Browser 已覆盖 submit/withdraw、direct reload 和 bucket recovery，且不请求 operation barrier。 |
| `WB-REL-E2E-004` | `covered` | `web/e2e/turnover-ledger-flow.spec.ts`、`tests/test_turnover_workbench_integration.py` | Browser 已覆盖 turnover confirm/withdraw、direct reload 和 grouped recovery，且不请求 operation barrier。 |
| `WB-REL-E2E-005` | `covered` | `web/e2e/workbench-relations-candidate-semantics.spec.ts`、`tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_input_invoice_usage_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_output_invoice_collection_service.py`、`tests/test_bank_details_service.py`、`tests/test_pending_invoice_service.py` | Browser 已证明 candidate 可以在银行明细、待找发票和 OA 待付款显示为证据/chip，但 pending invoice 状态仍为 `已支付待开票`、OA payment 状态仍为 `支付少了`，不会被 candidate 推成 linked-only 状态。 |
| `WB-REL-E2E-006` | `covered` | `web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`、`tests/test_workbench_relation_read_facade.py`、页面 Vitest | Browser 已证明 relation-backed pending invoice relation data unavailable 时页面显示诊断、保留行检查和 canonical-safe 的选择发票入口；rows 为空且关系数据不可用时仍显示同步诊断并禁用导出，不把空结果当无上下文真实空。 |
| `WB-REL-E2E-007` | `covered` | `web/e2e/workbench-withdraw-flow.spec.ts`、`web/e2e/workbench-network-recovery-flow.spec.ts`、`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_idempotency_contract.py` | Browser 已覆盖 withdraw 正向 preview lock、submit payload 和 direct refetch，也覆盖 confirm/split_candidate/withdraw 双击只产生一次 mutation、409 stale preview 不复用旧 expected_versions；后端/API 覆盖 idempotency 与版本冲突。 |
| `WB-REL-E2E-008` | `covered` | `web/e2e/workbench-relation-fanout.spec.ts`、`web/e2e/pending-invoices-fanout.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/e2e/input-invoice-relation-fanout.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/workbench-relations-tax-offset-fanout.spec.ts`、`web/e2e/workbench-relations-oa-pending-fanout.spec.ts`、`tests/test_workbench_relation_repository.py`、`tests/test_search_pending_sql_runtime.py`、多个后端 service/API tests | Browser 已证明 Workbench confirm 后银行明细、待找发票、进项发票使用、成本统计、税金抵扣和 OA 待付款各自重新读取并展示 relation 影响后的业务结果；销项收款红蓝票 relation 写入后 rows refresh 并展示人工依据，且同一用户流继续导航税金抵扣/成本统计，两个下游页面各自重新读取并展示 relation 影响后的进项计划行和成本项目/流水；进项发票使用页面中 candidate 只作证据、Workbench confirm 后 linked 证据驱动 `已支付`；成本统计 open candidate 不计入金额、confirmed 成本关系才进入项目/流水详情；Workbench confirm 后税金抵扣页重新读取、展示 relation 影响后的进项计划行且不误报同步错误；OA 待付款在 Workbench confirm 后刷新 rows、从 `支付少了` 变为 `已支付`、候选标记消失且显示 `关联台已确认`；这些下游成功节点都会检查没有操作失败、同步失败或同步超时残留，防止“关系已写入但页面仍报错”的假成功；API/runtime 已证明 Search refresh path 不回流、遗留 SQL projection 保留 linked group jump target，`/api/search` direct payload 返回 group context。Browser 外层 search 入口当前不存在，未来新增后再补用户可见入口测试。 |
| `WB-REL-E2E-009` | `covered` | `web/e2e/bank-details-export-download.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/e2e/pending-invoices-export-download.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/e2e/input-invoice-usage-flow.spec.ts`、后端导出 service tests | Browser 已证明银行明细在 Workbench confirm 后可触发真实 download event，且文件名、当前默认筛选和 linked relation 字段一致；也已证明账户/自定义日期/关键字/分类筛选会带入导出、分页状态不会限制导出范围、`read_export_only` 可下载且银行明细写入口禁用并零 mutation。待找发票 Browser 已证明 Workbench confirm 后 export-preview/export 带当前筛选和排序、不带分页，并下载包含 OA 申请人、进项发票号、relation case 和 linked 状态。银行明细和待找发票下载成功节点都会检查没有导出失败、同步失败残留。销项收款 Browser 已证明红蓝票人工关系确认后 export-preview 和真实 download event 均包含 `红蓝票关系`、`红蓝票来源`、`红蓝票依据`、红字发票号、`manual` 和确认依据。进项发票使用 Browser 已证明当前筛选导出不带分页，真实 download event 内容包含 OA 申请人、relation case 和 payment 字段。真实 XLSX 完整解析仍归 export service/后续真实文件 smoke，不作为本地 Browser covered 前提。 |
| `WB-REL-E2E-010` | `covered` | `tests/test_workbench_relation_alignment_service.py`、`web/src/test/groupDisplayModel.test.ts`、`web/src/test/CandidateGroupGrid.test.tsx` | 多 OA/source alignment 由 direct payload、relation metadata 和前端分段测试覆盖；旧 active generation display audit 已删除。 |

## 现有 E2E 审计结论

- 当前 relation fan-out / mutation Browser smoke、真实下载 smoke、candidate/linked 负面语义 smoke、unavailable 诊断 smoke 以及 automatic candidate split smoke 都可保留，且应继续纳入 `npm run e2e:smoke`；其中 `split_candidate` 保护的是“不要把自动候选误当 active relation withdraw”，不计为 relation lifecycle 写入。Workbench relation fan-out 下游成功节点还必须保留 UI 错误残留 guard，防止成功刷新后仍出现操作失败、同步失败提示。
- 它们验证的是用户可见业务结果和后端重新读取，不是单纯照代码断言。
- 本地 deterministic 主要 Spec ID 已覆盖。剩余风险是生产/staging display audit、真实历史半迁移、大数据后台任务收敛、未来 Browser 外层 search 入口和真实 XLSX 完整解析；这些不应被标成本地 CI covered。

## 下一轮补测建议

1. 本模块本地 Spec IDs 已覆盖；后续新增 Browser 外层 search 入口、更多撤销业务入口或新 relation 字段导出页面时，再补对应 Spec-first E2E。
2. 真实 XLSX 完整解析、真实大数据下载性能和代理层真实权限仍归 export service 测试、staging smoke 或发布前手动 gate。
3. 把生产/staging display audit 保持为 `external-risk`，不要写成本地 CI 通过项。
