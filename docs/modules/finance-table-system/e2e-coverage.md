# Finance Table System Spec-first E2E 覆盖矩阵

## 覆盖状态

| Spec ID | 状态 | 自动化证据 | 说明 |
| --- | --- | --- | --- |
| `FIN-TABLE-E2E-001` | `covered` | `web/src/test/FinanceTable.test.tsx` | 覆盖 pagination clamp、summary、previous/next disabled 和页码 callback。 |
| `FIN-TABLE-E2E-002` | `covered` | `web/src/test/FinanceTable.test.tsx`、`web/src/test/TableLayoutTokens.test.ts`、`web/src/test/TableAlignmentStyles.test.ts` | 覆盖金额/方向/状态/空值 primitive、列角色对齐、行高和 tag 尺寸。 |
| `FIN-TABLE-E2E-003` | `covered` | `web/e2e/finance-table-system-flow.spec.ts`、`web/e2e/bank-details-large-scroll-flow.spec.ts`、`web/e2e/workbench-large-scroll-flow.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts` | 覆盖 AppHealth 代表性宽表、银行明细/关联台长表和成本统计大表格窄屏横向滚动。 |
| `FIN-TABLE-E2E-004` | `covered` | 页面级 Vitest、`web/e2e/*flow.spec.ts` | 银行明细、待找发票、销项收款、进项使用、OA pending、成本统计、税金、往来款等页面覆盖筛选/排序/分页/search/tab 请求语义。 |
| `FIN-TABLE-E2E-005` | `covered` | `web/e2e/bank-details-export-download.spec.ts`、`web/e2e/pending-invoices-export-download.spec.ts`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/input-invoice-usage-flow.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts` | 覆盖当前筛选导出、不受分页限制、row-limit 和非 fresh 禁用/失败反馈。 |
| `FIN-TABLE-E2E-006` | `covered` | `web/e2e/bank-details-stale-refreshing.spec.ts`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/input-invoice-usage-flow.spec.ts`、`web/e2e/tax-offset-flow.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`、`web/e2e/workbench-stale-error-flow.spec.ts` | 覆盖 non-fresh 防 false-empty、防旧 rows、防导出或写入伪成功。 |
| `FIN-TABLE-E2E-007` | `covered` | `web/e2e/input-invoice-usage-flow.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`、页面级 Vitest | 覆盖详情 drawer/dialog fresh 与 non-fresh 不可用诊断。 |
| `FIN-TABLE-E2E-008` | `covered` | `web/src/test/useFinanceTableSession.test.tsx`、`web/src/test/PageSessionStateContext.test.tsx`、`web/src/test/MuiContainment.test.ts` | 覆盖 table session 保存/恢复、columnsVersion 清理、user/page/state 隔离，并防止旧 MUI/DataGrid session hook/test 回归。 |
| `FIN-TABLE-E2E-009` | `covered` | `web/e2e/finance-table-system-flow.spec.ts`、`web/e2e/drawer-motion.spec.ts`、页面级 Playwright smoke | 覆盖真实 Chromium 代表性宽表，以及 modal/persistent drawer viewport motion、focus/inert、tax rail 折叠生命周期和严格 console/page error 捕获。 |
| `FIN-TABLE-E2E-010` | `covered` | 各页面 `e2e-coverage.md`、页面级 Vitest / Playwright | 页面 wrapper 的业务差异由页面模块覆盖；本模块记录共享边界而不替代页面 Spec。 |

## 缺口分类

| 缺口 | 分类 | 处理方式 |
| --- | --- | --- |
| 真实生产大数据滚动性能和百万级 DOM/虚拟化行为 | `external-risk` | staging/production performance smoke，不写成本地 covered。 |
| 浏览器真实下载保存行为、代理 header、真实 XLSX 打开结果 | `external-risk` | 银行明细、待找发票、销项收款本地 E2E 已解析 deterministic XLSX workbook 并验证业务字段；其它页面真实 workbook 解析、生产代理 header 和 Excel/Numbers 打开结果仍由后续页面级 E2E 或 staging/manual smoke 补。 |
| 新增页面 wrapper 未登记到本模块和页面模块 | `partial` | 新增 wrapper 时必须同步页面 `e2e-spec.md` / `e2e-coverage.md` 和本模块测试矩阵。当前已知页面 wrapper 已登记。 |

## 下一轮建议

1. 新增或迁移任何表格 wrapper 时，先登记到本文件和目标页面模块，再补页面级筛选/排序/导出/状态测试。
2. 对真实生产大数据月份建立 staging smoke，验证横向滚动、详情打开、导出反馈和浏览器性能。
3. 若引入虚拟列表或列固定，补 `FIN-TABLE-E2E-003`、`FIN-TABLE-E2E-006` 和页面级 regression。
