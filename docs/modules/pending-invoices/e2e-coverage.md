# 待找发票 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的待找发票 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `PENDING-E2E-001` | `covered` | `web/src/test/PendingInvoicesPage.test.tsx`、`web/e2e/pending-invoices-fanout.spec.ts`、`web/e2e/pending-invoices-filter-sort-flow.spec.ts` | 组件测试覆盖默认请求和四区表；Browser 覆盖页面 ready、真实表格、默认 `status_code=paid_pending_invoice` 保留、对方户名列筛选、金额升/降序排序、rows query 口径和可见行变化；本轮补充首屏 rows 请求暂时失败时显示错误和错误态空行文案、不显示正常空态、禁用导出，用户点击刷新后 rows 恢复、错误消失且导出重新可用。 |
| `PENDING-E2E-002` | `covered` | `web/e2e/pending-invoices-fanout.spec.ts`、`tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | Browser 已证明 Workbench confirm 后返回待找发票，rows 重新读取并显示 `已支付已开票`、OA 和发票号。 |
| `PENDING-E2E-003` | `covered` | `web/e2e/workbench-relations-candidate-semantics.spec.ts`、后端 relation/read model tests | Browser 已证明 candidate 只展示证据，不驱动 linked-only 状态，也不产生 mutation。 |
| `PENDING-E2E-004` | `covered` | `web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`、`tests/test_search_pending_sql_runtime.py` | Browser 已覆盖 relation-backed `refreshing` 和 `stale` false-empty 诊断；后端覆盖 source mismatch/freshness gate。 |
| `PENDING-E2E-005` | `covered` | `web/e2e/pending-invoices-export-download.spec.ts`、`web/e2e/fixtures/apiMocks.ts` | Browser 已覆盖 Workbench confirm 后 export-preview/export 的当前筛选、排序、不带分页、真实 download event、文件名和 OA/发票/relation 字段内容；deterministic mock 返回真实 XLSX workbook，Playwright 会解析 workbook 后再断言业务字段，避免把 CSV 文本伪装成 `.xlsx`。 |
| `PENDING-E2E-006` | `covered` | `web/e2e/pending-invoices-export-download.spec.ts`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts`、`tests/test_pending_invoice_api.py` | Browser 覆盖导出预览后下载 row-limit 业务错误，断言后端错误文案可见、未生成下载文件；组件/API/后端覆盖 row-limit contract 和下载错误 mapper。 |
| `PENDING-E2E-007` | `covered` | `web/e2e/pending-invoices-attach-existing-flow.spec.ts`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts`、`tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py` | Browser 覆盖多选 eligible 支出流水、候选抽屉、后端事实驱动的“流水关联”chip、搜索条件、preview 汇总、confirm 后 rows refetch 到 `已支付已开票`；并覆盖 confirm 第一次暂时 503 时错误可见、drawer/preview/选择保持、confirm 可重试、rows 不重读且保持 `已支付待开票`，第二次重试成功后才刷新到 `已支付已开票`；同时覆盖 conflict 时确认禁用、零 confirm mutation 和无半写。 |
| `PENDING-E2E-008` | `covered` | `web/e2e/pending-invoices-income-status-flow.spec.ts`、`web/src/test/PendingInvoicesPage.test.tsx`、`tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py` | Browser 覆盖收入方向多选、工具栏批量标记现金收入、单次 `PUT /income-statuses`、rows refetch、状态更新；失败分支覆盖后端拒绝时错误可见、选中保留、rows 不重读且状态不半写；并覆盖第一次保存暂时 503 时错误可见、选择保持、按钮恢复、rows 不重读且保持 `未开票`，第二次重试成功后才刷新到 `现金收入`。 |
| `PENDING-E2E-009` | `covered` | `web/e2e/pending-invoices-rules-save-flow.spec.ts`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、后端 rules tests | Browser 覆盖支出规则抽屉保存、`PUT /api/pending-invoices/rules` contract、`pending_invoice:expense:requires_invoice` operation barrier、rows 重读、刷新中提示，以及成功后没有保存失败/同步失败/read model 失败残留；并覆盖第一次保存暂时 503 时规则抽屉内错误可见、草稿勾选保持、全局操作弹窗不阻塞、不触发 barrier/rows 刷新，第二次重试成功后才刷新 rows；组件/API 覆盖 barrier timeout 仍保持保存成功、支出/收入版本隔离、conflict 和 global operation 非阻塞错误选项。 |

## 下一轮补测建议

1. 在 staging/真实 infra 中补 `PENDING-E2E-007` / `PENDING-E2E-008` 的 PostgreSQL/RabbitMQ/Redis/systemd worker drain 证据，证明 attach existing 和 income status 后 pending/search/invoice-lifecycle read model 最终 fresh。
2. 继续在 staging/真实 infra 中补 rules save、attach existing、income status 后 PostgreSQL/RabbitMQ/Redis/systemd worker drain 证据。
3. 继续为其它待找发票 mutation 增加真实浏览器网络失败恢复场景；本地 Browser 已覆盖 rows 首屏加载失败后的手动刷新恢复、attach existing confirm 暂时失败后的重试恢复、income status 保存暂时失败后的重试恢复和 rules save 暂时失败后的草稿重试恢复，withdraw 以及其它真实网络中断仍需继续扩展。
4. 生产代理 header、Excel/Numbers 实际打开结果和真实大数据导出仍作为 staging/manual smoke 风险。
