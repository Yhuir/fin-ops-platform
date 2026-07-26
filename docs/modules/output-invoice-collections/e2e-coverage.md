# 销项发票收款情况 Spec-first E2E Coverage

本文件把 `output-invoice-collections` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

> 2026-07-27：本页 rows/detail/export 已改为 canonical PostgreSQL 直读；旧 read-model refreshing/worker 证据只保留历史价值，不再是本页验收合同。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `OUT-COLL-E2E-001` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`tests/test_output_invoice_collection_api.py` | Browser 覆盖 canonical 首屏、有界 `page_size=20`、keyword search、发票号码排序、收款状态/发票号码筛选、page-size 切换、rows 请求参数和表格结果同步；同时覆盖 rows 暂时 503 时错误 alert、错误态空行、不显示普通空态、禁用导出、点击刷新后恢复业务行/分页/导出。 |
| `OUT-COLL-E2E-002` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`tests/test_output_invoice_collection_lifecycle.py` | Browser 已证明状态/提醒保存后重跑当前 canonical rows GET、显示 `待冲红`；也覆盖 `collection-status` 暂时 503 时 drawer 不关闭、草稿保持、reminder 不半提交、rows 不提前刷新，以及 status 已保存而 reminder 暂时失败时重试不重复提交 status。 |
| `OUT-COLL-E2E-003` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`tests/test_output_invoice_collection_lifecycle.py`、`tests/test_output_invoice_collection_api.py` | Browser 已证明 receipt preview/create/history/void/reissue，创建、作废、重开后重跑当前 rows/history normal GET；失败时 idempotency key、drawer、原因和输入保持，不提前刷新或伪读 history；后端覆盖幂等、状态冲突、真实 history 与零普通写 fan-out。 |
| `OUT-COLL-E2E-004` | `covered` | `web/e2e/output-invoice-red-relation-fanout.spec.ts`、`tests/test_output_invoice_collection_lifecycle.py`、`tests/test_output_invoice_collection_api.py` | Browser 已证明红蓝票关系确认/撤销后本页 canonical GET 展示或移除人工依据、source 和 evidence；确认和撤销成功点无操作/同步错误残留。 |
| `OUT-COLL-E2E-005` | `covered` | `tests/test_output_invoice_collection_api.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | API/Vitest 固定 rows/detail 只返回 canonical `200` 或结构化错误且无旧状态字段；Browser 覆盖 rows 暂时加载失败时不伪装为空态、无自动 polling，并由用户刷新恢复。 |
| `OUT-COLL-E2E-006` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`tests/test_output_invoice_collection_api.py` | Browser 已证明 `read_export_only` 可读、可打开只读规则/收据历史和导出入口，但不显示状态/提醒、红蓝票、待出收据、收据编号设置、收据作废/重开等写入口，且全程零 mutation API；admin 场景已覆盖收据编号设置 GET/PUT、抽屉关闭、零 rows 重载、零 operation barrier，并记录 opener/save latency。 |
| `OUT-COLL-E2E-007` | `covered` | `tests/test_output_invoice_collection_api.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | API 覆盖 export-preview/export、筛选全集、不受分页限制、真实 xlsx 字段和 row-limit contract；Browser 覆盖 `read_export_only` 当前筛选导出、download event、文件名、导出请求不携带分页、样例字段，以及 row-limit 错误反馈且不触发下载；deterministic mock 返回真实 XLSX workbook，普通筛选导出和红蓝票人工关系确认后的导出都会解析 workbook 后断言 `红蓝票关系`、`红蓝票来源`、`红蓝票依据`、红字发票号、`manual` 和确认依据，避免把 CSV 文本伪装成 `.xlsx`。 |
| `OUT-COLL-E2E-008` | `covered` | `web/e2e/output-invoice-red-relation-fanout.spec.ts`、`web/e2e/workbench-relations-tax-offset-isolation.spec.ts`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_search_pending_sql_runtime.py`、`tests/test_read_model_architecture_guards.py` | Browser 证明红蓝票确认后本页与成本 consumer 分别重新访问并更新；guard 证明写时零页面 fan-out；独立 isolation spec 和 repository 测试证明税金抵扣不受 relation 影响。 |

## Operation latency baseline

本轮 Playwright latency 证据覆盖本页状态/收据/导出/红蓝票确认撤销、admin 收据编号设置打开/保存，以及成本统计 relation consumer 重读；税金抵扣隔离由独立 spec 保护。`CollectionStatusRulesDrawer` 是 Sheet6 静态规则只读展示，不存在保存操作，也不得写 dirty/outbox。

## 下一轮补测建议

1. 若后续新增独立 search 页面/入口，为 `OUT-COLL-E2E-008` 补 Browser search fan-out。
2. 继续按全局队列推进其他 `spec-first-partial` shared/runtime 模块，或补真实基础设施 worker drain / staging smoke。
