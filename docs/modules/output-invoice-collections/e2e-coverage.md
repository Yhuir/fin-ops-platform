# 销项发票收款情况 Spec-first E2E Coverage

本文件把 `output-invoice-collections` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `OUT-COLL-E2E-001` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`tests/test_output_invoice_collection_api.py` | Browser 覆盖 fresh 首屏、有界 `page_size=20`、keyword search、发票号码排序、收款状态/发票号码筛选、page-size 切换、rows 请求参数和表格结果同步；同时覆盖 rows 首屏暂时 503 时展示错误 alert 和错误态空行、不显示普通空态、禁用导出、点击刷新后恢复业务行/分页/导出。更多 money/date 组合由 Vitest/API 覆盖，真实大数据性能仍归 staging/专项 smoke。 |
| `OUT-COLL-E2E-002` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`tests/test_output_invoice_collection_lifecycle.py` | Browser 已证明状态/提醒保存后等待 `output_invoice_collection` barrier、rows refresh、显示 `待冲红`，并检查成功后无可见错误残留；同一 spec 也覆盖 `collection-status` 暂时 503 时 drawer 不关闭、错误可见、状态/提醒草稿保持、reminder endpoint 不半提交、rows 不提前刷新，第二次保存成功后才刷新 rows；还覆盖 `collection-status` 先 200 而 `collection-reminder` 暂时 503 时 drawer/提醒草稿保持、rows 不提前刷新、重试只重新提交 reminder 而不重复提交已保存且未改变的 status payload，reminder 成功后才刷新 rows。 |
| `OUT-COLL-E2E-003` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`tests/test_output_invoice_collection_lifecycle.py`、`tests/test_output_invoice_collection_api.py` | Browser 已证明 receipt preview/create/history/void/reissue，创建、作废、重开和历史成功后检查无可见错误残留，并断言作废/重开 reason POST body、history reload、`output_invoice_collection` barrier 和 rows refresh；同一 spec 也覆盖 receipt create 暂时 503 时 idempotency key 仍发送、预览 drawer 保持、错误可见、rows 不提前刷新、history 不伪读且重试成功后才显示已出收据；还覆盖 receipt void/reissue 暂时 503 时原因弹窗和输入值保持、错误可见、history/rows 不提前刷新且重试成功后才更新 history/rows；后端覆盖幂等、状态冲突和真实 history。 |
| `OUT-COLL-E2E-004` | `covered` | `web/e2e/output-invoice-red-relation-fanout.spec.ts`、`tests/test_output_invoice_collection_lifecycle.py`、`tests/test_output_invoice_collection_api.py` | Browser 已证明红蓝票关系确认后等待 barrier 再 rows refresh，并在重新打开 drawer 时展示人工依据、source 和 evidence；同一 spec 也覆盖撤销人工关系后再次 barrier/rows refresh、人工依据消失且行状态恢复。确认和撤销成功点都会断言没有操作失败、同步失败或 read model 失败等 UI 错误残留。 |
| `OUT-COLL-E2E-005` | `covered` | `tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | API/Vitest 覆盖 stale/source mismatch 返回 `202 refreshing` 且不返回 stale rows；Browser 覆盖 stale contract 下页面显示刷新诊断、不显示普通空态、不泄露 stale reason、不展示旧 rows 或写入口，也覆盖 rows 临时加载失败时不伪装为空态且刷新恢复。真实 worker drain 仍归 infra-smoke/staging。 |
| `OUT-COLL-E2E-006` | `covered` | `web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`tests/test_output_invoice_collection_api.py` | Browser 已证明 `read_export_only` 可读、可打开只读规则/收据历史和导出入口，但不显示状态/提醒、红蓝票、待出收据、收据编号设置、收据作废/重开等写入口，且全程零 mutation API；API/Vitest 覆盖读权限和 admin-only 设置入口。 |
| `OUT-COLL-E2E-007` | `covered` | `tests/test_output_invoice_collection_api.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | API 覆盖 export-preview/export、筛选全集、不受分页限制、真实 xlsx 字段和 row-limit contract；Browser 覆盖 `read_export_only` 当前筛选导出、download event、文件名、导出请求不携带分页、样例字段，以及 row-limit 错误反馈且不触发下载；deterministic mock 返回真实 XLSX workbook，普通筛选导出和红蓝票人工关系确认后的导出都会解析 workbook 后断言 `红蓝票关系`、`红蓝票来源`、`红蓝票依据`、红字发票号、`manual` 和确认依据，避免把 CSV 文本伪装成 `.xlsx`。 |
| `OUT-COLL-E2E-008` | `covered` | `web/e2e/output-invoice-red-relation-fanout.spec.ts`、`tests/test_invoice_lifecycle_page_integration.py`、`web/src/test/TaxOffsetPage.test.tsx`、`tests/test_search_pending_sql_runtime.py` | Browser 已证明销项收款页确认红蓝票关系后，本页 rows refresh 并继续导航到税金抵扣和成本统计，两个下游页面都重新请求自己的 fresh read model 并展示 relation 影响后的结果；search 当前没有独立前端 route，relation 写入到 search fresh group context 由 API/runtime 覆盖。未来新增外层 search UI 时再补 Browser search fan-out，不作为当前页面本地 Spec-first 缺口。 |

## Operation latency baseline

本轮已为 `web/e2e/output-invoice-collections-flow.spec.ts` 和 `web/e2e/output-invoice-red-relation-fanout.spec.ts` 接入 Playwright `operation-latency-*.json` 附件。当前记录的操作覆盖：页面打开、首屏 rows 暂时失败后的刷新恢复、keyword search、清空搜索、发票号码排序、收款状态筛选、发票号码筛选、page-size 切换、状态/提醒 drawer 打开、状态/提醒编辑、保存成功、状态保存 503 与重试、提醒保存 503 与重试、待出收据预览、创建正式收据、创建收据 503 与重试、已出收据历史、作废/重开 dialog、作废/重开成功、作废/重开 503 与重试、read model stale 诊断、当前筛选导出预览/下载、row-limit 错误反馈、read-export 只读规则/收据历史/导出路径，以及红蓝票关系确认、relation 字段导出、税金抵扣/成本统计下游 read model 重读、成本项目 drill-down 和红蓝票撤销。

## 下一轮补测建议

1. 若后续新增独立 search 页面/入口，为 `OUT-COLL-E2E-008` 补 Browser search fan-out。
2. 继续按全局队列推进其他 `spec-first-partial` shared/runtime 模块，或补真实基础设施 worker drain / staging smoke。
